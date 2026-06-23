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

    upload_id = uuid.uuid4().hex[:12]
    pdf_ref = artifacts.store_bytes(f"uploads/{upload_id}.pdf", data, base=base)
    h = hints or {}
    bundle = {
        "schema_version": INPUT_CONTRACT,
        "task_id": task_id or f"INTAKE_{upload_id[:8].upper()}",
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
        "ingestion_profile": ingestion_profile or dict(DEFAULT_INGESTION),
        "output_language": h.get("output_language", "English"),
    }
    res = contracts.validate(bundle, INPUT_CONTRACT)
    if not res["ok"]:
        raise ValueError("upload produced invalid intake_graph_input: " + "; ".join(res["errors"]))
    in_ref = artifacts.store(f"handoffs/{bundle['task_id']}.intake_input.json", bundle, base=base)
    return {"ref": in_ref, "task_id": bundle["task_id"], "pdf_ref": pdf_ref,
            "filename": p.name, "size_bytes": len(data)}


def resolve_context(path_or_ref, *, base=None):
    """Front-door normalizer: a ``*.pdf`` path is uploaded first; anything else passes through."""
    if isinstance(path_or_ref, str) and path_or_ref.lower().endswith(".pdf"):
        return upload(path_or_ref, base=base)["ref"]
    return path_or_ref
