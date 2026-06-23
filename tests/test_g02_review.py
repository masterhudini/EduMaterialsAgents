"""Repository regression tests for the universal G02-A10 reviewer seam."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from core import artifacts  # noqa: E402
from g02 import planner, review  # noqa: E402

MOCKS = ROOT / "mocks" / "g02"


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("EMAGENTS_HOME", str(tmp_path / ".emagents"))


def _load(name):
    return json.loads((MOCKS / name).read_text(encoding="utf-8"))


def _task():
    prepared = planner.prepare_planner(_load("research_graph_input.json"))
    envelope = planner.finalize_research_plan(
        prepared["planner_input"], _load("research_plan.json")
    )
    return planner.build_research_plan_review_task(
        prepared["planner_input"], envelope["produced"][0], review_id="REV_REPO_A10_001"
    )


def test_prepare_hydrates_exact_artifact_and_missing_executor_blocks():
    task = _task()
    prepared = review.prepare_review(task)
    assert prepared["ready"]
    assert prepared["artifact"]["schema_version"] == "research_plan@1"

    envelope = review.execute_review_task(task, None)
    assert envelope["status"] == "ok"
    produced = envelope["produced"][0]
    assert produced["type"] == "review_decision"
    decision = artifacts.hydrate(produced["path"])
    assert decision["decision"] == "BLOCKED"
    assert decision["root_cause"] == "external_dependency_blocked"


def test_invalid_reviewer_envelope_fails_without_decision():
    task = _task()

    def invalid(task, context):
        return {"status": "ok", "produced": [], "summary": "missing decision", "issues": []}

    envelope = review.execute_review_task(task, invalid)
    assert envelope["status"] == "failed"
    assert envelope["produced"] == []
    assert envelope["issues"][0]["type"] == "invalid_reviewer_envelope"


def test_approved_decision_may_carry_nonblocking_advisory():
    task = _task()
    criterion = task["acceptance_criteria"][0]["criterion_id"]
    decision = {
        "schema_version": "review_decision@1",
        "review_id": task["review_id"], "task_id": task["task_id"],
        "logical_review_node": task["logical_review_node"],
        "reviewer_agent": "g02-a10-output-reviewer",
        "producer_agent": task["producer_agent"],
        "artifact_ref": task["artifact"]["ref"],
        "artifact_version": task["artifact"]["artifact_version"],
        "review_profile": task["review_profile"], "decision": "APPROVED",
        "findings": [],
        "advisories": [{
            "criterion_id": criterion, "location": "topics[0]",
            "observation": "Optional wording could be shortened in a later edit.",
        }],
        "closed_finding_ids": [], "revision_scope": None, "root_cause": None,
        "confidence": "high", "attempt": task["attempt"],
        "summary": "Approved with one nonblocking advisory.",
    }
    envelope = review.finalize_review_decision(task, decision)
    assert envelope["status"] == "ok"
    stored = artifacts.hydrate(envelope["produced"][0]["path"])
    assert stored["decision"] == "APPROVED"
    assert stored["advisories"][0]["criterion_id"] == criterion
