"""Optional local PDF text extraction for G01 intake.

This module intentionally does not vendor or require a PDF parser. If ``pypdf`` is installed in
the active interpreter, it produces a page-wise ``pdf_extract_result@1`` artifact. If not, it
returns a valid dependency-missing result so hosts can fail closed or ask for a configured backend.
"""
from __future__ import annotations

import io
import json
import pathlib
import re
import sys
import uuid
from collections import Counter
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # -> shared/scripts
# Vendored pure-python PDF backend ships with the plugin so a bare system python3 (no pip/venv)
# can extract text from the read-only install. Appended, so a real installed pypdf still wins.
_VENDOR = str(pathlib.Path(__file__).resolve().parents[1] / "_vendor")
if _VENDOR not in sys.path:
    sys.path.append(_VENDOR)

from core import artifacts, contracts  # noqa: E402

CONTRACT = "pdf_extract_result@1"
SLIDE_VIEWS_CONTRACT = "slide_views@1"
ENGINE = "pypdf_optional"


def _blank_result(*, task_id: str, source_pdf_ref: str, filename: str, status: str,
                  warning: str) -> dict[str, Any]:
    return {
        "schema_version": CONTRACT,
        "task_id": task_id,
        "source_pdf_ref": source_pdf_ref,
        "filename": filename,
        "extraction_engine": ENGINE,
        "extraction_status": status,
        "page_count": 0,
        "pages": [],
        "warnings": [warning],
        "degraded": True,
        "result_ref": None,
    }


def _load_json_path(path: pathlib.Path) -> dict[str, Any] | None:
    if path.suffix.lower() != ".json" or not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_input(input_value: object, *, base=None) -> tuple[str, str, str, bytes]:
    """Return ``(task_id, source_pdf_ref, filename, data)`` for an intake bundle or PDF input."""
    if isinstance(input_value, dict):
        bundle = input_value
    elif isinstance(input_value, str) and input_value.startswith(artifacts.SCHEME):
        if input_value.lower().endswith(".pdf"):
            data = artifacts.read_bytes(input_value, base=base)
            return f"PDF_{uuid.uuid4().hex[:8].upper()}", input_value, pathlib.PurePosixPath(
                artifacts.parse_ref(input_value)[0]
            ).name, data
        bundle = artifacts.hydrate(input_value, base=base)
    elif isinstance(input_value, str):
        path = pathlib.Path(input_value).expanduser()
        loaded = _load_json_path(path)
        if loaded is not None:
            bundle = loaded
        else:
            data = path.read_bytes()
            return f"PDF_{uuid.uuid4().hex[:8].upper()}", str(path), path.name, data
    else:
        raise TypeError("input must be an intake_graph_input object, JSON path, PDF path or artifact ref")

    upload = bundle.get("upload") if isinstance(bundle, dict) else None
    if not isinstance(upload, dict):
        raise ValueError("input bundle has no upload object")
    pdf_ref = upload.get("pdf_file_ref")
    if not isinstance(pdf_ref, str) or not pdf_ref:
        raise ValueError("input bundle upload.pdf_file_ref is required")
    filename = upload.get("filename") if isinstance(upload.get("filename"), str) else "uploaded.pdf"
    task_id = bundle.get("task_id") if isinstance(bundle.get("task_id"), str) else "INTAKE_UNKNOWN"
    data = artifacts.read_bytes(pdf_ref, base=base) if pdf_ref.startswith(artifacts.SCHEME) else pathlib.Path(
        pdf_ref
    ).expanduser().read_bytes()
    return task_id, pdf_ref, filename, data


def _page_result(page_number: int, text: str, *, status: str = "ok",
                 warning: str | None = None, visual_status: str = "pending") -> dict[str, Any]:
    normalized = text.strip()
    text_status = status if status != "ok" else ("ok" if normalized else "empty")
    return {
        "page_number": page_number,
        "text": normalized,
        "text_status": text_status,
        "char_count": len(normalized),
        "needs_ocr": text_status in {"empty", "extraction_error", "unavailable"},
        "has_visual_content": visual_status == "pending",
        "visual_description_status": visual_status,
        "image_ref": None,
        "visual_description": None,
        "warning": warning,
    }


def extract(input_value: object, *, visual_policy: str = "pending", store: bool = True,
            base=None) -> dict[str, Any]:
    """Extract page text with optional ``pypdf`` and return a validated ``pdf_extract_result@1``."""
    if visual_policy not in {"none", "pending"}:
        raise ValueError("visual_policy must be 'none' or 'pending'")
    task_id, pdf_ref, filename, data = _resolve_input(input_value, base=base)
    if data[:5] != b"%PDF-":
        result = _blank_result(
            task_id=task_id,
            source_pdf_ref=pdf_ref,
            filename=filename,
            status="failed",
            warning="Input is not a PDF: missing %PDF- header.",
        )
        return _validate_and_store(result, store=store, base=base)

    try:
        from pypdf import PdfReader
    except ImportError:
        result = _blank_result(
            task_id=task_id,
            source_pdf_ref=pdf_ref,
            filename=filename,
            status="dependency_missing",
            warning="pypdf is not installed in the active Python interpreter.",
        )
        return _validate_and_store(result, store=store, base=base)

    warnings: list[str] = []
    pages: list[dict[str, Any]] = []
    visual_status = "pending" if visual_policy == "pending" else "not_requested"
    try:
        reader = PdfReader(io.BytesIO(data))
        page_count = len(reader.pages)
    except Exception as exc:  # pypdf raises several parser-specific exceptions.
        result = _blank_result(
            task_id=task_id,
            source_pdf_ref=pdf_ref,
            filename=filename,
            status="failed",
            warning=f"pypdf could not read the PDF: {exc}",
        )
        return _validate_and_store(result, store=store, base=base)

    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
            pages.append(_page_result(index, text, visual_status=visual_status))
        except Exception as exc:
            warning = f"page {index}: text extraction failed: {exc}"
            warnings.append(warning)
            pages.append(_page_result(index, "", status="extraction_error",
                                      warning=warning, visual_status=visual_status))

    degraded = any(page["text_status"] != "ok" for page in pages)
    result = {
        "schema_version": CONTRACT,
        "task_id": task_id,
        "source_pdf_ref": pdf_ref,
        "filename": filename,
        "extraction_engine": ENGINE,
        "extraction_status": "degraded" if degraded else "ok",
        "page_count": page_count,
        "pages": pages,
        "warnings": warnings,
        "degraded": degraded,
        "result_ref": None,
    }
    return _validate_and_store(result, store=store, base=base)


def _validate_and_store(result: dict[str, Any], *, store: bool, base=None) -> dict[str, Any]:
    validation = contracts.validate(result, CONTRACT)
    if not validation["ok"]:
        raise ValueError("invalid pdf_extract_result: " + "; ".join(validation["errors"]))
    if store:
        rel = f"g01/pdf-extract/{result['task_id']}.{uuid.uuid4().hex[:8]}.json"
        result["result_ref"] = artifacts.ref_for(rel)
        artifacts.store(rel, result, base=base)
    return result


def _norm_line(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _boilerplate_lines(pages: list[dict[str, Any]], *, min_pages: int = 4,
                       frac: float = 0.6) -> set[str]:
    """Lines repeated on a large fraction of pages = slide-master header/footer (not slide content).

    Detected deterministically by frequency: a normalized line present on >= ``frac`` of the pages
    is treated as boilerplate. Only kicks in for decks with enough pages to be confident.
    """
    n = len(pages)
    if n < min_pages:
        return set()
    counts: Counter[str] = Counter()
    for page in pages:
        for key in {_norm_line(ln) for ln in (page.get("text") or "").splitlines() if _norm_line(ln)}:
            counts[key] += 1
    threshold = max(2, round(frac * n))
    return {line for line, count in counts.items() if count >= threshold}


def _is_titleish(line: str) -> bool:
    stripped = line.strip()
    return len(stripped) >= 3 and not stripped.replace(".", "").replace(" ", "").isdigit()


def _clean_and_title(text: str, boilerplate: set[str]) -> tuple[str, str]:
    """Drop boilerplate lines; return (slide-specific text, first title-ish remaining line)."""
    kept = [ln.rstrip() for ln in (text or "").splitlines() if _norm_line(ln) not in boilerplate]
    title = next((ln.strip() for ln in kept if _is_titleish(ln)), "")
    return "\n".join(kept).strip(), title


def to_slide_views(result: dict[str, Any]) -> dict[str, Any]:
    """Project page-wise extraction into the thin ``slide_views@1`` shape, stripping the repeated
    slide-master header/footer so titles and per-slide text are slide-specific."""
    pages = result.get("pages", [])
    boilerplate = _boilerplate_lines(pages)
    slides = []
    for page in pages:
        cleaned, title = _clean_and_title(page.get("text", ""), boilerplate)
        slide = {
            "slide_id": page["page_number"],
            "title_candidate": title,
            "normalized_text": cleaned,
            "layout_type_hint": "visual_pending" if page.get("has_visual_content") else "text_only",
        }
        if page.get("image_ref"):
            slide["image_ref"] = page["image_ref"]
        slides.append(slide)
    views = {
        "slide_count": result.get("page_count", len(slides)),
        "slides": slides,
        "source_order_preserved": True,
        "warnings": ([f"stripped {len(boilerplate)} repeated master-slide line(s) from slide "
                      "text and titles"] if boilerplate else []),
    }
    return views


def _load_pdf_extract_result(input_value: object, *, base=None) -> dict[str, Any] | None:
    if isinstance(input_value, dict) and input_value.get("schema_version") == CONTRACT:
        return input_value
    if isinstance(input_value, str) and input_value.startswith(artifacts.SCHEME):
        try:
            hydrated = artifacts.hydrate(input_value, base=base)
        except Exception:
            return None
        if isinstance(hydrated, dict) and hydrated.get("schema_version") == CONTRACT:
            return hydrated
    if isinstance(input_value, str):
        path = pathlib.Path(input_value).expanduser()
        loaded = _load_json_path(path)
        if isinstance(loaded, dict) and loaded.get("schema_version") == CONTRACT:
            return loaded
    return None


def slide_views(input_value: object, *, visual_policy: str = "pending", store: bool = True,
                base=None) -> dict[str, Any]:
    """Build and optionally store ``slide_views@1`` from a PDF input or pdf_extract_result."""
    result = _load_pdf_extract_result(input_value, base=base)
    if result is None:
        result = extract(input_value, visual_policy=visual_policy, store=store, base=base)
    validation = contracts.validate(result, CONTRACT)
    if not validation["ok"]:
        raise ValueError("invalid pdf_extract_result: " + "; ".join(validation["errors"]))

    views = to_slide_views(result)
    views["source_pdf_extract_ref"] = result.get("result_ref")
    views["source_extraction_status"] = result.get("extraction_status")
    views["warnings"] = list(views.get("warnings") or []) + list(result.get("warnings") or [])
    slide_validation = contracts.validate(views, SLIDE_VIEWS_CONTRACT)
    if not slide_validation["ok"]:
        raise ValueError("invalid slide_views: " + "; ".join(slide_validation["errors"]))
    if store:
        rel = f"g01/slide-views/{result.get('task_id', 'INTAKE_UNKNOWN')}.{uuid.uuid4().hex[:8]}.json"
        views["slide_views_ref"] = artifacts.ref_for(rel)
        artifacts.store(rel, views, base=base)
    return views
