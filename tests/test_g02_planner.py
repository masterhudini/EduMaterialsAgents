"""Repository regression tests for G02-A01 Planner."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from core import artifacts, contracts  # noqa: E402
from g02 import planner, review  # noqa: E402

MOCKS = ROOT / "mocks" / "g02"


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("EMAGENTS_HOME", str(tmp_path / ".emagents"))


def _load(name):
    return json.loads((MOCKS / name).read_text(encoding="utf-8"))


def test_prepare_scope_finalize_and_review_task(tmp_path):
    boundary = _load("research_graph_input.json")
    original = copy.deepcopy(boundary)
    prepared = planner.prepare_planner(boundary)
    assert prepared["ready"]
    scoped = prepared["planner_input"]
    assert contracts.validate(scoped, "research_planner_input@1")["ok"]
    assert set(scoped) == set(planner.PLANNER_FIELDS) | {"schema_version", "source_input_contract"}
    assert scoped["constraints"]["max_topics"] == 2
    assert scoped["constraints"]["candidate_limit_per_topic"] == 12
    assert scoped["selection_profile"]["candidate_pool_target_per_topic"] == 8
    assert boundary == original

    envelope = planner.finalize_research_plan(
        scoped, copy.deepcopy(_load("research_plan.json")), base=tmp_path / "store"
    )
    assert envelope["status"] == "ok"
    descriptor = envelope["produced"][0]
    assert descriptor["type"] == "research_plan"
    assert contracts.validate(
        artifacts.hydrate(descriptor["path"], base=tmp_path / "store"), "research_plan@1"
    )["ok"]
    task = planner.build_research_plan_review_task(
        scoped, descriptor, review_id="REV_PLANNER_REPO_001"
    )
    assert review.validate_review_task(task)["ok"]


def test_scout_profile_expands_only_its_scoped_topic_limit():
    boundary = _load("research_graph_input.json")
    original = copy.deepcopy(boundary)

    prepared = planner.prepare_planner(boundary, execution_profile="scout")

    assert prepared["ready"]
    assert prepared["planner_input"]["constraints"]["max_topics"] == 6
    assert prepared["planner_input"]["constraints"]["candidate_limit_per_topic"] == 12
    assert boundary == original


def test_prepare_supplies_exact_plan_output_template():
    prepared = planner.prepare_planner(
        _load("research_graph_input.json"), execution_profile="scout"
    )

    template = prepared["plan_output_template"]
    assert template["artifact_version"] == "1.0.0"
    assert template["global_constraints"]["max_topics"] == 6
    assert set(template["topics"][0]) == {
        "topic_id", "name", "purpose", "priority", "linked_driver_ids",
        "related_claims", "related_concepts", "related_flow_issues",
        "related_update_needs", "approved_domains", "source_roles_required",
        "search_strategy", "coverage_requirements", "stop_rule",
    }
    assert set(template["topics"][0]["coverage_requirements"][0]) == {
        "coverage_id", "description", "source_roles", "minimum_sources", "mandatory"
    }


def test_finalize_normalizes_live_a01_contract_aliases_without_manual_repair(tmp_path):
    prepared = planner.prepare_planner(_load("research_graph_input.json"))
    scoped = prepared["planner_input"]
    plan = _load("research_plan.json")
    plan["artifact_version"] = 1
    plan["task_id"] = "model-must-not-own-this"
    plan["global_constraints"] = {"wrong": True}
    plan["output_language"] = "wrong"
    topic = plan["topics"][0]
    topic["driver_ids"] = topic.pop("linked_driver_ids")
    topic["related_claim_ids"] = topic.pop("related_claims")
    topic["related_concept_ids"] = topic.pop("related_concepts")
    topic["related_flow_issue_ids"] = topic.pop("related_flow_issues")
    topic["related_update_need_ids"] = topic.pop("related_update_needs")
    topic["approved_domain_ids"] = topic.pop("approved_domains")
    topic["required_source_roles"] = [
        role for role, enabled in topic.pop("source_roles_required").items() if enabled
    ]
    topic.pop("stop_rule")
    requirement = topic["coverage_requirements"][0]
    requirement["acceptable_source_roles"] = requirement.pop("source_roles")
    requirement["min_sources"] = requirement.pop("minimum_sources")
    requirement["must_cover"] = requirement.pop("mandatory")

    envelope = planner.finalize_research_plan(scoped, plan, base=tmp_path)

    assert envelope["status"] == "ok"
    stored = artifacts.hydrate(envelope["produced"][0]["path"], base=tmp_path)
    assert contracts.validate(stored, "research_plan@1")["ok"]
    assert stored["artifact_version"] == "1.0.0"
    assert stored["task_id"] == scoped["task_id"]
    normalized_topic = stored["topics"][0]
    assert normalized_topic["linked_driver_ids"]
    assert normalized_topic["stop_rule"] == {
        "candidate_limit": scoped["constraints"]["candidate_limit_per_topic"],
        "no_new_coverage_passes": scoped["constraints"]["no_new_coverage_passes"],
        "complementary_search_route_required": True,
    }
    assert normalized_topic["coverage_requirements"][0]["mandatory"] is True


def test_scout_profile_rejects_short_generic_primary_core_term():
    prepared = planner.prepare_planner(
        _load("research_graph_input.json"), execution_profile="scout"
    )
    scoped = prepared["planner_input"]
    plan = _load("research_plan.json")
    plan["global_constraints"] = copy.deepcopy(scoped["constraints"])
    plan["topics"][0]["search_strategy"]["core_terms"][0] = "Bayesian inference tutorial"
    plan["topics"][1]["search_strategy"]["core_terms"].append("variational calibration")

    validation = planner.validate_research_plan(plan, scoped)

    assert any(item["type"] == "generic_scout_core_term" for item in validation["issues"])


def test_prepare_rejects_missing_drivers_without_artifact():
    boundary = _load("research_graph_input.json")
    boundary["research_drivers"] = []
    prepared = planner.prepare_planner(boundary)
    assert not prepared["ready"]
    assert prepared["envelope"]["status"] == "needs_input"
    assert prepared["envelope"]["produced"] == []
