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


def _norm(text: object) -> str:
    return " ".join(str(text or "").split()).strip().lower()


def _dedup_bullets(bullets: list[str], narrative: str, web_case_facts: list[dict]) -> list[str]:
    """Drop bullets that merely restate the narrative or a case already shown as an example block.

    The deterministic seed otherwise repeats the same sentence in the narrative, a bullet and the
    example title; this keeps one clean copy so the fallback prompt does not read as padding.
    """
    nn = _norm(narrative)
    case_norms = {_norm(f.get("what_happened")) for f in web_case_facts}
    case_norms |= {_norm(f.get("title")) for f in web_case_facts}
    out: list[str] = []
    seen: set[str] = set()
    for bullet in bullets:
        nb = _norm(bullet)
        if not nb or nb in seen:
            continue
        if nn and (nb in nn or nn in nb):   # essentially the narrative
            continue
        if any(nb in cn or cn in nb for cn in case_norms if cn):  # already an example block
            continue
        seen.add(nb)
        out.append(bullet)
    return out


def _content_blocks(bullets: list[str], web_case_facts: list[dict], slot: dict) -> list[dict]:
    """Deterministic seed of structured slide elements the a03 agent refines.

    A bullet block from the planned content, plus one example block per real-world case (so the
    market fact + source travel to the prompt as elements, not just IDs).
    """
    blocks: list[dict] = []
    if bullets:
        blocks.append({"kind": "bullets", "content": bullets, "source_refs": _strings(slot.get("source_refs"))})
    for fact in web_case_facts:
        parts = [str(fact.get("what_happened") or "").strip()]
        if fact.get("institution_or_event"):
            parts.append(f"({fact.get('institution_or_event')}"
                         + (f", {fact.get('event_date')}" if fact.get("event_date") else "") + ")")
        content = " ".join(p for p in parts if p).strip()
        src = str(fact.get("source_url") or fact.get("source_title") or fact.get("case_id") or "")
        blocks.append({
            "kind": "example",
            "title": str(fact.get("title") or "Real-world case"),
            "content": content,
            "why_interesting": str(fact.get("why_interesting") or ""),
            "source_refs": [src] if src else [],
        })
    return blocks


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
        working_title = str(slot.get("working_title") or slot.get("slot_id") or "Slide")
        title = str(slot.get("power_title") or working_title)
        rationale = str(slot.get("rationale") or "")
        original_content = str(slot.get("original_content") or "").strip()
        teaching_message = str(slot.get("teaching_message") or "").strip()
        web_case_facts = [f for f in _as_list(slot.get("web_case_facts")) if isinstance(f, dict)]
        is_new = bool(slot.get("is_new_information"))
        # Seed the narrative from the real teaching message / slide text, so the agent expands actual
        # content instead of padding a title+rationale stub. Do NOT prepend the title — the power
        # title is already the heading, and the original content often starts with it (double-title).
        narrative = str(teaching_message or original_content or rationale).strip() or working_title
        bullets = _dedup_bullets(bullets, narrative, web_case_facts)
        content_blocks = _content_blocks(bullets, web_case_facts, slot)
        minutes = 3 if is_new else 2
        total_minutes += minutes
        slides.append({
            "slide_id": str(slot.get("slot_id") or f"D{slot.get('position', 0):03d}"),
            "slot_id": str(slot.get("slot_id") or ""),
            "position": int(slot.get("position") or (len(slides) + 1)),
            "status": status,
            "title": title,
            "subtitle": working_title if title != working_title else "",
            "body": {
                "bullets": bullets,
                "key_takeaway": bullets[0] if bullets else (teaching_message or rationale),
            },
            "content_blocks": content_blocks,
            "narrative": narrative,
            "speaker_notes": teaching_message or rationale,
            "design": {
                "layout": "comparison" if web_case_facts else "title+bullets",
                "visual_suggestion": "Table or schematic contrasting the concept with the real-world example."
                if web_case_facts else "",
                "emphasis": "",
                "artifacts": [b["kind"] for b in content_blocks if b["kind"] in {"example", "literature"}],
            },
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
