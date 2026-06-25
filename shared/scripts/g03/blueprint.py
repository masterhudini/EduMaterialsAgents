"""Build a ``solution_blueprint@1`` from the G03 dual-input boundary.

This module is deliberately local to g03. It does not call g01 or g02; it only hydrates the two
refs already present in ``solution_graph_input@1`` and turns them into the thin Solution deliverable.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys as _sys

_sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> shared/scripts

from core import artifacts, contracts  # noqa: E402
from g03 import solution  # noqa: E402

INPUT_CONTRACT = "solution_graph_input@1"
LECTURE_CONTRACT = "lecture_baseline@1"
CANDIDATE_KIND = "solution_input_candidate"
CANDIDATE_CONTRACT = "solution_input_candidate@1"
LEGACY_KIND = "user_approved_research_bundle"
LEGACY_CONTRACT = "user_approved_research_bundle@1"
OUTPUT_CONTRACT = "solution_blueprint@1"


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _strings(value: object) -> list[str]:
    return [str(item) for item in _as_list(value) if str(item or "").strip()]


def _first_string(value: object) -> str | None:
    values = _strings(value)
    return values[0] if values else None


def _load_json_path(path: str | Path) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _normalise_composite(path_or_ref, *, base=None) -> tuple[dict, str | None]:
    """Return ``solution_graph_input@1`` and, if available, its artifact ref."""
    if isinstance(path_or_ref, dict):
        if path_or_ref.get("schema_version") == INPUT_CONTRACT:
            composite = deepcopy(path_or_ref)
            ref = None
        else:
            ref = solution.resolve_context(path_or_ref, base=base)
            composite = artifacts.hydrate(ref, base=base)
    else:
        text = str(path_or_ref)
        if text.startswith(artifacts.SCHEME):
            ref = text
            composite = artifacts.hydrate(ref, base=base)
        else:
            payload = _load_json_path(text)
            if payload.get("schema_version") == INPUT_CONTRACT:
                composite = payload
                ref = None
            else:
                ref = solution.resolve_context(text, base=base)
                composite = artifacts.hydrate(ref, base=base)
    checked = contracts.validate(composite, INPUT_CONTRACT)
    if not checked["ok"]:
        raise ValueError("invalid solution_graph_input@1: " + "; ".join(checked["errors"]))
    return composite, ref


def hydrate_solution_context(path_or_ref, *, base=None) -> dict:
    """Hydrate G03 input refs and validate the selected research side."""
    composite, composite_ref = _normalise_composite(path_or_ref, base=base)
    lecture = artifacts.hydrate(composite["lecture_baseline_ref"], base=base)
    checked = contracts.validate(lecture, LECTURE_CONTRACT)
    if not checked["ok"]:
        raise ValueError("invalid lecture_baseline@1: " + "; ".join(checked["errors"]))

    research_kind = composite.get("research_bundle_kind") or LEGACY_KIND
    research_contract = CANDIDATE_CONTRACT if research_kind == CANDIDATE_KIND else LEGACY_CONTRACT
    research = artifacts.hydrate(composite["research_bundle_ref"], base=base)
    checked = contracts.validate(research, research_contract)
    if not checked["ok"]:
        raise ValueError(f"invalid {research_contract}: " + "; ".join(checked["errors"]))
    return {
        "composite": composite,
        "composite_ref": composite_ref,
        "lecture_baseline": lecture,
        "research_bundle": research,
        "research_bundle_kind": research_kind,
        "research_contract": research_contract,
    }


def _ordered_slides(lecture: dict) -> list[dict]:
    return sorted(
        [slide for slide in _as_list(lecture.get("slides")) if isinstance(slide, dict)],
        key=lambda slide: (slide.get("order", 0), str(slide.get("slide_id") or "")),
    )


def _section_maps(lecture: dict) -> tuple[dict[str, dict], dict[str, str]]:
    section_by_id: dict[str, dict] = {}
    section_by_slide: dict[str, str] = {}
    for section in _as_list(lecture.get("sections")):
        if not isinstance(section, dict) or not section.get("section_id"):
            continue
        section_id = str(section["section_id"])
        section_by_id[section_id] = section
        for slide_id in _strings(section.get("slide_ids")):
            section_by_slide.setdefault(slide_id, section_id)
    return section_by_id, section_by_slide


def _lecture_indexes(lecture: dict) -> dict:
    slides = _ordered_slides(lecture)
    section_by_id, section_by_slide = _section_maps(lecture)
    claim_to_slides: dict[str, list[str]] = {}
    concept_to_slides: dict[str, list[str]] = {}
    slide_by_id: dict[str, dict] = {}
    slide_pointer: dict[str, str] = {}
    original_slides = _as_list(lecture.get("slides"))
    for slide in slides:
        slide_id = str(slide.get("slide_id") or "")
        if not slide_id:
            continue
        slide_by_id[slide_id] = slide
        try:
            slide_pointer[slide_id] = f"#/slides/{original_slides.index(slide)}"
        except ValueError:
            slide_pointer[slide_id] = "#/slides/0"
        for claim_id in _strings(slide.get("claim_ids")):
            claim_to_slides.setdefault(claim_id, []).append(slide_id)
        for concept_id in _strings(slide.get("concept_ids")):
            concept_to_slides.setdefault(concept_id, []).append(slide_id)
    locked_sections = {str(item) for item in _as_list(lecture.get("locked_sections"))}
    locked_slides = {
        slide_id for slide_id, slide in slide_by_id.items()
        if slide.get("locked") is True
    }
    for slide_id, section_id in section_by_slide.items():
        section = section_by_id.get(section_id, {})
        if section_id in locked_sections or str(section.get("title") or "") in locked_sections:
            locked_slides.add(slide_id)
    return {
        "slides": slides,
        "slide_by_id": slide_by_id,
        "slide_pointer": slide_pointer,
        "section_by_id": section_by_id,
        "section_by_slide": section_by_slide,
        "claim_to_slides": claim_to_slides,
        "concept_to_slides": concept_to_slides,
        "locked_slides": locked_slides,
    }


def _outline(lecture: dict, indexes: dict) -> list[dict]:
    sections = [
        section for section in _as_list(lecture.get("sections"))
        if isinstance(section, dict) and section.get("section_id") and section.get("title")
    ]
    if not sections:
        return [{
            "section_id": "S1",
            "title": lecture.get("lecture", {}).get("title") or "Lecture",
            "summary": "Generated from lecture slide order.",
            "slide_ids": [str(slide["slide_id"]) for slide in indexes["slides"] if slide.get("slide_id")],
        }]
    outline = []
    for section in sections:
        slide_ids = _strings(section.get("slide_ids"))
        slide_titles = [
            indexes["slide_by_id"][slide_id].get("title")
            for slide_id in slide_ids
            if slide_id in indexes["slide_by_id"]
        ]
        outline.append({
            "section_id": str(section["section_id"]),
            "title": str(section["title"]),
            "summary": "; ".join(str(title) for title in slide_titles if title) or "No slide summary.",
            "slide_ids": slide_ids,
        })
    return outline


def _dedupe_in_order(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _resolve_candidate_slides(update: dict, indexes: dict) -> tuple[list[str], list[str]]:
    linked = update.get("linked_intake_ids") if isinstance(update.get("linked_intake_ids"), dict) else {}
    candidates: list[str] = []
    for claim_id in _strings(linked.get("claim_ids")):
        candidates.extend(indexes["claim_to_slides"].get(claim_id, []))
    if not candidates:
        for concept_id in _strings(linked.get("concept_ids")):
            candidates.extend(indexes["concept_to_slides"].get(concept_id, []))
    candidates = _dedupe_in_order(candidates)
    unlocked = [slide_id for slide_id in candidates if slide_id not in indexes["locked_slides"]]
    locked = [slide_id for slide_id in candidates if slide_id in indexes["locked_slides"]]
    return unlocked, locked


def _resolve_legacy_slides(finding: dict, indexes: dict) -> tuple[list[str], list[str]]:
    candidates: list[str] = []
    for claim_id in _strings(finding.get("related_claims")):
        candidates.extend(indexes["claim_to_slides"].get(claim_id, []))
    if not candidates:
        for concept_id in _strings(finding.get("related_concepts")):
            candidates.extend(indexes["concept_to_slides"].get(concept_id, []))
    candidates = _dedupe_in_order(candidates)
    unlocked = [slide_id for slide_id in candidates if slide_id not in indexes["locked_slides"]]
    locked = [slide_id for slide_id in candidates if slide_id in indexes["locked_slides"]]
    return unlocked, locked


def _source_ids(refs: object) -> list[str]:
    ids: list[str] = []
    for ref in _as_list(refs):
        if isinstance(ref, dict):
            value = ref.get("source_id") or ref.get("doi") or ref.get("title")
        else:
            value = ref
        if value:
            ids.append(str(value))
    return _dedupe_in_order(ids)


def _section_for(slide_ids: list[str], indexes: dict) -> str | None:
    for slide_id in slide_ids:
        section_id = indexes["section_by_slide"].get(slide_id)
        if section_id:
            return section_id
    return None


def _slide_ref(lecture_ref: str, slide_ids: list[str], indexes: dict) -> str | None:
    if not slide_ids:
        return None
    pointer = indexes["slide_pointer"].get(slide_ids[0])
    return f"{lecture_ref}{pointer}" if pointer else lecture_ref


def _candidate_summary(update: dict, slide_ids: list[str]) -> str:
    ready = update.get("ready_to_apply_text") if isinstance(update.get("ready_to_apply_text"), dict) else {}
    bullet = ready.get("slide_bullet") or update.get("finding") or ""
    note = ready.get("speaker_note") or update.get("rationale") or ""
    relation = update.get("extension_relation")
    prefix = f"Slides {', '.join(slide_ids)}: " if slide_ids else ""
    parts = [prefix + str(bullet).strip()]
    if note:
        parts.append(f"Rationale: {str(note).strip()}")
    if relation:
        parts.append(f"Relation: {relation}")
    return " ".join(part for part in parts if part).strip()


def _legacy_summary(finding: dict, slide_ids: list[str]) -> str:
    impact = finding.get("impact") or finding.get("summary") or finding.get("finding") or ""
    prefix = f"Slides {', '.join(slide_ids)}: " if slide_ids else ""
    return (prefix + str(impact).strip()).strip()


def _add_source_usage(source_usage: dict[str, list[str]], source_ids: list[str], update_id: str) -> None:
    for source_id in source_ids:
        bucket = source_usage.setdefault(source_id, [])
        if update_id not in bucket:
            bucket.append(update_id)


def _deferred(item_id: object, reason: str, related_claim: str | None = None) -> dict:
    item = {"item_id": str(item_id or "deferred_item"), "reason": reason}
    if related_claim:
        item["related_claim_ref"] = related_claim
    return item


def _candidate_blueprint(context: dict, indexes: dict) -> tuple[list[dict], list[dict], dict[str, list[str]]]:
    composite = context["composite"]
    lecture_ref = composite["lecture_baseline_ref"]
    research_ref = composite["research_bundle_ref"]
    research = context["research_bundle"]
    applied: list[dict] = []
    deferred: list[dict] = []
    source_usage: dict[str, list[str]] = {}

    for index, update in enumerate(_as_list(research.get("suggested_updates"))):
        if not isinstance(update, dict):
            continue
        update_id = str(update.get("update_id") or f"candidate_update_{index + 1:03d}")
        slide_ids, locked = _resolve_candidate_slides(update, indexes)
        linked = update.get("linked_intake_ids") if isinstance(update.get("linked_intake_ids"), dict) else {}
        related_claim = _first_string(linked.get("claim_ids"))
        if not slide_ids:
            reason = "No matching unlocked lecture slide for linked_intake_ids."
            if locked:
                reason = "Matching lecture slides are locked: " + ", ".join(locked)
            deferred.append(_deferred(update_id, reason, related_claim))
            continue
        source_ids = _source_ids(update.get("source_refs"))
        entry = {
            "update_id": update_id,
            "change_summary": _candidate_summary(update, slide_ids),
            "finding_ref": f"{research_ref}#/suggested_updates/{index}",
            "target_section_id": _section_for(slide_ids, indexes) or "",
            "source_refs": source_ids,
            "target_slide_ids": slide_ids,
        }
        slide_ref = _slide_ref(lecture_ref, slide_ids, indexes)
        if slide_ref:
            entry["slide_impact_card_ref"] = slide_ref
        applied.append(entry)
        _add_source_usage(source_usage, source_ids, update_id)

    for index, update in enumerate(_as_list(research.get("optional_improvements"))):
        if not isinstance(update, dict):
            continue
        linked = update.get("linked_intake_ids") if isinstance(update.get("linked_intake_ids"), dict) else {}
        reason = str(update.get("finding") or "Optional improvement left for solution-gate decision.")
        deferred.append(_deferred(
            update.get("update_id") or f"optional_{index + 1:03d}",
            "Optional improvement not applied automatically: " + reason,
            _first_string(linked.get("claim_ids")),
        ))

    for index, item in enumerate(_as_list(research.get("unresolved_items")), start=1):
        if not isinstance(item, dict):
            continue
        linked = item.get("linked_intake_ids") if isinstance(item.get("linked_intake_ids"), dict) else {}
        question = item.get("question") or item.get("why_unresolved") or "Unresolved research item."
        reason = str(question)
        if item.get("what_would_resolve"):
            reason += f" Resolution path: {item['what_would_resolve']}"
        deferred.append(_deferred(
            item.get("item_id") or f"unresolved_{index:03d}",
            reason,
            _first_string(linked.get("claim_ids")),
        ))

    for index, gap in enumerate(_as_list(research.get("coverage_gaps")), start=1):
        if not isinstance(gap, dict):
            continue
        linked = gap.get("linked_intake_ids") if isinstance(gap.get("linked_intake_ids"), dict) else {}
        reason = str(gap.get("note") or gap.get("gap_type") or "Coverage gap.")
        deferred.append(_deferred(
            gap.get("gap_id") or f"coverage_gap_{index:03d}",
            reason,
            _first_string(linked.get("claim_ids")),
        ))
    return applied, deferred, source_usage


def _legacy_blueprint(context: dict, indexes: dict) -> tuple[list[dict], list[dict], dict[str, list[str]]]:
    composite = context["composite"]
    lecture_ref = composite["lecture_baseline_ref"]
    research_ref = composite["research_bundle_ref"]
    research = context["research_bundle"]
    applied: list[dict] = []
    deferred: list[dict] = []
    source_usage: dict[str, list[str]] = {}

    for index, finding in enumerate(_as_list(research.get("approved_update_findings"))):
        if not isinstance(finding, dict):
            continue
        update_id = str(finding.get("finding_id") or f"legacy_update_{index + 1:03d}")
        slide_ids, locked = _resolve_legacy_slides(finding, indexes)
        related_claim = _first_string(finding.get("related_claims"))
        if not slide_ids:
            reason = "No matching unlocked lecture slide for approved finding."
            if locked:
                reason = "Matching lecture slides are locked: " + ", ".join(locked)
            deferred.append(_deferred(update_id, reason, related_claim))
            continue
        source_ids = _source_ids(finding.get("source_refs"))
        entry = {
            "update_id": update_id,
            "change_summary": _legacy_summary(finding, slide_ids),
            "finding_ref": f"{research_ref}#/approved_update_findings/{index}",
            "target_section_id": _section_for(slide_ids, indexes) or "",
            "source_refs": source_ids,
            "target_slide_ids": slide_ids,
        }
        slide_ref = _slide_ref(lecture_ref, slide_ids, indexes)
        if slide_ref:
            entry["slide_impact_card_ref"] = slide_ref
        applied.append(entry)
        _add_source_usage(source_usage, source_ids, update_id)

    for index, finding in enumerate(_as_list(research.get("approved_optional_findings"))):
        if not isinstance(finding, dict):
            continue
        deferred.append(_deferred(
            finding.get("finding_id") or f"legacy_optional_{index + 1:03d}",
            "Approved optional finding left for solution-gate decision: "
            + str(finding.get("impact") or finding.get("summary") or ""),
            _first_string(finding.get("related_claims")),
        ))

    handoff = research.get("solution_handoff") if isinstance(research.get("solution_handoff"), dict) else {}
    for index, item in enumerate(_as_list(handoff.get("unresolved_claim_cards")), start=1):
        if not isinstance(item, dict):
            continue
        deferred.append(_deferred(
            item.get("claim_id") or f"legacy_unresolved_{index:03d}",
            str(item.get("text") or item.get("status") or "Unresolved claim."),
            item.get("claim_id") if isinstance(item.get("claim_id"), str) else None,
        ))
    return applied, deferred, source_usage


def _source_attribution(source_usage: dict[str, list[str]]) -> list[dict]:
    return [
        {"source_ref": source_id, "used_for": used_for}
        for source_id, used_for in source_usage.items()
    ]


def build_blueprint(path_or_ref, *, base=None) -> dict:
    """Build a validated ``solution_blueprint@1`` from a G03 request/ref/path."""
    context = hydrate_solution_context(path_or_ref, base=base)
    composite = context["composite"]
    lecture = context["lecture_baseline"]
    indexes = _lecture_indexes(lecture)
    if context["research_bundle_kind"] == CANDIDATE_KIND:
        applied, deferred, source_usage = _candidate_blueprint(context, indexes)
    else:
        applied, deferred, source_usage = _legacy_blueprint(context, indexes)

    blueprint = {
        "schema_version": OUTPUT_CONTRACT,
        "task_id": composite["task_id"],
        "output_language": composite.get("output_language") or lecture.get("output_language") or "English",
        "lecture_outline": _outline(lecture, indexes),
        "applied_updates": applied,
        "deferred_items": deferred,
        "source_attribution": _source_attribution(source_usage),
    }
    checked = contracts.validate(blueprint, OUTPUT_CONTRACT)
    if not checked["ok"]:
        raise ValueError("invalid solution_blueprint@1: " + "; ".join(checked["errors"]))
    return blueprint


def finalize_blueprint_from_input(path_or_ref, *, base=None) -> dict:
    """Build and persist the blueprint through the official G03 finalize path."""
    blueprint = build_blueprint(path_or_ref, base=base)
    return solution.finalize_blueprint(blueprint["task_id"], blueprint, base=base)
