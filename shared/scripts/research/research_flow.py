"""Thin runnable Research Graph — stub nodes so the whole graph executes end-to-end without
an LLM.

Every node is a no-op that returns an empty ``envelope@1`` (the "pass"). The flow exercises
the REAL runtime seams, though: it loads + re-validates the boundary input contract, walks the
manifest node sequence (single source of truth: shared/graphs/research.graph.json), logs each
step, then freezes a stub UserApprovedResearchBundle and emits it as a typed handoff.

Replace each stub with a real agent invocation as the graph is fleshed out. Pure stdlib.

Run it directly:
    python3 shared/scripts/research/research_flow.py run tests/fixtures/research_graph_input.example.json
"""
from __future__ import annotations

import json
import sys as _sys
import pathlib as _pl

# Make `core` importable whether run as a module or as a script.
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))

from core import contracts, event_log, gate, graphs, handoff  # noqa: E402
from core import state as st  # noqa: E402
from core import validate_state as vs  # noqa: E402

GRAPH_ID = "research"
INPUT_CONTRACT = "research_graph_input@1"
OUTPUT_CONTRACT = "user_approved_research_bundle@1"


def _empty_envelope(node: str) -> dict:
    return {"status": "ok", "produced": [], "summary": f"{node}: stub no-op", "issues": []}


def _stub_bundle() -> dict:
    """Minimal UserApprovedResearchBundle that satisfies the output contract."""
    return {
        "approved_research_summary_ref": "artifact://research/research_summary.approved.md",
        "approved_update_findings": [],
        "approved_optional_findings": [],
        "rejected_findings": [],
        "unresolved_claim_policy": {"action": "move_to_speaker_note_or_remove"},
        "solution_handoff": {"evidence_cards": [], "slide_impact_cards": [],
                             "source_cards": [], "unresolved_claim_cards": []},
    }


def load_context(path, *, validate: bool = True) -> dict:
    """Read a research_graph_input JSON from disk; validate it against the boundary contract."""
    seed = json.loads(_pl.Path(path).read_text(encoding="utf-8"))
    if validate:
        res = contracts.validate(seed, INPUT_CONTRACT)
        if not res["ok"]:
            raise ValueError(f"context fails {INPUT_CONTRACT}: " + "; ".join(res["errors"]))
    return seed


def scoped_input(node: dict, rgi: dict) -> dict:
    """The input bundle a given node receives.

    SINGLE place where per-node context scoping lives. At stub stage every node gets the full
    ResearchGraphInput; real scoping (planner -> ResearchPlan -> per-topic for research-domain,
    one document for research-paper-review, etc.) will narrow this here as producers come online.
    """
    return rgi


def node_input_map(rgi: dict, manifest: dict) -> dict:
    """What each agent node would receive — for inspecting/testing a single agent in isolation."""
    return {n["name"]: scoped_input(n, rgi)
            for n in graphs.nodes(manifest) if n.get("kind") == "agent"}


def _load_any(path_or_ref, *, base=None) -> dict:
    """Load + validate a research_graph_input from a file path or an artifact:// ref."""
    if str(path_or_ref).startswith("artifact://"):
        return handoff.load_handoff(path_or_ref, contract_ref=INPUT_CONTRACT, base=base)
    return load_context(path_or_ref)


def front_door(path_or_ref, *, base=None) -> dict:
    """Validate the input context and ensure it is in the artifact store. Returns {ref, task_id}.

    Fail-fast: raises if the context does not satisfy ``research_graph_input@1``. This is the
    orchestrator's first step — the ``ref`` it returns threads through the rest of the run.
    """
    from core import artifacts
    ctx = _load_any(path_or_ref, base=base)
    ref = (path_or_ref if str(path_or_ref).startswith("artifact://")
           else artifacts.store("handoffs/research_graph_input.json", ctx, base=base))
    return {"ref": ref, "task_id": ctx.get("task_id")}


def finalize(bundle_path, *, base=None) -> dict:
    """Validate a result bundle against the output contract and emit it as the typed handoff."""
    bundle = json.loads(_pl.Path(bundle_path).read_text(encoding="utf-8"))
    return handoff.emit_handoff(bundle, OUTPUT_CONTRACT, name="research_bundle", base=base)


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
    results: dict[str, dict] = {}
    for node in graphs.nodes(manifest):
        kind = node.get("kind")
        if kind == "agent":
            ctx = {"input": scoped_input(node, rgi)}  # per-node scoped context
            results[node["name"]] = node_runner(node, ctx, log)
            profile = node.get("review_profile")
            if profile:
                log.append(reviewer, "review", status="APPROVED",
                           detail={"target": node["name"], "profile": profile, "stub": True})
        elif kind == "user-gate":
            log.append(node["name"], "user_decision", status="APPROVED",
                       detail={"stub": "auto-approve"})

    # 4. freeze a stub output bundle and emit it as the typed handoff to Solution
    st.set_field(state, "user_approved_research_bundle", _stub_bundle(), "confirmed")

    def _validator(s):
        return vs.validate_state(s, required=["research_graph_input",
                                              "user_approved_research_bundle"])

    spec = gate.pass_gate_and_freeze(state, _validator, drop={"research_graph_input"})
    desc = handoff.emit_handoff(spec["user_approved_research_bundle"], OUTPUT_CONTRACT,
                                name="research_bundle", base=base)
    log.append("EXIT", "emit_handoff", detail=desc)
    return desc


def _cli(argv: list[str]) -> int:
    import argparse

    p = argparse.ArgumentParser(
        prog="research_flow.py",
        description="Research Graph CLI: deterministic seams (front-door / inputs / finalize) "
                    "plus a stub harness (run) — no LLM.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("front-door", help="validate input, store it, print {ref, task_id}")
    sp.add_argument("context", help="path or artifact:// ref to a research_graph_input bundle")

    sp = sub.add_parser("inputs", help="print the scoped input each agent node receives")
    sp.add_argument("context", help="path or artifact:// ref to a research_graph_input bundle")
    sp.add_argument("--node", help="restrict to this node name")

    sp = sub.add_parser("run", help="run the whole graph with STUB nodes (no LLM)")
    sp.add_argument("context", help="path or artifact:// ref to a research_graph_input bundle")

    sp = sub.add_parser("finalize", help="validate a result bundle and emit the handoff")
    sp.add_argument("bundle", help="path to a user_approved_research_bundle JSON")

    args = p.parse_args(argv)
    try:
        if args.cmd == "front-door":
            out = front_door(args.context)
        elif args.cmd == "inputs":
            inputs = node_input_map(_load_any(args.context), graphs.load(GRAPH_ID))
            if args.node:
                if args.node not in inputs:
                    print(f"error: no agent node {args.node!r} (have: {', '.join(inputs)})",
                          file=_sys.stderr)
                    return 1
                inputs = {args.node: inputs[args.node]}
            out = inputs
        elif args.cmd == "run":
            out = run(front_door(args.context)["ref"])
        elif args.cmd == "finalize":
            out = finalize(args.bundle)
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=_sys.stderr)
        return 1
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli(_sys.argv[1:]))
