"""Smoke + unit tests for the domain-agnostic runtime engine (core/*).

Stdlib only; no LLM nodes involved. Each test exercises one engine module. Runtime artifacts
are redirected to a tmp dir via EMAGENTS_HOME so tests never touch the real .emagents/.
"""
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from core import (artifacts, contracts, event_log, gate, graph_check, graphs,  # noqa: E402
                  handoff, paths, revision, state, validate_state)


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("EMAGENTS_HOME", str(tmp_path / ".emagents"))


# ---- contracts ----------------------------------------------------------

def test_envelope_contract_roundtrip():
    ok_env = {"status": "ok", "produced": [], "summary": "done", "issues": []}
    assert contracts.validate_envelope(ok_env)["ok"]

    bad = {"status": "weird", "produced": [], "summary": "x", "issues": []}
    res = contracts.validate_envelope(bad)
    assert not res["ok"] and any("enum" in e for e in res["errors"])

    missing = {"status": "ok", "summary": "x", "issues": []}
    assert not contracts.validate_envelope(missing)["ok"]


def test_parse_ref_and_major_mismatch():
    assert contracts.parse_ref("envelope@2") == ("envelope", 2)
    assert contracts.parse_ref("envelope") == ("envelope", None)
    with pytest.raises(ValueError):
        contracts.load_schema("envelope@99")  # registered major is 1


# ---- state --------------------------------------------------------------

def test_state_facts_and_meta_separation():
    s = state.new_state("demo")
    state.set_field(s, "topic", "bayes", "confirmed")
    state.set_field(s, "draft", None, "empty")
    assert state.get_value(s, "topic") == "bayes"
    assert set(state.fact_fields(s)) == {"topic", "draft"}
    with pytest.raises(KeyError):
        state.set_field(s, "phase", "x")  # meta key rejected


def test_phase_transitions_guarded():
    s = state.new_state("demo")
    state.set_phase(s, "checked")
    state.set_phase(s, "gated")
    with pytest.raises(ValueError):
        state.set_phase(s, "empty")  # illegal


def test_persist_and_resume(tmp_path):
    s = state.new_state("demo")
    state.set_field(s, "topic", "bayes")
    p = state.state_path("demo")
    state.save(p, s)
    loaded = state.resume(p)
    assert state.get_value(loaded, "topic") == "bayes"


def test_freeze_unwraps_and_drops():
    s = state.new_state("demo")
    state.set_field(s, "topic", "bayes")
    state.set_field(s, "secret", "x")
    state.set_field(s, "empty_one", None, "empty")
    spec = state.freeze(s, drop={"secret"})
    assert spec == {"topic": "bayes"}  # meta gone, secret dropped, None omitted


# ---- validate_state + gate ----------------------------------------------

def _validator(s):
    return validate_state.validate_state(
        s, required=["topic"], route_back={"topic": "collector-topic"})


def test_gate_blocks_then_passes():
    s = state.new_state("demo")
    assert not gate.gate_status(s, _validator)["ok"]
    with pytest.raises(ValueError):
        gate.pass_gate_and_freeze(s, _validator)

    state.set_field(s, "topic", "bayes", "confirmed")
    status = gate.gate_status(s, _validator)
    assert status["ok"]
    spec = gate.pass_gate_and_freeze(s, _validator)
    assert spec == {"topic": "bayes"} and state.get_phase(s) == "frozen"


def test_not_confirmed_is_flagged_with_routeback():
    s = state.new_state("demo")
    state.set_field(s, "topic", "bayes", "inferred")
    res = _validator(s)
    assert not res["ok"]
    assert res["issues"][0]["route_back_to"] == "collector-topic"


# ---- revision -----------------------------------------------------------

def test_revision_decisions():
    policy = {"retry_scope": "plan", "escalation_after_exhaustion": "human-gate",
              "max_revision_attempts": {"low": 0, "medium": 2, "high": 3, "critical": 3}}
    assert revision.decide(policy, "high", approved=True, attempts_used=0)["action"] == "APPROVED"
    assert revision.decide(policy, "high", approved=False, attempts_used=1)["action"] == "REVISE"
    out = revision.decide(policy, "high", approved=False, attempts_used=3)
    assert out["action"] == "ESCALATE" and out["to"] == "human-gate"
    # low budget = 0 -> immediate escalation on first rejection
    assert revision.decide(policy, "low", approved=False, attempts_used=0)["action"] == "ESCALATE"


def test_attempt_counter():
    c = revision.AttemptCounter()
    assert c.bump("plan") == 1 and c.bump("plan") == 2 and c.used("plan") == 2


# ---- artifacts ----------------------------------------------------------

def test_artifact_hydration_with_pointer(tmp_path):
    base = tmp_path / "artifacts"
    base.mkdir()
    (base / "claims.json").write_text('{"claims": {"CLM_001": {"text": "hi"}}}')
    ref = "artifact://claims.json#/claims/CLM_001"
    assert artifacts.parse_ref(ref) == ("claims.json", "/claims/CLM_001")
    assert artifacts.hydrate(ref, base=base) == {"text": "hi"}
    assert artifacts.hydrate("artifact://claims.json", base=base)["claims"]["CLM_001"]["text"] == "hi"


# ---- graph_check + event_log --------------------------------------------

def test_graph_check_ok_with_no_manifests():
    res = graph_check.check_all()
    assert res["ok"] and res["checked"] == 0


def test_event_log_appends(tmp_path):
    log = event_log.open_log("demo")
    log.append("planner", "plan", detail={"n": 1})
    log.append("gate", "freeze", status="ok")
    entries = log.entries()
    assert len(entries) == 2 and entries[0]["node"] == "planner"


# ---- artifact store + handoff (the subgraph seam) -----------------------

def test_artifact_store_roundtrip(tmp_path):
    base = tmp_path / "store"
    ref = artifacts.store("states/concept.json", {"concepts": ["C1"]}, base=base)
    assert ref == "artifact://states/concept.json"
    assert artifacts.hydrate(ref, base=base) == {"concepts": ["C1"]}


def test_handoff_emit_and_load(tmp_path):
    base = tmp_path / "store"
    # use envelope@1 as a stand-in contract for the bundle shape
    bundle = {"status": "ok", "produced": [], "summary": "intake done", "issues": []}
    desc = handoff.emit_handoff(bundle, "envelope@1", name="intake_bundle", base=base)
    assert desc["type"] == "envelope" and desc["schema_version"] == "envelope@1"
    assert desc["ref"] == "artifact://handoffs/intake_bundle.json"
    # next subgraph loads it and re-validates on the way in
    loaded = handoff.load_handoff(desc, contract_ref="envelope@1", base=base)
    assert loaded["summary"] == "intake done"


def test_handoff_rejects_bad_bundle(tmp_path):
    base = tmp_path / "store"
    with pytest.raises(ValueError):
        handoff.emit_handoff({"status": "nope"}, "envelope@1", name="bad", base=base)


# ---- graphs loader + subgraph-aware graph_check -------------------------

def _write(p, obj):
    import json
    p.write_text(json.dumps(obj))


def test_graphs_loader_and_subgraph_nodes(tmp_path):
    gdir = tmp_path / "graphs"
    gdir.mkdir()
    _write(gdir / "intake.graph.json", {"graph_id": "intake", "nodes": []})
    _write(gdir / "system.graph.json", {
        "graph_id": "system",
        "nodes": [{"name": "intake", "kind": "subgraph", "graph": "intake"}],
    })
    assert set(graphs.all_graph_ids(gdir)) == {"intake", "system"}
    sysm = graphs.load("system", gdir)
    subs = graphs.subgraph_nodes(sysm)
    assert len(subs) == 1 and graphs.subgraph_id(subs[0]) == "intake"


def test_graph_check_subgraph_existence(tmp_path):
    gdir = tmp_path / "graphs"
    gdir.mkdir()
    plugin = tmp_path / "plugin.json"
    _write(plugin, {"skills": [], "agents": [], "commands": []})
    _write(gdir / "intake.graph.json", {"graph_id": "intake", "nodes": []})
    _write(gdir / "system.graph.json", {
        "graph_id": "system",
        "nodes": [
            {"name": "intake", "kind": "subgraph", "graph": "intake"},     # exists -> ok
            {"name": "research", "kind": "subgraph", "graph": "research"},  # missing -> error
        ],
    })
    res = graph_check.check_all(graphs_dir=gdir, plugin_path=plugin)
    assert not res["ok"]
    flat = [e for r in res["results"] for e in r["errors"]]
    assert any("research.graph.json" in e for e in flat)
    assert not any("intake" in e for e in flat)
