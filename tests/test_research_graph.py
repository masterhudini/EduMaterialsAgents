"""The thin Research Graph must run end-to-end (no LLM) and emit a valid output bundle.

Also guards manifest/registration coherence and the boundary contracts. Stdlib only; runtime
artifacts go to a tmp dir via EMAGENTS_HOME.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from core import artifacts, contracts, graph_check, graphs, handoff  # noqa: E402
from research import research_flow  # noqa: E402

SEED = ROOT / "tests" / "fixtures" / "research_graph_input.example.json"


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("EMAGENTS_HOME", str(tmp_path / ".emagents"))


def test_seed_satisfies_input_contract():
    seed = json.loads(SEED.read_text())
    assert contracts.validate(seed, "research_graph_input@1")["ok"]


def test_graph_runs_end_to_end_and_emits_valid_bundle():
    seed = json.loads(SEED.read_text())
    in_ref = artifacts.store("handoffs/research_graph_input.json", seed)

    desc = research_flow.run(in_ref)

    assert desc["type"] == "human_approved_research_bundle"
    assert desc["schema_version"] == "human_approved_research_bundle@1"

    # the emitted bundle is loadable and satisfies its contract
    bundle = handoff.load_handoff(desc, contract_ref="human_approved_research_bundle@1")
    assert "approved_update_findings" in bundle


def test_nodes_receive_mocked_context():
    """The graph must hand the loaded context to every agent node."""
    seed = json.loads(SEED.read_text())
    in_ref = artifacts.store("handoffs/research_graph_input.json", seed)

    seen = []

    def spy(node, ctx, log):
        seen.append((node["name"], ctx["input"]["task_id"], len(ctx["input"]["claim_cards"])))
        return {"status": "ok", "produced": [], "summary": "spy", "issues": []}

    research_flow.run(in_ref, node_runner=spy)

    names = [n for n, _, _ in seen]
    # all 9 producer agents ran (reviewer + the 2 user gates are not agent nodes)
    assert len(seen) == 9
    assert "research-planner" in names and "research-synthesizer" in names
    # every node received the SAME mocked context (task_id + claim cards visible)
    assert all(task_id == "RESEARCH_001" and n_claims == 1 for _, task_id, n_claims in seen)


def test_run_rejects_bad_input():
    bad_ref = artifacts.store("handoffs/bad.json", {"task_id": "x"})  # missing required fields
    with pytest.raises(ValueError):
        research_flow.run(bad_ref)


def test_manifest_matches_registration():
    res = graph_check.check_all()
    assert res["ok"], res

    # every agent node in the manifest is a registered agent; gates are not
    manifest = graphs.load("research")
    plugin = json.loads((ROOT / "plugin.json").read_text())
    registered = {Path(a).stem for a in plugin["agents"]}
    for node in graphs.nodes(manifest):
        if node["kind"] == "agent":
            assert node["name"] in registered
        if node["kind"] == "user-gate":
            assert node["name"] not in registered
