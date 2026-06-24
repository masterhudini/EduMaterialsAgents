"""g01 deterministic upload seam — turn a real lecture PDF into the typed boundary contract.

The graph never assumes an already-formed ``intake_graph_input@1``. A user supplies a PDF path;
this copies the bytes into the project-local artifact store (``<project>/.emagents/artifacts/
uploads/<id>.pdf`` — cwd-anchored, never the read-only plugin install), then builds and validates
the ``intake_graph_input@1`` envelope that references it. Pure stdlib (no PDF parsing here — that
is g01-a01-pdf-intake's job; this only ingests bytes + ingestion profile + hints).
"""
from __future__ import annotations

import sys as _sys
import pathlib as _pl
import hashlib
import uuid

_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))  # -> shared/scripts

from core import artifacts, contracts, finalize  # noqa: E402

INPUT_CONTRACT = "intake_graph_input@1"
DEFAULT_INGESTION = {
    "extract_text": True,
    "render_slide_images": True,
    "extract_assets": True,
    "ocr_policy": "only_if_text_missing",
    "keep_original_order": True,
}


def _merged_ingestion_profile(ingestion_profile: dict | None) -> dict:
    profile = dict(DEFAULT_INGESTION)
    if ingestion_profile:
        profile.update(ingestion_profile)
    return profile


def upload(pdf_path, *, hints: dict | None = None, ingestion_profile: dict | None = None,
           task_id: str | None = None, base=None) -> dict:
    """Copy a PDF into the artifact store and emit a stored, validated intake_graph_input@1.

    Returns ``{ref, task_id, pdf_ref, filename, size_bytes}`` where ``ref`` is the artifact:// ref
    of the boundary bundle — feed it straight to ``g01_flow.run`` / ``front_door``.
    """
    p = _pl.Path(pdf_path).expanduser()
    if not p.is_file():
        raise FileNotFoundError(f"no such PDF: {pdf_path}")
    data = p.read_bytes()
    if data[:5] != b"%PDF-":
        raise ValueError(f"not a PDF (missing %PDF- header): {p.name}")

    sha256 = hashlib.sha256(data).hexdigest()
    upload_id = f"sha256-{sha256[:12]}"
    pdf_relpath = f"uploads/{upload_id}.pdf"
    pdf_ref = artifacts.ref_for(pdf_relpath)
    task = task_id or f"INTAKE_{uuid.uuid4().hex[:8].upper()}"
    h = hints or {}
    bundle = {
        "schema_version": INPUT_CONTRACT,
        "task_id": task,
        "upload": {
            "pdf_file_ref": pdf_ref, "filename": p.name, "mime_type": "application/pdf",
            "upload_id": upload_id, "size_bytes": len(data),
        },
        "user_provided_context": {
            "title_hint": h.get("title") or p.stem,
            "course_hint": h.get("course"),
            "audience_hint": h.get("audience"),
            "language_hint": h.get("language"),
        },
        "ingestion_profile": _merged_ingestion_profile(ingestion_profile),
        "output_language": h.get("output_language") or h.get("language") or "English",
    }
    res = contracts.validate(bundle, INPUT_CONTRACT)
    if not res["ok"]:
        raise ValueError("upload produced invalid intake_graph_input: " + "; ".join(res["errors"]))
    pdf_path_in_store = artifacts.resolve_path(pdf_ref, base=base)
    if not pdf_path_in_store.exists():
        artifacts.store_bytes(pdf_relpath, data, base=base)
    in_ref = artifacts.store(f"handoffs/{bundle['task_id']}.intake_input.json", bundle, base=base)
    return {"ref": in_ref, "task_id": bundle["task_id"], "pdf_ref": pdf_ref,
            "filename": p.name, "size_bytes": len(data), "sha256": sha256}


def _finalize_artifact(task_id: str, payload: dict, *, contract: str, type_name: str,
                       subdir: str, base=None) -> dict:
    """Validate + store a producer artifact server-side; return envelope@1 (see core.finalize)."""
    return finalize.artifact_envelope(task_id, payload, contract=contract, type_name=type_name,
                                      subdir=subdir, namespace="g01", base=base,
                                      unknown_task="INTAKE_UNKNOWN")


def finalize_understanding(task_id: str, understanding: dict, *, base=None) -> dict:
    """G02-A02 write path: persist a validated intake_understanding@1; return envelope@1."""
    return _finalize_artifact(task_id, understanding, contract="intake_understanding@1",
                              type_name="intake_understanding", subdir="understanding", base=base)


def finalize_synthesis(task_id: str, research_graph_input: dict, *, base=None) -> dict:
    """G01-A03 write path: persist a validated research_graph_input@1; return envelope@1."""
    return _finalize_artifact(task_id, research_graph_input, contract="research_graph_input@1",
                              type_name="research_graph_input", subdir="synthesis", base=base)


def finalize_lecture_baseline(task_id: str, lecture_baseline: dict, *, base=None) -> dict:
    """G01-A04 write path: persist a validated lecture_baseline@1 (the targeted 01->03 context).

    This is g01's SECOND boundary artifact: research_graph_input@1 feeds g02, lecture_baseline@1
    feeds g03 with the lecture skeleton (slides + claim_id/concept_id join keys) that g02 never
    carried. Persisted server-side; the worker forwards only the returned envelope@1.
    """
    return _finalize_artifact(task_id, lecture_baseline, contract="lecture_baseline@1",
                              type_name="lecture_baseline", subdir="baseline", base=base)


def resolve_context(path_or_ref, *, base=None):
    """Front-door normalizer: a ``*.pdf`` path is uploaded first; anything else passes through."""
    if isinstance(path_or_ref, str) and path_or_ref.lower().endswith(".pdf"):
        return upload(path_or_ref, base=base)["ref"]
    return path_or_ref
