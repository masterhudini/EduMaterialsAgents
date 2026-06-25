"""Prepared offline tests for G02-A09 fast synthesis and final bundle gate."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from core import artifacts, contracts, graphs  # noqa: E402
from g02 import synthesis  # noqa: E402

MOCKS = ROOT / "mocks" / "g02"
TASK = "RESEARCH_MOCK_001"
TOPIC = "TOPIC_BAYESIAN_COMPUTATION"
CLAIM = "CLM_001"
SOURCE = "SRC_OPENALEX_4FBB7A48C33F038E"


@pytest.fixture(autouse=True)
def _runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("EMAGENTS_HOME", str(tmp_path / ".emagents"))
    monkeypatch.setenv("EMAGENTS_RESEARCH_CONTACT_EMAIL", "tests@example.org")
    monkeypatch.setenv("OPENALEX_API_KEY", "openalex-test-key")


def _load(name):
    return json.loads((MOCKS / name).read_text(encoding="utf-8"))


def _upstream_refs():
    plan = _load("research_plan.json")
    plan_ref = artifacts.store("g02/research-plans/a09-plan.json", plan)
    source_record = copy.deepcopy(_load("domain_candidate_sources.json")["candidates"][0])
    source_record["classification"]["related_claims"] = [CLAIM]
    index = {
        "schema_version": "candidate_source_index@1",
        "artifact_version": "1.0.0",
        "task_id": TASK,
        "research_plan_ref": plan_ref,
        "research_plan_artifact_version": "1.0.0",
        "output_language": "English",
        "reviewed_upstreams": [],
        "selection_profile": {},
        "sources": [{
            "source_id": SOURCE,
            "record_type": "scholarly",
            "record": source_record,
            "origin_streams": ["domain"],
            "topic_ids": [TOPIC],
            "claim_ids": [CLAIM],
            "role_assignments": [{"role": "canonical", "confidence": "high"}],
            "coverage_unit_ids": ["COV_BAYESIAN_COST_CONDITIONS"],
            "duplicate_source_ids": [],
            "ranking": {"score": 1.0, "rank": 1, "components": {},
                        "recommended_action": "DOWNLOAD", "rationale": []},
            "human_annotation": {
                "content_summary": "HMC source.",
                "description_basis": "abstract",
                "selection_relevance": "Bayesian computation.",
                "limitations": [],
                "basis_excerpt": "Hamiltonian Monte Carlo",
            },
            "access_summary": source_record["access"],
            "signal_summary": {},
            "provenance_records": [],
        }],
        "displayed_source_ids": [SOURCE],
        "reserve_source_ids": [],
        "merge_log": [],
        "ambiguous_duplicate_groups": [],
        "coverage_matrix": [],
        "search_summary": {},
        "annotation_policy": {},
        "human_review_document_ref": "artifact://g02/candidate-index/a09.md",
        "review_profile_ref": "candidate_index",
    }
    index_ref = artifacts.store("g02/candidate-index/a09-index.json", index)
    approved = {
        "schema_version": "user_approved_source_set@1",
        "artifact_version": "1.0.0",
        "task_id": TASK,
        "source_selection_ref": "artifact://g02/source-selection/a09.json",
        "candidate_source_index_ref": index_ref,
        "approved_sources": [{
            "source_id": SOURCE,
            "action": "DOWNLOAD",
            "record_type": "scholarly",
            "source_record": source_record,
            "related_topics": [TOPIC],
            "related_claims": [CLAIM],
            "source_roles": ["canonical"],
            "doi_verification": None,
            "market_candidate_sources_ref": None,
        }],
        "library_queue": [],
        "citation_only": [],
        "reserve": [],
        "excluded": [],
        "coverage_at_approval": [],
        "accepted_coverage_exceptions": [],
        "final_confirmation": True,
    }
    approved_ref = artifacts.store("g02/source-selection/a09-approved.json", approved)
    corpus = {
        "schema_version": "retrieved_corpus@1",
        "artifact_version": "1.0.0",
        "task_id": TASK,
        "approved_source_set_ref": approved_ref,
        "approved_source_set_artifact_version": "1.0.0",
        "candidate_source_index_ref": index_ref,
        "run_directory_ref": "corpus://accepted/a09",
        "documents": [{"source_id": SOURCE, "status": "accepted",
                       "local_ref": "corpus://accepted/a09/documents/source.pdf",
                       "sha256": "0" * 64}],
        "market_cases": [],
        "unavailable": [],
        "failed": [],
        "skipped_actions": {"library": [], "citation": [], "reserve": [], "excluded": []},
        "attempt_log": [],
        "retrieval_summary": {
            "approved_download_count": 1,
            "validated_document_count": 1,
            "market_case_count": 0,
            "market_case_human_document_count": 0,
            "market_case_machine_artifact_count": 0,
            "unavailable_count": 0,
            "failed_count": 0,
            "network_attempt_count": 0,
        },
        "policy": {},
        "review_profile_ref": "retrieved_corpus",
    }
    corpus_ref = artifacts.store("g02/retrieved-corpora/a09-corpus.json", corpus)
    paper = {
        "schema_version": "paper_review@1",
        "artifact_version": "1.0.0",
        "task_id": TASK,
        "source_id": SOURCE,
        "source_kind": "scholarly",
        "reviewed_document_ref": "corpus://accepted/a09/documents/source.pdf",
        "reviewed_document_sha256": "0" * 64,
        "topic_ids": [TOPIC],
        "claim_ids": [CLAIM],
        "relevance_to_lecture": "Supports Bayesian computation.",
        "limitations": "Fixture review.",
        "contribution": "Conceptual HMC source.",
        "method": "Conceptual exposition.",
        "method_or_source_basis": "Conceptual exposition.",
        "findings": "HMC contextualizes posterior sampling.",
        "evidence_cards": [{
            "evidence_id": "EV_A09_001",
            "source_id": SOURCE,
            "topic_ids": [TOPIC],
            "claim_ids": [CLAIM],
            "relation": "contextualizes",
            "summary": "HMC supports efficient posterior sampling discussion.",
            "locations": [{"section_id": "SEC_001_DOCUMENT", "page": 1,
                           "document_ref": "corpus://accepted/a09/documents/source.pdf"}],
            "confidence": "medium",
        }],
        "review_status": "sufficient",
        "confidence": "medium",
        "evidence_access_level": "full_text_window",
        "review_profile_ref": "paper_evidence",
        "location_flags": {},
        "conflict_flags": [],
        "prompt_injection_flags": [],
    }
    paper_ref = artifacts.store("g02/paper-reviews/a09-paper.json", paper)
    return plan_ref, index_ref, approved_ref, corpus_ref, paper_ref


def test_a09_fast_synthesis_without_a08_creates_research_state_and_packet():
    refs = _upstream_refs()
    prepared = synthesis.prepare_synthesis(
        refs[0], refs[1], refs[2], refs[3], [refs[4]],
        profile={
            **graphs.load("g02")["execution_profiles"]["scout_e2e"],
            "require_reviewed_a07_provenance": False,
        },
    )
    assert prepared["ready"], prepared.get("envelope")
    output = {
        "required_updates": [{
            "finding_id": "FIND_CLM_001",
            "impact": "Update the lecture to qualify Bayesian computation cost discussion.",
            "priority": "medium",
            "status": "supported_by_reviewed_source",
            "related_claims": [CLAIM],
            "related_topics": [TOPIC],
            "source_refs": [SOURCE],
            "evidence_refs": [f"{refs[4]}#/evidence_cards/0"],
            "confidence": "medium",
        }],
        "optional_improvements": [],
        "findings": [{
            "finding_id": "FIND_CLM_001",
            "status": "supported_by_reviewed_source",
            "claim_ids": [CLAIM],
            "topic_ids": [TOPIC],
            "source_ids": [SOURCE],
            "evidence_refs": [f"{refs[4]}#/evidence_cards/0"],
            "summary": "Evidence supports a cautious update.",
            "limitations": ["A08 skipped in fast mode."],
            "confidence": "medium",
        }],
        "unresolved": [],
        "claim_assessment_performed": False,
        "fast_mode_limitation": prepared["synthesis_input"]["fast_mode_limitation"],
    }
    envelope = synthesis.finalize_synthesis(prepared["synthesis_input"], output)
    assert envelope["status"] == "ok", envelope["issues"]
    state_ref = next(item["path"] for item in envelope["produced"]
                     if item["type"] == "research_state")
    state = artifacts.hydrate(state_ref)
    assert state["claim_assessment_performed"] is False
    assert "A08" in state["fast_mode_limitation"]
    assert contracts.validate(state, "research_state@1")["ok"]


def test_a09_preserves_retrieval_gaps_when_no_document_was_downloaded():
    refs = _upstream_refs()
    corpus = artifacts.hydrate(refs[3])
    corpus["documents"] = []
    corpus["unavailable"] = [{"source_id": SOURCE, "reason": "unavailable"}]
    corpus["retrieval_summary"]["validated_document_count"] = 0
    corpus["retrieval_summary"]["unavailable_count"] = 1
    corpus_ref = artifacts.store("g02/retrieved-corpora/a09-unavailable.json", corpus)
    prepared = synthesis.prepare_synthesis(
        refs[0], refs[1], refs[2], corpus_ref, [],
        profile=graphs.load("g02")["execution_profiles"]["scout_e2e"],
        reviewed_paper_reviews=[],
    )
    assert prepared["ready"], prepared.get("envelope")
    envelope = synthesis.finalize_synthesis(prepared["synthesis_input"], {})
    assert envelope["status"] == "ok", envelope["issues"]
    state_ref = next(item["path"] for item in envelope["produced"]
                     if item["type"] == "research_state")
    state = artifacts.hydrate(state_ref)
    assert state["unresolved"][0]["status"] == "insufficient_evidence"


def test_a09_blocks_missing_evidence_refs_and_hidden_a08_limitation():
    refs = _upstream_refs()
    prepared = synthesis.prepare_synthesis(refs[0], refs[1], refs[2], refs[3], [refs[4]])
    output = {
        "required_updates": [{"finding_id": "FIND_BAD", "impact": "Missing evidence."}],
        "optional_improvements": [],
        "findings": [{
            "finding_id": "FIND_BAD",
            "status": "supported_by_reviewed_source",
            "claim_ids": [CLAIM],
            "topic_ids": [TOPIC],
            "source_ids": [SOURCE],
            "evidence_refs": [],
            "summary": "Bad finding.",
            "limitations": ["Missing evidence refs."],
            "confidence": "medium",
        }],
        "claim_assessment_performed": True,
        "fast_mode_limitation": "No limitation reported.",
    }
    envelope = synthesis.finalize_synthesis(prepared["synthesis_input"], output)
    assert envelope["status"] == "failed"
    assert "evidence refs" in envelope["issues"][0]["message"] \
        or "A08" in envelope["issues"][0]["message"]


def test_human_research_gate_bundle_finalize_after_approval_only():
    refs = _upstream_refs()
    prepared = synthesis.prepare_synthesis(refs[0], refs[1], refs[2], refs[3], [refs[4]])
    envelope = synthesis.finalize_synthesis(prepared["synthesis_input"], {
        "required_updates": [],
        "optional_improvements": [],
    })
    state_ref = next(item["path"] for item in envelope["produced"]
                     if item["type"] == "research_state")
    pending = synthesis.finalize_research_bundle(state_ref, {"status": "needs_changes"})
    assert pending["status"] == "needs_input"
    approved = synthesis.finalize_research_bundle(state_ref, {
        "status": "approved",
        "approve_required_updates": True,
        "approve_optional_improvements": True,
        "unresolved_claim_handling": "keep_as_unresolved_items",
    })
    assert approved["status"] == "ok", approved["issues"]
    bundle_ref = approved["produced"][0]["path"]
    bundle = artifacts.hydrate(bundle_ref)
    assert bundle["solution_handoff"]["claim_assessment_performed"] is False
    assert bundle["solution_handoff"]["claim_assessment_status"] == "not_in_workflow"
    assert contracts.validate(bundle, "user_approved_research_bundle@1")["ok"]


def test_active_graph_scout_e2e_skips_a08_and_reaches_research_gate():
    manifest = graphs.load("g02")
    assert manifest["sequence"] == [
        "g02-a01-planner",
        "research-scout-fanout",
        "g02-a07-paper-review",
        "g02-a09-synthesizer",
        "user-research-gate",
    ]
    profile = manifest["execution_profiles"]["scout_e2e"]
    assert profile["skip_nodes"] == ["g02-a08-claim-verification"]
    assert profile["implemented_terminal_stage"] == "user-research-gate"
    assert profile["review_mode"] == "none"
