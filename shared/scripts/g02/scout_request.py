"""Build Scout search requests from a G02-A01 research plan.

This module is the Phase B input seam: it reads the stable ``research_plan@1``
shape and emits one thin ``scout_search_request@1`` per topic. It does not run
Scout and does not touch A09 or the graph.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
import json

from core import artifacts, contracts, graphs

SCOUT_SEARCH_REQUEST_CONTRACT = "scout_search_request@1"
RESEARCH_PLAN_CONTRACT = "research_plan@1"

DEFAULT_TARGET_N = 15
MIN_TARGET_N = 5
DEFAULT_SCOUT_TOTAL_TARGET = 50


def _strings(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    for value in values:
        if isinstance(value, str):
            item = value.strip()
            if item:
                out.append(item)
    return out


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _positive_int(value: object) -> int | None:
    parsed = _int_or_none(value)
    return parsed if parsed is not None and parsed > 0 else None


def _target_n(*, default: int = DEFAULT_TARGET_N) -> int:
    """Return the configured per-topic Scout target.

    The single tuning point for Phase B is ``DEFAULT_TARGET_N``. A01's
    ``candidate_limit_per_topic`` remains a planner/discovery hint; Scout gets
    its own target count here.
    """
    configured = _positive_int(default)
    value = configured if configured is not None else DEFAULT_TARGET_N
    return max(MIN_TARGET_N, value)


def scout_profile_settings(profile_name: str = "scout") -> dict:
    """Return validated Scout settings from the graph manifest.

    Keeping this lookup here gives the A01 -> Scout adapter one authoritative
    total-budget knob while preserving the legacy per-topic default for callers
    outside the dedicated ``scout`` profile.
    """
    manifest = graphs.load("g02")
    profiles = manifest.get("execution_profiles", {})
    profile = profiles.get(profile_name, {}) if isinstance(profiles, dict) else {}
    settings = profile.get("scout", {}) if isinstance(profile, dict) else {}
    total_target = _positive_int(settings.get("total_target"))
    max_parallel = _positive_int(settings.get("max_parallel_topics"))
    return {
        "total_target": total_target or DEFAULT_SCOUT_TOTAL_TARGET,
        "max_parallel_topics": max_parallel or 6,
    }


def _year_bounds(plan: dict, topic: dict, *, current_year: int | None = None) -> tuple[int | None, int | None]:
    search_strategy = topic.get("search_strategy") if isinstance(topic.get("search_strategy"), dict) else {}
    global_constraints = plan.get("global_constraints") if isinstance(plan.get("global_constraints"), dict) else {}

    year_from = _int_or_none(search_strategy.get("year_from"))
    year_to = _int_or_none(search_strategy.get("year_to"))
    if year_from is None:
        year_from = _int_or_none(global_constraints.get("year_from"))
    if year_to is None:
        year_to = _int_or_none(global_constraints.get("year_to"))

    approved_scope = plan.get("approved_research_scope")
    if year_from is None and isinstance(approved_scope, dict):
        recency_window = _positive_int(approved_scope.get("recency_window_years"))
        include_recent = approved_scope.get("include_recent_developments") is True
        if recency_window is not None and include_recent:
            anchor_year = current_year if current_year is not None else date.today().year
            year_from = anchor_year - recency_window
    return year_from, year_to


def _lang(plan: dict, topic: dict) -> str:
    search_strategy = topic.get("search_strategy") if isinstance(topic.get("search_strategy"), dict) else {}
    languages = _strings(search_strategy.get("languages"))
    if not languages:
        global_constraints = plan.get("global_constraints")
        if isinstance(global_constraints, dict):
            languages = _strings(global_constraints.get("allowed_languages"))
    normalized = {item.strip().lower() for item in languages}
    has_en = "en" in normalized or "english" in normalized
    has_pl = "pl" in normalized or "polish" in normalized
    if has_en and has_pl:
        return "both"
    if has_pl:
        return "pl"
    if has_en:
        return "en"
    return "both"


def _work_type(plan: dict, topic: dict) -> str:
    search_strategy = topic.get("search_strategy") if isinstance(topic.get("search_strategy"), dict) else {}
    work_types = _dedupe_strings(_strings(search_strategy.get("work_types")))
    if not work_types:
        global_constraints = plan.get("global_constraints")
        if isinstance(global_constraints, dict):
            work_types = _dedupe_strings(_strings(global_constraints.get("allowed_work_types")))
    return work_types[0] if len(work_types) == 1 else ""


def _keywords(topic: dict) -> list[str]:
    search_strategy = topic.get("search_strategy") if isinstance(topic.get("search_strategy"), dict) else {}
    return _dedupe_strings(
        _strings(search_strategy.get("core_terms"))
        + _strings(search_strategy.get("allowed_expansion_areas"))
    )


def build_scout_search_requests(
    research_plan: dict,
    *,
    current_year: int | None = None,
    target_n_default: int = DEFAULT_TARGET_N,
    total_target: int | None = None,
) -> list[dict]:
    """Return one ``scout_search_request@1`` per topic in ``research_plan``."""
    if not isinstance(research_plan, dict):
        raise TypeError("research_plan must be a dict")
    task_id = str(research_plan.get("task_id") or "").strip()
    output_language = str(research_plan.get("output_language") or "").strip()
    topics = research_plan.get("topics")
    if not isinstance(topics, list):
        topics = []

    usable_topics = [topic for topic in topics if isinstance(topic, dict)
                     and str(topic.get("topic_id") or "").strip()
                     and str(topic.get("name") or "").strip()]
    per_topic_target = _target_n(default=target_n_default)
    if total_target is not None:
        configured_total = _positive_int(total_target)
        if configured_total is None:
            raise ValueError("total_target must be a positive integer")
        if not usable_topics:
            raise ValueError("cannot allocate Scout budget without topics")
        per_topic_target = max(MIN_TARGET_N, int(round(configured_total / len(usable_topics))))

    requests: list[dict] = []
    for index, topic in enumerate(usable_topics, start=1):
        if not isinstance(topic, dict):
            continue
        topic_id = str(topic.get("topic_id") or f"topic_{index}").strip()
        query = str(topic.get("name") or "").strip()
        if not topic_id or not query:
            continue
        search_strategy = topic.get("search_strategy") if isinstance(topic.get("search_strategy"), dict) else {}
        year_from, year_to = _year_bounds(research_plan, topic, current_year=current_year)
        request = {
            "schema_version": SCOUT_SEARCH_REQUEST_CONTRACT,
            "artifact_version": "1.0.0",
            "task_id": task_id,
            "topic_id": topic_id,
            "query": query,
            "keywords": _keywords(topic),
            "intent": str(topic.get("purpose") or "").strip(),
            "target_n": per_topic_target,
            "year_from": year_from,
            "year_to": year_to,
            "lang": _lang(research_plan, topic),
            "work_type": _work_type(research_plan, topic),
            "output_language": output_language,
            "excluded_terms": _strings(search_strategy.get("excluded_terms")),
            "created_from": {
                "task_id": task_id,
                "topic_id": topic_id,
            },
        }
        requests.append(request)
    return requests


def validate_scout_search_request(request: dict) -> dict:
    return contracts.validate(request, SCOUT_SEARCH_REQUEST_CONTRACT)


def select_request(requests: list[dict], topic_id: str | None = None) -> dict:
    """Select one request for a smoke run.

    Without ``topic_id`` exactly one request must be present. This keeps
    multi-topic plans explicit at the command line.
    """
    if topic_id:
        matches = [item for item in requests if item.get("topic_id") == topic_id]
        if not matches:
            available = ", ".join(str(item.get("topic_id")) for item in requests)
            raise ValueError(f"topic_id {topic_id!r} not found; available: {available}")
        if len(matches) > 1:
            raise ValueError(f"topic_id {topic_id!r} is not unique")
        return matches[0]
    if len(requests) != 1:
        available = ", ".join(str(item.get("topic_id")) for item in requests)
        raise ValueError(f"--topic-id is required for a plan with {len(requests)} topics: {available}")
    return requests[0]


def load_research_plan(path_or_ref: str, *, base=None) -> dict:
    """Load ``research_plan@1`` from a filesystem path or artifact ref."""
    if path_or_ref.startswith(artifacts.SCHEME):
        plan = artifacts.hydrate(path_or_ref, base=base)
    else:
        plan = json.loads(Path(path_or_ref).expanduser().read_text(encoding="utf-8"))
    validation = contracts.validate(plan, RESEARCH_PLAN_CONTRACT)
    if not validation["ok"]:
        raise ValueError("invalid research_plan@1: " + "; ".join(validation["errors"]))
    return plan


def store_scout_search_requests(requests: list[dict], task_id: str, *, base=None) -> str:
    rel = f"g02/scout-search-requests/{task_id or 'unknown'}.json"
    return artifacts.store(rel, requests, base=base)
