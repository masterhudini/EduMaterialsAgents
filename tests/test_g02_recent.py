"""Deterministic G02-A04 Recent Developments vertical-slice tests."""
from __future__ import annotations

import copy
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from core import artifacts, contracts  # noqa: E402
from g02 import citations, planner, providers, query_planning, recent  # noqa: E402
from mcp import research_server as srv  # noqa: E402

MOCKS = ROOT / "mocks" / "g02"
TOPIC_ID = "TOPIC_BAYESIAN_COMPUTATION"
SEED_ID = "SRC_OPENALEX_4FBB7A48C33F038E"


@pytest.fixture(autouse=True)
def _runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("EMAGENTS_HOME", str(tmp_path / ".emagents"))
    monkeypatch.setenv("EMAGENTS_RESEARCH_CONTACT_EMAIL", "tests@example.com")
    monkeypatch.setenv("OPENALEX_API_KEY", "openalex-test-key")
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _transport(path: Path):
    body = path.read_bytes()

    def run(url, headers, timeout, max_bytes):
        assert url.startswith("https://")
        assert timeout > 0 and max_bytes > len(body)
        assert "User-Agent" in headers
        return {
            "status_code": 200,
            "headers": {"content-type": "application/json", "x-request-id": "REQ-RECENT"},
            "body": body,
            "final_url": url,
        }

    return run


def _prepared():
    plan = _json(MOCKS / "research_plan.json")
    domain_pool = _json(MOCKS / "domain_candidate_sources.json")
    plan_ref = artifacts.store(
        "g02/research-plans/RESEARCH_MOCK_001.1.0.0.json", plan
    )
    assert plan_ref == domain_pool["research_plan_ref"]
    domain_ref = artifacts.store(
        "g02/domain-candidates/RESEARCH_MOCK_001."
        "TOPIC_BAYESIAN_COMPUTATION.1.0.0.json",
        domain_pool,
    )
    prepared = recent.prepare_recent(plan_ref, domain_ref, TOPIC_ID)
    assert prepared["ready"], prepared.get("envelope")
    return prepared


def _operation_entry(result: dict) -> dict:
    request = result["request"]
    entry = {
        "operation_id": result["operation_id"],
        "operation_type": result["operation_type"],
        "provider": result["provider"],
        "status": result["status"],
        "result_count": len(result["records"]),
        "literature_tool_result_ref": result["artifact_ref"],
    }
    if result["operation_type"] == "metadata_search":
        entry.update({"route_id": request["route_id"], "query_id": request["query_id"]})
    else:
        entry.update({
            "seed_source_id": request["seed_source_id"],
            "relation": request["relation"],
        })
    return entry


def _annotation(record: dict, *, update_class: str, level: str,
                signals: list[dict], roles: list[str]) -> dict:
    coverage = ["COV_BAYESIAN_COST_CONDITIONS", "COV_POSTERIOR_METHODS"]
    assignments = [{
        "role": role,
        "confidence": "high" if role == "current" else "medium",
        "observed_signals": [
            "publication year lies in the frozen window",
            "available abstract maps to approved topic coverage",
        ],
        "access_basis": "abstract",
        "topic_ids": [TOPIC_ID],
        "claim_ids": ["CLM_001"] if role == "claim_specific" else [],
        "coverage_unit_ids": coverage,
    } for role in roles]
    year = record["bibliographic"]["year"]
    work_type = record["bibliographic"]["work_type"]
    preprint = "preprint" if work_type == "preprint" else "not_preprint"
    peer = "preprint" if work_type == "preprint" else "published_unknown"
    return {
        "source_id": record["source_id"],
        "role_assignments": assignments,
        "recency_basis": {
            "publication_year": year,
            "window_year_from": 2022,
            "window_year_to": 2026,
            "within_window": True,
        },
        "publication_status": {
            "preprint_status": preprint,
            "peer_review_status": peer,
            "basis": f"provider work_type={work_type}",
        },
        "maturity_assessment": {"level": level, "observed_signals": signals},
        "update_classification": {
            "class": update_class,
            "basis": ["relevant to approved claims and coverage using available abstract"],
        },
        "citation_relations": [],
        "coverage_unit_ids": coverage,
        "quality_status": "not_assessed",
    }


def _build_output(prepared: dict) -> tuple[dict, list[dict]]:
    recent_input = prepared["recent_input"]
    query_plan = _json(MOCKS / "recent_query_plan.json")
    results = []
    for route in query_plan["routes"]:
        result = providers.search_metadata(
            query_plan, recent_input, route_id=route["route_id"], provider="openalex",
            transport=_transport(MOCKS / "provider_responses" / "openalex_recent.json"),
        )
        assert result["status"] == "ok"
        assert all(item["inclusion"]["pool"] == "recent_metadata"
                   for item in result["records"])
        results.append(result)
    candidates = copy.deepcopy(results[0]["records"])
    first, second = candidates
    annotations = [
        _annotation(
            first, update_class="core_update", level="established",
            roles=["current", "claim_specific"],
            signals=[
                {"signal_type": "review_work_type", "observed_value": "review",
                 "evidence_source": "metadata"},
                {"signal_type": "citation_count", "observed_value": "84",
                 "evidence_source": "metadata"},
                {"signal_type": "abstract_scope", "observed_value": "scalable posterior methods",
                 "evidence_source": "abstract"},
            ],
        ),
        _annotation(
            second, update_class="optional_trend", level="developing",
            roles=["current", "qualifying_or_critical"],
            signals=[
                {"signal_type": "citation_count", "observed_value": "37",
                 "evidence_source": "metadata"},
                {"signal_type": "abstract_scope", "observed_value": "adaptive posterior sampling",
                 "evidence_source": "abstract"},
            ],
        ),
    ]
    coverage = ["COV_BAYESIAN_COST_CONDITIONS", "COV_POSTERIOR_METHODS"]
    output = {
        "schema_version": "candidate_sources@1",
        "artifact_version": "1.0.0",
        "stream": "recent",
        "task_id": recent_input["task_id"],
        "topic_id": TOPIC_ID,
        "research_plan_ref": recent_input["research_plan_ref"],
        "upstream_refs": {"domain_candidate_sources": recent_input["domain_candidates_ref"]},
        "recency_window": copy.deepcopy(recent_input["recency_window"]),
        "query_plan": query_plan,
        "candidates": candidates,
        "recent_annotations": annotations,
        "operation_log": [_operation_entry(result) for result in results],
        "coverage_map": [
            {"source_id": item["source_id"], "coverage_unit_ids": coverage,
             "basis": "abstract"} for item in candidates
        ],
        "remaining_coverage_units": [],
        "provider_issues": [],
        "unresolved_seed_ids": [],
        "stop_reason": "completed",
        "review_profile_ref": "recent_developments",
    }
    return output, results


def test_upstream_and_recent_contracts_are_valid():
    assert contracts.validate(_json(MOCKS / "research_plan.json"), "research_plan@1")["ok"]
    assert contracts.validate(
        _json(MOCKS / "domain_candidate_sources.json"), "domain_candidate_sources@1"
    )["ok"]
    assert contracts.load_schema("recent_research_input@1")["x-major"] == 1
    assert contracts.load_schema("candidate_sources@1")["x-version"] == "1.3"


def test_planner_preserves_intake_recency_policy():
    graph_input = _json(MOCKS / "research_graph_input.json")
    planner_input = planner.scope_planner_input(graph_input)
    plan = _json(MOCKS / "research_plan.json")
    validation = planner.validate_research_plan(plan, planner_input)
    assert validation["ok"], validation["issues"]
    assert plan["approved_research_scope"] == graph_input["approved_research_scope"]


def test_prepare_derives_intake_window_and_excludes_secrets():
    prepared = _prepared()
    scoped = prepared["recent_input"]
    assert recent.validate_recent_basis(scoped)["ok"]
    assert scoped["recency_window"] == {
        "as_of_year": datetime.now(UTC).year,
        "window_years": 5,
        "year_from": 2022,
        "year_to": 2026,
        "basis": "approved_research_scope",
    }
    assert "preprint" in scoped["topic"]["search_strategy"]["work_types"]
    rendered = json.dumps(scoped)
    assert "openalex-test-key" not in rendered
    assert "tests@example.com" not in rendered


def test_prepare_skips_topic_without_current_role():
    plan = _json(MOCKS / "research_plan.json")
    domain_pool = _json(MOCKS / "domain_candidate_sources.json")
    plan_ref = artifacts.store("g02/research-plans/plan.json", plan)
    domain_pool["topic_id"] = "TOPIC_LIKELIHOOD_POSTERIOR_BRIDGE"
    domain_pool["research_plan_ref"] = plan_ref
    domain_ref = artifacts.store("g02/domain-candidates/domain.json", domain_pool)
    prepared = recent.prepare_recent(
        plan_ref, domain_ref, "TOPIC_LIKELIHOOD_POSTERIOR_BRIDGE"
    )
    assert not prepared["ready"] and prepared["skipped"]
    assert prepared["envelope"]["status"] == "ok"


def test_prepare_rejects_mismatched_domain_identity():
    plan = _json(MOCKS / "research_plan.json")
    domain_pool = _json(MOCKS / "domain_candidate_sources.json")
    plan_ref = artifacts.store("g02/research-plans/plan.json", plan)
    domain_pool["task_id"] = "OTHER_TASK"
    domain_ref = artifacts.store("g02/domain-candidates/domain.json", domain_pool)
    prepared = recent.prepare_recent(plan_ref, domain_ref, TOPIC_ID)
    assert not prepared["ready"]
    assert prepared["envelope"]["status"] == "failed"
    assert prepared["envelope"]["issues"][0]["type"] == "recent_upstream_identity_mismatch"


def test_recent_query_plan_and_metadata_search_are_scoped():
    prepared = _prepared()
    query_plan = _json(MOCKS / "recent_query_plan.json")
    assert query_planning.validate_query_plan(query_plan, prepared["recent_input"])["ok"]
    result = providers.search_metadata(
        query_plan, prepared["recent_input"],
        route_id="ROUTE_RECENT_BAYESIAN_CORE", provider="openalex",
        transport=_transport(MOCKS / "provider_responses" / "openalex_recent.json"),
    )
    assert result["status"] == "ok"
    assert len(result["records"]) == 2
    assert all(item["inclusion"]["pool"] == "recent_metadata" for item in result["records"])


def test_recent_citation_expansion_uses_recent_pool():
    prepared = _prepared()
    result = citations.expand_citations(
        prepared["recent_input"], seed_source_id=SEED_ID,
        provider="semantic_scholar", relation="cited_by", limit=2,
        transport=_transport(
            MOCKS / "provider_responses" / "semantic_scholar_recent_cited_by.json"
        ),
    )
    assert result["status"] == "ok"
    assert result["records"][0]["inclusion"]["pool"] == "recent_expansion"
    assert result["records"][0]["bibliographic"]["work_type"] == "preprint"


def test_finalize_and_review_task_happy_path():
    prepared = _prepared()
    output, _ = _build_output(prepared)
    validation = recent.validate_recent_candidates(output, prepared["recent_input"])
    assert validation["ok"], validation["issues"]
    envelope = recent.finalize_recent_candidates(prepared["recent_input"], output)
    assert envelope["status"] == "ok"
    descriptor = envelope["produced"][0]
    assert descriptor["type"] == "candidate_sources"
    task = recent.build_recent_review_task(
        prepared["recent_input"], descriptor, review_id="REV_A04_001"
    )
    assert contracts.validate(task, "review_task@1")["ok"]
    assert task["review_profile"] == "recent_developments"
    assert [item["criterion_id"] for item in task["acceptance_criteria"]] == [
        "RD-01", "RD-02", "RD-03", "RD-04", "RD-05", "RD-06", "RD-07"
    ]


def test_recent_mcp_prepare_finalize_and_review_parity():
    prepared = _prepared()
    args = {
        "research_plan_ref": prepared["recent_input"]["research_plan_ref"],
        "domain_candidates_ref": prepared["recent_input"]["domain_candidates_ref"],
        "topic_id": TOPIC_ID,
    }
    prepare_call = srv.handle({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "research_recent_prepare", "arguments": args},
    })
    prepared_payload = json.loads(prepare_call["result"]["content"][0]["text"])
    assert prepared_payload["ready"]
    output, _ = _build_output(prepared)
    finalize_call = srv.handle({
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {
            "name": "research_recent_finalize",
            "arguments": {**args, "output": output},
        },
    })
    envelope = json.loads(finalize_call["result"]["content"][0]["text"])
    assert envelope["status"] == "ok"
    descriptor = envelope["produced"][0]
    review_call = srv.handle({
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {
            "name": "research_recent_review_task",
            "arguments": {**args, "artifact": descriptor, "review_id": "REV_MCP_A04"},
        },
    })
    review_task = json.loads(review_call["result"]["content"][0]["text"])
    assert review_task["review_profile"] == "recent_developments"


def test_validator_rejects_out_of_window_and_modified_record():
    prepared = _prepared()
    output, _ = _build_output(prepared)
    output["candidates"][0]["bibliographic"]["year"] = 2018
    validation = recent.validate_recent_candidates(output, prepared["recent_input"])
    codes = {item["type"] for item in validation["issues"]}
    assert "recent_provider_metadata_modified" in codes
    assert "recent_candidate_outside_window" in codes
    assert "recent_recency_basis_mismatch" in codes


def test_validator_rejects_tool_result_from_another_scope():
    prepared = _prepared()
    output, _ = _build_output(prepared)
    original_ref = output["operation_log"][0]["literature_tool_result_ref"]
    result = artifacts.hydrate(original_ref)
    result["request"]["scope"]["domain_candidates_ref"] = "artifact://other/domain.json"
    forged_ref = artifacts.store("g02/literature-results/forged-recent-scope.json", result)
    output["operation_log"][0]["literature_tool_result_ref"] = forged_ref
    validation = recent.validate_recent_candidates(output, prepared["recent_input"])
    assert "recent_operation_scope_mismatch" in {
        item["type"] for item in validation["issues"]
    }


def test_validator_rejects_false_maturity_peer_status_and_quality():
    prepared = _prepared()
    output, _ = _build_output(prepared)
    annotation = output["recent_annotations"][0]
    annotation["publication_status"]["peer_review_status"] = "preprint"
    annotation["maturity_assessment"]["observed_signals"][1]["observed_value"] = "9999"
    annotation["maturity_assessment"]["observed_signals"][0][
        "evidence_source"
    ] = "abstract"
    annotation["quality_status"] = "high_quality"
    validation = recent.validate_recent_candidates(output, prepared["recent_input"])
    codes = {item["type"] for item in validation["issues"]}
    assert "recent_publication_status_mismatch" in codes
    assert "unsupported_recent_maturity_signal" in codes
    assert "recent_quality_conflation" in codes


def test_unknown_work_type_keeps_publication_status_unknown():
    record = {"bibliographic": {"work_type": None}}
    assert recent._expected_publication_status(record) == ("unknown", "unknown")


def test_preprint_cannot_be_core_update():
    prepared = _prepared()
    output, _ = _build_output(prepared)
    citation = citations.expand_citations(
        prepared["recent_input"], seed_source_id=SEED_ID,
        provider="semantic_scholar", relation="cited_by", limit=2,
        transport=_transport(
            MOCKS / "provider_responses" / "semantic_scholar_recent_cited_by.json"
        ),
    )
    record = copy.deepcopy(citation["records"][0])
    output["candidates"].append(record)
    annotation = _annotation(
        record, update_class="core_update", level="established", roles=["current"],
        signals=[
            {"signal_type": "citation_count", "observed_value": "9",
             "evidence_source": "metadata"},
            {"signal_type": "abstract_scope", "observed_value": "recent HMC",
             "evidence_source": "abstract"},
        ],
    )
    annotation["citation_relations"] = [{
        "seed_source_id": SEED_ID,
        "relation": "cited_by",
        "distance": 1,
        "provider": "semantic_scholar",
        "operation_id": citation["operation_id"],
    }]
    output["recent_annotations"].append(annotation)
    output["operation_log"].append(_operation_entry(citation))
    output["coverage_map"].append({
        "source_id": record["source_id"],
        "coverage_unit_ids": ["COV_BAYESIAN_COST_CONDITIONS", "COV_POSTERIOR_METHODS"],
        "basis": "abstract",
    })
    validation = recent.validate_recent_candidates(output, prepared["recent_input"])
    assert "unsupported_core_update" in {item["type"] for item in validation["issues"]}


def test_query_window_cannot_be_widened():
    prepared = _prepared()
    output, _ = _build_output(prepared)
    output["query_plan"]["routes"][0]["filters"]["year_from"] = 2010
    validation = recent.validate_recent_candidates(output, prepared["recent_input"])
    codes = {item["type"] for item in validation["issues"]}
    assert "recent_query_window_mismatch" in codes
    assert "date_scope_expansion" in codes


def test_modified_recent_scope_is_rejected_before_provider_call():
    prepared = _prepared()
    forged = copy.deepcopy(prepared["recent_input"])
    forged["recency_window"]["year_from"] = 2010
    assert not recent.validate_recent_basis(forged)["ok"]
    result = providers.search_metadata(
        _json(MOCKS / "recent_query_plan.json"), forged,
        route_id="ROUTE_RECENT_BAYESIAN_CORE", provider="openalex",
        transport=_transport(MOCKS / "provider_responses" / "openalex_recent.json"),
    )
    assert result["status"] == "failed"
    assert result["issues"][0]["code"] == "invalid_discovery_input_basis"


def test_revision_preserves_untargeted_fields():
    prepared = _prepared()
    output, _ = _build_output(prepared)
    first = recent.finalize_recent_candidates(prepared["recent_input"], output)
    previous_ref = first["produced"][0]["path"]
    revision_items = [{
        "finding_id": "F_RD_001",
        "location": "recent_annotations[1].update_classification",
        "required_correction": "Clarify optional trend basis.",
    }]
    revised_prepared = recent.prepare_recent(
        prepared["recent_input"]["research_plan_ref"],
        prepared["recent_input"]["domain_candidates_ref"], TOPIC_ID,
        previous_candidates_ref=previous_ref, revision_items=revision_items,
    )
    assert revised_prepared["ready"]
    revised = copy.deepcopy(output)
    revised["artifact_version"] = "1.1.0"
    revised["recent_annotations"][1]["update_classification"]["basis"] = [
        "Available abstract supports relevance; maturity remains developing."
    ]
    validation = recent.validate_recent_candidates(
        revised, revised_prepared["recent_input"],
        previous_candidates=revised_prepared["previous_candidates"],
        revision_items=revision_items,
    )
    assert validation["ok"], validation["issues"]


def test_execute_requires_real_host_executor():
    prepared = _prepared()
    envelope = recent.execute_recent(
        prepared["recent_input"]["research_plan_ref"],
        prepared["recent_input"]["domain_candidates_ref"], TOPIC_ID, None,
    )
    assert envelope["status"] == "failed"
    assert envelope["issues"][0]["type"] == "recent_executor_unavailable"
