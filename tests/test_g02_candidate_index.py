"""Offline contract tests for the G02-A05 candidate index and human review document."""
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from core import artifacts, contracts  # noqa: E402
from g02 import candidate_index  # noqa: E402
from mcp import research_server as srv  # noqa: E402

MOCKS = ROOT / "mocks" / "g02"
TOPIC = "TOPIC_DERIVATIVES_OPTIONS"


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("EMAGENTS_HOME", str(tmp_path / ".emagents"))


def _load(name):
    return json.loads((MOCKS / name).read_text(encoding="utf-8"))


def _decision(task_id, artifact_ref, artifact, *, stream, review_id):
    profile, producer, _ = candidate_index.STREAM_PROFILE[stream]
    return {
        "schema_version": "review_decision@1", "review_id": review_id,
        "task_id": task_id, "logical_review_node": f"{producer}-review",
        "reviewer_agent": "g02-a10-output-reviewer", "producer_agent": producer,
        "artifact_ref": artifact_ref, "artifact_version": artifact["artifact_version"],
        "review_profile": profile, "decision": "APPROVED", "findings": [],
        "closed_finding_ids": [], "revision_scope": None, "root_cause": None,
        "confidence": "high", "attempt": 1, "summary": "Approved fixture.",
    }


def _market_annotation(record):
    coverage = ["COV_OPTIONS_RISK_FAILURE"]
    return {
        "source_id": record["source_id"],
        "role_assignments": [{
            "role": "qualifying_or_critical", "confidence": "high",
            "observed_signals": ["documented institutional loss"],
            "access_basis": "search_snippet", "topic_ids": [TOPIC],
            "claim_ids": ["CLM_OPTIONS_CONTROL_RISK"], "coverage_unit_ids": coverage,
        }],
        "case_identity": {"institution_or_event": "Societe Generale",
                          "event_label": "Unauthorized derivatives positions",
                          "event_date": "2008-01-24", "observed_basis": []},
        "evidence_type": {"value": "control_failure", "basis": []},
        "source_assessment": {"source_tier": "tier_2_reputable_media",
                              "weakly_sourced": False, "corroborating_source_ids": [],
                              "tier_basis": "reviewed Reuters result"},
        "materiality_assessment": {"scale_observed": True,
                                   "real_consequence_observed": True,
                                   "higher_tier_confirmation": True,
                                   "passes_threshold": True, "basis": []},
        "market_fact": {"statement": "The bank disclosed a EUR 4.9 billion loss after the positions were unwound.",
                        "basis": []},
        "didactic_interpretation": {
            "mechanism": "The case connects derivatives exposure and weak controls with a realized institutional loss.",
            "topic_ids": [TOPIC], "claim_ids": ["CLM_OPTIONS_CONTROL_RISK"],
        },
        "documentation_status": "documented",
        "regime_context": {"status": "historical_regime",
                           "note": "Teach within the 2008 control and regulatory regime.",
                           "basis": "event date"},
        "coverage_unit_ids": coverage, "quality_status": "not_assessed", "doi_status": "absent",
    }


def _candidate_artifact(stream, plan_ref, task_id, record, coverage):
    value = {
        "schema_version": "candidate_sources@1", "artifact_version": "1.0.0",
        "stream": stream, "task_id": task_id, "topic_id": TOPIC,
        "research_plan_ref": plan_ref,
        "upstream_refs": {"domain_candidate_sources": "artifact://g02/domain/domain.json"},
        "query_plan": {}, "candidates": [copy.deepcopy(record)], "operation_log": [],
        "coverage_map": [{"source_id": record["source_id"],
                          "coverage_unit_ids": coverage,
                          "basis": "search_snippet" if stream == "market_cases" else "abstract"}],
        "remaining_coverage_units": [], "provider_issues": [], "unresolved_seed_ids": [],
        "stop_reason": "completed", "review_profile_ref": (
            "market_cases" if stream == "market_cases" else "canonical_sources"),
    }
    if stream == "market_cases":
        value["market_case_annotations"] = [_market_annotation(record)]
    return value


def _prepared():
    plan = _load("market_research_plan.json")
    plan["output_language"] = "Polish"
    plan_ref = artifacts.store("g02/research-plans/a05-plan.json", plan)
    scholarly = _load("domain_candidate_sources.json")["candidates"][0]
    scholarly["classification"]["related_topics"] = [TOPIC]
    scholarly["inclusion"]["coverage_units"] = ["COV_OPTIONS_APPLIED_USE"]
    domain = _load("market_domain_candidate_sources.json")
    domain.update({"artifact_version": "1.0.0", "task_id": plan["task_id"],
                   "topic_id": TOPIC, "research_plan_ref": plan_ref,
                   "candidates": [copy.deepcopy(scholarly)],
                   "coverage_map": [{"source_id": scholarly["source_id"],
                                     "coverage_unit_ids": ["COV_OPTIONS_APPLIED_USE"],
                                     "basis": "abstract"}],
                   "remaining_coverage_units": []})
    domain_ref = artifacts.store("g02/domain/domain.json", domain)
    canonical = _candidate_artifact("canonical", plan_ref, plan["task_id"], scholarly,
                                    ["COV_OPTIONS_APPLIED_USE"])
    canonical_ref = artifacts.store("g02/canonical/a05.json", canonical)
    market_record = _load("market_case_source_record.json")
    market = _candidate_artifact("market_cases", plan_ref, plan["task_id"], market_record,
                                 ["COV_OPTIONS_RISK_FAILURE"])
    market_ref = artifacts.store("g02/market/a05.json", market)
    descriptors = []
    for stream, ref, artifact, review_id in (
        ("domain", domain_ref, domain, "REV_A02_A05"),
        ("canonical", canonical_ref, canonical, "REV_A03_A05"),
        ("market_cases", market_ref, market, "REV_A11_A05"),
    ):
        decision = _decision(plan["task_id"], ref, artifact, stream=stream, review_id=review_id)
        decision_ref = artifacts.store(f"reviews/{review_id}.json", decision)
        descriptors.append({"stream": stream, "artifact_ref": ref,
                            "review_decision_ref": decision_ref})
    profile = _load("candidate_index_selection_profile.json")
    return plan_ref, descriptors, profile


def test_prepare_requires_exact_approved_reviews_and_projects_scoped_input():
    plan_ref, descriptors, profile = _prepared()
    prepared = candidate_index.prepare_candidate_index(plan_ref, descriptors,
                                                       selection_profile=profile)
    assert prepared["ready"], prepared
    scoped = prepared["candidate_index_input"]
    assert contracts.validate(scoped, "candidate_index_input@1")["ok"]
    assert len(scoped["source_entries"]) == 3
    assert "query_plan" not in scoped and "reviewer_agent" not in json.dumps(scoped)
    assert scoped["upstream_issues"][0]["type"] == "missing_reviewed_stream"
    rejected = copy.deepcopy(descriptors)
    decision = artifacts.hydrate(rejected[0]["review_decision_ref"])
    decision["decision"] = "BLOCKED"
    rejected[0]["review_decision_ref"] = artifacts.store("reviews/rejected.json", decision)
    assert not candidate_index.prepare_candidate_index(plan_ref, rejected)["ready"]


def test_build_deduplicates_and_describes_scholarly_and_market_content():
    plan_ref, descriptors, profile = _prepared()
    scoped = candidate_index.prepare_candidate_index(
        plan_ref, descriptors, selection_profile=profile)["candidate_index_input"]
    index = candidate_index.build_candidate_index(scoped)
    assert contracts.validate(index, "candidate_source_index@1")["ok"]
    assert len(index["sources"]) == 2
    scholarly = next(item for item in index["sources"] if item["record_type"] == "scholarly")
    market = next(item for item in index["sources"] if item["record_type"] == "market_case")
    assert scholarly["human_annotation"]["description_basis"] == "abstract"
    assert "Hamiltonian Monte Carlo" in scholarly["human_annotation"]["content_summary"]
    assert market["human_annotation"]["description_basis"] == "market_case_annotation"
    assert "EUR 4.9 billion" in market["human_annotation"]["content_summary"]
    assert market["signal_summary"]["market_source_tier"] == "tier_2_reputable_media"
    assert market["signal_summary"]["scientific_quality"] == "not_assessed"
    assert index["merge_log"] and len(index["displayed_source_ids"]) == 2


def test_finalize_writes_friendly_document_and_review_task():
    plan_ref, descriptors, profile = _prepared()
    scoped = candidate_index.prepare_candidate_index(
        plan_ref, descriptors, selection_profile=profile)["candidate_index_input"]
    envelope = candidate_index.finalize_candidate_index(scoped)
    assert envelope["status"] == "degraded"  # recent stream is intentionally absent
    index_descriptor, document_descriptor = envelope["produced"]
    document_path = artifacts.resolve_path(document_descriptor["path"])
    document = document_path.read_text(encoding="utf-8")
    assert "Co zawiera według dostępnych danych" in document
    assert "Podstawa opisu" in document and "Szablon decyzji" in document
    task = candidate_index.build_candidate_index_review_task(
        scoped, index_descriptor, review_id="REV_A05_001")
    assert [item["criterion_id"] for item in task["acceptance_criteria"]] == [
        "CI-01", "CI-02", "CI-03", "CI-04", "CI-05", "CI-06", "CI-07", "CI-08"
    ]


def test_mcp_inventory_and_candidate_index_prepare_parity():
    plan_ref, descriptors, profile = _prepared()
    result = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                         "params": {"name": "research_candidate_index_prepare", "arguments": {
                             "research_plan_ref": plan_ref, "reviewed_upstreams": descriptors,
                             "selection_profile": profile}}})
    assert json.loads(result["result"]["content"][0]["text"])["ready"]
    names = {tool["name"] for tool in srv.TOOLS}
    assert {"research_candidate_index_prepare", "research_candidate_index_finalize",
            "research_candidate_index_review_task"} <= names
