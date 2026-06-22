"""Deterministic G02-A03 Canonical Sources vertical-slice tests."""
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
from g02 import canonical, citations, provider_config, providers  # noqa: E402

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
            "headers": {"content-type": "application/json", "x-request-id": "REQ-MOCK"},
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
    prepared = canonical.prepare_canonical(plan_ref, domain_ref, TOPIC_ID)
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


def test_disabled_provider_returns_unavailable_without_request(tmp_path):
    prepared = _prepared()
    query_plan = _json(MOCKS / "query_plan.json")
    config_payload = _json(ROOT / "shared" / "config" / "g02.providers.example.json")
    config_payload["providers"]["openalex"]["enabled"] = False
    config_path = tmp_path / "openalex-disabled.json"
    config_path.write_text(json.dumps(config_payload), encoding="utf-8")
    config = provider_config.load_config(config_path)
    scoped = copy.deepcopy(prepared["canonical_input"])
    scoped["provider_capabilities"] = config.public_status()["capabilities"]

    def no_request(*args, **kwargs):
        raise AssertionError("disabled provider must not execute a request")

    result = providers.search_metadata(
        query_plan, scoped, route_id=query_plan["routes"][0]["route_id"],
        provider="openalex", config_path=config_path, transport=no_request,
    )
    assert result["status"] == "unavailable"
    assert result["issues"][0]["code"] == "provider_disabled"


def _build_output(prepared: dict) -> tuple[dict, list[dict]]:
    canonical_input = prepared["canonical_input"]
    query_plan = _json(MOCKS / "query_plan.json")
    metadata_results = []
    for route in query_plan["routes"]:
        result = providers.search_metadata(
            query_plan,
            canonical_input,
            route_id=route["route_id"],
            provider="openalex",
            transport=_transport(MOCKS / "provider_responses" / "openalex.json"),
        )
        assert result["status"] == "ok"
        metadata_results.append(result)
    citation_result = citations.expand_citations(
        canonical_input,
        seed_source_id=SEED_ID,
        provider="semantic_scholar",
        relation="references",
        limit=5,
        transport=_transport(
            MOCKS / "provider_responses" / "semantic_scholar_citations.json"
        ),
    )
    assert citation_result["status"] == "ok"
    assert len(citation_result["records"]) == 1
    seed = copy.deepcopy(canonical_input["domain_candidates"][0])
    related = copy.deepcopy(citation_result["records"][0])
    coverage = ["COV_BAYESIAN_COST_CONDITIONS", "COV_POSTERIOR_METHODS"]
    output = {
        "schema_version": "candidate_sources@1",
        "artifact_version": "1.0.0",
        "stream": "canonical",
        "task_id": canonical_input["task_id"],
        "topic_id": TOPIC_ID,
        "research_plan_ref": canonical_input["research_plan_ref"],
        "upstream_refs": {
            "domain_candidate_sources": canonical_input["domain_candidates_ref"]
        },
        "query_plan": query_plan,
        "candidates": [seed, related],
        "canonical_annotations": [
            {
                "source_id": seed["source_id"],
                "role_assignments": [{
                    "role": "canonical",
                    "confidence": "high",
                    "observed_signals": [
                        "provider citation count 1200",
                        "review-style methodological scope visible in title and abstract",
                    ],
                    "access_basis": "abstract",
                    "topic_ids": [TOPIC_ID],
                    "coverage_unit_ids": coverage,
                }],
                "canonicality_basis": [
                    {
                        "signal_type": "citation_count",
                        "observed_value": "1200",
                        "evidence_source": "metadata",
                        "explanation": "Provider-observed discovery signal, not a quality verdict.",
                    },
                    {
                        "signal_type": "methodological_anchor",
                        "observed_value": "conceptual HMC treatment",
                        "evidence_source": "abstract",
                        "explanation": "The available abstract exposes methodological scope.",
                    },
                ],
                "citation_relations": [],
                "access_statement": {
                    "access_level": seed["access"]["access_level"],
                    "library_access_required": seed["access"]["library_access_required"],
                    "accessible_surrogate_source_ids": [],
                    "note": "Classification uses metadata and abstract only.",
                },
                "coverage_unit_ids": coverage,
            },
            {
                "source_id": related["source_id"],
                "role_assignments": [{
                    "role": "foundational",
                    "confidence": "high",
                    "observed_signals": [
                        "returned by an approved reference edge",
                        "provider-observed chapter metadata and abstract",
                    ],
                    "access_basis": "abstract",
                    "topic_ids": [TOPIC_ID],
                    "coverage_unit_ids": coverage,
                }],
                "canonicality_basis": [
                    {
                        "signal_type": "citation_relation",
                        "observed_value": f"reference from {SEED_ID}",
                        "evidence_source": "citation_relation",
                        "explanation": "The provider returned a direct one-hop reference edge.",
                    },
                    {
                        "signal_type": "citation_count",
                        "observed_value": "4200",
                        "evidence_source": "metadata",
                        "explanation": "Provider-observed discovery signal, not a quality verdict.",
                    },
                ],
                "citation_relations": [{
                    "seed_source_id": SEED_ID,
                    "relation": "references",
                    "distance": 1,
                    "provider": "semantic_scholar",
                    "operation_id": citation_result["operation_id"],
                }],
                "access_statement": {
                    "access_level": related["access"]["access_level"],
                    "library_access_required": related["access"]["library_access_required"],
                    "accessible_surrogate_source_ids": [],
                    "note": "Closed chapter; classification uses provider metadata and abstract only.",
                },
                "coverage_unit_ids": coverage,
            },
        ],
        "operation_log": [
            *[_operation_entry(result) for result in metadata_results],
            _operation_entry(citation_result),
        ],
        "coverage_map": [
            {"source_id": seed["source_id"], "coverage_unit_ids": coverage,
             "basis": "abstract"},
            {"source_id": related["source_id"], "coverage_unit_ids": coverage,
             "basis": "citation_relation"},
        ],
        "remaining_coverage_units": [],
        "provider_issues": [],
        "unresolved_seed_ids": canonical_input["unresolved_plan_seed_ids"],
        "stop_reason": "unresolved_seed",
        "review_profile_ref": "canonical_sources",
    }
    return output, metadata_results + [citation_result]


def test_contracts_and_mock_domain_are_valid():
    assert contracts.validate(_json(MOCKS / "domain_candidate_sources.json"),
                              "domain_candidate_sources@1")["ok"]
    assert contracts.load_schema("canonical_research_input@1")["x-major"] == 1
    assert contracts.load_schema("candidate_sources@1")["x-version"] == "1.3"


def test_prepare_scopes_reviewed_domain_and_excludes_secrets():
    prepared = _prepared()
    scoped = prepared["canonical_input"]
    assert canonical.validate_canonical_input(scoped)["ok"]
    assert scoped["verified_seed_ids"] == [SEED_ID]
    assert scoped["unresolved_plan_seed_ids"] == ["SRC_EXISTING_001"]
    assert scoped["search_limits"]["citation_depth"] == 1
    rendered = json.dumps(scoped)
    assert "openalex-test-key" not in rendered
    assert "tests@example.com" not in rendered


def test_prepare_rejects_mismatched_upstream_identity():
    plan = _json(MOCKS / "research_plan.json")
    domain_pool = _json(MOCKS / "domain_candidate_sources.json")
    domain_pool["task_id"] = "OTHER_TASK"
    plan_ref = artifacts.store(
        "g02/research-plans/RESEARCH_MOCK_001.1.0.0.json", plan
    )
    domain_ref = artifacts.store("g02/domain-candidates/bad.json", domain_pool)
    prepared = canonical.prepare_canonical(plan_ref, domain_ref, TOPIC_ID)
    assert not prepared["ready"]
    assert prepared["envelope"]["status"] == "failed"


def test_citation_expand_preserves_relation_and_provider_record():
    prepared = _prepared()
    result = citations.expand_citations(
        prepared["canonical_input"], seed_source_id=SEED_ID,
        provider="semantic_scholar", relation="references", limit=5,
        transport=_transport(
            MOCKS / "provider_responses" / "semantic_scholar_citations.json"
        ),
    )
    assert result["status"] == "ok"
    assert result["operation_type"] == "citation_expand"
    assert result["request"]["depth"] == 1
    assert result["request"]["seed_provider_id"].startswith("DOI:")
    assert result["records"][0]["inclusion"]["pool"] == "canonical_expansion"
    assert result["records"][0]["access"]["library_access_required"] is True
    assert result["artifact_ref"].startswith("artifact://")


@pytest.mark.parametrize(("provider", "relation", "fixture"), [
    ("openalex", "cited_by", "openalex.json"),
    ("semantic_scholar", "references", "semantic_scholar_citations.json"),
    ("semantic_scholar", "cited_by", "semantic_scholar_citations_cited_by.json"),
    ("semantic_scholar", "recommendations", "semantic_scholar_recommendations.json"),
])
def test_all_supported_citation_routes_normalize_offline(provider, relation, fixture):
    prepared = _prepared()
    result = citations.expand_citations(
        prepared["canonical_input"], seed_source_id=SEED_ID,
        provider=provider, relation=relation, limit=2,
        transport=_transport(MOCKS / "provider_responses" / fixture),
    )
    assert result["status"] == "ok"
    assert len(result["records"]) == 1
    assert result["request"]["relation"] == relation
    assert result["records"][0]["inclusion"]["reason_included"] == [
        f"citation_{relation}"
    ]
    assert contracts.validate(result["records"][0], "source_record@1")["ok"]


def test_citation_expand_reports_unsupported_and_unapproved_routes():
    prepared = _prepared()
    unsupported = citations.expand_citations(
        prepared["canonical_input"], seed_source_id=SEED_ID,
        provider="arxiv", relation="references", limit=2,
    )
    assert unsupported["status"] == "unavailable"
    assert unsupported["issues"][0]["code"] == "citation_relation_unsupported"
    unapproved = citations.expand_citations(
        prepared["canonical_input"], seed_source_id="SRC_UNKNOWN",
        provider="semantic_scholar", relation="references", limit=2,
    )
    assert unapproved["status"] == "failed"
    assert unapproved["issues"][0]["code"] == "unapproved_citation_seed"


def test_metadata_search_accepts_canonical_scoped_input():
    prepared = _prepared()
    query_plan = _json(MOCKS / "query_plan.json")
    result = providers.search_metadata(
        query_plan, prepared["canonical_input"],
        route_id="ROUTE_BAYESIAN_CORE", provider="openalex",
        transport=_transport(MOCKS / "provider_responses" / "openalex.json"),
    )
    assert result["status"] == "ok"
    assert result["operation_type"] == "metadata_search"
    assert contracts.validate(result["records"][0], "source_record@1")["ok"]


def test_provider_operations_reject_modified_scoped_domain_basis():
    prepared = _prepared()
    forged = copy.deepcopy(prepared["canonical_input"])
    forged["domain_candidates"][0]["bibliographic"]["title"] = "Forged seed title"
    assert not canonical.validate_canonical_basis(forged)["ok"]
    metadata = providers.search_metadata(
        _json(MOCKS / "query_plan.json"), forged,
        route_id="ROUTE_BAYESIAN_CORE", provider="openalex",
        transport=_transport(MOCKS / "provider_responses" / "openalex.json"),
    )
    assert metadata["status"] == "failed"
    assert metadata["issues"][0]["code"] == "invalid_discovery_input_basis"
    citation = citations.expand_citations(
        forged, seed_source_id=SEED_ID, provider="semantic_scholar",
        relation="references", limit=2,
        transport=_transport(
            MOCKS / "provider_responses" / "semantic_scholar_citations.json"
        ),
    )
    assert citation["status"] == "failed"
    assert citation["issues"][0]["code"] == "invalid_canonical_input_basis"


def test_finalize_and_review_task_happy_path():
    prepared = _prepared()
    output, _ = _build_output(prepared)
    validation = canonical.validate_canonical_candidates(
        output, prepared["canonical_input"]
    )
    assert validation["ok"], validation["issues"]
    envelope = canonical.finalize_canonical_candidates(
        prepared["canonical_input"], output
    )
    assert envelope["status"] == "degraded"
    assert envelope["resume_token"] == envelope["produced"][0]["path"]
    assert len(envelope["produced"]) == 1
    descriptor = envelope["produced"][0]
    assert descriptor["type"] == "candidate_sources"
    stored = artifacts.hydrate(descriptor["path"])
    assert stored == output
    task = canonical.build_canonical_review_task(
        prepared["canonical_input"], descriptor, review_id="REV_A03_001"
    )
    assert contracts.validate(task, "review_task@1")["ok"]
    assert task["producer_agent"] == "g02-a03-canonical-sources"
    assert task["review_profile"] == "canonical_sources"
    assert [item["criterion_id"] for item in task["acceptance_criteria"]] == [
        "CS-01", "CS-02", "CS-03", "CS-04", "CS-05", "CS-06"
    ]


def test_validator_rejects_modified_provider_record_and_weak_basis():
    prepared = _prepared()
    output, _ = _build_output(prepared)
    output["candidates"][1]["bibliographic"]["title"] = "Invented title"
    output["canonical_annotations"][0]["canonicality_basis"] = [
        output["canonical_annotations"][0]["canonicality_basis"][0]
    ]
    validation = canonical.validate_canonical_candidates(
        output, prepared["canonical_input"]
    )
    codes = {item["type"] for item in validation["issues"]}
    assert "provider_metadata_modified" in codes
    assert "insufficient_canonicality_basis" in codes


def test_validator_rejects_tool_result_from_another_scope():
    prepared = _prepared()
    output, _ = _build_output(prepared)
    original_ref = output["operation_log"][0]["literature_tool_result_ref"]
    result = artifacts.hydrate(original_ref)
    result["request"]["scope"]["task_id"] = "OTHER_TASK"
    forged_ref = artifacts.store("g02/literature-results/forged-scope.json", result)
    output["operation_log"][0]["literature_tool_result_ref"] = forged_ref
    validation = canonical.validate_canonical_candidates(
        output, prepared["canonical_input"]
    )
    assert "canonical_operation_scope_mismatch" in {
        item["type"] for item in validation["issues"]
    }


def test_domain_authority_requires_exact_approved_seed_and_evidence_type():
    prepared = _prepared()
    output, _ = _build_output(prepared)
    output["canonical_annotations"][0]["canonicality_basis"] = [{
        "signal_type": "domain_authoritative",
        "observed_value": "claimed authority",
        "evidence_source": "metadata",
        "explanation": "A metadata label cannot establish domain authority.",
    }]
    validation = canonical.validate_canonical_candidates(
        output, prepared["canonical_input"]
    )
    codes = {item["type"] for item in validation["issues"]}
    assert "insufficient_canonicality_basis" in codes
    assert "unsupported_canonicality_evidence" in codes


def test_validator_rejects_missing_edge_false_signal_and_excess_access_basis():
    prepared = _prepared()
    output, _ = _build_output(prepared)
    output["canonical_annotations"][1]["citation_relations"] = []
    output["canonical_annotations"][0]["canonicality_basis"][0][
        "observed_value"
    ] = "999999"
    output["canonical_annotations"][0]["role_assignments"][0][
        "access_basis"
    ] = "full_text"
    validation = canonical.validate_canonical_candidates(
        output, prepared["canonical_input"]
    )
    codes = {item["type"] for item in validation["issues"]}
    assert "missing_candidate_citation_provenance" in codes
    assert "unsupported_canonicality_evidence" in codes
    assert "unobserved_citation_count" in codes
    assert "role_access_basis_exceeds_record" in codes


def test_completed_rejects_preserved_unresolved_seed():
    prepared = _prepared()
    output, _ = _build_output(prepared)
    output["stop_reason"] = "completed"
    validation = canonical.validate_canonical_candidates(
        output, prepared["canonical_input"]
    )
    codes = {item["type"] for item in validation["issues"]}
    assert "completed_with_canonical_gaps" in codes
    assert "unresolved_seed_stop_reason_mismatch" in codes


def test_revision_requires_previous_and_preserves_untargeted_fields():
    prepared = _prepared()
    output, _ = _build_output(prepared)
    first = canonical.finalize_canonical_candidates(prepared["canonical_input"], output)
    previous_ref = first["produced"][0]["path"]
    revision_items = [{
        "finding_id": "F_CS_001",
        "location": "canonical_annotations[0].canonicality_basis",
        "required_correction": "Clarify the observed methodological signal.",
    }]
    revised_prepared = canonical.prepare_canonical(
        prepared["canonical_input"]["research_plan_ref"],
        prepared["canonical_input"]["domain_candidates_ref"],
        TOPIC_ID,
        previous_candidates_ref=previous_ref,
        revision_items=revision_items,
    )
    assert revised_prepared["ready"]
    revised = copy.deepcopy(output)
    revised["artifact_version"] = "1.1.0"
    revised["canonical_annotations"][0]["canonicality_basis"][1]["explanation"] = (
        "The provider abstract directly exposes methodological scope."
    )
    validation = canonical.validate_canonical_candidates(
        revised, revised_prepared["canonical_input"],
        previous_candidates=revised_prepared["previous_candidates"],
        revision_items=revision_items,
    )
    assert validation["ok"], validation["issues"]


def test_execute_requires_real_host_executor():
    prepared = _prepared()
    envelope = canonical.execute_canonical(
        prepared["canonical_input"]["research_plan_ref"],
        prepared["canonical_input"]["domain_candidates_ref"],
        TOPIC_ID,
        None,
    )
    assert envelope["status"] == "failed"
    assert envelope["issues"][0]["type"] == "canonical_executor_unavailable"
