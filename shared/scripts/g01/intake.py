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

from core import artifacts, contracts  # noqa: E402

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
    """Validate + atomically store a producer artifact server-side; return an envelope@1.

    This is the g02-style write path: the deterministic op (run in the unsandboxed MCP/engine
    process) persists the typed artifact and hands back only its ref in ``produced[]`` — so a
    read-only/sandboxed Codex worker never needs filesystem write access.
    """
    if not isinstance(payload, dict):
        return {"status": "failed", "produced": [],
                "summary": f"{type_name}: payload must be an object",
                "issues": [{"severity": "blocker", "type": "contract",
                            "message": "finalize payload is not a JSON object"}]}
    res = contracts.validate(payload, contract)
    if not res["ok"]:
        return {"status": "failed", "produced": [],
                "summary": f"{type_name}: invalid {contract}",
                "issues": [{"severity": "blocker", "type": "contract",
                            "message": "; ".join(res["errors"])}]}
    tid = task_id if isinstance(task_id, str) and task_id else "INTAKE_UNKNOWN"
    rel = f"g01/{subdir}/{tid}.{uuid.uuid4().hex[:8]}.json"
    ref = artifacts.store(rel, payload, base=base)
    return {"status": "ok",
            "produced": [{"type": type_name, "path": ref, "schema_version": contract}],
            "summary": f"{type_name} finalized to {ref}", "issues": []}


def finalize_understanding(task_id: str, understanding: dict, *, base=None) -> dict:
    """G02-A02 write path: persist a validated intake_understanding@1; return envelope@1."""
    return _finalize_artifact(task_id, understanding, contract="intake_understanding@1",
                              type_name="intake_understanding", subdir="understanding", base=base)


def finalize_synthesis(task_id: str, research_graph_input: dict, *, base=None) -> dict:
    """G01-A03 write path: persist a validated research_graph_input@1; return envelope@1."""
    return _finalize_artifact(task_id, research_graph_input, contract="research_graph_input@1",
                              type_name="research_graph_input", subdir="synthesis", base=base)


def resolve_context(path_or_ref, *, base=None):
    """Front-door normalizer: a ``*.pdf`` path is uploaded first; anything else passes through."""
    if isinstance(path_or_ref, str) and path_or_ref.lower().endswith(".pdf"):
        return upload(path_or_ref, base=base)["ref"]
    return path_or_ref
