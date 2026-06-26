"""Build a deterministic ``slide_plan@1`` draft for G03-A02 (Slide Plan Architect).

This is the STARTING POINT the agent refines, mirroring the blueprint draft pattern: it mechanically
assembles the ordered new-deck skeleton from the lecture baseline (existing slides, default KEEP),
overlays g03-a01's ``solution_blueprint@1`` applied updates (-> UPDATE) and proposes NEW slides
(status ADD) seeded ONLY from the g02 candidate's coverage gaps, unresolved items and optional
improvements, covered topics, recommended claims and market-case findings. No new evidence; no slide
content design (that is g03-a03). Pure stdlib.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys as _sys

_sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> shared/scripts

from core import artifacts, contracts  # noqa: E402
from g03 import blueprint as bp  # noqa: E402
from g03 import solution  # noqa: E402

OUTPUT_CONTRACT = "slide_plan@1"


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _strings(value: object) -> list[str]:
    return [str(item) for item in _as_list(value) if str(item or "").strip()]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _anchor_for(linked: object, indexes: dict) -> str | None:
    linked = linked if isinstance(linked, dict) else {}
    for claim_id in _strings(linked.get("claim_ids")):
        hits = indexes["claim_to_slides"].get(claim_id)
        if hits:
            return hits[0]
    for concept_id in _strings(linked.get("concept_ids")):
        hits = indexes["concept_to_slides"].get(concept_id)
        if hits:
            return hits[0]
    return None


def _topic_linked_ids(topic: dict) -> dict:
    return {
        "claim_ids": _strings(topic.get("linked_claims")),
        "concept_ids": _strings(topic.get("linked_concepts")),
    }


def build_slide_plan(path_or_ref, *, base=None) -> dict:
    """Build a validated ``slide_plan@1`` draft from a G03 request/ref/path."""
    context = bp.hydrate_solution_context(path_or_ref, base=base)
    blueprint = bp.build_blueprint(path_or_ref, base=base)
    lecture = context["lecture_baseline"]
    research = context["research_bundle"]
    kind = context["research_bundle_kind"]
    indexes = bp._lecture_indexes(lecture)

    update_by_slide: dict[str, list[dict]] = {}
    for update in _as_list(blueprint.get("applied_updates")):
        if not isinstance(update, dict):
            continue
        for slide_id in _strings(update.get("target_slide_ids")):
            update_by_slide.setdefault(slide_id, []).append(update)

    source_slide_by_id: dict[str, dict] = {
        str(s.get("slide_id")): s for s in _as_list(blueprint.get("source_slides"))
        if isinstance(s, dict) and s.get("slide_id")
    }

    existing_slots: list[dict] = []
    for slide in indexes["slides"]:
        slide_id = str(slide.get("slide_id") or "")
        if not slide_id:
            continue
        locked = slide_id in indexes["locked_slides"]
        updates = update_by_slide.get(slide_id, [])
        section_id = indexes["section_by_slide"].get(slide_id, "")
        if updates and not locked:
            status = "UPDATE"
            add = _dedupe([str(u.get("change_summary")) for u in updates if u.get("change_summary")])
            applied_ids = _dedupe([str(u.get("update_id")) for u in updates if u.get("update_id")])
            source_refs = _dedupe([s for u in updates for s in _strings(u.get("source_refs"))])
            rationale = "Existing slide updated from reviewed research."
        else:
            status = "KEEP"
            add, applied_ids, source_refs = [], [], []
            rationale = ("Existing slide kept; matching research is locked or deferred."
                         if updates else "Existing slide kept.")
        source_slide = source_slide_by_id.get(slide_id, {})
        original_content = str(source_slide.get("original_content") or "").strip()
        keep_pointers = _strings([original_content or slide.get("gist") or slide.get("title")])
        working_title = str(slide.get("title") or slide_id)
        update_text = " ".join(add).strip()
        teaching_seed = original_content or str(slide.get("gist") or "")
        if update_text:
            teaching_seed = (teaching_seed + " " + update_text).strip()
        existing_slots.append({
            "slot_id": f"SLOT_E_{slide_id}",
            "position": 0,
            "kind": "existing",
            "status": status,
            "source_slide_ids": [slide_id],
            "section_id": section_id,
            "working_title": working_title,
            "power_title": working_title,
            "teaching_message": teaching_seed,
            "rationale": rationale,
            "original_content": original_content,
            "web_case_facts": [],
            "content_pointers": {
                "keep": keep_pointers,
                "add": add,
                "remove": [],
            },
            "applied_update_ids": applied_ids,
            "evidence_basis": [],
            "source_refs": source_refs,
            "locked": locked,
            "is_new_information": False,
        })

    new_after: dict[str, list[dict]] = {}
    tail_new: list[dict] = []
    counter = 0

    def emit_new(anchor: str | None, title: str, add_text: str, basis: list[str],
                 source_refs: list[str], web_case_facts: list[dict] | None = None) -> None:
        nonlocal counter
        counter += 1
        slot = {
            "slot_id": f"SLOT_N_{counter:03d}",
            "position": 0,
            "kind": "new",
            "status": "ADD",
            "source_slide_ids": [],
            "section_id": indexes["section_by_slide"].get(anchor, "") if anchor else "",
            "working_title": title or "New slide",
            "power_title": title or "New slide",
            "teaching_message": add_text,
            "rationale": "Proposed new slide carrying information not present in the previous presentation.",
            "original_content": "",
            "web_case_facts": [f for f in (web_case_facts or []) if isinstance(f, dict)],
            "content_pointers": {"keep": [], "add": _strings([add_text]), "remove": []},
            "applied_update_ids": [],
            "evidence_basis": basis,
            "source_refs": source_refs,
            "locked": False,
            "is_new_information": True,
        }
        if anchor:
            new_after.setdefault(anchor, []).append(slot)
        else:
            tail_new.append(slot)

    seen: set[tuple] = set()
    if kind == bp.CANDIDATE_KIND:
        for index, gap in enumerate(_as_list(research.get("coverage_gaps")), start=1):
            if not isinstance(gap, dict):
                continue
            note = str(gap.get("note") or gap.get("gap_type") or "Coverage gap")
            if ("gap", note) in seen:
                continue
            seen.add(("gap", note))
            emit_new(_anchor_for(gap.get("linked_intake_ids"), indexes), note[:80], note,
                     [f"coverage_gap:{gap.get('gap_type') or index}"], [])
        for index, item in enumerate(_as_list(research.get("unresolved_items")), start=1):
            if not isinstance(item, dict):
                continue
            question = str(item.get("question") or item.get("why_unresolved") or "Unresolved item")
            if ("unresolved", question) in seen:
                continue
            seen.add(("unresolved", question))
            emit_new(_anchor_for(item.get("linked_intake_ids"), indexes), question[:80], question,
                     [f"unresolved:{item.get('why_unresolved') or index}"], [])
        for index, opt in enumerate(_as_list(research.get("optional_improvements")), start=1):
            if not isinstance(opt, dict):
                continue
            finding = str(opt.get("finding") or "Optional improvement")
            key = ("optional", str(opt.get("update_id") or finding))
            if key in seen:
                continue
            seen.add(key)
            source_refs = _dedupe([str(s.get("source_id")) for s in _as_list(opt.get("source_refs"))
                                   if isinstance(s, dict) and s.get("source_id")])
            emit_new(_anchor_for(opt.get("linked_intake_ids"), indexes), finding[:80], finding,
                     [f"optional:{opt.get('update_id') or index}"], source_refs)
        for index, topic in enumerate(_as_list(research.get("topics_covered")), start=1):
            if not isinstance(topic, dict):
                continue
            topic_id = str(topic.get("topic_id") or f"topic_{index:03d}")
            name = str(topic.get("name") or "").strip()
            note = str(topic.get("coverage_note") or "").strip()
            if not name and not note:
                continue
            key = ("topic", topic_id)
            if key in seen:
                continue
            seen.add(key)
            title = name or note[:80]
            add_text = note if note else name
            if name and note and name not in note:
                add_text = f"{name}: {note}"
            emit_new(_anchor_for(_topic_linked_ids(topic), indexes), title[:80], add_text,
                     [f"topic:{topic_id}"], [])

    # Additive recommendations and market cases run for BOTH kinds: the candidate path carries them
    # top level, the gated user_approved_research_bundle@1 under solution_handoff (handled in
    # _extract_additive_candidates). This is where A11 cases and A08 recommendations become slides.
    for candidate in bp._extract_additive_candidates(research, base=base):
        if not isinstance(candidate, dict) or candidate.get("kind") == "market_case_ref_unavailable":
            continue
        candidate_id = str(candidate.get("candidate_id") or candidate.get("finding") or "additive")
        ckind = str(candidate.get("kind") or "additive")
        key = (ckind, candidate_id)
        if key in seen:
            continue
        seen.add(key)
        finding = str(candidate.get("finding") or "Recommended additive material")
        rationale = str(candidate.get("rationale") or "")
        add_text = finding if not rationale else f"{finding} Rationale: {rationale}"
        basis = _strings(candidate.get("evidence_basis")) or [f"{ckind}:{candidate_id}"]
        source_refs = _dedupe(_strings(candidate.get("source_refs")))
        emit_new(
            _anchor_for(candidate.get("linked_intake_ids"), indexes),
            finding[:80],
            add_text,
            basis,
            source_refs,
            web_case_facts=[f for f in _as_list(candidate.get("web_case_facts")) if isinstance(f, dict)],
        )

    ordered: list[dict] = []
    for slot in existing_slots:
        ordered.append(slot)
        for new_slot in new_after.get(slot["source_slide_ids"][0], []):
            ordered.append(new_slot)
    ordered.extend(tail_new)
    for position, slot in enumerate(ordered, start=1):
        slot["position"] = position

    stats = {"keep": 0, "update": 0, "add": 0, "remove": 0, "merge": 0, "split": 0, "reorder": 0}
    for slot in ordered:
        key = slot["status"].lower()
        stats[key] = stats.get(key, 0) + 1

    plan = {
        "schema_version": OUTPUT_CONTRACT,
        "task_id": blueprint["task_id"],
        "output_language": blueprint["output_language"],
        "deck_summary": "Draft new-deck plan: existing slides plus proposed new slides from reviewed research.",
        "slots": ordered,
        "deferred_items": deepcopy(_as_list(blueprint.get("deferred_items"))),
        "source_attribution": deepcopy(_as_list(blueprint.get("source_attribution"))),
        "change_stats": stats,
    }
    presentation = research.get("presentation_context")
    if isinstance(presentation, dict) and isinstance(presentation.get("target_duration_minutes"), int):
        plan["target_duration_minutes"] = presentation["target_duration_minutes"]

    checked = contracts.validate(plan, OUTPUT_CONTRACT)
    if not checked["ok"]:
        raise ValueError("invalid slide_plan@1: " + "; ".join(checked["errors"]))
    return plan


def finalize_slide_plan_from_input(path_or_ref, *, base=None) -> dict:
    """Build and persist the slide plan through the official G03 finalize path."""
    plan = build_slide_plan(path_or_ref, base=base)
    return solution.finalize_slide_plan(plan["task_id"], plan, base=base)
