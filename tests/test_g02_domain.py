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
from g02 import domain, provider_config, query_planning  # noqa: E402

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
    assert all(route["preferred_providers"] == ["openalex"] for route in plan["routes"])
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
