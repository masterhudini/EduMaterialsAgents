"""Driver-loop tests for the g02 nested-Codex entrypoint (reviewed_flow.run_with_codex).

These exercise only the orchestration the driver adds on top of the hosted single-pass ``run``:
play each ``awaiting_node`` through the node_runner, then pause or play the Human Research Gate.
The hosted ``run`` itself is stubbed so the loop is tested in isolation, mirroring how g01/g03 drive
nested Codex workers synchronously and pause only at human gates.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared" / "scripts"))

import pytest  # noqa: E402

from g02 import reviewed_flow  # noqa: E402


def _awaiting_node(node, node_key, resume_token="tok"):
    return {
        "status": "awaiting_node", "resume_token": resume_token, "node": node,
        "node_key": node_key, "input": {"task_id": "T"}, "upstream": {},
        "output_contract": "a07_review@1",
    }


def test_driver_plays_each_node_then_pauses_at_gate(monkeypatch):
    # Scripted hosted run: A07(2 tasks) -> A09 -> Human Research Gate (awaiting_user).
    script = [
        _awaiting_node("g02-a07-paper-review", "g02-a07-paper-review:T1:S1"),
        _awaiting_node("g02-a07-paper-review", "g02-a07-paper-review:T1:S2"),
        _awaiting_node("g02-a09-synthesizer", "g02-a09-synthesizer"),
        {"status": "awaiting_user", "resume_token": "tok", "gate": {"id": "research"}},
    ]
    seen_node_results = []

    def fake_run(input_ref=None, **kwargs):
        if kwargs.get("node_results"):
            seen_node_results.append(kwargs["node_results"])
        return script.pop(0)

    monkeypatch.setattr(reviewed_flow, "run", fake_run)

    runner_calls = []

    def node_runner(node, ctx, log):
        runner_calls.append(node["name"])
        return {"schema_version": "envelope@1", "status": "ok", "produced": []}

    # No gate_handler -> the driver must hand the gate back to the caller.
    out = reviewed_flow.run_with_codex("artifact://g02/in.json", node_runner=node_runner)

    assert out["status"] == "awaiting_user"
    assert runner_calls == [
        "g02-a07-paper-review", "g02-a07-paper-review", "g02-a09-synthesizer",
    ]
    # Each played node fed its envelope back keyed by the awaiting node_key.
    assert [list(nr)[0] for nr in seen_node_results] == [
        "g02-a07-paper-review:T1:S1", "g02-a07-paper-review:T1:S2", "g02-a09-synthesizer",
    ]


def test_driver_plays_gate_with_handler_until_completed(monkeypatch):
    script = [
        {"status": "awaiting_user", "resume_token": "tok", "gate": {"id": "research"}},
        {"status": "completed", "output_ref": "artifact://g02/bundle.json"},
    ]
    decisions_seen = []

    def fake_run(input_ref=None, **kwargs):
        if kwargs.get("decisions"):
            decisions_seen.append(kwargs["decisions"])
        return script.pop(0)

    monkeypatch.setattr(reviewed_flow, "run", fake_run)

    out = reviewed_flow.run_with_codex(
        "artifact://g02/in.json",
        node_runner=lambda *a, **k: {"schema_version": "envelope@1", "status": "ok", "produced": []},
        gate_handler=lambda gate: {"status": "approved"},
    )

    assert out["status"] == "completed"
    assert decisions_seen == [{reviewed_flow.RESEARCH_GATE: {"status": "approved"}}]


def test_driver_plays_a11_early_and_a08_late(monkeypatch):
    # Full active node order: A11 (after planner) -> A07 -> A09 -> A08 (before gate).
    script = [
        _awaiting_node("g02-a11-market-cases", "g02-a11-market-cases"),
        _awaiting_node("g02-a07-paper-review", "g02-a07-paper-review:T1:S1"),
        _awaiting_node("g02-a09-synthesizer", "g02-a09-synthesizer"),
        _awaiting_node("g02-a08-claim-verification", "g02-a08-claim-verification"),
        {"status": "awaiting_user", "resume_token": "tok", "gate": {"id": "research"}},
    ]

    def fake_run(input_ref=None, **kwargs):
        return script.pop(0)

    monkeypatch.setattr(reviewed_flow, "run", fake_run)

    runner_calls = []

    def node_runner(node, ctx, log):
        runner_calls.append(node["name"])
        return {"schema_version": "envelope@1", "status": "ok", "produced": []}

    out = reviewed_flow.run_with_codex("artifact://g02/in.json", node_runner=node_runner)

    assert out["status"] == "awaiting_user"
    assert runner_calls == [
        "g02-a11-market-cases", "g02-a07-paper-review",
        "g02-a09-synthesizer", "g02-a08-claim-verification",
    ]


def test_run_with_codex_requires_node_runner():
    with pytest.raises(ValueError, match="node_runner"):
        reviewed_flow.run_with_codex("artifact://g02/in.json", node_runner=None)
