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

from core import artifacts, contracts, graph_check, graphs, handoff, paths  # noqa: E402
from research import research_flow  # noqa: E402
from research.runners.stub import stub_node_runner  # noqa: E402

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

    assert desc["type"] == "user_approved_research_bundle"
    assert desc["schema_version"] == "user_approved_research_bundle@1"

    # the emitted bundle is loadable and satisfies its contract
    bundle = handoff.load_handoff(desc, contract_ref="user_approved_research_bundle@1")
    assert "approved_update_findings" in bundle


def test_run_persists_node_artifacts_and_threads_upstream_refs():
    """Each agent node's output is persisted to the store; downstream nodes get upstream refs."""
    seed = json.loads(SEED.read_text())
    in_ref = artifacts.store("handoffs/research_graph_input.json", seed)

    seen_upstream = {}

    def spy(node, ctx, log):
        seen_upstream[node["name"]] = sorted(ctx.get("upstream") or {})
        return stub_node_runner(node, ctx, log)

    research_flow.run(in_ref, node_runner=spy)

    # every agent node persisted an artifact under the store
    research_dir = paths.artifacts_dir() / "research"
    persisted = {p.stem for p in research_dir.glob("*.json")}
    assert "research-planner" in persisted and len(persisted) == 9

    # the first node sees no upstream; a later node sees the planner's ref threaded in
    assert seen_upstream["research-planner"] == []
    assert "research-planner" in seen_upstream["research-synthesizer"]


def test_typed_artifact_is_validated_and_persisted():
    """A producer's envelope.artifact is validated against output_contract and persisted as THE
    artifact (not the envelope); stub nodes with no artifact fall back to the envelope."""
    seed = json.loads(SEED.read_text())
    in_ref = artifacts.store("handoffs/research_graph_input.json", seed)

    plan_artifact = {"task_id": "T",
                     "topics": [{"topic_id": "T1", "purpose": "verify",
                                 "required_source_roles": ["canonical"]}]}

    def runner(node, ctx, log):
        if node["name"] == "research-planner":
            env = stub_node_runner(node, ctx, log)
            env["artifact"] = plan_artifact
            return env
        return stub_node_runner(node, ctx, log)

    research_flow.run(in_ref, node_runner=runner)

    research_dir = paths.artifacts_dir() / "research"
    plan = json.loads((research_dir / "research-planner.json").read_text())
    assert plan == plan_artifact                        # the artifact, not the envelope
    assert contracts.validate(plan, "research_plan@1")["ok"]

    # a stub node (no artifact) still persisted its envelope as a fallback
    other = json.loads((research_dir / "research-synthesizer.json").read_text())
    assert other["status"] == "ok" and "summary" in other


def test_artifact_contracts_exist():
    for ref in ("research_plan@1", "candidate_sources@1", "candidate_source_index@1",
                "retrieved_corpus@1", "paper_review@1", "claim_assessment@1", "research_state@1",
                "review_decision@1"):
        assert contracts.load_schema(ref)["x-major"] == 1


def test_gate_handler_surface_runs_through():
    """A synchronous gate_handler (terminal surface) resolves both gates in one pass."""
    in_ref = artifacts.store("handoffs/research_graph_input.json", json.loads(SEED.read_text()))
    seen_gates = []

    def handler(payload):
        seen_gates.append(payload["gate"])
        assert payload["required_decisions"]            # the gate carries its spec
        return {"answered": True}

    desc = research_flow.run(in_ref, gate_handler=handler)
    assert desc["type"] == "user_approved_research_bundle"
    assert seen_gates == ["user-source-selection-gate", "user-research-gate"]


def test_gate_pause_and_resume():
    """pause_on_gate stops at each gate with a resume_token; resuming continues without re-running."""
    in_ref = artifacts.store("handoffs/research_graph_input.json", json.loads(SEED.read_text()))
    runs = {}

    def runner(node, ctx, log):
        if node.get("kind") == "reviewer":
            return {"status": "ok", "produced": [], "summary": "r", "issues": [],
                    "artifact": {"verdict": "APPROVED"}}
        runs[node["name"]] = runs.get(node["name"], 0) + 1
        return stub_node_runner(node, ctx, log)

    # 1st leg -> pause at the source-selection gate
    r1 = research_flow.run(in_ref, node_runner=runner, pause_on_gate=True)
    assert r1["status"] == "awaiting_user" and r1["gate"] == "user-source-selection-gate"
    assert runs.get("research-candidate-source-index") == 1   # producers up to the gate ran
    assert "research-synthesizer" not in runs                 # nothing past the gate yet

    # resume with the decision -> pause at the research gate
    r2 = research_flow.run(node_runner=runner, pause_on_gate=True,
                           resume_token=r1["resume_token"], decisions={r1["gate"]: {"source_actions": {}}})
    assert r2["status"] == "awaiting_user" and r2["gate"] == "user-research-gate"
    assert runs.get("research-candidate-source-index") == 1   # NOT re-run on resume

    # final resume -> completes
    r3 = research_flow.run(node_runner=runner, pause_on_gate=True,
                           resume_token=r2["resume_token"], decisions={r2["gate"]: {"approve_required_updates": True}})
    assert r3["type"] == "user_approved_research_bundle"
    assert runs.get("research-synthesizer") == 1


def _runner_with_reviewer(producer_calls, verdict_for):
    """Fake runner: stub producers (counted) + a reviewer whose verdict comes from verdict_for."""
    def runner(node, ctx, log):
        if node.get("kind") == "reviewer":
            review = ctx["review"]
            decision = verdict_for(review["target"], review["attempt"])
            return {"status": "ok", "produced": [], "summary": "review", "issues": [],
                    "artifact": decision}
        producer_calls[node["name"]] = producer_calls.get(node["name"], 0) + 1
        return stub_node_runner(node, ctx, log)
    return runner


def test_reviewer_revise_then_approve_reruns_producer():
    in_ref = artifacts.store("handoffs/research_graph_input.json", json.loads(SEED.read_text()))
    calls = {}

    def verdict_for(target, attempt):
        if target == "research-planner" and attempt == 0:
            return {"verdict": "REVISE", "issues": [{"severity": "high"}]}
        return {"verdict": "APPROVED"}

    research_flow.run(in_ref, node_runner=_runner_with_reviewer(calls, verdict_for))
    assert calls["research-planner"] == 2          # original + one revision
    assert calls["research-synthesizer"] == 1      # others approved first time


def test_reviewer_exhausts_budget_then_escalates():
    in_ref = artifacts.store("handoffs/research_graph_input.json", json.loads(SEED.read_text()))
    calls = {}

    def verdict_for(target, attempt):
        if target == "research-planner":
            return {"verdict": "REVISE", "issues": [{"severity": "high"}]}
        return {"verdict": "APPROVED"}

    research_flow.run(in_ref, node_runner=_runner_with_reviewer(calls, verdict_for))
    # research_planning @ high = 3 revision attempts -> 1 initial + 3 retries, then ESCALATE
    assert calls["research-planner"] == 4


def test_nodes_receive_mocked_context():
    """The graph must hand the loaded context to every agent node."""
    seed = json.loads(SEED.read_text())
    in_ref = artifacts.store("handoffs/research_graph_input.json", seed)

    seen = []

    def spy(node, ctx, log):
        if node.get("kind") != "agent":  # reviewer call: empty envelope -> APPROVED by default
            return {"status": "ok", "produced": [], "summary": "review", "issues": []}
        seen.append((node["name"], ctx["input"]["task_id"], len(ctx["input"]["claim_cards"])))
        return {"status": "ok", "produced": [], "summary": "spy", "issues": []}

    research_flow.run(in_ref, node_runner=spy)

    names = [n for n, _, _ in seen]
    # all 9 producer agents ran (reviewer + the 2 user gates are not agent nodes)
    assert len(seen) == 9
    assert "research-planner" in names and "research-synthesizer" in names
    # every node received the SAME mocked context (task_id + claim cards visible)
    assert all(task_id == "RESEARCH_001" and n_claims == 1 for _, task_id, n_claims in seen)


def test_node_input_map_exposes_per_agent_context():
    """The harness can show exactly what each agent node receives (for isolated agent testing)."""
    seed = json.loads(SEED.read_text())
    manifest = graphs.load("research")
    inputs = research_flow.node_input_map(seed, manifest)
    assert len(inputs) == 9                       # 9 agent nodes (gates/reviewer excluded)
    assert inputs["research-planner"]["task_id"] == "RESEARCH_001"
    assert inputs["research-claim-verification"]["claim_cards"][0]["claim_id"] == "CLM_001"


def test_load_context_validates(tmp_path):
    good = tmp_path / "good.json"
    good.write_text(SEED.read_text())
    assert research_flow.load_context(good)["task_id"] == "RESEARCH_001"

    bad = tmp_path / "bad.json"
    bad.write_text('{"task_id": "x"}')
    with pytest.raises(ValueError):
        research_flow.load_context(bad)


def test_run_rejects_bad_input():
    bad_ref = artifacts.store("handoffs/bad.json", {"task_id": "x"})  # missing required fields
    with pytest.raises(ValueError):
        research_flow.run(bad_ref)


def test_manifest_matches_registration():
    res = graph_check.check_all()
    assert res["ok"], res

    # every agent node in the manifest has a component file on disk; gates do not
    manifest = graphs.load("research")
    registered = graph_check.registered_component_names()
    for node in graphs.nodes(manifest):
        if node["kind"] == "agent":
            assert node["name"] in registered
        if node["kind"] == "user-gate":
            assert node["name"] not in registered
