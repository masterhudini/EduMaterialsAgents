"""Tests for the A11 market-case finder (host web search) and the A08 claim recommender.

These cover the deterministic finalizers that keep the graph non-blocking: A11 coerces loose model
cases into market_case_findings@1 (dropping unusable ones) and falls back to an empty completed set;
A08 binds the A09 candidate and A11 findings into the additive recommended_claims array and falls
back to deterministic recommendations. No network or host web search is exercised.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared" / "scripts"))

import pytest  # noqa: E402

from core import artifacts, contracts  # noqa: E402
from g02 import a08_recommend, a11_cases  # noqa: E402


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("EMAGENTS_HOME", str(tmp_path / ".emagents"))


def _plan_ref():
    plan = {
        "schema_version": "research_plan@1",
        "task_id": "T1",
        "topics": [
            {"topic_id": "TOP1", "name": "Caching", "purpose": "p",
             "related_claims": ["C1"], "search_strategy": {"core_terms": ["cache"]}},
            {"topic_id": "TOP2", "name": "Sharding", "purpose": "p",
             "related_claims": [], "search_strategy": {}},
        ],
        "global_constraints": {"output_language": "Polish"},
    }
    return artifacts.store("g02/plan/T1.json", plan)


def _candidate_ref(updates=None):
    cand = {
        "schema_version": "solution_input_candidate@1", "artifact_version": "1.0.0", "task_id": "T1",
        "synthesis_mode": "evidence_without_claim_assessment", "claim_assessment_performed": False,
        "claim_assessment_status": "not_in_workflow",
        "graph03_handoff_constraints": {"output_language": "Polish"},
        "topics_covered": [{"topic_id": "TOP1", "name": "Caching"}, {"topic_id": "TOP2", "name": "Sharding"}],
        "suggested_updates": updates or [], "optional_improvements": [],
        "evidence_map_ref": "artifact://x", "source_refs": [], "limitations": [],
        "unresolved_items": [], "confidence": "medium",
    }
    return artifacts.store("g02/cand/T1.json", cand)


# --- A11 ---------------------------------------------------------------------

def test_a11_prepare_exposes_plan_topics_and_language():
    task = a11_cases.prepare_a11(_plan_ref())["task_input"]
    assert {t["topic_id"] for t in task["topics"]} == {"TOP1", "TOP2"}
    assert task["output_language"] == "Polish"
    assert task["discovery_method"] == "host_web_search"


def test_a11_finalize_coerces_cases_and_drops_unusable():
    plan_ref = _plan_ref()
    out = {"cases": [
        {"topic_id": "TOP1", "title": "Redis at Scale", "what_happened": "ran redis",
         "source_url": "https://x", "didactic_mechanism": "shows scale",
         "materiality": "documented", "why_interesting": "famous"},
        {"topic_id": "UNKNOWN", "title": "x", "what_happened": "y", "source_url": "https://z"},
        {"topic_id": "TOP2", "title": "missing url"},
    ], "limitations": ["partial web"]}
    env = a11_cases.finalize_a11(plan_ref, out)
    assert env["status"] == "ok" and env["metrics"]["case_count"] == 1
    findings = artifacts.hydrate(env["produced"][0]["path"])
    assert contracts.validate(findings, "market_case_findings@1")["ok"]
    assert findings["cases"][0]["topic_id"] == "TOP1"
    assert findings["cases"][0]["case_id"]  # generated
    # two unusable cases dropped -> recorded as a limitation
    assert any("dropped" in lim for lim in findings["limitations"])


def test_a11_finalize_empty_fallback_is_completed():
    env = a11_cases.finalize_a11(_plan_ref(), None)
    assert env["status"] == "ok" and env["metrics"]["case_count"] == 0
    findings = artifacts.hydrate(env["produced"][0]["path"])
    assert findings["status"] == "completed"
    assert any("No web cases" in lim for lim in findings["limitations"])


# --- A08 ---------------------------------------------------------------------

def test_a08_finalize_model_pass_enriches_candidate():
    plan_ref = _plan_ref()
    findings_ref = a11_cases.finalize_a11(plan_ref, {"cases": [
        {"topic_id": "TOP1", "title": "Redis", "what_happened": "ran redis", "source_url": "https://x",
         "didactic_mechanism": "scale", "materiality": "documented", "why_interesting": "famous"}]})["produced"][0]["path"]
    cand_ref = _candidate_ref()
    out = {"recommended_claims": [
        {"topic_id": "TOP1", "claim": "Cache invalidation is hard", "why_interesting": "classic",
         "support_basis": "both", "web_case_refs": ["MC_X"], "confidence": "high"},
        {"topic_id": "GHOST", "claim": "dropped", "why_interesting": "n", "support_basis": "web", "confidence": "low"},
    ]}
    env = a08_recommend.finalize_a08(cand_ref, findings_ref=findings_ref, output=out)
    assert env["status"] == "ok" and env["metrics"]["model_pass"] is True
    enriched = artifacts.hydrate(env["produced"][0]["path"])
    assert contracts.validate(enriched, "solution_input_candidate@1")["ok"]
    recs = enriched["recommended_claims"]
    assert len(recs) == 1 and recs[0]["topic_id"] == "TOP1"  # GHOST topic dropped
    assert enriched["market_case_findings_ref"] == findings_ref


def test_a08_finalize_deterministic_fallback_from_web_and_literature():
    plan_ref = _plan_ref()
    findings_ref = a11_cases.finalize_a11(plan_ref, {"cases": [
        {"topic_id": "TOP1", "title": "Redis", "what_happened": "ran redis", "source_url": "https://x",
         "didactic_mechanism": "scale", "materiality": "documented", "why_interesting": "famous"}]})["produced"][0]["path"]
    update = {
        "update_id": "U1", "finding": "Caches cut latency", "rationale": "studies", "topic_id": "TOP1",
        "linked_intake_ids": {}, "target": {"slide_ids": [], "placement": "append", "teaching_role": "support"},
        "ready_to_apply_text": {"slide_bullet": "b", "speaker_note": "n", "optional_detail": "d"},
        "source_refs": [{"source_id": "S1"}], "confidence": "high",
        "evidence_refs": [{"source_id": "S1", "location": "p1", "quote": "q"}],
    }
    cand_ref = _candidate_ref(updates=[update])
    env = a08_recommend.finalize_a08(cand_ref, findings_ref=findings_ref, output=None)
    assert env["status"] == "ok" and env["metrics"]["model_pass"] is False
    enriched = artifacts.hydrate(env["produced"][0]["path"])
    assert contracts.validate(enriched, "solution_input_candidate@1")["ok"]
    bases = {r["support_basis"] for r in enriched["recommended_claims"]}
    assert bases == {"web", "literature"}
