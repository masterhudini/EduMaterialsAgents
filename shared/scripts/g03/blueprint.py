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


def _sanitize_candidate(research: dict) -> dict:
    """Defensively complete partial ``optional_improvements`` so one malformed lower-priority entry
    cannot block the whole G03 front door.

    The contract requires optional improvements to carry the same field set as suggested updates;
    older or hand-authored candidates sometimes omit them. We backfill the required scaffolding with
    empty values (optional improvements are non-essential deferral material — the substantive
    ``suggested_updates`` are untouched) and drop non-dict entries. The post-hydration contract
    validation stays strict, so this never hides a malformed ``suggested_updates``. Returns a copy.
    """
    if research.get("schema_version") != CANDIDATE_CONTRACT \
            or not isinstance(research.get("optional_improvements"), list):
        return research
    result = deepcopy(research)
    sanitized: list[dict] = []
    for index, item in enumerate(result.get("optional_improvements") or [], start=1):
        if not isinstance(item, dict):
            continue
        item.setdefault("update_id", f"OPT_{index:03d}")
        item.setdefault("finding", "")
        item.setdefault("rationale", "")
        if not isinstance(item.get("linked_intake_ids"), dict):
            item["linked_intake_ids"] = {}
        if not isinstance(item.get("target"), dict):
            item["target"] = {}
        ready = item.get("ready_to_apply_text")
        ready = ready if isinstance(ready, dict) else {}
        ready.setdefault("slide_bullet", "")
        ready.setdefault("speaker_note", "")
        ready.setdefault("optional_detail", "")
        item["ready_to_apply_text"] = ready
        if not isinstance(item.get("evidence_refs"), list):
            item["evidence_refs"] = []
        if not isinstance(item.get("source_refs"), list):
            item["source_refs"] = []
        item.setdefault("confidence", "needs_human_check")
        sanitized.append(item)
    result["optional_improvements"] = sanitized
    return result


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
    if research_kind == CANDIDATE_KIND:
        research = _sanitize_candidate(research)
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


def _slide_views_text(lecture: dict, *, base=None) -> dict[str, str]:
    """Hydrate the lecture's ``slide_views_ref`` and map slide_id -> original slide text.

    g01's ``lecture_baseline@1`` is a thin skeleton (title + one-line gist); the real per-slide text
    lives in ``slide_views@1``. Without this, KEEP slides reach G03 with no content and downstream
    stages can only emit generic filler. Failing open returns an empty map (skeleton-only fallback).
    """
    ref = lecture.get("slide_views_ref")
    if not (isinstance(ref, str) and ref.startswith(artifacts.SCHEME)):
        return {}
    try:
        views = artifacts.hydrate(ref, base=base)
    except (OSError, ValueError, KeyError):
        return {}
    out: dict[str, str] = {}
    for slide in _as_list(views.get("slides")):
        if isinstance(slide, dict) and slide.get("slide_id"):
            text = slide.get("normalized_text") or slide.get("text") or ""
            out[str(slide["slide_id"])] = str(text)
    return out


def _source_slides(indexes: dict, slide_text: dict[str, str]) -> list[dict]:
    """Per-slide original content carried into the blueprint so KEEP slides are not empty."""
    result = []
    for slide in indexes["slides"]:
        slide_id = str(slide.get("slide_id") or "")
        if not slide_id:
            continue
        result.append({
            "slide_id": slide_id,
            "title": str(slide.get("title") or ""),
            "gist": str(slide.get("gist") or ""),
            "original_content": slide_text.get(slide_id, ""),
            "locked": slide_id in indexes["locked_slides"],
            "section_id": indexes["section_by_slide"].get(slide_id, ""),
        })
    return result


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


def _linked_intake_ids(item: dict) -> dict:
    linked = item.get("linked_intake_ids")
    if isinstance(linked, dict):
        return linked
    related = (
        item.get("related_claims")
        or item.get("linked_claims")
        or item.get("linked_claim_ids")
        or item.get("claim_ids")
    )
    claim_ids = _strings(related)
    concept_ids = _strings(
        item.get("related_concepts") or item.get("linked_concepts") or item.get("linked_concept_ids")
        or item.get("concept_ids")
    )
    result: dict[str, list[str]] = {}
    if claim_ids:
        result["claim_ids"] = claim_ids
    if concept_ids:
        result["concept_ids"] = concept_ids
    return result


def _first_present(item: dict, keys: tuple[str, ...]) -> object:
    for key in keys:
        value = item.get(key)
        if value not in (None, "", []):
            return value
    return None


def _market_case_items(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("market_case_findings", "findings", "cases", "items"):
        items = payload.get(key)
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return [payload]


def _recommendation_source_ids(item: dict) -> list[str]:
    ids = _source_ids(item.get("source_refs") or item.get("sources"))
    for ref in _as_list(item.get("literature_refs")):
        if isinstance(ref, dict):
            value = ref.get("source_id") or ref.get("evidence_ref") or ref.get("doi") or ref.get("title")
        else:
            value = ref
        if value:
            ids.append(str(value))
    ids.extend(_strings(item.get("web_case_refs")))
    return _dedupe_in_order(ids)


def _extract_additive_candidates(research: dict, *, base=None) -> list[dict]:
    """Normalize additive G02 hints into local G03 candidate cards.

    These hints are intentionally non-blocking and never become required slide updates here. They
    give the blueprint a visible audit trail so later G03 stages can decide whether to add slides.

    Reads from the candidate top level (official ``solution_input_candidate@1`` path) and, when the
    research side is the gated ``user_approved_research_bundle@1``, from its ``solution_handoff`` —
    that is where the approved bundle carries ``recommended_claims`` and the market-case findings.
    """
    candidates: list[dict] = []
    handoff = research.get("solution_handoff") if isinstance(research.get("solution_handoff"), dict) else {}

    def _pick(key: str):
        value = research.get(key)
        if value not in (None, [], ""):
            return value
        return handoff.get(key)

    for index, item in enumerate(_as_list(_pick("recommended_claims")), start=1):
        if not isinstance(item, dict):
            continue
        candidate_id = str(
            _first_present(item, ("recommendation_id", "claim_id", "finding_id", "id"))
            or f"recommended_claim_{index:03d}"
        )
        finding = str(
            _first_present(item, ("claim", "finding", "summary", "text", "title"))
            or "Recommended claim."
        )
        rationale = str(
            _first_present(item, ("why_interesting", "rationale", "reason", "note", "teaching_role")) or ""
        )
        candidates.append({
            "candidate_id": candidate_id,
            "kind": "recommended_claim",
            "finding": finding,
            "rationale": rationale,
            "support_basis": (str(item.get("support_basis")).strip() or None) if item.get("support_basis") else None,
            "web_case_facts": [f for f in _as_list(item.get("web_case_facts")) if isinstance(f, dict)],
            "linked_intake_ids": _linked_intake_ids(item),
            "source_refs": _recommendation_source_ids(item),
            "evidence_basis": [f"recommended_claim:{candidate_id}"],
            "source_pointer": f"#/recommended_claims/{index - 1}",
        })

    inline_cases = _as_list(_pick("market_case_findings"))
    case_sources: list[tuple[str, list[dict]]] = []
    if inline_cases:
        case_sources.append(("#/market_case_findings", [item for item in inline_cases if isinstance(item, dict)]))

    ref = _pick("market_case_findings_ref")
    if isinstance(ref, str) and ref.startswith(artifacts.SCHEME):
        try:
            case_sources.append((ref, _market_case_items(artifacts.hydrate(ref, base=base))))
        except Exception:
            candidates.append({
                "candidate_id": "market_case_findings_ref_unavailable",
                "kind": "market_case_ref_unavailable",
                "finding": f"Market case findings ref could not be hydrated: {ref}",
                "rationale": "The additive market-case ref is optional and did not block G03.",
                "linked_intake_ids": {},
                "source_refs": [],
                "evidence_basis": ["market_case_ref:unavailable"],
                "source_pointer": ref,
            })

    case_counter = 0
    for source_pointer, items in case_sources:
        for source_index, item in enumerate(items):
            case_counter += 1
            candidate_id = str(
                _first_present(item, ("case_id", "finding_id", "item_id", "id", "source_id"))
                or f"market_case_{case_counter:03d}"
            )
            finding = str(
                _first_present(item, ("finding", "summary", "case_summary", "claim", "text", "title"))
                or "Market case finding."
            )
            rationale = str(_first_present(item, ("rationale", "implication", "teaching_value", "note"))
                            or item.get("why_interesting") or "")
            # Build a self-contained fact card so the market example reaches the prompt as content,
            # not just a source ID — covering handoffs that carry only the findings ref.
            fact = {
                "case_id": candidate_id,
                "title": str(item.get("title") or finding),
                "institution_or_event": item.get("institution_or_event"),
                "event_date": item.get("event_date"),
                "what_happened": str(item.get("what_happened") or finding),
                "why_interesting": str(item.get("why_interesting") or ""),
                "source_url": str(item.get("source_url") or ""),
                "source_title": str(item.get("source_title") or ""),
            }
            candidates.append({
                "candidate_id": candidate_id,
                "kind": "market_case",
                "finding": finding,
                "rationale": rationale,
                "web_case_facts": [fact],
                "linked_intake_ids": _linked_intake_ids(item),
                "source_refs": _source_ids(item.get("source_refs") or item.get("sources"))
                or ([str(item.get("source_url"))] if item.get("source_url") else []),
                "evidence_basis": [f"market_case:{candidate_id}"],
                "source_pointer": (
                    f"{source_pointer}/{source_index}" if source_pointer.startswith("#") else source_pointer
                ),
            })

    return candidates


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


def _candidate_blueprint(
    context: dict,
    indexes: dict,
    *,
    base=None,
) -> tuple[list[dict], list[dict], dict[str, list[str]]]:
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

    for candidate in _extract_additive_candidates(research, base=base):
        linked = candidate.get("linked_intake_ids") if isinstance(candidate.get("linked_intake_ids"), dict) else {}
        label = "Recommended additive claim"
        if candidate.get("kind") == "market_case":
            label = "Market case finding"
        elif candidate.get("kind") == "market_case_ref_unavailable":
            label = "Market case findings ref"
        reason_parts = [f"{label} not applied automatically: {candidate.get('finding') or ''}".strip()]
        if candidate.get("rationale"):
            reason_parts.append(f"Rationale: {candidate['rationale']}")
        if candidate.get("source_pointer"):
            reason_parts.append(f"Source: {candidate['source_pointer']}")
        deferred.append(_deferred(
            candidate.get("candidate_id"),
            " ".join(reason_parts),
            _first_string(linked.get("claim_ids")),
        ))
    return applied, deferred, source_usage


def _legacy_blueprint(context: dict, indexes: dict, *, base=None) -> tuple[list[dict], list[dict], dict[str, list[str]]]:
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
    for candidate in _extract_additive_candidates(research, base=base):
        linked = candidate.get("linked_intake_ids") if isinstance(candidate.get("linked_intake_ids"), dict) else {}
        label = "Market case finding" if candidate.get("kind") == "market_case" else "Recommended additive claim"
        reason = f"{label} not applied automatically: {candidate.get('finding') or ''}".strip()
        if candidate.get("rationale"):
            reason += f" Rationale: {candidate['rationale']}"
        deferred.append(_deferred(
            candidate.get("candidate_id"),
            reason,
            _first_string(linked.get("claim_ids")),
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
    slide_text = _slide_views_text(lecture, base=base)
    if context["research_bundle_kind"] == CANDIDATE_KIND:
        applied, deferred, source_usage = _candidate_blueprint(context, indexes, base=base)
    else:
        applied, deferred, source_usage = _legacy_blueprint(context, indexes, base=base)

    blueprint = {
        "schema_version": OUTPUT_CONTRACT,
        "task_id": composite["task_id"],
        "output_language": composite.get("output_language") or lecture.get("output_language") or "English",
        "lecture_outline": _outline(lecture, indexes),
        "source_slides": _source_slides(indexes, slide_text),
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
