"""Thin runnable Research Graph — stub nodes so the whole graph executes end-to-end without
an LLM.

Every node is a no-op that returns an empty ``envelope@1`` (the "pass"). The flow exercises
the REAL runtime seams, though: it loads + re-validates the boundary input contract, walks the
manifest node sequence (single source of truth: shared/graphs/research.graph.json), logs each
step, then freezes a stub HumanApprovedResearchBundle and emits it as a typed handoff.

Replace each stub with a real agent invocation as the graph is fleshed out. Pure stdlib.

Run it directly:
    python3 shared/scripts/research/research_flow.py tests/fixtures/research_graph_input.example.json
"""
from __future__ import annotations

import sys as _sys
import pathlib as _pl

# Make `core` importable whether run as a module or as a script.
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))

from core import event_log, gate, graphs, handoff  # noqa: E402
from core import state as st  # noqa: E402
from core import validate_state as vs  # noqa: E402

GRAPH_ID = "research"
INPUT_CONTRACT = "research_graph_input@1"
OUTPUT_CONTRACT = "human_approved_research_bundle@1"


def _empty_envelope(node: str) -> dict:
    return {"status": "ok", "produced": [], "summary": f"{node}: stub no-op", "issues": []}


def _stub_bundle() -> dict:
    """Minimal HumanApprovedResearchBundle that satisfies the output contract."""
    return {
        "approved_research_summary_ref": "artifact://research/research_summary.approved.md",
        "approved_update_findings": [],
        "approved_optional_findings": [],
        "rejected_findings": [],
        "unresolved_claim_policy": {"action": "move_to_speaker_note_or_remove"},
        "solution_handoff": {"evidence_cards": [], "slide_impact_cards": [],
                             "source_cards": [], "unresolved_claim_cards": []},
    }


def _stub_node_runner(node: dict, ctx: dict, log) -> dict:
    """Default no-op node: RECEIVES the scoped context, returns an empty ok-envelope.

    It records the task_id it was handed, so the event log proves the context reached the node.
    Real agents replace this; the signature ``(node, ctx, log) -> envelope`` stays.
    """
    name = node["name"]
    log.append(name, "run", detail={"kind": node.get("kind"),
                                    "received_task_id": ctx["input"].get("task_id"),
                                    "stub": True})
    return _empty_envelope(name)


def run(input_ref, *, base=None, node_runner=None) -> dict:
    """Run the thin Research Graph. ``input_ref`` is an artifact:// ref (or handoff descriptor)
    to a ``research_graph_input`` bundle. ``node_runner(node, ctx, log) -> envelope`` is the
    per-node executor (defaults to the no-op stub; injectable for tests / real agents).
    Returns the output handoff descriptor."""
    log = event_log.open_log(GRAPH_ID)
    node_runner = node_runner or _stub_node_runner

    # 1. front door — load + RE-validate the boundary contract (graph never starts on bad input)
    rgi = handoff.load_handoff(input_ref, contract_ref=INPUT_CONTRACT, base=base)
    ref = input_ref.get("ref") if isinstance(input_ref, dict) else input_ref
    log.append("ENTRY", "load_input", detail={"ref": ref, "task_id": rgi.get("task_id")})

    # 2. fresh run state
    state = st.new_state(GRAPH_ID)
    st.set_field(state, "research_graph_input", rgi, "confirmed")

    # 3. walk the manifest — pass the context to each node; agents get a reviewer pass
    manifest = graphs.load(GRAPH_ID)
    reviewer = manifest.get("reviewer", "research-output-reviewer")
    ctx = {"input": rgi}  # the scoped context handed to every node (whole bundle at stub stage)
    results: dict[str, dict] = {}
    for node in graphs.nodes(manifest):
        kind = node.get("kind")
        if kind == "agent":
            results[node["name"]] = node_runner(node, ctx, log)
            profile = node.get("review_profile")
            if profile:
                log.append(reviewer, "review", status="APPROVED",
                           detail={"target": node["name"], "profile": profile, "stub": True})
        elif kind == "user-gate":
            log.append(node["name"], "user_decision", status="APPROVED",
                       detail={"stub": "auto-approve"})

    # 4. freeze a stub output bundle and emit it as the typed handoff to Solution
    st.set_field(state, "human_approved_research_bundle", _stub_bundle(), "confirmed")

    def _validator(s):
        return vs.validate_state(s, required=["research_graph_input",
                                              "human_approved_research_bundle"])

    spec = gate.pass_gate_and_freeze(state, _validator, drop={"research_graph_input"})
    desc = handoff.emit_handoff(spec["human_approved_research_bundle"], OUTPUT_CONTRACT,
                                name="research_bundle", base=base)
    log.append("EXIT", "emit_handoff", detail=desc)
    return desc


if __name__ == "__main__":
    import json
    from core import artifacts

    if len(_sys.argv) != 2:
        print("usage: research_flow.py <research_graph_input.json>", file=_sys.stderr)
        raise SystemExit(2)
    seed = json.loads(_pl.Path(_sys.argv[1]).read_text())
    in_ref = artifacts.store("handoffs/research_graph_input.json", seed)
    out = run(in_ref)
    print(json.dumps(out, indent=2))
