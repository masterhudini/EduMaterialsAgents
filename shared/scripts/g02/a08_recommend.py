"""G02-A08 claim recommender — the additive binder that closes the Research graph.

A08 runs last, after A09 synthesis and before the User Research Gate, and uses NO web search of its
own. It binds two streams already gathered for the analysed topics — A09's scholarly synthesis
(``solution_input_candidate@1``) and A11's real-world cases (``market_case_findings@1``) — into
positively framed *recommendations*: per topic, the interesting, well-documented claims worth
featuring, grounded in literature and/or web cases. It does not draft slide text or pick placement
(that is Graph03) and it does not audit existing slides; it recommends what is worth adding at the
research/topic level.

The recommendations are written back into ``solution_input_candidate@1`` as the additive
``recommended_claims`` array, so the existing single handoff to Graph03 carries them. The finalizer
is deterministic: with no model output it derives recommendations from the web cases and the
top scholarly updates already present, so the gate always runs.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
from typing import Any

from core import artifacts, contracts
from g02 import a11_cases

SOLUTION_CONTRACT = "solution_input_candidate@1"
FINDINGS_CONTRACT = "market_case_findings@1"
A08_AGENT = "g02-a08-claim-verification"

_SUPPORT = {"literature", "web", "both"}
_CONFIDENCE = {"low", "medium", "high"}


def _str(value: object, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _as_list(value: object) -> list:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _hydrate(ref_or_obj: object, base=None) -> dict:
    if isinstance(ref_or_obj, str) and ref_or_obj.startswith(artifacts.SCHEME):
        return artifacts.hydrate(ref_or_obj, base=base)
    if isinstance(ref_or_obj, dict):
        return ref_or_obj
    raise ValueError("expected an artifact:// ref or object")


def _topic_names(candidate: dict) -> dict[str, str]:
    names = {}
    for topic in candidate.get("topics_covered", []):
        if isinstance(topic, dict) and _str(topic.get("topic_id")):
            names[_str(topic.get("topic_id"))] = _str(topic.get("name"))
    return names


def build_a08_task(candidate: dict, findings: dict | None, *,
                   candidate_ref: str, findings_ref: str | None = None) -> dict:
    """Build the agent-facing A08 task: the two streams to bind into claim recommendations."""
    topics = [
        {"topic_id": _str(t.get("topic_id")), "name": _str(t.get("name"))}
        for t in candidate.get("topics_covered", []) if isinstance(t, dict) and _str(t.get("topic_id"))
    ]
    scholarly = [
        {
            "topic_id": _str(u.get("topic_id")),
            "finding": _str(u.get("finding")),
            "rationale": _str(u.get("rationale")),
            "evidence_refs": deepcopy(u.get("evidence_refs", [])),
        }
        for u in candidate.get("suggested_updates", []) if isinstance(u, dict)
    ]
    web_cases = [
        {
            "case_id": _str(c.get("case_id")),
            "topic_id": _str(c.get("topic_id")),
            "title": _str(c.get("title")),
            "what_happened": _str(c.get("what_happened")),
            "didactic_mechanism": _str(c.get("didactic_mechanism")),
            "source_url": _str(c.get("source_url")),
            "why_interesting": _str(c.get("why_interesting")),
        }
        for c in (findings or {}).get("cases", []) if isinstance(c, dict)
    ]
    return {
        "schema_version": "a08_claim_recommend_task@1",
        "task_id": _str(candidate.get("task_id"), "task"),
        "candidate_ref": candidate_ref,
        "findings_ref": findings_ref,
        "output_language": _str(
            candidate.get("graph03_handoff_constraints", {}).get("output_language")
            or candidate.get("presentation_context", {}).get("output_language"),
            "English",
        ),
        "topics": topics,
        "scholarly_synthesis": scholarly,
        "web_cases": web_cases,
        "instructions": (
            "Bind the scholarly synthesis and the real-world web cases into positive, per-topic "
            "recommendations of interesting, well-documented claims worth featuring in this topic. "
            "Recommend what is worth adding; do not critique what the slides currently contain and "
            "do not write slide text or choose placement (that is Graph03). Each recommendation maps "
            "to one topic_id, states the claim, one sentence on why it is interesting for students, "
            "and its support_basis (literature | web | both) with refs."
        ),
        "recommendation_output_shape": {
            "recommendation_id": "stable-id",
            "topic_id": "<one of topics[].topic_id>",
            "claim": "the interesting, well-supported claim worth featuring",
            "why_interesting": "one sentence on student value",
            "support_basis": "literature | web | both",
            "literature_refs": [{"source_id": "...", "location": "...", "quote": "..."}],
            "web_case_refs": ["<case_id from web_cases>"],
            "linked_claim_ids": ["optional intake claim ids"],
            "confidence": "low | medium | high",
        },
    }


def prepare_a08(candidate_ref: str, *, findings_ref: str | None = None, base=None) -> dict:
    candidate = _hydrate(candidate_ref, base=base)
    findings = _hydrate(findings_ref, base=base) if findings_ref else None
    task = build_a08_task(
        candidate, findings,
        candidate_ref=candidate_ref if isinstance(candidate_ref, str) else "inline",
        findings_ref=findings_ref,
    )
    return {"ready": True, "task_input": task,
            "candidate_ref": task["candidate_ref"], "findings_ref": findings_ref}


def _rec_id(raw: dict, topic_id: str, index: int) -> str:
    given = _str(raw.get("recommendation_id"))
    if given:
        return given
    seed = f"{topic_id}|{_str(raw.get('claim'))}|{index}"
    return "REC_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12].upper()


def _coerce_rec(raw: object, valid_topics: set[str], index: int) -> dict | None:
    if not isinstance(raw, dict):
        return None
    topic_id = _str(raw.get("topic_id"))
    if topic_id not in valid_topics:
        if len(valid_topics) == 1:
            topic_id = next(iter(valid_topics))
        else:
            return None
    claim = _str(raw.get("claim"))
    if not claim:
        return None
    support = _str(raw.get("support_basis"), "literature")
    if support not in _SUPPORT:
        support = "literature"
    confidence = _str(raw.get("confidence"), "medium")
    if confidence not in _CONFIDENCE:
        confidence = "medium"
    rec = {
        "recommendation_id": _rec_id(raw, topic_id, index),
        "topic_id": topic_id,
        "claim": claim,
        "why_interesting": _str(raw.get("why_interesting")) or "Interesting, well-supported addition for students.",
        "support_basis": support,
        "confidence": confidence,
    }
    lit = [r for r in _as_list(raw.get("literature_refs")) if isinstance(r, dict)]
    web = [_str(r) for r in _as_list(raw.get("web_case_refs")) if _str(r)]
    linked = [_str(r) for r in _as_list(raw.get("linked_claim_ids")) if _str(r)]
    if lit:
        rec["literature_refs"] = lit
    if web:
        rec["web_case_refs"] = web
    if linked:
        rec["linked_claim_ids"] = linked
    return rec


def _deterministic_recs(candidate: dict, findings: dict | None, valid_topics: set[str]) -> list[dict]:
    """Fallback recommendations when no model pass: web cases + top scholarly updates per topic."""
    recs: list[dict] = []
    index = 0
    for case in (findings or {}).get("cases", []):
        if not isinstance(case, dict):
            continue
        topic_id = _str(case.get("topic_id"))
        if topic_id not in valid_topics:
            continue
        index += 1
        recs.append({
            "recommendation_id": _rec_id({}, topic_id, index),
            "topic_id": topic_id,
            "claim": f"Feature the real-world case: {_str(case.get('title'))}.",
            "why_interesting": _str(case.get("why_interesting")) or _str(case.get("didactic_mechanism"))
            or "Concrete real-world hook for students.",
            "support_basis": "web",
            "web_case_refs": [_str(case.get("case_id"))] if _str(case.get("case_id")) else [],
            "confidence": "medium",
        })
    for update in candidate.get("suggested_updates", []):
        if not isinstance(update, dict):
            continue
        topic_id = _str(update.get("topic_id"))
        if topic_id not in valid_topics:
            continue
        finding = _str(update.get("finding"))
        if not finding:
            continue
        index += 1
        rec = {
            "recommendation_id": _rec_id({}, topic_id, index),
            "topic_id": topic_id,
            "claim": finding,
            "why_interesting": _str(update.get("rationale")) or "Well-supported finding worth featuring.",
            "support_basis": "literature",
            "confidence": _str(update.get("confidence"), "medium")
            if _str(update.get("confidence")) in _CONFIDENCE else "medium",
        }
        lit = [r for r in _as_list(update.get("evidence_refs")) if isinstance(r, dict)]
        if lit:
            rec["literature_refs"] = lit
        recs.append(rec)
    return recs


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


def finalize_a08(candidate_ref: str, *, findings_ref: str | None = None, output: object | None = None,
                 artifact_version: str | None = None, base=None) -> dict:
    """Enrich ``solution_input_candidate@1`` with ``recommended_claims`` and persist it.

    Returns an envelope whose produced ``solution_input_candidate`` is the enriched candidate, so the
    reviewed flow builds research_state (and the gate) from the recommendation-enriched handoff.
    """
    try:
        candidate = _hydrate(candidate_ref, base=base)
        findings = _hydrate(findings_ref, base=base) if findings_ref else None
        check = contracts.validate(candidate, SOLUTION_CONTRACT)
        if not check["ok"]:
            raise ValueError(f"invalid {SOLUTION_CONTRACT}: " + "; ".join(check["errors"]))
        valid_topics = {
            _str(t.get("topic_id")) for t in candidate.get("topics_covered", [])
            if isinstance(t, dict) and _str(t.get("topic_id"))
        }

        model_pass = False
        recs: list[dict] = []
        raw_recs = []
        if isinstance(output, dict):
            raw_recs = _as_list(output.get("recommended_claims") or output.get("recommendations"))
        elif output is not None:
            raw_recs = _as_list(output)
        for idx, raw in enumerate(raw_recs, start=1):
            rec = _coerce_rec(raw, valid_topics, idx)
            if rec is not None:
                recs.append(rec)
        if recs:
            model_pass = True
        else:
            recs = _deterministic_recs(candidate, findings, valid_topics)

        enriched = deepcopy(candidate)
        version = artifact_version or _str(candidate.get("artifact_version"), "1.0.0")
        enriched["artifact_version"] = version
        enriched["recommended_claims"] = recs
        if findings_ref:
            enriched["market_case_findings_ref"] = findings_ref
        validated = contracts.validate(enriched, SOLUTION_CONTRACT)
        if not validated["ok"]:
            raise ValueError(f"invalid enriched {SOLUTION_CONTRACT}: " + "; ".join(validated["errors"]))
        task = a11_cases._safe(_str(candidate.get("task_id"), "task"))
        ver = a11_cases._safe(version)
        candidate_out_ref = artifacts.store(
            f"g02/a08/{task}.{ver}.solution-input-candidate.json", enriched, base=base
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return _envelope(
            "failed",
            "A08 claim recommendation finalization failed.",
            [{"severity": "blocker", "code": "a08_finalize_failed",
              "message": str(exc), "location": "recommended_claims"}],
        )
    return _envelope(
        "ok",
        "Stored A08 recommendation-enriched solution candidate.",
        produced=[{
            "type": "solution_input_candidate", "path": candidate_out_ref,
            "schema_version": SOLUTION_CONTRACT, "artifact_version": version,
        }],
        metrics={"recommended_claim_count": len(recs), "model_pass": model_pass},
    )
