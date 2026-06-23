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


def test_prepare_rejects_missing_drivers_without_artifact():
    boundary = _load("research_graph_input.json")
    boundary["research_drivers"] = []
    prepared = planner.prepare_planner(boundary)
    assert not prepared["ready"]
    assert prepared["envelope"]["status"] == "needs_input"
    assert prepared["envelope"]["produced"] == []
