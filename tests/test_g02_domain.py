"""Repository regression tests for G02-A02 Domain preparation and executor boundary."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from core import artifacts, contracts  # noqa: E402
from g02 import crossref, domain, provider_config, providers, query_planning  # noqa: E402

MOCKS = ROOT / "mocks" / "g02"
TOPIC_ID = "TOPIC_BAYESIAN_COMPUTATION"


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("EMAGENTS_HOME", str(tmp_path / ".emagents"))
    monkeypatch.setenv("EMAGENTS_RESEARCH_CONTACT_EMAIL", "tests@example.com")
    monkeypatch.setenv("OPENALEX_API_KEY", "openalex-test-key")


def _load(name):
    return json.loads((MOCKS / name).read_text(encoding="utf-8"))


def _plan_ref():
    return artifacts.store(
        "g02/research-plans/RESEARCH_MOCK_001.1.0.0.json", _load("research_plan.json")
    )


def test_prepare_projects_one_topic_and_redacts_secrets():
    prepared = domain.prepare_domain(_plan_ref(), TOPIC_ID)
    assert prepared["ready"], prepared.get("envelope")
    scoped = prepared["domain_input"]
    assert contracts.validate(scoped, "domain_research_input@1")["ok"]
    assert scoped["topic"]["topic_id"] == TOPIC_ID
    serialized = json.dumps(scoped)
    assert "openalex-test-key" not in serialized
    assert "tests@example.com" not in serialized


def test_missing_host_executor_is_explicit_failure():
    envelope = domain.execute_domain(_plan_ref(), TOPIC_ID, None)
    assert envelope["status"] == "failed"
    assert envelope["produced"] == []
    assert envelope["issues"][0]["type"] == "domain_executor_unavailable"


def test_prepare_fails_before_discovery_when_crossref_is_disabled():
    prepared = domain.prepare_domain(
        _plan_ref(), TOPIC_ID, config_path=MOCKS / "web_provider_config.json"
    )
    assert prepared["ready"] is False
    assert prepared["envelope"]["status"] == "failed"
    assert prepared["envelope"]["issues"][0]["type"] == "crossref_not_ready"


def test_fast_query_plan_generator_uses_bounded_ready_provider():
    prepared = domain.prepare_domain(_plan_ref(), TOPIC_ID)
    generated = query_planning.generate_fast_query_plan(
        prepared["domain_input"],
        {"discovery": {
            "max_routes_per_topic": 3,
            "default_provider": "openalex",
            "max_records_per_query": 8,
            "route_limit": 8,
        }},
    )
    assert generated["ready"], generated
    plan = generated["query_plan"]
    assert len(plan["routes"]) <= 3
    assert all(route["preferred_providers"][:2] == [
        "openalex", "semantic_scholar"
    ] for route in plan["routes"])
    assert all("arxiv" in route["preferred_providers"] for route in plan["routes"])
    assert all(route["limit"] <= 8 for route in plan["routes"])
    assert query_planning.validate_query_plan(
        plan, prepared["domain_input"], max_records_per_query=8
    )["ok"]


def test_default_fast_profile_caps_provider_fanout(monkeypatch):
    config = provider_config.load_config(create_dirs=False)
    assert config.data["limits"] == {
        "per_page": 8, "max_pages_per_call": 1, "max_records_per_query": 8,
    }
    assert config.data["web"]["limits"]["max_queries_per_task"] == 4
    assert config.data["web"]["limits"]["max_results_per_query"] == 5
    assert config.data["retrieval"]["limits"]["max_documents_per_task"] == 5

    monkeypatch.setenv("EMAGENTS_G02_PROFILE", "strict")
    strict = provider_config.load_config(create_dirs=False)
    assert strict.data["limits"]["max_records_per_query"] == 12


def _stored_search_results(domain_input, query_plan):
    openalex_item = _load("provider_responses/openalex.json")["results"][0]
    refs = []
    record = None
    for index, route in enumerate(query_plan["routes"]):
        records = []
        if index == 0:
            record = providers._normalize_openalex(
                openalex_item,
                query_id=route["query_id"],
                topic_id=TOPIC_ID,
                raw_ref="artifact://g02/provider-raw/openalex-test.json",
                retrieved_at="2026-06-24T00:00:00Z",
            )
            assert record is not None
            records = [record]
        result = {
            "schema_version": "literature_tool_result@1",
            "operation_id": f"OP_ASSEMBLY_{index}",
            "operation_type": "metadata_search",
            "provider": "openalex",
            "status": "ok",
            "started_at": "2026-06-24T00:00:00Z",
            "completed_at": "2026-06-24T00:00:01Z",
            "request": {
                "route_id": route["route_id"],
                "query_id": route["query_id"],
                "canonical_query": route["canonical_query"],
                "filters": route["filters"],
                "cursor": None,
                "limit": route["limit"],
                "scope": {
                    "input_contract": "domain_research_input@1",
                    "task_id": domain_input["task_id"],
                    "topic_id": TOPIC_ID,
                    "research_plan_ref": domain_input["research_plan_ref"],
                    "domain_candidates_ref": None,
                },
            },
            "records": records,
            "file_descriptors": [],
            "pagination": {"next_cursor": None, "exhausted": True, "pages_processed": 1},
            "provenance": {
                "raw_response_refs": ["artifact://g02/provider-raw/openalex-test.json"],
                "provider_request_ids": [],
                "cache_hit": False,
                "config_profile": "test",
            },
            "issues": [],
        }
        assert contracts.validate(result, "literature_tool_result@1")["ok"]
        refs.append(artifacts.store(f"g02/literature-results/{result['operation_id']}.json", result))
    assert record is not None
    return refs, record


def _stored_doi_verification(record):
    def transport(url, headers, timeout, max_bytes):
        payload = {
            "message": {
                "DOI": record["identifiers"]["doi"],
                "title": [record["bibliographic"]["title"]],
                "author": [{"given": "Michael", "family": "Betancourt"}],
                "published": {"date-parts": [[record["bibliographic"]["year"]]]},
                "container-title": [record["bibliographic"]["venue"]],
                "publisher": record["bibliographic"]["publisher"],
                "type": "journal-article",
            }
        }
        return {
            "status_code": 200,
            "headers": {},
            "body": json.dumps(payload).encode(),
            "final_url": url,
        }

    result = crossref.verify_source_record(
        record, config_path=ROOT / "shared" / "config" / "g02.providers.example.json",
        transport=transport,
    )
    return result["artifact_ref"]


def test_finalize_from_results_builds_technical_fields_and_preserves_provider_record():
    prepared = domain.prepare_domain(_plan_ref(), TOPIC_ID)
    assert prepared["ready"]
    domain_input = prepared["domain_input"]
    query_plan = _load("query_plan.json")
    result_refs, record = _stored_search_results(domain_input, query_plan)
    doi_ref = _stored_doi_verification(record)
    assignments = [{
        "source_id": record["source_id"],
        "coverage_unit_ids": [
            "COV_BAYESIAN_COST_CONDITIONS",
            "COV_POSTERIOR_METHODS",
            "COV_LIKELIHOOD_POSTERIOR_SEQUENCE",
        ],
        "basis": "abstract",
    }]

    envelope = domain.finalize_domain_from_results(
        domain_input, query_plan, result_refs, [doi_ref], assignments,
    )
    assert envelope["status"] == "degraded", envelope
    ref = envelope["produced"][0]["path"]
    output = artifacts.hydrate(ref)
    assert output["candidates"] == [record]
    assert len(output["query_log"]) == len(query_plan["routes"])
    assert output["provider_issues"] == []
    assert output["stop_reason"] == "partial_coverage"
    assert output["remaining_coverage_units"] == [
        "COV_BAYESIAN_COST_CONDITIONS",
        "COV_POSTERIOR_METHODS",
        "COV_LIKELIHOOD_POSTERIOR_SEQUENCE",
    ]
    assert output["doi_verifications"][0] == crossref.descriptor({
        **artifacts.hydrate(doi_ref), "artifact_ref": doi_ref,
    })


def test_finalize_from_results_rejects_foreign_scope_and_missing_doi_binding():
    prepared = domain.prepare_domain(_plan_ref(), TOPIC_ID)
    domain_input = prepared["domain_input"]
    query_plan = _load("query_plan.json")
    result_refs, record = _stored_search_results(domain_input, query_plan)
    foreign = artifacts.hydrate(result_refs[0])
    foreign["request"]["scope"]["topic_id"] = "TOPIC_OTHER"
    result_refs[0] = artifacts.store("g02/literature-results/foreign.json", foreign)
    failed = domain.finalize_domain_from_results(
        domain_input, query_plan, result_refs, [], [],
    )
    assert failed["status"] == "failed"
    assert failed["issues"][0]["type"] == "domain_assembly_failed"

    result_refs, record = _stored_search_results(domain_input, query_plan)
    missing_doi = domain.finalize_domain_from_results(
        domain_input, query_plan, result_refs, [], [{
            "source_id": record["source_id"],
            "coverage_unit_ids": ["COV_POSTERIOR_METHODS"],
            "basis": "title",
        }],
    )
    assert missing_doi["status"] == "failed"
    assert "lack Crossref verification" in missing_doi["issues"][0]["message"]
