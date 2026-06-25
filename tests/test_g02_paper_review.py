"""Prepared offline tests for G02-A07 text windows and PaperReview finalization."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from core import artifacts  # noqa: E402
from g02 import oa_retrieval, paper_review, provider_config  # noqa: E402

MOCKS = ROOT / "mocks" / "g02"
CONFIG = MOCKS / "retrieval_provider_config.json"
TASK = "RESEARCH_MOCK_001"
TOPIC = "TOPIC_BAYESIAN_COMPUTATION"
CLAIM = "CLM_001"


@pytest.fixture(autouse=True)
def _runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("EMAGENTS_HOME", str(tmp_path / ".emagents"))
    monkeypatch.setenv("EMAGENTS_RESEARCH_CONTACT_EMAIL", "tests@example.org")
    monkeypatch.setenv("OPENALEX_API_KEY", "openalex-test-key")


def _load(name):
    return json.loads((MOCKS / name).read_text(encoding="utf-8"))


def _source_record():
    record = copy.deepcopy(_load("domain_candidate_sources.json")["candidates"][0])
    record["classification"]["related_topics"] = [TOPIC]
    record["classification"]["related_claims"] = [CLAIM]
    return record


def _plan_and_index(record, plan_ref):
    record_type = record.get("record_type") or ("market_case" if "market" in record["source_id"].casefold() else "scholarly")
    origin_stream = "market_cases" if record_type == "market_case" else "domain"
    role = "applied_case" if record_type == "market_case" else "canonical"
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
            "source_id": record["source_id"],
            "record_type": record_type,
            "record": record,
            "origin_streams": [origin_stream],
            "topic_ids": [TOPIC],
            "claim_ids": [CLAIM],
            "role_assignments": [{"role": role, "confidence": "high"}],
            "coverage_unit_ids": ["COV_BAYESIAN_COST_CONDITIONS"],
            "duplicate_source_ids": [],
            "ranking": {"score": 1.0, "rank": 1, "components": {},
                        "recommended_action": "DOWNLOAD", "rationale": []},
            "human_annotation": {
                "content_summary": "Hamiltonian Monte Carlo posterior sampling source.",
                "description_basis": "abstract",
                "selection_relevance": "Supports Bayesian computation topic.",
                "limitations": [],
                "basis_excerpt": "Hamiltonian Monte Carlo supports efficient posterior sampling",
            },
            "access_summary": record["access"],
            "signal_summary": {},
            "provenance_records": [],
        }],
        "displayed_source_ids": [record["source_id"]],
        "reserve_source_ids": [],
        "merge_log": [],
        "ambiguous_duplicate_groups": [],
        "coverage_matrix": [],
        "search_summary": {},
        "annotation_policy": {},
        "human_review_document_ref": "artifact://g02/candidate-index/mock.md",
        "review_profile_ref": "candidate_index",
    }
    return artifacts.store("g02/candidate-index/a07-index.json", index)


def _scholarly_corpus():
    runtime = provider_config.load_config(CONFIG)
    record = _source_record()
    pdf_path = runtime.retrieval_accepted_dir / TASK / "1.0.0" / "documents" / f"{record['source_id']}.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes((MOCKS / "sample_article.pdf").read_bytes())
    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    plan = _load("research_plan.json")
    plan_ref = artifacts.store("g02/research-plans/a07-plan.json", plan)
    index_ref = _plan_and_index(record, plan_ref)
    approved = {
        "schema_version": "user_approved_source_set@1",
        "artifact_version": "1.0.0",
        "task_id": TASK,
        "source_selection_ref": "artifact://g02/source-selection/a07.json",
        "candidate_source_index_ref": index_ref,
        "approved_sources": [{
            "source_id": record["source_id"],
            "action": "DOWNLOAD",
            "record_type": "scholarly",
            "source_record": record,
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
    approved_ref = artifacts.store("g02/source-selection/a07-approved.json", approved)
    corpus = {
        "schema_version": "retrieved_corpus@1",
        "artifact_version": "1.0.0",
        "task_id": TASK,
        "approved_source_set_ref": approved_ref,
        "approved_source_set_artifact_version": "1.0.0",
        "candidate_source_index_ref": index_ref,
        "run_directory_ref": oa_retrieval.corpus_ref(pdf_path.parent.parent, runtime),
        "documents": [{
            "schema_version": "validated_document@1",
            "task_id": TASK,
            "source_id": record["source_id"],
            "status": "accepted",
            "local_ref": oa_retrieval.corpus_ref(pdf_path, runtime),
            "file_type": "pdf",
            "byte_count": pdf_path.stat().st_size,
            "sha256": digest,
            "content_type_valid": True,
            "signature_valid": True,
            "identity_valid": True,
            "identity_basis": ["doi_exact:10.1214/17-sts668"],
            "version_type": "accepted",
            "license": "unknown",
            "page_count": 1,
            "duplicate_of_source_id": None,
            "resolution_ref": "artifact://g02/oa-resolutions/a07.json",
            "retrieved_file_ref": "artifact://g02/retrieved-files/a07.json",
            "issues": [],
            "validated_at": "2026-06-23T00:00:00Z",
            "validated_document_ref": "artifact://g02/validated-documents/a07.json",
        }],
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
    return artifacts.store("g02/retrieved-corpora/a07-corpus.json", corpus), record["source_id"]


def _market_annotation(record):
    return {
        "source_id": record["source_id"],
        "role_assignments": [{
            "role": "applied_case", "confidence": "high",
            "observed_signals": ["reported loss"], "access_basis": "search_snippet",
            "topic_ids": [TOPIC], "claim_ids": [CLAIM], "coverage_unit_ids": ["COV_MARKET"],
        }],
        "case_identity": {
            "institution_or_event": "Societe Generale",
            "event_label": "Unauthorized trading loss",
            "event_date": "2008-01-24", "observed_basis": [],
        },
        "evidence_type": {"value": "control_failure", "basis": []},
        "source_assessment": {
            "source_tier": "tier_2_reputable_media", "weakly_sourced": False,
            "corroborating_source_ids": [], "tier_basis": "reviewed A11 result",
        },
        "materiality_assessment": {
            "scale_observed": True, "real_consequence_observed": True,
            "higher_tier_confirmation": True, "passes_threshold": True, "basis": [],
        },
        "market_fact": {"statement": "The bank disclosed a EUR 4.9 billion loss.", "basis": []},
        "didactic_interpretation": {
            "mechanism": "The case links weak controls to a realized trading loss.",
            "topic_ids": [TOPIC], "claim_ids": [CLAIM],
        },
        "documentation_status": "documented",
        "regime_context": {"status": "historical_regime", "note": "2008 regime.", "basis": "event date"},
        "coverage_unit_ids": ["COV_MARKET"], "quality_status": "not_assessed",
        "doi_status": "absent",
    }


def _market_corpus():
    runtime = provider_config.load_config(CONFIG)
    record = copy.deepcopy(_load("market_case_source_record.json"))
    record["classification"]["related_topics"] = [TOPIC]
    record["classification"]["related_claims"] = [CLAIM]
    plan = _load("research_plan.json")
    plan_ref = artifacts.store("g02/research-plans/a07-market-plan.json", plan)
    a11 = {
        "schema_version": "candidate_sources@1",
        "artifact_version": "1.0.0",
        "stream": "market_cases",
        "task_id": TASK,
        "topic_id": TOPIC,
        "research_plan_ref": plan_ref,
        "upstream_refs": {"domain_candidate_sources": "artifact://g02/domain/a07-market.json"},
        "query_plan": {},
        "candidates": [record],
        "market_case_annotations": [_market_annotation(record)],
        "operation_log": [],
        "coverage_map": [{"source_id": record["source_id"],
                          "coverage_unit_ids": ["COV_MARKET"],
                          "basis": "search_snippet"}],
        "remaining_coverage_units": [],
        "provider_issues": [],
        "unresolved_seed_ids": [],
        "stop_reason": "completed",
        "review_profile_ref": "market_cases",
    }
    a11_ref = artifacts.store("g02/market/a07-reviewed-market.json", a11)
    index_ref = _plan_and_index(record, plan_ref)
    approved = {
        "schema_version": "user_approved_source_set@1",
        "artifact_version": "1.0.0",
        "task_id": TASK,
        "source_selection_ref": "artifact://g02/source-selection/a07-market.json",
        "candidate_source_index_ref": index_ref,
        "approved_sources": [{
            "source_id": record["source_id"],
            "action": "DOWNLOAD",
            "record_type": "market_case",
            "source_record": record,
            "related_topics": [TOPIC],
            "related_claims": [CLAIM],
            "source_roles": ["applied_case"],
            "doi_verification": None,
            "market_candidate_sources_ref": a11_ref,
        }],
        "library_queue": [], "citation_only": [], "reserve": [], "excluded": [],
        "coverage_at_approval": [], "accepted_coverage_exceptions": [],
        "final_confirmation": True,
    }
    approved_ref = artifacts.store("g02/source-selection/a07-market-approved.json", approved)
    case_dir = runtime.retrieval_accepted_dir / TASK / "1.0.0" / "market-cases"
    case_dir.mkdir(parents=True, exist_ok=True)
    human_path = case_dir / f"{record['source_id']}.market-case.md"
    human_text = (
        "# Market case\n\n## A11 reviewed market fact\n"
        "The bank disclosed a EUR 4.9 billion loss.\n\n"
        "## A11 didactic significance\n"
        "The case links weak controls to a realized trading loss.\n"
    )
    human_path.write_text(human_text, encoding="utf-8")
    machine_path = case_dir / f"{record['source_id']}.market-case.json"
    machine_payload = {
        "schema_version": "untrusted_web_content@1",
        "source_id": record["source_id"],
        "source_url": record["access"]["publisher_url"],
        "content_boundary": "untrusted_external_research",
        "content": "Bounded external content only.",
        "content_sha256": hashlib.sha256(b"Bounded external content only.").hexdigest(),
    }
    machine_path.write_text(json.dumps(machine_payload), encoding="utf-8")
    corpus = {
        "schema_version": "retrieved_corpus@1", "artifact_version": "1.0.0",
        "task_id": TASK,
        "approved_source_set_ref": approved_ref,
        "approved_source_set_artifact_version": "1.0.0",
        "candidate_source_index_ref": index_ref,
        "run_directory_ref": oa_retrieval.corpus_ref(case_dir.parent, runtime),
        "documents": [],
        "market_cases": [{
            "source_id": record["source_id"], "status": "accepted",
            "file_type": "market_case_bundle",
            "source_title": record["bibliographic"]["title"],
            "source_url": record["access"]["publisher_url"],
            "human_document_ref": oa_retrieval.corpus_ref(human_path, runtime),
            "human_document_sha256": hashlib.sha256(human_path.read_bytes()).hexdigest(),
            "machine_artifact_ref": oa_retrieval.corpus_ref(machine_path, runtime),
            "machine_artifact_sha256": hashlib.sha256(machine_path.read_bytes()).hexdigest(),
            "local_ref": oa_retrieval.corpus_ref(machine_path, runtime),
            "sha256": hashlib.sha256(machine_path.read_bytes()).hexdigest(),
            "content_sha256": machine_payload["content_sha256"],
            "content_boundary": "untrusted_external_research",
            "truncated": False,
            "prompt_injection_patterns_detected": [],
            "web_extract_result_ref": "artifact://g02/web-case-extract-results/a07-market.json",
            "market_candidate_sources_ref": a11_ref,
            "source_selection_ref": approved["source_selection_ref"],
        }],
        "unavailable": [], "failed": [],
        "skipped_actions": {"library": [], "citation": [], "reserve": [], "excluded": []},
        "attempt_log": [],
        "retrieval_summary": {
            "approved_download_count": 1, "validated_document_count": 0,
            "market_case_count": 1, "market_case_human_document_count": 1,
            "market_case_machine_artifact_count": 1, "unavailable_count": 0,
            "failed_count": 0, "network_attempt_count": 0,
        },
        "policy": {}, "review_profile_ref": "retrieved_corpus",
    }
    return artifacts.store("g02/retrieved-corpora/a07-market-corpus.json", corpus), record["source_id"]


def test_document_text_index_and_bounded_window_for_pdf_fixture():
    corpus_ref, source_id = _scholarly_corpus()
    index = paper_review.build_document_text_index(corpus_ref, source_id, config_path=CONFIG)
    assert index["source_id"] == source_id
    assert index["schema_version"] == "document_text_index@1"
    assert index["section_map"]
    window = paper_review.document_text_window(
        index["artifact_ref"],
        query_terms=["Hamiltonian Monte Carlo", CLAIM],
        max_chars=500,
        config_path=CONFIG,
    )
    assert window["schema_version"] == "document_text_window@1"
    assert len(window["text"]) <= 500
    assert "Hamiltonian Monte Carlo" in window["text"]


def test_a07_finalizes_one_pdf_and_rejects_fabricated_location():
    corpus_ref, source_id = _scholarly_corpus()
    prepared = paper_review.prepare_paper_review(
        corpus_ref, source_id, config_path=CONFIG, artifact_base=None
    )
    assert prepared["ready"], prepared.get("envelope")
    section_id = prepared["paper_review_input"]["section_map"][0]["section_id"]
    output = {
        "source_id": source_id,
        "relevance_to_lecture": "Supports the Bayesian computation sequence.",
        "limitations": "Fixture PDF has sparse extractable text.",
        "contribution": "Conceptual source on Hamiltonian Monte Carlo.",
        "method_or_source_basis": "Conceptual exposition.",
        "evidence_cards": [{
            "evidence_id": "EV_A07_001",
            "source_id": source_id,
            "topic_ids": [TOPIC],
            "claim_ids": [CLAIM],
            "relation": "contextualizes",
            "summary": "HMC is presented as efficient posterior sampling.",
            "locations": [{"section_id": section_id,
                           "document_ref": prepared["paper_review_input"]["reviewed_document_ref"]}],
            "confidence": "medium",
        }],
        "review_status": "partial",
        "confidence": "medium",
    }
    envelope = paper_review.finalize_paper_review(prepared["paper_review_input"], output)
    assert envelope["status"] == "degraded"
    bad = copy.deepcopy(output)
    bad["evidence_cards"][0]["locations"][0]["section_id"] = "SEC_999_FAKE"
    rejected = paper_review.finalize_paper_review(prepared["paper_review_input"], bad)
    assert rejected["status"] == "failed"
    assert "fabricated" in rejected["issues"][0]["message"]


def test_prompt_injection_flags_trigger_a07_conditional_review_metrics():
    corpus_ref, source_id = _scholarly_corpus()
    index = paper_review.build_document_text_index(corpus_ref, source_id, config_path=CONFIG)
    index["prompt_injection_flags"] = ["ignore previous"]
    index_ref = artifacts.store("g02/document-text-index/a07-injected.json", index)
    prepared = paper_review.prepare_paper_review(
        corpus_ref, source_id, text_index_ref=index_ref, config_path=CONFIG,
        artifact_base=None
    )
    output = {
        "source_id": source_id,
        "relevance_to_lecture": "Insufficient after safety flag.",
        "limitations": "Prompt-injection-like text is present.",
        "contribution": "Unsafe fixture.",
        "method_or_source_basis": "Bounded window.",
        "evidence_cards": [],
        "review_status": "insufficient",
        "confidence": "low",
    }
    envelope = paper_review.finalize_paper_review(prepared["paper_review_input"], output)
    assert envelope["status"] == "degraded"
    assert envelope["metrics"]["prompt_injection_flag_count"] == 1


def test_a07_market_case_uses_a06_bundle_and_reviewed_a11_without_network():
    corpus_ref, source_id = _market_corpus()
    prepared = paper_review.prepare_paper_review(
        corpus_ref, source_id, config_path=CONFIG, artifact_base=None
    )
    assert prepared["ready"], prepared.get("envelope")
    assert prepared["paper_review_input"]["source_kind"] == "market_case"
    assert prepared["paper_review_input"]["market_case_annotation"]["source_id"] == source_id
    assert prepared["paper_review_input"]["market_machine_summary"]["source_id"] == source_id
    assert prepared["paper_review_input"]["review_budget"]["max_windows_total"] == 4
    window = prepared["paper_review_input"]["suggested_windows"][0]
    assert "EUR 4.9 billion" in window["text"]
    output = {
        "source_id": source_id,
        "relevance_to_lecture": "Market case signal for risk-control discussion.",
        "limitations": "Market case is not a scientific claim verification.",
        "contribution": "Shows an applied loss event.",
        "method_or_source_basis": "Reviewed A11 annotation plus A06 market-case bundle.",
        "evidence_cards": [{
            "evidence_id": "EV_A07_MARKET_001",
            "source_id": source_id,
            "topic_ids": [TOPIC],
            "claim_ids": [CLAIM],
            "relation": "contextualizes",
            "summary": "The case links weak controls to a trading loss.",
            "locations": [{"section_id": prepared["paper_review_input"]["section_map"][0]["section_id"],
                           "document_ref": prepared["paper_review_input"]["reviewed_document_ref"]}],
            "confidence": "medium",
        }],
        "review_status": "sufficient",
        "confidence": "medium",
    }
    envelope = paper_review.finalize_paper_review(prepared["paper_review_input"], output)
    assert envelope["status"] == "ok"
