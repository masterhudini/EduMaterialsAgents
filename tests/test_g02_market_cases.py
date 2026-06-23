"""Offline contracts and deterministic behavior planned for the G02-A11 test environment."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from core import artifacts, contracts  # noqa: E402
from g02 import market_cases, provider_config, query_planning, web_cases  # noqa: E402
from mcp import research_server as srv  # noqa: E402

MOCKS = ROOT / "mocks" / "g02"
CONFIG = MOCKS / "web_provider_config.json"
TOPIC_ID = "TOPIC_DERIVATIVES_OPTIONS"


@pytest.fixture(autouse=True)
def _runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("EMAGENTS_HOME", str(tmp_path / ".emagents"))
    monkeypatch.setenv("EMAGENTS_RESEARCH_CONFIG", str(CONFIG))
    monkeypatch.setenv("TAVILY_API_KEY", "tavily-test-secret")
    # Pin the deterministic market-case mechanics tests to the declared config
    # limits instead of the global fast execution profile (default), which caps
    # web fan-out (max_queries_per_task=4, max_results_per_query=5) and would
    # starve this fixture's three-route auto_budgeted plan. Fast-limit application
    # is asserted separately in test_g02_domain.py.
    monkeypatch.setenv("EMAGENTS_G02_PROFILE", "strict")
    monkeypatch.delenv("EMAGENTS_RESEARCH_CONTACT_EMAIL", raising=False)
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _transport(url, headers, timeout, max_bytes, *, method, body):
    assert timeout > 0
    if "search.admin.example" in url:
        payload = (MOCKS / "provider_responses" / "searxng.json").read_bytes()
        assert method == "GET" and body is None and "format=json" in url
        request_id = "REQ-SEARX-MOCK"
    elif url == web_cases.TAVILY_SEARCH_ENDPOINT:
        payload = (MOCKS / "provider_responses" / "tavily.json").read_bytes()
        assert method == "POST" and b"tavily-test-secret" in body
        request_id = "REQ-TAVILY-MOCK"
    elif url == web_cases.TAVILY_EXTRACT_ENDPOINT:
        payload = (MOCKS / "provider_responses" / "tavily_extract.json").read_bytes()
        assert method == "POST" and b"tavily-test-secret" in body
        request_id = "REQ-TAVILY-EXTRACT-MOCK"
    else:
        raise AssertionError(f"unexpected URL {url}")
    assert len(payload) < max_bytes
    return {
        "status_code": 200,
        "headers": {"content-type": "application/json", "x-request-id": request_id},
        "body": payload,
        "final_url": url,
    }


def _prepared():
    plan = _json(MOCKS / "market_research_plan.json")
    domain_pool = _json(MOCKS / "market_domain_candidate_sources.json")
    plan_ref = artifacts.store(
        "g02/research-plans/RESEARCH_MARKET_MOCK_001.1.0.0.json", plan
    )
    assert plan_ref == domain_pool["research_plan_ref"]
    domain_ref = artifacts.store(
        "g02/domain-candidates/RESEARCH_MARKET_MOCK_001."
        "TOPIC_DERIVATIVES_OPTIONS.1.0.0.json",
        domain_pool,
    )
    prepared = market_cases.prepare_market_cases(
        plan_ref, domain_ref, TOPIC_ID, config_path=CONFIG
    )
    assert prepared["ready"], prepared.get("envelope")
    return prepared


def _operations(prepared):
    plan = _json(MOCKS / "web_case_query_plan.json")
    results = [
        web_cases.search_web_cases(
            plan, prepared["market_case_input"], route_id=route["route_id"],
            provider="auto_budgeted", config_path=CONFIG, transport=_transport,
        )
        for route in plan["routes"]
    ]
    assert all(item["status"] == "ok" for item in results)
    return plan, results


def _operation_entry(result):
    return {
        "operation_id": result["operation_id"],
        "operation_type": "web_case_search",
        "provider": result["provider"],
        "status": result["status"],
        "result_count": len(result["records"]),
        "web_case_tool_result_ref": result["artifact_ref"],
        "route_id": result["request"]["route_id"],
        "query_id": result["request"]["query_id"],
    }


def _annotation(record):
    coverage = ["COV_OPTIONS_RISK_FAILURE"]
    snippet = record["content_available"]["abstract"]
    assert "Societe Generale" in snippet and "EUR 4.9 billion loss" in snippet
    return {
        "source_id": record["source_id"],
        "role_assignments": [
            {
                "role": "applied_case", "confidence": "high",
                "observed_signals": ["dated institutional loss in a provider snippet"],
                "access_basis": "search_snippet", "topic_ids": [TOPIC_ID],
                "claim_ids": ["CLM_OPTIONS_CONTROL_RISK"],
                "coverage_unit_ids": coverage,
            },
            {
                "role": "qualifying_or_critical", "confidence": "high",
                "observed_signals": ["unauthorized derivatives positions and control failure"],
                "access_basis": "search_snippet", "topic_ids": [TOPIC_ID],
                "claim_ids": ["CLM_OPTIONS_CONTROL_RISK"],
                "coverage_unit_ids": coverage,
            },
        ],
        "case_identity": {
            "institution_or_event": "Societe Generale",
            "event_label": "Unauthorized derivatives positions and resulting loss",
            "event_date": "2008-01-24",
            "observed_basis": [
                {"source_field": "snippet", "evidence_text": "Societe Generale",
                 "explanation": "named institution"},
                {"source_field": "provider_date", "evidence_text": "2008-01-24",
                 "explanation": "provider-supplied date"},
            ],
        },
        "evidence_type": {
            "value": "control_failure",
            "basis": [{"source_field": "snippet",
                       "evidence_text": "unauthorized equity-index derivatives positions",
                       "explanation": "observed mechanism"}],
        },
        "source_assessment": {
            "source_tier": "tier_2_reputable_media", "weakly_sourced": False,
            "corroborating_source_ids": [], "tier_basis": "reuters.com tier policy",
        },
        "materiality_assessment": {
            "scale_observed": True, "real_consequence_observed": True,
            "higher_tier_confirmation": True, "passes_threshold": True,
            "basis": [{"source_field": "snippet", "evidence_text": "EUR 4.9 billion loss",
                       "explanation": "scale and realized consequence"}],
        },
        "market_fact": {
            "statement": "The bank disclosed a EUR 4.9 billion loss after the positions were unwound.",
            "basis": [{"source_field": "snippet", "evidence_text": "EUR 4.9 billion loss",
                       "explanation": "provider-observed loss"}],
        },
        "didactic_interpretation": {
            "mechanism": "The case illustrates how derivatives exposure and weak controls can turn modelled market risk into a realized institutional loss.",
            "topic_ids": [TOPIC_ID], "claim_ids": ["CLM_OPTIONS_CONTROL_RISK"],
        },
        "documentation_status": "documented",
        "regime_context": {
            "status": "historical_regime",
            "note": "The 2008 event must be taught with the controls and regulatory regime then in force.",
            "basis": "event date predates the current regime by more than ten years",
        },
        "coverage_unit_ids": coverage,
        "quality_status": "not_assessed",
        "doi_status": "absent",
    }


def _output(prepared):
    query_plan, results = _operations(prepared)
    failure = next(item for item in results
                   if item["request"]["route_id"] == "ROUTE_OPTIONS_FAILURE_CASE")
    record = next(item for item in failure["records"]
                  if item["provenance"]["source_apis"] == ["searxng"]
                  and item["access"]["publisher_url"] ==
                  "https://www.reuters.com/markets/societe-generale-kerviel-2008")
    output = {
        "schema_version": "candidate_sources@1", "artifact_version": "1.0.0",
        "stream": "market_cases", "task_id": prepared["market_case_input"]["task_id"],
        "topic_id": TOPIC_ID,
        "research_plan_ref": prepared["market_case_input"]["research_plan_ref"],
        "upstream_refs": {
            "domain_candidate_sources": prepared["market_case_input"]["domain_candidates_ref"]
        },
        "query_plan": query_plan,
        "candidates": [copy.deepcopy(record)],
        "market_case_annotations": [_annotation(record)],
        "operation_log": [_operation_entry(item) for item in results],
        "coverage_map": [{
            "source_id": record["source_id"],
            "coverage_unit_ids": ["COV_OPTIONS_RISK_FAILURE"],
            "basis": "search_snippet",
        }],
        "remaining_coverage_units": ["COV_OPTIONS_APPLIED_USE"],
        "provider_issues": [], "unresolved_seed_ids": [],
        "stop_reason": "partial_coverage", "review_profile_ref": "market_cases",
    }
    return output


def test_market_contracts_config_and_scoped_prepare():
    for ref in (
        "market_case_research_input@1", "web_case_tool_result@1",
        "web_case_extract_result@1", "human_source_selection@1",
    ):
        assert contracts.load_schema(ref)["x-major"] == 1
    assert contracts.load_schema("source_record@1")["x-version"] == "1.2"
    status = provider_config.provider_status(CONFIG)
    assert status["ok"]
    assert status["web"]["mode"] == "auto_budgeted"
    assert all("endpoint" not in item for item in status["web"]["capabilities"])
    prepared = _prepared()
    scoped = prepared["market_case_input"]
    assert market_cases.validate_market_case_basis(scoped, config_path=CONFIG)["ok"]
    assert "domain_candidates" not in scoped
    assert scoped["linked_claim_ids"] == [
        "CLM_OPTIONS_HEDGING", "CLM_OPTIONS_CONTROL_RISK"
    ]
    assert "tavily-test-secret" not in json.dumps(scoped)
    assert "search.admin.example" not in json.dumps(scoped)


def test_market_query_plan_and_auto_budgeted_provider_result():
    prepared = _prepared()
    plan, results = _operations(prepared)
    assert query_planning.validate_query_plan(plan, prepared["market_case_input"])["ok"]
    result = results[-1]
    assert result["schema_version"] == "web_case_tool_result@1"
    assert [item["provider"] for item in result["provenance"]["provider_runs"]] == [
        "searxng", "tavily"
    ]
    assert all(item["record_type"] == "market_case" for item in result["records"])
    assert all(item["web_case"]["event_date"] is None for item in result["records"])
    assert any(item["web_case"]["provider_date"] for item in result["records"])
    assert "tavily-test-secret" not in json.dumps(result)


def test_market_finalize_review_and_mcp_parity():
    prepared = _prepared()
    output = _output(prepared)
    validation = market_cases.validate_market_case_candidates(
        output, prepared["market_case_input"], config_path=CONFIG
    )
    assert validation["ok"], validation["issues"]
    assert not validation["complete"]
    envelope = market_cases.finalize_market_case_candidates(
        prepared["market_case_input"], output, config_path=CONFIG
    )
    assert envelope["status"] == "degraded"
    task = market_cases.build_market_case_review_task(
        prepared["market_case_input"], envelope["produced"][0],
        review_id="REV_A11_001", config_path=CONFIG,
    )
    assert [item["criterion_id"] for item in task["acceptance_criteria"]] == [
        "MC-01", "MC-02", "MC-03", "MC-04", "MC-05", "MC-06"
    ]
    prepare_call = srv.handle({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "research_market_cases_prepare", "arguments": {
            "research_plan_ref": prepared["market_case_input"]["research_plan_ref"],
            "domain_candidates_ref": prepared["market_case_input"]["domain_candidates_ref"],
            "topic_id": TOPIC_ID,
        }},
    })
    assert json.loads(prepare_call["result"]["content"][0]["text"])["ready"]


def test_validator_rejects_modified_record_scope_and_fabricated_observation():
    prepared = _prepared()
    output = _output(prepared)
    output["candidates"][0]["bibliographic"]["title"] = "Fabricated title"
    output["market_case_annotations"][0]["case_identity"]["observed_basis"][0][
        "evidence_text"
    ] = "institution absent from provider data"
    first_ref = output["operation_log"][0]["web_case_tool_result_ref"]
    forged = artifacts.hydrate(first_ref)
    forged["request"]["scope"]["domain_candidates_ref"] = "artifact://other/a02.json"
    output["operation_log"][0]["web_case_tool_result_ref"] = artifacts.store(
        "g02/web-case-results/forged-scope.json", forged
    )
    validation = market_cases.validate_market_case_candidates(
        output, prepared["market_case_input"], config_path=CONFIG
    )
    codes = {item["type"] for item in validation["issues"]}
    assert "market_provider_record_modified" in codes
    assert "unsupported_market_case_identity" in codes
    assert "market_operation_scope_mismatch" in codes


def test_agent_cannot_supply_searxng_endpoint_or_cross_origin_redirect():
    prepared = _prepared()
    forged = copy.deepcopy(prepared["market_case_input"])
    forged["searxng_endpoint"] = "https://random-public.example/search"
    assert not market_cases.validate_market_case_input(forged)["ok"]

    plan = _json(MOCKS / "web_case_query_plan.json")

    def redirected(url, headers, timeout, max_bytes, *, method, body):
        response = _transport(url, headers, timeout, max_bytes, method=method, body=body)
        if "search.admin.example" in url:
            response["final_url"] = "https://attacker.example/search"
        return response

    result = web_cases.search_web_cases(
        plan, prepared["market_case_input"], route_id="ROUTE_OPTIONS_FAILURE_CASE",
        provider="auto_budgeted", config_path=CONFIG, transport=redirected,
    )
    assert result["status"] == "partial"
    assert "cross_origin_redirect_blocked" in {item["code"] for item in result["issues"]}

    def changed_path(url, headers, timeout, max_bytes, *, method, body):
        response = _transport(url, headers, timeout, max_bytes, method=method, body=body)
        if url == web_cases.TAVILY_SEARCH_ENDPOINT:
            response["final_url"] = web_cases.TAVILY_EXTRACT_ENDPOINT
        return response

    result = web_cases.search_web_cases(
        plan, prepared["market_case_input"], route_id="ROUTE_OPTIONS_COMPLEMENTARY_CASE",
        provider="auto_budgeted", config_path=CONFIG, transport=changed_path,
    )
    assert result["status"] == "partial"
    assert "provider_redirect_target_mismatch" in {
        item["code"] for item in result["issues"]
    }


def test_response_limit_and_pre_gate_extraction_are_enforced():
    prepared = _prepared()
    plan = _json(MOCKS / "web_case_query_plan.json")

    def oversized(url, headers, timeout, max_bytes, *, method, body):
        if "search.admin.example" in url:
            return {
                "status_code": 200, "headers": {"content-type": "application/json"},
                "body": b"{" + b" " * (max_bytes + 1) + b"}", "final_url": url,
            }
        return _transport(url, headers, timeout, max_bytes, method=method, body=body)

    result = web_cases.search_web_cases(
        plan, prepared["market_case_input"], route_id="ROUTE_OPTIONS_FAILURE_CASE",
        provider="auto_budgeted", config_path=CONFIG, transport=oversized,
    )
    assert "web_response_too_large" in {item["code"] for item in result["issues"]}

    output = _output(prepared)
    envelope = market_cases.finalize_market_case_candidates(
        prepared["market_case_input"], output, config_path=CONFIG
    )
    candidate_ref = envelope["produced"][0]["path"]
    source_id = output["candidates"][0]["source_id"]
    selection_ref = artifacts.store("g02/source-selection/not-confirmed.json", {
        "schema_version": "human_source_selection@1", "artifact_version": "1.0.0",
        "task_id": output["task_id"],
        "candidate_source_index_ref": "artifact://g02/index/mock.json",
        "status": "approved", "approved_for_download": [source_id],
        "keep_citation_only": [], "request_library_access": [], "keep_in_reserve": [],
        "excluded": [], "requested_search_extensions": [], "coverage_exceptions": [],
        "human_notes": None, "final_confirmation": False,
    })
    extracted = web_cases.extract_web_case(
        selection_ref, candidate_ref, source_id, config_path=CONFIG, transport=_transport
    )
    assert extracted["status"] == "failed"
    assert extracted["issues"][0]["code"] == "web_extract_authorization_failed"

    missing_index_ref = artifacts.store("g02/source-selection/missing-index.json", {
        "schema_version": "human_source_selection@1", "artifact_version": "1.0.0",
        "task_id": output["task_id"],
        "candidate_source_index_ref": "artifact://g02/index/absent.json",
        "status": "approved", "approved_for_download": [source_id],
        "keep_citation_only": [], "request_library_access": [], "keep_in_reserve": [],
        "excluded": [], "requested_search_extensions": [], "coverage_exceptions": [],
        "human_notes": None, "final_confirmation": True,
    })
    extracted = web_cases.extract_web_case(
        missing_index_ref, candidate_ref, source_id,
        config_path=CONFIG, transport=_transport,
    )
    assert extracted["status"] == "failed"
    assert extracted["issues"][0]["code"] == "web_extract_authorization_failed"


def test_post_gate_extraction_returns_bounded_untrusted_artifact():
    prepared = _prepared()
    output = _output(prepared)
    envelope = market_cases.finalize_market_case_candidates(
        prepared["market_case_input"], output, config_path=CONFIG
    )
    candidate_ref = envelope["produced"][0]["path"]
    source_id = output["candidates"][0]["source_id"]
    review_document_ref = artifacts.store_text(
        "g02/index/mock-review.md", "DOWNLOAD: SRC_...\nFINAL_CONFIRMATION: yes\n"
    )
    record = output["candidates"][0]
    index_ref = artifacts.store("g02/index/mock.json", {
        "schema_version": "candidate_source_index@1", "artifact_version": "1.0.0",
        "task_id": output["task_id"], "research_plan_ref": output["research_plan_ref"],
        "research_plan_artifact_version": "1.0.0", "output_language": "English",
        "reviewed_upstreams": [], "selection_profile": {},
        "sources": [{
            "source_id": source_id, "record_type": "market_case", "record": record,
            "origin_streams": ["market_cases"], "topic_ids": [TOPIC_ID],
            "claim_ids": ["CLM_OPTIONS_CONTROL_RISK"],
            "role_assignments": [{"role": "applied_case"}],
            "coverage_unit_ids": ["COV_OPTIONS_RISK_FAILURE"],
            "duplicate_source_ids": [], "provenance_records": [],
            "ranking": {"score": 1.0, "rank": 1, "components": {},
                        "recommended_action": "DOWNLOAD", "rationale": ["test fixture"]},
            "human_annotation": {"content_summary": "Reviewed market case.",
                                 "description_basis": "market_case_annotation",
                                 "selection_relevance": "Options control failure.",
                                 "limitations": ["Page not extracted before the gate."],
                                 "basis_excerpt": "EUR 4.9 billion loss"},
            "access_summary": record["access"],
            "signal_summary": {"scientific_quality": "not_assessed"},
        }],
        "displayed_source_ids": [source_id], "reserve_source_ids": [],
        "merge_log": [], "ambiguous_duplicate_groups": [], "coverage_matrix": [],
        "search_summary": {}, "annotation_policy": {},
        "human_review_document_ref": review_document_ref,
        "review_profile_ref": "candidate_index",
    })
    selection_ref = artifacts.store("g02/source-selection/approved.json", {
        "schema_version": "human_source_selection@1", "artifact_version": "1.0.0",
        "task_id": output["task_id"],
        "candidate_source_index_ref": index_ref,
        "status": "approved", "approved_for_download": [source_id],
        "keep_citation_only": [], "request_library_access": [], "keep_in_reserve": [],
        "excluded": [], "requested_search_extensions": [], "coverage_exceptions": [],
        "human_notes": None, "final_confirmation": True,
    })
    extracted = web_cases.extract_web_case(
        selection_ref, candidate_ref, source_id, config_path=CONFIG, transport=_transport
    )
    assert extracted["status"] == "ok"
    assert "content" not in extracted
    descriptor = extracted["content_artifact"]
    assert descriptor["content_boundary"] == "untrusted_external_research"
    stored = artifacts.hydrate(descriptor["ref"])
    assert stored["source_id"] == source_id
    assert stored["content_sha256"] == descriptor["content_sha256"]


def test_revision_preserves_untargeted_fields():
    prepared = _prepared()
    output = _output(prepared)
    first = market_cases.finalize_market_case_candidates(
        prepared["market_case_input"], output, config_path=CONFIG
    )
    finding = [{
        "finding_id": "F_MC_001",
        "location": "market_case_annotations[0].regime_context",
        "required_correction": "Clarify the historical regime basis.",
    }]
    revised_prepared = market_cases.prepare_market_cases(
        prepared["market_case_input"]["research_plan_ref"],
        prepared["market_case_input"]["domain_candidates_ref"], TOPIC_ID,
        config_path=CONFIG, previous_candidates_ref=first["produced"][0]["path"],
        revision_items=finding,
    )
    revised = copy.deepcopy(output)
    revised["artifact_version"] = "1.1.0"
    revised["market_case_annotations"][0]["regime_context"]["note"] = (
        "The event occurred in 2008; use the then-applicable controls and regulation."
    )
    validation = market_cases.validate_market_case_candidates(
        revised, revised_prepared["market_case_input"], config_path=CONFIG,
        previous_candidates=revised_prepared["previous_candidates"],
        revision_items=finding,
    )
    assert validation["ok"], validation["issues"]


def test_revision_rejects_unknown_target_and_unscoped_change():
    prepared = _prepared()
    output = _output(prepared)
    first = market_cases.finalize_market_case_candidates(
        prepared["market_case_input"], output, config_path=CONFIG
    )
    finding = [{
        "finding_id": "F_MC_UNKNOWN",
        "location": "unsupported_section.note",
        "required_correction": "Change a field outside the A11 output contract.",
    }]
    revised_prepared = market_cases.prepare_market_cases(
        prepared["market_case_input"]["research_plan_ref"],
        prepared["market_case_input"]["domain_candidates_ref"], TOPIC_ID,
        config_path=CONFIG, previous_candidates_ref=first["produced"][0]["path"],
        revision_items=finding,
    )
    revised = copy.deepcopy(output)
    revised["artifact_version"] = "1.1.0"
    revised["stop_reason"] = "candidate_limit"
    validation = market_cases.validate_market_case_candidates(
        revised, revised_prepared["market_case_input"], config_path=CONFIG,
        previous_candidates=revised_prepared["previous_candidates"],
        revision_items=finding,
    )
    codes = {item["type"] for item in validation["issues"]}
    assert "invalid_market_revision_target" in codes
    assert "unscoped_market_revision_change" in codes
