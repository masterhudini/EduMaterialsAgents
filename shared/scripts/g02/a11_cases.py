"""G02-A11 real-world / market case discovery via the host's native web search.

A11 is a single agent node that runs early (right after the A01 planner, alongside the
deterministic scholarly Scout). It does NOT use any provider API seam (no Tavily/SearXNG): the
isolated agent calls the host's own ``WebSearch``/``WebFetch`` tools, then this module's finalizer
validates and persists a ``market_case_findings@1`` artifact into the ``.emagents`` artifact store.

The finalizer is deterministic and never blocks the graph: with no usable model output it stores an
empty, ``completed`` findings set plus an explicit limitation, so the downstream A08 recommender and
the User Research Gate still run.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from typing import Any

from core import artifacts, contracts

FINDINGS_CONTRACT = "market_case_findings@1"
RESEARCH_PLAN_CONTRACT = "research_plan@1"
A11_AGENT = "g02-a11-market-cases"
DISCOVERY_METHOD = "host_web_search"

_MATERIALITY = {"documented", "weak_signal"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe(value: object) -> str:
    text = "".join(c if (c.isalnum() or c in "._-") else "-" for c in str(value)).strip("-")
    return text or "x"


def _as_list(value: object) -> list:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _str(value: object, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _plan_topics(plan: dict) -> list[dict]:
    """Compact, agent-facing view of plan topics: id, name, purpose, claim ids, seed terms."""
    topics = []
    for topic in plan.get("topics", []):
        if not isinstance(topic, dict):
            continue
        strategy = topic.get("search_strategy") if isinstance(topic.get("search_strategy"), dict) else {}
        topics.append({
            "topic_id": _str(topic.get("topic_id")),
            "name": _str(topic.get("name")),
            "purpose": _str(topic.get("purpose")),
            "claim_ids": [_str(c) for c in _as_list(topic.get("related_claims")) if _str(c)],
            "core_terms": [_str(t) for t in _as_list(strategy.get("core_terms")) if _str(t)],
            "allowed_expansion_areas": [
                _str(t) for t in _as_list(strategy.get("allowed_expansion_areas")) if _str(t)
            ],
        })
    return [t for t in topics if t["topic_id"]]


def _output_language(plan: dict) -> str:
    constraints = plan.get("global_constraints") if isinstance(plan.get("global_constraints"), dict) else {}
    return _str(constraints.get("output_language"), "English")


def build_a11_task(plan: dict, *, plan_ref: str, intake_ref: str | None = None) -> dict:
    """Build the bounded ``a11_market_case_task`` the isolated A11 agent consumes.

    This is plain input for the agent (not a registered handoff contract): the topics to illustrate,
    the output language and the exact ``market_case_findings@1`` case shape to return.
    """
    topics = _plan_topics(plan)
    return {
        "schema_version": "a11_market_case_task@1",
        "task_id": _str(plan.get("task_id"), "task"),
        "plan_ref": plan_ref,
        "intake_ref": intake_ref,
        "output_language": _output_language(plan),
        "discovery_method": DISCOVERY_METHOD,
        "topics": topics,
        "instructions": (
            "Use the host's native web search/fetch tools to find concrete, dated, real-world or "
            "market cases that would make each topic vivid for students: notable applications, "
            "spectacular failures, current events or fresh data. Map every case to one topic_id "
            "(and claim_ids when it fits a specific claim). Keep one short factual 'what_happened' "
            "and one separate one-sentence 'didactic_mechanism' (why it teaches the point). Cite a "
            "real source_url + source_title. Do not draft slide text or pick slide placement — that "
            "is Graph03's job. Recommend additions; do not critique existing slides."
        ),
        "case_output_shape": {
            "case_id": "stable-id",
            "topic_id": "<one of topics[].topic_id>",
            "claim_ids": ["optional"],
            "title": "short case title",
            "institution_or_event": "who/what (or null)",
            "event_date": "YYYY or YYYY-MM-DD (or null)",
            "what_happened": "1-2 factual sentences",
            "didactic_mechanism": "one sentence: why this illustrates the topic",
            "source_url": "https://...",
            "source_title": "page/article title",
            "materiality": "documented | weak_signal",
            "why_interesting": "one sentence on student value",
        },
    }


def prepare_a11(plan_ref: str, *, intake_ref: str | None = None, base=None) -> dict:
    """Load the research plan and return the agent-facing A11 task."""
    plan = artifacts.hydrate(plan_ref, base=base) if isinstance(plan_ref, str) and plan_ref.startswith(
        artifacts.SCHEME) else plan_ref
    if not isinstance(plan, dict):
        raise ValueError("prepare_a11 requires a research_plan@1 ref or object")
    task = build_a11_task(plan, plan_ref=plan_ref if isinstance(plan_ref, str) else "inline", intake_ref=intake_ref)
    return {"ready": True, "task_input": task, "plan_ref": task["plan_ref"]}


def _case_id(raw: dict, topic_id: str, index: int) -> str:
    given = _str(raw.get("case_id"))
    if given:
        return given
    seed = f"{topic_id}|{_str(raw.get('source_url'))}|{_str(raw.get('title'))}|{index}"
    return "MC_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12].upper()


def _coerce_case(raw: object, valid_topics: set[str], index: int, *, observed_at: str) -> dict | None:
    """Coerce one loose model case into the contract shape, or return None if unusable."""
    if not isinstance(raw, dict):
        return None
    topic_id = _str(raw.get("topic_id"))
    if topic_id not in valid_topics:
        # fall back to the first valid topic only when exactly one exists; otherwise drop it.
        if len(valid_topics) == 1:
            topic_id = next(iter(valid_topics))
        else:
            return None
    title = _str(raw.get("title")) or _str(raw.get("institution_or_event"))
    what = _str(raw.get("what_happened"))
    source_url = _str(raw.get("source_url"))
    if not (title and what and source_url):
        return None
    materiality = _str(raw.get("materiality"), "weak_signal")
    if materiality not in _MATERIALITY:
        materiality = "weak_signal"
    claim_ids = [_str(c) for c in _as_list(raw.get("claim_ids")) if _str(c)]
    return {
        "case_id": _case_id(raw, topic_id, index),
        "topic_id": topic_id,
        "claim_ids": claim_ids,
        "title": title,
        "institution_or_event": _str(raw.get("institution_or_event")) or None,
        "event_date": _str(raw.get("event_date")) or None,
        "what_happened": what,
        "didactic_mechanism": _str(raw.get("didactic_mechanism")) or f"Illustrates topic {topic_id}.",
        "source_url": source_url,
        "source_title": _str(raw.get("source_title")) or title,
        "observed_at": _str(raw.get("observed_at")) or observed_at,
        "materiality": materiality,
        "why_interesting": _str(raw.get("why_interesting")) or "Concrete real-world hook for students.",
    }


def _envelope(status: str, summary: str, issues: list[dict] | None = None,
              *, produced: list[dict] | None = None, metrics: dict | None = None) -> dict:
    return {
        "schema_version": "envelope@1",
        "status": status,
        "summary": summary,
        "issues": issues or [],
        "produced": produced or [],
        "metrics": metrics or {},
    }


def finalize_a11(plan_ref: str, output: object | None = None, *, intake_ref: str | None = None,
                 artifact_version: str = "1.0.0", base=None) -> dict:
    """Validate and persist ``market_case_findings@1`` from the A11 agent's raw web-search output.

    ``output`` is the raw model JSON (``{"cases": [...], "limitations": [...]}``) or None for the
    deterministic empty fallback. Cases that cannot be coerced into the contract are dropped and
    summarised as a limitation; the run still completes.
    """
    try:
        plan = artifacts.hydrate(plan_ref, base=base) if isinstance(plan_ref, str) and plan_ref.startswith(
            artifacts.SCHEME) else plan_ref
        if not isinstance(plan, dict):
            raise ValueError("finalize_a11 requires a research_plan@1 ref or object")
        task_id = _str(plan.get("task_id"), "task")
        topics = _plan_topics(plan)
        valid_topics = {t["topic_id"] for t in topics}
        observed_at = _utc_now()

        raw_cases = []
        limitations: list[str] = []
        if isinstance(output, dict):
            raw_cases = _as_list(output.get("cases"))
            limitations = [_str(x) for x in _as_list(output.get("limitations")) if _str(x)]
        elif output is not None:
            raw_cases = _as_list(output)

        cases: list[dict] = []
        dropped = 0
        for index, raw in enumerate(raw_cases, start=1):
            case = _coerce_case(raw, valid_topics, index, observed_at=observed_at)
            if case is None:
                dropped += 1
                continue
            cases.append(case)
        if dropped:
            limitations.append(f"{dropped} model case(s) dropped: missing topic/title/what_happened/source_url.")
        if not cases:
            limitations.append("No web cases gathered; topics carry no real-world illustration from A11.")

        topics_covered = sorted({c["topic_id"] for c in cases})
        findings = {
            "schema_version": FINDINGS_CONTRACT,
            "artifact_version": artifact_version,
            "task_id": task_id,
            "status": "completed",
            "plan_ref": plan_ref if isinstance(plan_ref, str) else "inline",
            "intake_ref": intake_ref,
            "discovery_method": DISCOVERY_METHOD,
            "cases": cases,
            "topics_covered": [{"topic_id": tid} for tid in topics_covered],
            "limitations": limitations,
        }
        checked = contracts.validate(findings, FINDINGS_CONTRACT)
        if not checked["ok"]:
            raise ValueError(f"invalid {FINDINGS_CONTRACT}: " + "; ".join(checked["errors"]))
        task = _safe(task_id)
        version = _safe(artifact_version)
        findings_ref = artifacts.store(
            f"g02/a11/{task}.{version}.market-case-findings.json", findings, base=base
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return _envelope(
            "failed",
            "A11 market case findings finalization failed.",
            [{"severity": "blocker", "code": "a11_finalize_failed",
              "message": str(exc), "location": "market_case_findings"}],
        )
    return _envelope(
        "ok",
        "Stored A11 market case findings.",
        produced=[{
            "type": "market_case_findings", "path": findings_ref,
            "schema_version": FINDINGS_CONTRACT, "artifact_version": artifact_version,
        }],
        metrics={"case_count": len(cases), "topics_covered": len(topics_covered)},
    )
