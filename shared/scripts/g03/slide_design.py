"""Build a deterministic ``slide_design_set@1`` draft for G03-A03 (Slide Designer).

One design entry per non-REMOVE slot of the approved ``slide_plan@1``: title, body bullets, a
narrative seed (the agent expands it to 6-10 sentences), speaker-note seed, a layout heuristic and a
timing estimate. The agent authors the real prose; this draft only guarantees a valid, complete
skeleton. Pure stdlib.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys as _sys

_sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> shared/scripts

from core import artifacts, contracts  # noqa: E402
from g03 import solution  # noqa: E402

INPUT_CONTRACT = "slide_plan@1"
OUTPUT_CONTRACT = "slide_design_set@1"


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _strings(value: object) -> list[str]:
    return [str(item) for item in _as_list(value) if str(item or "").strip()]


def _load_slide_plan(path_or_ref, *, base=None) -> dict:
    if isinstance(path_or_ref, dict):
        if path_or_ref.get("schema_version") == INPUT_CONTRACT and "slots" in path_or_ref:
            plan = path_or_ref
        elif isinstance(path_or_ref.get("ref"), str):
            plan = artifacts.hydrate(path_or_ref["ref"], base=base)
        else:
            raise ValueError("expected slide_plan@1 object or a descriptor with ref")
    else:
        text = str(path_or_ref)
        if text.startswith(artifacts.SCHEME):
            plan = artifacts.hydrate(text, base=base)
        else:
            loaded = json.loads(Path(text).read_text(encoding="utf-8"))
            plan = artifacts.hydrate(loaded["ref"], base=base) if isinstance(loaded.get("ref"), str) else loaded
    checked = contracts.validate(plan, INPUT_CONTRACT)
    if not checked["ok"]:
        raise ValueError("invalid slide_plan@1: " + "; ".join(checked["errors"]))
    return plan


def build_slide_design(slide_plan_or_ref, *, base=None) -> dict:
    """Build a validated ``slide_design_set@1`` draft from a ``slide_plan@1``."""
    plan = _load_slide_plan(slide_plan_or_ref, base=base)
    slides: list[dict] = []
    total_minutes = 0
    for slot in sorted(_as_list(plan.get("slots")), key=lambda s: s.get("position", 0) if isinstance(s, dict) else 0):
        if not isinstance(slot, dict):
            continue
        status = str(slot.get("status") or "KEEP")
        if status == "REMOVE":
            continue
        pointers = slot.get("content_pointers") if isinstance(slot.get("content_pointers"), dict) else {}
        bullets = _strings(pointers.get("add")) + _strings(pointers.get("keep"))
        title = str(slot.get("working_title") or slot.get("slot_id") or "Slide")
        rationale = str(slot.get("rationale") or "")
        is_new = bool(slot.get("is_new_information"))
        narrative = f"{title}. {rationale}".strip() or f"{title}."
        minutes = 3 if is_new else 2
        total_minutes += minutes
        slides.append({
            "slide_id": str(slot.get("slot_id") or f"D{slot.get('position', 0):03d}"),
            "slot_id": str(slot.get("slot_id") or ""),
            "position": int(slot.get("position") or (len(slides) + 1)),
            "status": status,
            "title": title,
            "body": {
                "bullets": bullets,
                "key_takeaway": bullets[0] if bullets else rationale,
            },
            "narrative": narrative,
            "speaker_notes": rationale,
            "design": {"layout": "title+bullets", "visual_suggestion": "", "emphasis": ""},
            "estimated_minutes": minutes,
            "source_refs": _strings(slot.get("source_refs")),
            "is_new_information": is_new,
        })

    design = {
        "schema_version": OUTPUT_CONTRACT,
        "task_id": plan["task_id"],
        "output_language": plan["output_language"],
        "slides": slides,
        "deck_metrics": {
            "slide_count": len(slides),
            "estimated_total_minutes": total_minutes,
            "target_minutes": int(plan.get("target_duration_minutes") or 0),
        },
    }
    checked = contracts.validate(design, OUTPUT_CONTRACT)
    if not checked["ok"]:
        raise ValueError("invalid slide_design_set@1: " + "; ".join(checked["errors"]))
    return design


def finalize_slide_design_from_input(slide_plan_or_ref, *, base=None) -> dict:
    """Build and persist the slide design set through the official G03 finalize path."""
    design = build_slide_design(slide_plan_or_ref, base=base)
    return solution.finalize_slide_design(design["task_id"], design, base=base)
