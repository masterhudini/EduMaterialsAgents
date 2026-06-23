"""Fail-closed tests for the real-host A01-A06 scheduler."""
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
from g02 import domain, planner, review, reviewed_flow  # noqa: E402

MOCKS = ROOT / "mocks" / "g02"


@pytest.fixture(autouse=True)
def _runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("EMAGENTS_HOME", str(tmp_path / ".emagents"))
    monkeypatch.setenv("EMAGENTS_RESEARCH_CONTACT_EMAIL", "tests@example.com")
    monkeypatch.setenv("OPENALEX_API_KEY", "openalex-test-key")


def _load(name):
    return json.loads((MOCKS / name).read_text(encoding="utf-8"))


def _input_ref(base):
    return artifacts.store("handoffs/research_graph_input.json", _load("research_graph_input.json"), base=base)


def _decision(task, verdict="APPROVED"):
    blocked = verdict == "BLOCKED"
    return {
        "schema_version": "review_decision@1",
        "review_id": task["review_id"], "task_id": task["task_id"],
        "logical_review_node": task["logical_review_node"],
        "reviewer_agent": "g02-a10-output-reviewer",
        "producer_agent": task["producer_agent"],
        "artifact_ref": task["artifact"]["ref"],
        "artifact_version": task["artifact"]["artifact_version"],
        "review_profile": task["review_profile"], "decision": verdict,
        "findings": ([{
            "finding_id": "RF_BLOCKED", "criterion_id": "EXTERNAL_DEPENDENCY",
            "severity": "blocker", "location": "review",
            "observed": "dependency unavailable", "required_correction": "restore dependency",
            "evidence_refs": [],
        }] if blocked else []),
        "closed_finding_ids": [], "revision_scope": None,
        "root_cause": "external_dependency_blocked" if blocked else None,
        "confidence": "high", "attempt": task["attempt"],
        "summary": "Blocked." if blocked else "Approved.",
    }


def _happy_runner(base, calls, *, verdict="APPROVED"):
    def run(node, ctx, log):
        calls.append(node["name"])
        if node["name"] == planner.PLANNER_AGENT:
            return planner.finalize_research_plan(ctx["input"], copy.deepcopy(_load("research_plan.json")), base=base)
        task = ctx["review_task"]
        return review.finalize_review_decision(task, _decision(task, verdict), base=base)
    return run


def test_reviewed_a01_happy_path_returns_typed_report(tmp_path):
    base = tmp_path / "store"
    calls = []
    report = reviewed_flow.run(
        _input_ref(base), node_runner=_happy_runner(base, calls), base=base,
        through=planner.PLANNER_AGENT,
    )
    assert report["status"] == "completed", report["issues"]
    assert contracts.validate(report, "research_run_report@1")["ok"]
    assert calls == [planner.PLANNER_AGENT, "g02-a10-output-reviewer"]
    assert report["records"][0]["status"] == "approved"
    assert artifacts.hydrate(report["output_ref"], base=base)["schema_version"] == "research_plan@1"


def test_failed_or_inline_worker_output_stops_before_review(tmp_path):
    base = tmp_path / "store"
    calls = []

    def failed(node, ctx, log):
        calls.append(node["name"])
        return {"status": "failed", "produced": [], "summary": "worker failed",
                "issues": [{"severity": "blocker", "type": "worker", "message": "failed"}]}

    report = reviewed_flow.run(
        _input_ref(base), node_runner=failed, base=base, through=planner.PLANNER_AGENT
    )
    assert report["status"] == "failed"
    assert calls == [planner.PLANNER_AGENT]
    assert report["records"] == []

    calls.clear()

    def inline(node, ctx, log):
        calls.append(node["name"])
        envelope = planner.finalize_research_plan(ctx["input"], copy.deepcopy(_load("research_plan.json")), base=base)
        envelope["artifact"] = _load("research_plan.json")
        return envelope

    report = reviewed_flow.run(
        _input_ref(base), node_runner=inline, base=base, through=planner.PLANNER_AGENT
    )
    assert report["status"] == "failed"
    assert calls == [planner.PLANNER_AGENT]
    assert "inline artifact" in report["issues"][0]["message"]


def test_blocked_review_does_not_schedule_domain(tmp_path):
    base = tmp_path / "store"
    calls = []
    report = reviewed_flow.run(
        _input_ref(base), node_runner=_happy_runner(base, calls, verdict="BLOCKED"),
        base=base, through="g02-a02-domain",
    )
    assert report["status"] == "blocked"
    assert calls == [planner.PLANNER_AGENT, "g02-a10-output-reviewer"]
    assert not any(item["node"] == "g02-a02-domain" for item in report["records"])


def test_revise_runs_producer_once_more_without_second_review(tmp_path):
    base = tmp_path / "store"
    calls = []
    producer_attempt = 0

    def runner(node, ctx, log):
        nonlocal producer_attempt
        calls.append(node["name"])
        if node["name"] == planner.PLANNER_AGENT:
            producer_attempt += 1
            plan = copy.deepcopy(_load("research_plan.json"))
            plan["artifact_version"] = f"1.0.{producer_attempt - 1}"
            ref = artifacts.store(
                f"g02/research-plans/single-review-{producer_attempt}.json", plan, base=base
            )
            if producer_attempt == 2:
                assert ctx["revision"]["attempt"] == 2
                assert [item["finding_id"] for item in ctx["revision"]["items"]] == [
                    "RF_SINGLE_REVISE"
                ]
            return {
                "status": "ok", "summary": "Stored plan.", "issues": [],
                "produced": [{
                    "type": "research_plan", "path": ref,
                    "schema_version": "research_plan@1",
                    "artifact_version": plan["artifact_version"],
                }],
            }

        task = ctx["review_task"]
        criterion = task["acceptance_criteria"][0]["criterion_id"]
        decision = {
            "schema_version": "review_decision@1",
            "review_id": task["review_id"], "task_id": task["task_id"],
            "logical_review_node": task["logical_review_node"],
            "reviewer_agent": "g02-a10-output-reviewer",
            "producer_agent": task["producer_agent"],
            "artifact_ref": task["artifact"]["ref"],
            "artifact_version": task["artifact"]["artifact_version"],
            "review_profile": task["review_profile"], "decision": "REVISE",
            "findings": [{
                "finding_id": "RF_SINGLE_REVISE", "criterion_id": criterion,
                "severity": "major", "location": "topics[0]",
                "observed": "Material correction required.",
                "required_correction": "Correct only the named field.",
                "evidence_refs": [],
            }],
            "closed_finding_ids": [],
            "revision_scope": {
                "target_agent": task["producer_agent"],
                "finding_ids": ["RF_SINGLE_REVISE"],
                "allowed_paths": ["topics[0]"],
            },
            "root_cause": "producer_error", "confidence": "high",
            "attempt": 1, "summary": "One material correction is required.",
        }
        return review.finalize_review_decision(task, decision, base=base)

    report = reviewed_flow.run(
        _input_ref(base), node_runner=runner, base=base, through=planner.PLANNER_AGENT
    )
    assert report["status"] == "completed", report["issues"]
    assert calls == [
        planner.PLANNER_AGENT, "g02-a10-output-reviewer", planner.PLANNER_AGENT
    ]
    record = report["records"][0]
    assert record["status"] == "revised_after_review"
    receipt = artifacts.hydrate(record["revision_completion_ref"], base=base)
    assert receipt["finding_ids"] == ["RF_SINGLE_REVISE"]
    assert receipt["review_decision_ref"] == record["review_decision_ref"]
    assert receipt["revised_artifact_ref"] == record["artifact_ref"]


def test_one_topic_a01_a02_threads_scoped_protocol_and_reviews(tmp_path):
    base = tmp_path / "store"
    calls = []
    topic_id = "TOPIC_BAYESIAN_COMPUTATION"

    def runner(node, ctx, log):
        calls.append((node["name"], ctx.get("protocol", {})))
        if node["name"] == planner.PLANNER_AGENT:
            return planner.finalize_research_plan(
                ctx["input"], copy.deepcopy(_load("research_plan.json")), base=base
            )
        if node["name"] == domain.DOMAIN_AGENT:
            assert ctx["input"]["schema_version"] == "domain_research_input@1"
            assert ctx["input"]["topic"]["topic_id"] == topic_id
            assert ctx["protocol"]["prepare"]["operation"] == "research_domain_prepare"
            artifact = copy.deepcopy(_load("domain_candidate_sources.json"))
            ref = artifacts.store("g02/domain-candidates/forward-domain.json", artifact, base=base)
            return {
                "status": "ok", "summary": "Stored domain candidates.", "issues": [],
                "produced": [{
                    "type": "domain_candidate_sources", "path": ref,
                    "schema_version": "domain_candidate_sources@1",
                    "artifact_version": artifact["artifact_version"],
                }],
            }
        task = ctx["review_task"]
        return review.finalize_review_decision(task, _decision(task), base=base)

    report = reviewed_flow.run(
        _input_ref(base), node_runner=runner, base=base,
        through=domain.DOMAIN_AGENT, topic_ids=[topic_id],
    )
    assert report["status"] == "completed", report["issues"]
    assert [item[0] for item in calls] == [
        planner.PLANNER_AGENT, "g02-a10-output-reviewer",
        domain.DOMAIN_AGENT, "g02-a10-output-reviewer",
    ]
    assert {item["node"] for item in report["records"]} == {
        planner.PLANNER_AGENT, domain.DOMAIN_AGENT,
    }


def test_candidate_index_rejects_partial_plan_topic_execution(tmp_path):
    base = tmp_path / "store"
    calls = []
    report = reviewed_flow.run(
        _input_ref(base), node_runner=_happy_runner(base, calls), base=base,
        through="g02-a05-candidate-source-index",
        topic_ids=["TOPIC_BAYESIAN_COMPUTATION"],
    )
    assert report["status"] == "failed"
    assert report["issues"][0]["type"] == "partial_topic_set_before_candidate_index"
    assert calls == [planner.PLANNER_AGENT, "g02-a10-output-reviewer"]
