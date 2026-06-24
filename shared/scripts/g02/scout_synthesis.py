"""Scout-fast A09 handoff from A07 light reviews to Graph03 input.

This is the Scout-specific A09 path. It consumes ``scout_a07_reviews@1`` and
emits a complete ``solution_input_candidate@1`` for Graph03. It does not use the
legacy Human Research Gate. Optional deep-dive access is limited to five source
work items and reuses A07's bounded PDF window selector for at most twelve
windows per source. Full-document reading stays forbidden and research work is
never delegated to Graph03.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import artifacts, contracts  # noqa: E402
from g02 import scout_a07_bridge  # noqa: E402


SCOUT_A07_REVIEWS_CONTRACT = "scout_a07_reviews@1"
SOLUTION_CONTRACT = "solution_input_candidate@1"
RESEARCH_GRAPH_INPUT_CONTRACT = "research_graph_input@1"
SYNTHESIS_MODE_SCOUT = "scout_fast"
DEFAULT_MAX_DEEP_DIVE_SOURCES = 5
DEFAULT_MAX_DEEP_DIVE_WINDOWS = 12
DEFAULT_MAX_DEEP_DIVE_CHARS = 1800
SCOUT_A09_MODEL_TASK_CONTRACT = "scout_a09_model_task@1"
# Token-thrifty A09 deep-dive budget: at most 5 sources, 8 windows, ~1200 chars.
A09_DEEP_DIVE_WINDOWS = 8
A09_DEEP_DIVE_CHARS = 1200

CONFIDENCE_RANK = {
    "insufficient_evidence": 0,
    "context_only": 1,
    "needs_human_check": 2,
    "supported_by_reviewed_source": 3,
}
EXTENSION_RANK = {
    "didactic_example": 0,
    "confirms": 1,
    "qualifies": 2,
    "adds_new_angle": 2,
    "contradicts": 3,
    "updates_outdated": 3,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip()) or "unknown"


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{id(value)}.tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    tmp.replace(path)


def _load_json_or_ref(value: str | Path | dict | None, *, contract: str | None = None) -> tuple[dict | None, str | None]:
    if value is None:
        return None, None
    if isinstance(value, dict):
        payload = deepcopy(value)
        ref = None
    else:
        text = str(value)
        if text.startswith(artifacts.SCHEME):
            payload = artifacts.hydrate(text)
            ref = text
        else:
            path = Path(text).expanduser().resolve()
            payload = _read_json(path)
            ref = str(path)
    if contract:
        validation = contracts.validate(payload, contract)
        if not validation["ok"]:
            raise ValueError(f"invalid {contract}: " + "; ".join(validation["errors"]))
    return payload, ref


def _strings(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str) and item.strip()] \
        if isinstance(value, list) else []


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _normalized_finding(value: object) -> str:
    return " ".join(str(value or "").casefold().split())[:120]


def _confidence_rank(value: object) -> int:
    return CONFIDENCE_RANK.get(str(value or "needs_human_check"), 1)


def _extension_rank(value: object) -> int:
    return EXTENSION_RANK.get(str(value or "adds_new_angle"), 1)


def _ref_key(value: object) -> tuple[str, str, str, str]:
    if isinstance(value, dict):
        return (
            str(value.get("source_id") or ""),
            str(value.get("location") or ""),
            str(value.get("quote") or ""),
            "",
        )
    return ("", "", "", json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


def _merge_refs(*groups: object) -> list:
    merged = []
    seen = set()
    for group in groups:
        for item in _as_list(group):
            key = _ref_key(item)
            if key in seen:
                continue
            seen.add(key)
            merged.append(deepcopy(item))
    return merged


def _merge_linked_ids(*groups: object) -> dict:
    merged: dict[str, list] = {}
    for group in groups:
        if not isinstance(group, dict):
            continue
        for key, values in group.items():
            bucket = merged.setdefault(str(key), [])
            for value in _as_list(values):
                if value not in bucket:
                    bucket.append(deepcopy(value))
    return merged


def _dedup_candidates(candidates: list[dict]) -> list[dict]:
    """Merge A07 candidates that carry the same bounded presentation signal."""
    ordered_keys = []
    merged: dict[tuple[str, str, str], dict] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        key = (
            str(candidate.get("topic_id") or ""),
            str(candidate.get("source_id") or ""),
            _normalized_finding(candidate.get("finding")),
        )
        if key not in merged:
            ordered_keys.append(key)
            merged[key] = deepcopy(candidate)
            continue
        current = merged[key]
        winner = candidate if _confidence_rank(candidate.get("confidence")) \
            > _confidence_rank(current.get("confidence")) else current
        combined = deepcopy(winner)
        combined["evidence_refs"] = _merge_refs(
            current.get("evidence_refs"), candidate.get("evidence_refs")
        )
        combined["source_refs"] = _merge_refs(
            current.get("source_refs"), candidate.get("source_refs")
        )
        combined["linked_intake_ids"] = _merge_linked_ids(
            current.get("linked_intake_ids"), candidate.get("linked_intake_ids")
        )
        merged[key] = combined
    return [merged[key] for key in ordered_keys]


def _group_key(update: dict) -> tuple[str, tuple[str, ...]]:
    target = update.get("target") if isinstance(update.get("target"), dict) else {}
    slides = _as_list(target.get("affected_slides")) or _as_list(target.get("slide_ids"))
    if slides:
        return "0_slide", tuple(sorted(str(value) for value in slides))
    linked = update.get("linked_intake_ids") \
        if isinstance(update.get("linked_intake_ids"), dict) else {}
    flow_ids = _as_list(linked.get("flow_issue_ids"))
    if flow_ids:
        return "1_flow", tuple(sorted(str(value) for value in flow_ids))
    claim_ids = _as_list(linked.get("claim_ids"))
    if claim_ids:
        return "2_claim", tuple(sorted(str(value) for value in claim_ids))
    return "3_topic", (str(update.get("topic_id") or ""),)


def _group_updates(updates: list[dict]) -> list[dict]:
    """Keep updates for the same slide/flow/claim/topic adjacent and stable."""
    indexed = [(index, deepcopy(update)) for index, update in enumerate(updates)
               if isinstance(update, dict)]
    return [item for _, item in sorted(indexed, key=lambda pair: (_group_key(pair[1]), pair[0]))]


def _update_priority(update: dict) -> tuple[int, int, int]:
    confidence = _confidence_rank(update.get("confidence"))
    relation = _extension_rank(update.get("extension_relation"))
    return confidence * 10 + relation, confidence, relation


def _rank_updates(updates: list[dict]) -> tuple[list[dict], list[dict]]:
    """Separate weak updates and order both sets by deterministic evidence priority."""
    primary = []
    optional = []
    for index, update in enumerate(updates):
        if not isinstance(update, dict):
            continue
        evidence = _as_list(update.get("evidence")) or _as_list(update.get("evidence_refs"))
        ranked = (index, deepcopy(update))
        if str(update.get("confidence") or "") == "insufficient_evidence" or not evidence:
            optional.append(ranked)
        else:
            primary.append(ranked)
    order = lambda pair: (-_update_priority(pair[1])[0], pair[0])
    return (
        [item for _, item in sorted(primary, key=order)],
        [item for _, item in sorted(optional, key=order)],
    )


def _revision_priorities(updates: list[dict]) -> list[dict]:
    ranked = []
    for index, update in enumerate(updates):
        score, confidence, relation = _update_priority(update)
        ranked.append((score, index, {
            "update_id": update.get("update_id"),
            "priority_score": score,
            "reason": (
                f"confidence={update.get('confidence') or 'context_only'} ({confidence}); "
                f"extension_relation={update.get('extension_relation') or 'adds_new_angle'} "
                f"({relation})"
            ),
        }))
    return [item for _, _, item in sorted(ranked, key=lambda value: (-value[0], value[1]))]


def _resolve_plan_ref(reviews: dict) -> str:
    """Build a traceable reference to the A01 plan used by this Scout run.

    The reviews artifact stores ``plan_ref`` relative to the Scout run dir plus
    the absolute ``scout_run_ref``. Join them so the G03 handoff points at the
    real plan.json instead of a bare relative name.
    """
    plan_ref = reviews.get("plan_ref") or "plan.json"
    run_ref = reviews.get("scout_run_ref")
    if isinstance(plan_ref, str) and plan_ref.startswith(artifacts.SCHEME):
        return plan_ref
    if isinstance(run_ref, str) and run_ref and isinstance(plan_ref, str):
        return f"{run_ref.rstrip('/')}/{plan_ref}"
    return plan_ref


def _confidence_from_candidates(candidates: list[dict], gaps: list[dict]) -> str:
    if not candidates:
        return "low"
    labels = {str(item.get("confidence") or "") for item in candidates}
    if "supported_by_reviewed_source" in labels and len(candidates) >= 2 and not gaps:
        return "high"
    return "medium"


def _presentation_context(intake: dict | None, reviews: dict, output_language: str | None = None) -> dict:
    if not isinstance(intake, dict):
        return {
            "course_name": None,
            "audience_level": None,
            "target_duration_minutes": None,
            "teaching_goal": None,
            "output_language": output_language,
            "locked_sections": [],
        }
    context = intake.get("user_approved_context")
    context = context if isinstance(context, dict) else {}
    return {
        "course_name": context.get("course_name"),
        "audience_level": context.get("audience_level"),
        "target_duration_minutes": context.get("target_duration_minutes"),
        "teaching_goal": context.get("teaching_goal"),
        "output_language": intake.get("output_language") or output_language,
        "locked_sections": deepcopy(intake.get("locked_sections", [])),
    }


def _linked_intake_ids(reviews: dict) -> dict[str, set[str]]:
    collected = {
        "driver_ids": set(),
        "claim_ids": set(),
        "concept_ids": set(),
        "flow_issue_ids": set(),
        "update_need_ids": set(),
    }
    groups = [
        reviews.get("topic_reviews", []),
        reviews.get("presentation_update_candidates", []),
        reviews.get("lookup_pointers", []),
        reviews.get("coverage_gaps", []),
    ]
    for group in groups:
        for item in _as_list(group):
            if not isinstance(item, dict):
                continue
            linked = item.get("linked_intake_ids") \
                if isinstance(item.get("linked_intake_ids"), dict) else {}
            for key in collected:
                collected[key].update(str(value) for value in _as_list(linked.get(key)) if value)
    return collected


def _compact_intake_context(intake: dict | None, reviews: dict) -> dict:
    """Keep only intake cards referenced by the Scout/A07 handoff."""
    if not isinstance(intake, dict):
        return {
            "available": False,
            "research_drivers": [],
            "claim_cards": [],
            "concept_context_cards": [],
            "selected_flow_issue_cards": [],
            "selected_update_need_cards": [],
            "locked_sections": [],
            "output_language": None,
        }
    linked = _linked_intake_ids(reviews)

    def selected(field: str, id_field: str, linked_key: str) -> list[dict]:
        allowed = linked[linked_key]
        return [
            deepcopy(item) for item in _as_list(intake.get(field))
            if isinstance(item, dict) and str(item.get(id_field) or "") in allowed
        ]

    return {
        "available": True,
        "research_drivers": selected("research_drivers", "driver_id", "driver_ids"),
        "claim_cards": selected("claim_cards", "claim_id", "claim_ids"),
        "concept_context_cards": selected(
            "concept_context_cards", "concept_id", "concept_ids"
        ),
        "selected_flow_issue_cards": selected(
            "selected_flow_issue_cards", "issue_id", "flow_issue_ids"
        ),
        "selected_update_need_cards": selected(
            "selected_update_need_cards", "update_need_id", "update_need_ids"
        ),
        "locked_sections": deepcopy(intake.get("locked_sections", [])),
        "output_language": intake.get("output_language"),
    }


def _topics_covered(reviews: dict) -> list[dict]:
    topics = []
    for item in reviews.get("topic_reviews", []):
        if not isinstance(item, dict):
            continue
        linked = item.get("linked_intake_ids") if isinstance(item.get("linked_intake_ids"), dict) else {}
        counts = item.get("counts") if isinstance(item.get("counts"), dict) else {}
        topics.append({
            "topic_id": item.get("topic_id"),
            "name": item.get("name"),
            "linked_claims": deepcopy(linked.get("claim_ids", [])),
            "linked_concepts": deepcopy(linked.get("concept_ids", [])),
            "linked_flow_issues": deepcopy(linked.get("flow_issue_ids", [])),
            "linked_update_needs": deepcopy(linked.get("update_need_ids", [])),
            "source_count": counts.get("review_candidate_count", 0) + counts.get("context_only_count", 0),
            "coverage_note": item.get("status") or "unknown",
        })
    return topics


def _source_refs_from_reviews(reviews: dict) -> list[dict]:
    seen: set[str] = set()
    refs = []
    for review in reviews.get("source_reviews", []):
        if not isinstance(review, dict):
            continue
        source_id = review.get("source_id")
        if not isinstance(source_id, str) or source_id in seen:
            continue
        seen.add(source_id)
        refs.append({
            "source_id": source_id,
            "title": review.get("title"),
            "doi": review.get("doi"),
            "year": review.get("year"),
            "venue": review.get("venue"),
            "source_type": review.get("source_type"),
            "a07_review_status": review.get("a07_review_status")
            or review.get("prefilter_status"),
        })
    return refs


def _source_review_map(reviews: dict) -> dict[str, dict]:
    return {
        str(item.get("source_id")): item
        for item in reviews.get("source_reviews", [])
        if isinstance(item, dict) and item.get("source_id")
    }


def _plan_topic_priorities(reviews: dict) -> dict[str, str]:
    run_ref = reviews.get("scout_run_ref")
    if not isinstance(run_ref, str) or not run_ref or run_ref.startswith(artifacts.SCHEME):
        return {}
    try:
        plan = _read_json(Path(run_ref).expanduser().resolve() / "plan.json")
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return {
        str(topic.get("topic_id")): str(topic.get("priority") or "")
        for topic in plan.get("topics", [])
        if isinstance(topic, dict) and topic.get("topic_id")
    }


def _deep_dive_signal(pointer: dict, reviews: dict, topic_priorities: dict[str, str]) \
        -> tuple[int, int, int, str]:
    topic_id = str(pointer.get("topic_id") or "")
    source_id = str(pointer.get("source_id") or "")
    related = [
        candidate for candidate in reviews.get("presentation_update_candidates", [])
        if isinstance(candidate, dict)
        and str(candidate.get("topic_id") or "") == topic_id
        and str(candidate.get("source_id") or "") == source_id
    ]
    best_confidence = max(
        [_confidence_rank(pointer.get("confidence")),
         *[_confidence_rank(item.get("confidence")) for item in related]],
        default=_confidence_rank(None),
    )
    best_relation = max(
        [_extension_rank(item.get("extension_relation") or item.get("update_kind"))
         for item in related],
        default=_extension_rank(pointer.get("extension_relation")),
    )
    relations = {
        str(item.get("extension_relation") or item.get("update_kind") or "")
        for item in related
    }
    if best_confidence == 3 and relations.intersection({"contradicts", "updates_outdated"}):
        return 0, best_confidence, best_relation, "high_slide_change_potential"
    if pointer.get("conflicting_findings") or pointer.get("conflict") \
            or "contradicts" in relations:
        return 1, best_confidence, best_relation, "conflicting_findings"
    linked = pointer.get("linked_intake_ids") \
        if isinstance(pointer.get("linked_intake_ids"), dict) else {}
    confidence = str(pointer.get("confidence") or "needs_human_check")
    if _as_list(linked.get("claim_ids")) \
            and topic_priorities.get(topic_id) in {"high", "critical"} \
            and confidence in {"needs_human_check", "insufficient_evidence"}:
        return 2, best_confidence, best_relation, "high_priority_claim_without_certain_evidence"
    source_review = _source_review_map(reviews).get(source_id, {})
    source_type = str(pointer.get("source_type") or source_review.get("source_type") or "")
    if source_type == "canonical":
        return 3, best_confidence, best_relation, "canonical_source"
    if source_type in {"recent", "current"} and best_confidence >= 2:
        return 4, best_confidence, best_relation, "high_value_recent_source"
    return 5, best_confidence, best_relation, "unresolved_lookup_pointer"


def _select_deep_dive_requests(
    reviews: dict,
    *,
    max_sources: int = DEFAULT_MAX_DEEP_DIVE_SOURCES,
) -> list[dict]:
    if max_sources <= 0:
        return []
    topic_priorities = _plan_topic_priorities(reviews)
    ranked = []
    for index, pointer in enumerate(reviews.get("lookup_pointers", [])):
        if not isinstance(pointer, dict) or not pointer.get("source_id"):
            continue
        criterion, confidence, relation, label = _deep_dive_signal(
            pointer, reviews, topic_priorities
        )
        ranked.append((
            criterion,
            -confidence,
            -relation,
            str(pointer.get("topic_id") or ""),
            str(pointer.get("source_id") or ""),
            str(pointer.get("pointer_id") or f"pointer_{index:04d}"),
            index,
            pointer,
            label,
        ))
    selected = []
    seen_sources: set[str] = set()
    for item in sorted(ranked, key=lambda value: value[:7]):
        pointer = item[7]
        label = item[8]
        source_id = str(pointer.get("source_id"))
        if source_id in seen_sources:
            continue
        seen_sources.add(source_id)
        where = pointer.get("where_to_look") \
            if isinstance(pointer.get("where_to_look"), dict) else {}
        pointer_id = str(pointer.get("pointer_id") or f"A07_PTR_{item[6] + 1:04d}")
        selected.append({
            "deep_dive_id": f"A09_DD_{len(selected) + 1:02d}",
            "pointer_id": pointer_id,
            "topic_id": pointer.get("topic_id"),
            "source_id": source_id,
            "selection_criterion": label,
            "reason": f"{label}: {pointer.get('why_relevant') or 'bounded follow-up required'}",
            "work_input_ref": where.get("work_input_ref"),
            "where_to_look": deepcopy(where),
            "linked_intake_ids": deepcopy(pointer.get("linked_intake_ids", {})),
            "confidence": pointer.get("confidence") or "needs_human_check",
            "max_additional_windows": DEFAULT_MAX_DEEP_DIVE_WINDOWS,
        })
        if len(selected) >= max_sources:
            break
    return selected


def gather_deep_dive_windows(
    reviews: dict,
    requests: list[dict],
    *,
    max_windows: int = DEFAULT_MAX_DEEP_DIVE_WINDOWS,
    max_chars: int = DEFAULT_MAX_DEEP_DIVE_CHARS,
) -> dict:
    """Attach expanded bounded PDF windows to selected A09 deep-dive requests."""
    if max_windows < 1 or max_windows > DEFAULT_MAX_DEEP_DIVE_WINDOWS:
        raise ValueError("deep dive max_windows must be between 1 and 12")
    if max_chars < 1:
        raise ValueError("deep dive max_chars must be positive")
    package_requests = []
    package_limitations = []
    loaded = None
    lenses = {}
    try:
        run_ref = reviews.get("scout_run_ref")
        if not isinstance(run_ref, str) or not run_ref:
            raise ValueError("scout_run_ref is missing")
        loaded = scout_a07_bridge._load_scout_run(run_ref)
        lenses = scout_a07_bridge._topic_lenses(loaded["plan"], loaded["requests"])
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        package_limitations.append(f"deep_dive_run_unavailable: {exc}")

    for request in requests:
        if not isinstance(request, dict):
            continue
        enriched = deepcopy(request)
        windows = []
        limitations = []
        topic_id = str(request.get("topic_id") or "")
        source_id = str(request.get("source_id") or "")
        if loaded is None:
            limitations.extend(package_limitations)
        else:
            corpus = loaded["corpora"].get(topic_id)
            lens = lenses.get(topic_id)
            document = next((
                item for item in (corpus or {}).get("documents", [])
                if isinstance(item, dict) and str(item.get("source_id") or "") == source_id
            ), None)
            if not isinstance(corpus, dict):
                limitations.append("deep_dive_corpus_missing")
            elif not isinstance(document, dict):
                limitations.append("deep_dive_source_missing_from_corpus")
            elif not isinstance(lens, dict):
                limitations.append("deep_dive_topic_lens_missing")
            else:
                try:
                    windows, issues = scout_a07_bridge.select_pdf_windows(
                        loaded["root"], document, lens,
                        max_windows=max_windows,
                        max_chars=max_chars,
                    )
                    limitations.extend(str(issue) for issue in issues)
                except (OSError, ValueError, KeyError) as exc:
                    limitations.append(f"deep_dive_window_extraction_failed: {exc}")
                    windows = []
        enriched["additional_windows"] = windows[:max_windows]
        enriched["limitations"] = list(dict.fromkeys(limitations))
        enriched["limitation"] = enriched["limitations"][0] if enriched["limitations"] else None
        package_requests.append(enriched)

    package = {
        "schema_version": "scout_a07_deep_dive@1",
        "artifact_version": "1.0.0",
        "task_id": str(reviews.get("task_id") or ""),
        "scout_run_ref": str(reviews.get("scout_run_ref") or ""),
        "max_windows_per_source": max_windows,
        "max_chars_per_window": max_chars,
        "requests": package_requests,
        "limitations": package_limitations,
    }
    validation = contracts.validate(package, "scout_a07_deep_dive@1")
    if not validation["ok"]:
        raise ValueError("invalid scout_a07_deep_dive@1: " + "; ".join(validation["errors"]))
    return package


def _ready_update(candidate: dict, index: int) -> dict:
    update_id = candidate.get("update_id") or candidate.get("candidate_id") \
        or f"G02_UPD_{index:03d}"
    target = candidate.get("presentation_target") or candidate.get("target")
    target = deepcopy(target) if isinstance(target, dict) else {}
    affected_slides = _as_list(target.get("affected_slides")) \
        or _as_list(candidate.get("affected_slides")) \
        or _as_list(target.get("slide_ids"))
    target["affected_slides"] = deepcopy(affected_slides)
    target["slide_ids"] = deepcopy(_as_list(target.get("slide_ids")) or affected_slides)
    target.setdefault(
        "section_hint",
        candidate.get("section_hint") or target.get("section") or candidate.get("topic_id"),
    )
    target.setdefault("section", target.get("section_hint"))
    target.setdefault("placement", "best_fit_by_graph03")
    finding = str(candidate.get("finding") or "").strip()
    rationale = str(
        candidate.get("rationale_vs_existing_presentation")
        or candidate.get("rationale")
        or ""
    ).strip()
    draft_insert = candidate.get("draft_insert") or candidate.get("ready_to_apply_text")
    if isinstance(draft_insert, dict):
        ready_text = deepcopy(draft_insert)
        ready_text.setdefault("slide_bullet", finding)
        ready_text.setdefault("speaker_note", rationale)
        ready_text.setdefault("optional_detail", "")
    else:
        ready_text = {
            "slide_bullet": str(draft_insert or finding).strip(),
            "speaker_note": rationale,
            "optional_detail": "",
        }
    ready_text = {
        "slide_bullet": str(ready_text.get("slide_bullet") or ""),
        "speaker_note": str(ready_text.get("speaker_note") or ""),
        "optional_detail": str(ready_text.get("optional_detail") or ""),
    }
    return {
        "update_id": update_id,
        "pointer_id": candidate.get("pointer_id"),
        "deep_dive_id": candidate.get("deep_dive_id"),
        "source_id": candidate.get("source_id"),
        "target": target,
        "action": candidate.get("suggested_slide_action") or "add_or_refine_content",
        "ready_to_apply_text": ready_text,
        "topic_id": candidate.get("topic_id"),
        "linked_intake_ids": deepcopy(candidate.get("linked_intake_ids", {})),
        "extension_relation": candidate.get("extension_relation")
        or candidate.get("update_kind")
        or "adds_new_angle",
        "finding": finding,
        "rationale": rationale,
        "evidence": deepcopy(candidate.get("evidence_refs") or candidate.get("evidence") or []),
        "source_refs": deepcopy(candidate.get("source_refs", [])),
        "confidence": candidate.get("confidence") or "needs_human_check",
        "source_type": candidate.get("source_type"),
    }


def prepare_scout_fast_synthesis(
    scout_a07_reviews: str | Path | dict,
    *,
    intake: str | Path | dict | None = None,
    max_deep_dive_sources: int = DEFAULT_MAX_DEEP_DIVE_SOURCES,
) -> dict:
    reviews, reviews_ref = _load_json_or_ref(
        scout_a07_reviews, contract=SCOUT_A07_REVIEWS_CONTRACT
    )
    assert reviews is not None
    intake_payload, intake_ref = _load_json_or_ref(
        intake, contract=RESEARCH_GRAPH_INPUT_CONTRACT
    ) if intake is not None else (None, reviews.get("intake_ref"))
    if max_deep_dive_sources > DEFAULT_MAX_DEEP_DIVE_SOURCES:
        raise ValueError("A09 scout_fast deep dive budget cannot exceed 5 sources")
    deep_dive = _select_deep_dive_requests(
        reviews, max_sources=max_deep_dive_sources
    )
    synthesis_input = {
        "schema_version": "research_scout_synthesis_input@1",
        "task_id": reviews["task_id"],
        "synthesis_mode": SYNTHESIS_MODE_SCOUT,
        "scout_a07_reviews_ref": reviews_ref or "inline",
        "scout_run_ref": reviews.get("scout_run_ref"),
        "plan_ref": _resolve_plan_ref(reviews),
        "intake_ref": intake_ref,
        "reviews": deepcopy(reviews),
        "presentation_context": _presentation_context(
            intake_payload, reviews, output_language=None
        ),
        "intake_context": _compact_intake_context(intake_payload, reviews),
        "deep_dive_budget": {
            "max_sources": max_deep_dive_sources,
            "selected_count": len(deep_dive),
            "full_pdf_forbidden": True,
        },
        "deep_dive_requests": deep_dive,
        "rules": [
            "A09 may use A07 candidates and at most the listed deep-dive work items.",
            "A09 must return complete slide-update instructions for Graph03.",
            "Graph03 must not be asked to perform further research.",
            "Full PDFs and full extracted text are forbidden in the final handoff.",
        ],
    }
    return {"ready": True, "synthesis_input": synthesis_input}


def _pointer_id(pointer: dict, index: int) -> str:
    return str(pointer.get("pointer_id") or f"A07_PTR_{index:04d}")


def _pointer_lookup(reviews: dict) -> dict[str, dict]:
    return {
        _pointer_id(pointer, index): pointer
        for index, pointer in enumerate(reviews.get("lookup_pointers", []), start=1)
        if isinstance(pointer, dict)
    }


def _where_to_look_text(pointer: dict) -> str:
    where = pointer.get("where_to_look") \
        if isinstance(pointer.get("where_to_look"), dict) else {}
    parts = []
    terms = _strings(where.get("matched_terms"))
    pages = _as_list(where.get("pages"))
    if terms:
        parts.append("matched terms: " + ", ".join(terms))
    if pages:
        parts.append("pages: " + ", ".join(str(page) for page in pages))
    if where.get("work_input_ref"):
        parts.append("work item: " + str(where["work_input_ref"]))
    return "; ".join(parts) or "Inspect the source under the original topic lens."


def _deep_dive_candidates(
    reviews: dict,
    deep_dive: dict | None,
) -> tuple[list[dict], list[dict], set[str], list[dict]]:
    if not isinstance(deep_dive, dict):
        return [], [], set(), []
    validation = contracts.validate(deep_dive, "scout_a07_deep_dive@1")
    if not validation["ok"]:
        raise ValueError("invalid scout_a07_deep_dive@1: " + "; ".join(validation["errors"]))
    pointers = _pointer_lookup(reviews)
    sources = _source_review_map(reviews)
    candidates = []
    gaps = []
    consumed: set[str] = set()
    audit = []
    for request_index, request in enumerate(deep_dive.get("requests", []), start=1):
        if not isinstance(request, dict):
            continue
        pointer_id = str(request.get("pointer_id") or "")
        pointer = pointers.get(pointer_id, {})
        windows = [
            window for window in request.get("additional_windows", [])
            if isinstance(window, dict)
        ]
        matching = [
            window for window in windows
            if _strings(window.get("matched_terms")) and str(window.get("text") or "").strip()
        ]
        limitations = _strings(request.get("limitations"))
        status = "recommendation_created" if matching else (
            "unavailable" if limitations else "no_matching_signal"
        )
        audit.append({
            "deep_dive_id": request.get("deep_dive_id"),
            "pointer_id": pointer_id,
            "topic_id": request.get("topic_id"),
            "source_id": request.get("source_id"),
            "selection_criterion": request.get("selection_criterion"),
            "window_count": len(windows),
            "matching_window_count": len(matching),
            "status": status,
            "limitations": limitations,
        })
        if not matching:
            gaps.append({
                "gap_id": f"A09_DD_GAP_{request_index:02d}",
                "pointer_id": pointer_id,
                "topic_id": request.get("topic_id"),
                "source_id": request.get("source_id"),
                "gap_type": "deep_dive_unavailable" if limitations
                else "deep_dive_no_matching_signal",
                "linked_intake_ids": deepcopy(
                    pointer.get("linked_intake_ids")
                    or request.get("linked_intake_ids")
                    or {}
                ),
                "note": "; ".join(limitations) if limitations else (
                    "The bounded deep dive found no window with a topic-lens term match."
                ),
            })
            continue
        window = matching[0]
        source_id = str(request.get("source_id") or pointer.get("source_id") or "")
        source = sources.get(source_id, {})
        why_relevant = str(
            pointer.get("why_relevant") or request.get("reason")
            or "The source adds a topic-lens clarification."
        ).strip()
        matched_terms = _strings(window.get("matched_terms"))
        excerpt = str(window.get("text") or "").strip()[:500]
        page = window.get("page")
        location = f"deep-dive window {window.get('window_id') or 'unknown'}"
        if page is not None:
            location += f", page {page}"
        candidates.append({
            "candidate_id": f"A09_DD_UPD_{request_index:02d}",
            "pointer_id": pointer_id,
            "deep_dive_id": request.get("deep_dive_id"),
            "topic_id": request.get("topic_id"),
            "source_id": source_id,
            "linked_intake_ids": deepcopy(
                pointer.get("linked_intake_ids")
                or request.get("linked_intake_ids")
                or {}
            ),
            "presentation_target": {
                "affected_slides": [],
                "section_hint": request.get("topic_id"),
                "placement": "best_fit_by_graph03",
            },
            "extension_relation": "adds_new_angle",
            "finding": why_relevant,
            "rationale_vs_existing_presentation": (
                "A bounded A09 deep dive found a targeted window matching: "
                + ", ".join(matched_terms)
            ),
            "suggested_slide_action": "add_or_refine_content",
            "draft_insert": {
                "slide_bullet": why_relevant,
                "speaker_note": excerpt,
                "optional_detail": "Matched terms: " + ", ".join(matched_terms),
            },
            "evidence_refs": [{
                "source_id": source_id,
                "location": location,
                "quote": excerpt,
            }],
            "source_refs": [{
                "source_id": source_id,
                "title": source.get("title"),
                "doi": source.get("doi"),
                "year": source.get("year"),
                "venue": source.get("venue"),
                "source_type": source.get("source_type"),
            }],
            "confidence": pointer.get("confidence") or "needs_human_check",
            "source_type": source.get("source_type"),
        })
        consumed.add(pointer_id)
    return candidates, gaps, consumed, audit


def _pointer_unresolved_item(pointer: dict, index: int, deep_dive_gaps: dict[str, dict]) -> dict:
    pointer_id = _pointer_id(pointer, index)
    gap = deep_dive_gaps.get(pointer_id)
    resolution = _where_to_look_text(pointer)
    if gap and gap.get("note"):
        resolution = f"{resolution}; deep-dive result: {gap['note']}"
    return {
        "question": pointer.get("why_relevant") or "Follow up the bounded A07 lookup pointer.",
        "topic_id": pointer.get("topic_id"),
        "linked_intake_ids": deepcopy(pointer.get("linked_intake_ids", {})),
        "why_unresolved": "lookup_pointer_not_resolved",
        "what_would_resolve": resolution,
    }


def validate_scout_a09_output(output: object | None) -> dict | None:
    """Validate the minimum raw model output before it can be marked as an A09 pass."""
    if output is None or output == {}:
        return None
    if not isinstance(output, dict):
        raise ValueError("A09 output must be a JSON object")
    required = {
        "slide_update_plan", "slide_revision_priorities",
        "optional_improvements", "unresolved_items", "confidence",
    }
    missing = sorted(required.difference(output))
    if missing:
        raise ValueError("A09 output missing: " + ", ".join(missing))
    for field in required.difference({"confidence"}):
        if not isinstance(output.get(field), list):
            raise ValueError(f"A09 output field {field} must be an array")
    if output.get("confidence") not in {"low", "medium", "high"}:
        raise ValueError("A09 output confidence must be low, medium or high")
    return output


def finalize_scout_fast_solution(
    synthesis_input: dict,
    output: object | None = None,
    *,
    deep_dive: dict | None = None,
    artifact_version: str = "1.0.0",
    output_path: str | Path | None = None,
) -> dict:
    """Finalize complete A09 Scout handoff for Graph03."""
    if not isinstance(synthesis_input, dict) \
            or synthesis_input.get("schema_version") != "research_scout_synthesis_input@1":
        raise ValueError("research_scout_synthesis_input@1 is required")
    validated_output = validate_scout_a09_output(output)
    model_output = validated_output or {}
    reviews = synthesis_input["reviews"]
    deep_dive_candidates, deep_dive_gaps, consumed_pointers, deep_dive_audit = \
        _deep_dive_candidates(reviews, deep_dive)
    a07_candidates = _dedup_candidates([
        item for item in reviews.get("presentation_update_candidates", [])
        if isinstance(item, dict)
    ] + deep_dive_candidates)
    fallback_updates = [
        _ready_update(item, index)
        for index, item in enumerate(a07_candidates, start=1)
    ]
    if isinstance(model_output.get("slide_update_plan"), list):
        base_updates = [
            _ready_update(item, index)
            for index, item in enumerate(model_output["slide_update_plan"], start=1)
            if isinstance(item, dict)
        ]
        existing_pointer_ids = {
            str(item.get("pointer_id")) for item in base_updates if item.get("pointer_id")
        }
        for candidate in deep_dive_candidates:
            if str(candidate.get("pointer_id")) not in existing_pointer_ids:
                base_updates.append(_ready_update(candidate, len(base_updates) + 1))
    else:
        base_updates = fallback_updates
    for update in base_updates:
        if update.get("pointer_id"):
            consumed_pointers.add(str(update["pointer_id"]))
    slide_update_ranked, weak_updates = _rank_updates(base_updates)
    slide_update_plan = _group_updates(slide_update_ranked)
    model_optional = [
        _ready_update(item, index)
        for index, item in enumerate(_as_list(model_output.get("optional_improvements")), start=1)
        if isinstance(item, dict)
    ]
    optional = [*model_optional, *weak_updates]
    suggested_updates = slide_update_plan
    unresolved = deepcopy(model_output.get("unresolved_items")) \
        if isinstance(model_output.get("unresolved_items"), list) else []
    coverage_gaps = [
        deepcopy(gap) for gap in reviews.get("coverage_gaps", []) if isinstance(gap, dict)
    ] + deep_dive_gaps
    for gap in reviews.get("coverage_gaps", []):
        if not isinstance(gap, dict):
            continue
        unresolved.append({
            "question": gap.get("note") or gap.get("gap_type") or "coverage gap",
            "topic_id": gap.get("topic_id"),
            "linked_intake_ids": deepcopy(gap.get("linked_intake_ids", {})),
            "why_unresolved": gap.get("gap_type") or "insufficient_evidence",
            "what_would_resolve": "Run a narrower Scout query or provide a canonical source.",
        })
    deep_dive_gap_map = {
        str(gap.get("pointer_id")): gap
        for gap in deep_dive_gaps if gap.get("pointer_id")
    }
    for item in _as_list(model_output.get("deep_dive_used")):
        if isinstance(item, dict) and item.get("pointer_id") \
                and item.get("status") in {"resolved", "recommendation_created"}:
            consumed_pointers.add(str(item["pointer_id"]))
    for index, pointer in enumerate(reviews.get("lookup_pointers", []), start=1):
        if not isinstance(pointer, dict):
            continue
        if _pointer_id(pointer, index) not in consumed_pointers:
            unresolved.append(_pointer_unresolved_item(pointer, index, deep_dive_gap_map))
    deep_dive_limitations = []
    if isinstance(deep_dive, dict):
        deep_dive_limitations.extend(_strings(deep_dive.get("limitations")))
        for request in deep_dive.get("requests", []):
            if isinstance(request, dict):
                deep_dive_limitations.extend(_strings(request.get("limitations")))
    limitations = list(dict.fromkeys([
        *_strings(reviews.get("limitations")),
        *_strings(model_output.get("limitations")),
        *deep_dive_limitations,
        "A08 claim verification was skipped in scout_fast mode.",
        "A09 did not read full PDFs; it used A07 bounded reviews and optional bounded deep-dive windows.",
    ]))
    source_refs = deepcopy(model_output.get("source_refs")) \
        if isinstance(model_output.get("source_refs"), list) else _source_refs_from_reviews(reviews)
    confidence = model_output.get("confidence")
    if confidence not in {"low", "medium", "high"}:
        confidence = _confidence_from_candidates(a07_candidates, coverage_gaps)
    model_priorities = model_output.get("slide_revision_priorities")
    slide_revision_priorities = deepcopy(model_priorities) \
        if isinstance(model_priorities, list) and model_priorities \
        else _revision_priorities(slide_update_plan)
    deep_dive_used = [
        *deep_dive_audit,
        *[deepcopy(item) for item in _as_list(model_output.get("deep_dive_used"))
          if isinstance(item, dict)],
    ]
    solution = {
        "schema_version": SOLUTION_CONTRACT,
        "artifact_version": artifact_version,
        "task_id": synthesis_input["task_id"],
        "synthesis_mode": SYNTHESIS_MODE_SCOUT,
        "source_pipeline": "intake -> a01 -> scout -> a07 -> a09",
        "intake_ref": synthesis_input.get("intake_ref"),
        "plan_ref": synthesis_input.get("plan_ref") or "plan.json",
        "presentation_context": deepcopy(synthesis_input.get("presentation_context", {})),
        "topics_covered": _topics_covered(reviews),
        "slide_update_plan": slide_update_plan,
        "slide_revision_priorities": slide_revision_priorities,
        "suggested_updates": suggested_updates,
        "optional_improvements": optional,
        "do_not_change": deepcopy(model_output.get("do_not_change", []))
        if isinstance(model_output.get("do_not_change"), list) else [],
        "coverage_gaps": coverage_gaps,
        "evidence_map_ref": f"{synthesis_input.get('scout_a07_reviews_ref', 'inline')}#/presentation_update_candidates",
        "source_refs": source_refs,
        "limitations": limitations,
        "unresolved_items": unresolved,
        "confidence": confidence,
        "claim_assessment_performed": False,
        "a08_status": "skipped_scout_fast",
        "a09_model_pass": bool(validated_output),
        "synthesis_engine": "a09_opus_medium" if bool(validated_output)
        else "deterministic_fallback",
        "graph03_handoff_constraints": {
            "compact": True,
            "no_full_text": True,
            "no_full_pdfs": True,
            "ready_to_apply_updates_required": True,
            "graph03_must_not_call_g02": True,
            "output_language": synthesis_input.get("presentation_context", {}).get("output_language"),
            "locked_sections": deepcopy(
                synthesis_input.get("presentation_context", {}).get("locked_sections", [])
            ),
        },
        "deep_dive_used": deep_dive_used,
        "generated_at": _utc_now(),
    }
    validation = contracts.validate(solution, SOLUTION_CONTRACT)
    if not validation["ok"]:
        raise ValueError("invalid solution_input_candidate@1: " + "; ".join(validation["errors"]))
    if output_path is not None:
        _write_json(Path(output_path).expanduser().resolve(), solution)
    return solution


def _baseline_for_model(synthesis_input: dict, deep_dive: dict | None) -> dict:
    """Run the deterministic A09 finalize so the model can verify/refine it."""
    baseline = finalize_scout_fast_solution(synthesis_input, None, deep_dive=deep_dive)
    return {
        "slide_update_plan": deepcopy(baseline.get("slide_update_plan", [])),
        "slide_revision_priorities": deepcopy(baseline.get("slide_revision_priorities", [])),
        "optional_improvements": deepcopy(baseline.get("optional_improvements", [])),
        "unresolved_items": deepcopy(baseline.get("unresolved_items", [])),
        "coverage_gaps": deepcopy(baseline.get("coverage_gaps", [])),
        "confidence": baseline.get("confidence"),
    }


def build_scout_a09_model_task(
    synthesis_input: dict,
    deep_dive: dict | None = None,
    *,
    artifact_version: str = "1.0.0",
) -> dict:
    """Build the compact host-model task for the obligatory A09 verify/refine pass.

    A09 is a verifier: it receives the deterministic baseline plan plus the A07
    candidates and bounded deep-dive windows, and returns a corrected plan. Full
    PDFs stay forbidden; the deep-dive budget is at most five sources.
    """
    if not isinstance(synthesis_input, dict) \
            or synthesis_input.get("schema_version") != "research_scout_synthesis_input@1":
        raise ValueError("research_scout_synthesis_input@1 is required")
    reviews = synthesis_input["reviews"]
    presentation_context = deepcopy(synthesis_input.get("presentation_context", {}))
    intake_context = deepcopy(synthesis_input.get("intake_context", {}))
    a07_candidates = [
        deepcopy(item) for item in reviews.get("presentation_update_candidates", [])
        if isinstance(item, dict)
    ]
    deep_dive_package = deep_dive if isinstance(deep_dive, dict) else {
        "schema_version": "scout_a07_deep_dive@1",
        "artifact_version": "1.0.0",
        "task_id": str(reviews.get("task_id") or ""),
        "scout_run_ref": str(reviews.get("scout_run_ref") or ""),
        "max_windows_per_source": A09_DEEP_DIVE_WINDOWS,
        "max_chars_per_window": A09_DEEP_DIVE_CHARS,
        "requests": [],
        "limitations": [],
    }
    task = {
        "schema_version": SCOUT_A09_MODEL_TASK_CONTRACT,
        "artifact_version": artifact_version,
        "task_id": synthesis_input["task_id"],
        "synthesis_mode": SYNTHESIS_MODE_SCOUT,
        "scout_a07_reviews_ref": synthesis_input.get("scout_a07_reviews_ref"),
        "plan_ref": synthesis_input.get("plan_ref"),
        "intake_ref": synthesis_input.get("intake_ref"),
        "deterministic_baseline": _baseline_for_model(synthesis_input, deep_dive),
        "a07_candidates": a07_candidates,
        "deep_dive": deep_dive_package,
        "intake_context": {
            **intake_context,
            "available": bool(intake_context.get("available")),
            "intake_ref": synthesis_input.get("intake_ref"),
        },
        "presentation_context": presentation_context,
        "model_policy": {
            "recommended_model": "opus",
            "reasoning_effort": "medium",
            "max_deep_dive_sources": int(
                synthesis_input.get("deep_dive_budget", {}).get(
                    "max_sources", DEFAULT_MAX_DEEP_DIVE_SOURCES
                )
            ),
            "max_windows_per_source": int(
                deep_dive_package.get("max_windows_per_source", A09_DEEP_DIVE_WINDOWS)
            ),
            "max_chars_per_window": int(
                deep_dive_package.get("max_chars_per_window", A09_DEEP_DIVE_CHARS)
            ),
            "full_pdf_forbidden": True,
        },
        "expected_output": {
            "finalizer": "research_scout_synthesis_finalize",
            "return_fields": [
                "slide_update_plan",
                "slide_revision_priorities",
                "optional_improvements",
                "do_not_change",
                "unresolved_items",
                "deep_dive_used",
                "confidence",
            ],
        },
        "rules": [
            "Verify and correct the deterministic_baseline; do not regenerate it from scratch.",
            "Use only a07_candidates, deep_dive.additional_windows and the presentation context.",
            "Do not read or request any full PDF.",
            "Drop weak or unsupported updates; keep every kept update tied to linked_intake_ids and evidence.",
            "Turn each useful deep-dive window into a ready slide update; otherwise leave it as a coverage gap.",
            "Never hand Graph03 a bare lookup pointer or a request for more research.",
            "Return a JSON object with expected_output.return_fields for research_scout_synthesis_finalize.",
        ],
    }
    validation = contracts.validate(task, SCOUT_A09_MODEL_TASK_CONTRACT)
    if not validation["ok"]:
        raise ValueError("invalid scout_a09_model_task@1: " + "; ".join(validation["errors"]))
    return task


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Scout-fast A09 synthesis")
    sub = parser.add_subparsers(dest="cmd", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("reviews_json")
    prepare.add_argument("--intake", default="")
    prepare.add_argument("--max-deep-dive-sources", type=int, default=DEFAULT_MAX_DEEP_DIVE_SOURCES)
    finalize = sub.add_parser("finalize")
    finalize.add_argument("reviews_json")
    finalize.add_argument("--intake", default="")
    finalize.add_argument("--a09-output", default="")
    finalize.add_argument("--out", default="")
    args = parser.parse_args(argv)
    if args.cmd == "prepare":
        result = prepare_scout_fast_synthesis(
            args.reviews_json,
            intake=args.intake or None,
            max_deep_dive_sources=args.max_deep_dive_sources,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    output = _read_json(Path(args.a09_output).expanduser().resolve()) if args.a09_output else None
    prepared = prepare_scout_fast_synthesis(args.reviews_json, intake=args.intake or None)
    solution = finalize_scout_fast_solution(
        prepared["synthesis_input"], output, output_path=args.out or None
    )
    print(json.dumps({
        "task_id": solution["task_id"],
        "synthesis_mode": solution["synthesis_mode"],
        "slide_update_count": len(solution["slide_update_plan"]),
        "unresolved_count": len(solution["unresolved_items"]),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
