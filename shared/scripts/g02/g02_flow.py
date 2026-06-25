"""g02 (Research Graph) flow — a thin wrapper over the generic ``core.engine``.

The engine drives the manifest (single source of truth: shared/graphs/g02.graph.json) and the
reviewer/gate/checkpoint machinery. This module supplies only what is g02-specific: the boundary
contracts, the per-node scoped input (G02-A01 gets a typed research_planner_input@1), the thin
stub exit bundle, and the human source-selection gate hooks. The public API
(run / front_door / finalize / node_input_map / load_context / scoped_input / _load_any /
terminal_gate_handler / GRAPH_ID / INPUT_CONTRACT / OUTPUT_CONTRACT / _cli) is preserved for the
MCP server, the Codex runner and the tests.

Run it directly:
    python3 shared/scripts/g02/g02_flow.py run mocks/g02/research_graph_input.json
"""
from __future__ import annotations

import json
import sys as _sys
import pathlib as _pl

# Make `core` / `g02` importable whether run as a module or as a script.
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))

from core import artifacts, contracts, engine, graphs  # noqa: E402
from g02 import planner  # noqa: E402
from g02 import source_selection  # noqa: E402

GRAPH_ID = "g02"
INPUT_CONTRACT = "research_graph_input@1"
OUTPUT_CONTRACT = "user_approved_research_bundle@1"

_SOURCE_GATE = "user-source-selection-gate"
_SOURCE_INDEX_NODE = "g02-a05-candidate-source-index"
_SOURCE_INDEX_TYPE = "candidate_source_index"
_SOURCE_INDEX_CONTRACT = "candidate_source_index@1"


def _scoped_input(node: dict, rgi: dict) -> dict:
    """G02-A01 receives a typed research_planner_input@1; other producers get the boundary input
    in this no-op harness (their approved upstream artifacts do not exist here)."""
    if node.get("name") == planner.PLANNER_AGENT:
        return planner.scope_planner_input(rgi)
    return rgi


def _stub_bundle() -> dict:
    """Minimal UserApprovedResearchBundle that satisfies the output contract."""
    return {
        "schema_version": OUTPUT_CONTRACT,
        "artifact_version": "1.0.0",
        "task_id": "STUB_RESEARCH_TASK",
        "research_state_ref": "artifact://g02/synthesis/stub.research-state.json",
        "approved_research_summary_ref": "artifact://g02/research_summary.approved.md",
        "approved_update_findings": [],
        "approved_optional_findings": [],
        "rejected_findings": [],
        "unresolved_claim_policy": {"action": "keep_as_unresolved_items"},
        "human_gate_decision": {
            "status": "approved",
            "approve_required_updates": True,
            "approve_optional_improvements": False,
            "unresolved_claim_handling": "keep_as_unresolved_items",
        },
        "solution_handoff": {
            "evidence_cards": [], "source_cards": [], "unresolved_claim_cards": [],
        },
        "approved_at": "1970-01-01T00:00:00Z",
    }


def _source_index_ref(produced_refs: dict, base):
    stored = produced_refs.get(_SOURCE_INDEX_NODE)
    if not isinstance(stored, str):
        return None
    return engine._produced_artifact_ref(stored, _SOURCE_INDEX_TYPE, _SOURCE_INDEX_CONTRACT, base=base)


def _gate_prepare(gname: str, produced_refs: dict, base) -> dict:
    """Attach the source-selection prompt to the gate payload when the index is ready."""
    if gname != _SOURCE_GATE:
        return {}
    ref = _source_index_ref(produced_refs, base)
    if not ref:
        return {}
    prepared = source_selection.prepare_source_selection(ref, base=base)
    if prepared.get("ready"):
        return {"payload": {"source_selection": prepared["gate_prompt"]}}
    return {}


def _gate_finalize(gname: str, decision, produced_refs: dict, base):
    """Resolve / validate the human-approved source set after the source-selection gate."""
    if gname != _SOURCE_GATE:
        return None
    ref = _source_index_ref(produced_refs, base)
    if not ref:
        return None
    approved_ref = decision.get("user_approved_source_set_ref") if isinstance(decision, dict) else None
    if (isinstance(decision, dict) and not approved_ref
            and isinstance(decision.get("selection"), dict)
            and isinstance(decision.get("confirmation_token"), str)):
        finalized = source_selection.finalize_source_selection(
            ref, decision["selection"], decision["confirmation_token"], base=base)
        approved_ref = next((item.get("path") for item in finalized.get("produced", [])
                             if item.get("type") == "user_approved_source_set"), None)
    if isinstance(approved_ref, str):
        approved_set = artifacts.hydrate(approved_ref, base=base)
        validation = contracts.validate(approved_set, "user_approved_source_set@1")
        if not validation["ok"]:
            raise ValueError("invalid human approved source set: " + "; ".join(validation["errors"]))
        return approved_ref
    return None


SPEC = engine.EngineSpec(
    graph_id=GRAPH_ID,
    input_contract=INPUT_CONTRACT,
    output_contract=OUTPUT_CONTRACT,
    scoped_input=_scoped_input,
    stub_exit_bundle=_stub_bundle,
    input_state_field="research_graph_input",
    output_state_field="user_approved_research_bundle",
    artifact_namespace="research",
    emit_name="research_bundle",
    gate_prepare=_gate_prepare,
    gate_finalize=_gate_finalize,
)


# ---- preserved public API (bound to the g02 spec) ------------------------


def front_door(path_or_ref, *, base=None):
    return engine.front_door(SPEC, path_or_ref, base=base)


def finalize(bundle_path, *, base=None):
    return engine.finalize(SPEC, bundle_path, base=base)


def node_input_map(rgi, manifest):
    return engine.node_input_map(SPEC, rgi, manifest)


def load_context(path, *, validate=True):
    return engine.load_context(SPEC, path, validate=validate)


def scoped_input(node, rgi):
    return _scoped_input(node, rgi)


def _load_any(path_or_ref, *, base=None):
    return engine._load_any(SPEC, path_or_ref, base=base)


terminal_gate_handler = engine.terminal_gate_handler


def run(
    input_ref=None,
    *,
    base=None,
    node_runner=None,
    gate_handler=None,
    pause_on_gate=False,
    pause_on_node=False,
    resume_token=None,
    decisions=None,
    node_results=None,
    node_failures=None,
    review_results=None,
    usage_reports=None,
    reviewed=False,
    through="g02-a09-synthesizer",
    topic_ids=None,
) -> dict:
    """Dispatch to the no-op wiring harness or the fail-closed reviewed frontier.

    ``reviewed=False`` is intentionally the default for compatibility with deterministic wiring
    tests. Every real host entrypoint must pass ``reviewed=True``. Host-driven mode
    (``pause_on_node=True``) needs no ``node_runner`` — reviewed_flow yields each node to the host.
    """
    if not reviewed:
        return engine.run(
            SPEC, input_ref, base=base, node_runner=node_runner,
            gate_handler=gate_handler, pause_on_gate=pause_on_gate,
            resume_token=resume_token, decisions=decisions,
        )
    if node_runner is None and not pause_on_node:
        raise ValueError("reviewed execution requires a real host node_runner")
    from g02 import reviewed_flow

    return reviewed_flow.run(
        input_ref,
        base=base,
        node_runner=node_runner,
        gate_handler=gate_handler,
        pause_on_gate=pause_on_gate,
        pause_on_node=pause_on_node,
        resume_token=resume_token,
        decisions=decisions,
        node_results=node_results,
        node_failures=node_failures,
        review_results=review_results,
        usage_reports=usage_reports,
        through=through,
        topic_ids=topic_ids,
    )


def _cli(argv: list[str]) -> int:
    import argparse

    def decision_payload(value: str | None) -> dict | None:
        if value is None:
            return None
        stripped = value.strip()
        if stripped.startswith("{"):
            raw = stripped
        else:
            candidate = _pl.Path(value)
            raw = candidate.read_text(encoding="utf-8") if candidate.is_file() else value
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("--decisions must be a JSON object or a path to one")
        return parsed

    p = argparse.ArgumentParser(
        prog="g02_flow.py",
        description=(
            "Research Graph CLI: deterministic seams (front-door / inputs / finalize) "
            "plus a stub harness (run) — no LLM."
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("front-door", help="validate input, store it, print {ref, task_id}")
    sp.add_argument("context", help="path or artifact:// ref to a research_graph_input bundle")

    sp = sub.add_parser("inputs", help="print the scoped input each agent node receives")
    sp.add_argument("context", help="path or artifact:// ref to a research_graph_input bundle")
    sp.add_argument("--node", help="restrict to this node name")

    sp = sub.add_parser("run", help="run the whole graph with STUB nodes (no LLM)")
    sp.add_argument("context", help="path or artifact:// ref to a research_graph_input bundle")
    sp.add_argument(
        "--gates",
        choices=["auto", "prompt"],
        default="auto",
        help="auto-approve gates (default) or prompt for each on stdin",
    )

    sp = sub.add_parser(
        "run-codex",
        help="run the whole graph with Codex workers (codex exec) + terminal gates",
    )
    sp.add_argument(
        "context", nargs="?",
        help="path or artifact:// ref to research_graph_input; omit when --resume-token is used",
    )
    sp.add_argument(
        "--gates",
        choices=["prompt", "pause"],
        default="prompt",
        help="prompt for both gates on stdin (default) or return a pause/resume token",
    )
    sp.add_argument("--resume-token", help="resume token returned by an awaiting_user report")
    sp.add_argument(
        "--decisions",
        help="gate decisions as a JSON object or a path to JSON, keyed by gate name",
    )
    sp.add_argument(
        "--through",
        default="g02-a09-synthesizer",
        choices=[
            "g02-a01-planner", "g02-a02-domain", "g02-a03-canonical-sources",
            "g02-a04-recent-developments", "g02-a11-market-cases",
            "g02-a05-candidate-source-index", "user-source-selection-gate",
            "g02-a06-paper-retrieval", "g02-a07-paper-review",
            "g02-a09-synthesizer", "user-research-gate",
        ],
        help="stop after this implemented stage (default: reviewed A09, then Human Research Gate)",
    )
    sp.add_argument(
        "--topic-id",
        action="append",
        dest="topic_ids",
        help="restrict discovery to one or more ResearchPlan topics; A05 requires all topics",
    )

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
                    print(
                        f"error: no agent node {args.node!r} (have: {', '.join(inputs)})",
                        file=_sys.stderr,
                    )
                    return 1
                inputs = {args.node: inputs[args.node]}
            out = inputs
        elif args.cmd == "run":
            handler = terminal_gate_handler if args.gates == "prompt" else None
            out = run(front_door(args.context)["ref"], gate_handler=handler)
        elif args.cmd == "run-codex":
            from runners.codex import codex_node_runner
            from g02.reviewed_flow import terminal_gate_handler as reviewed_terminal_gate

            if args.resume_token and args.context:
                raise ValueError("omit context when resuming with --resume-token")
            if not args.resume_token and not args.context:
                raise ValueError("context is required for a new run")
            handler = reviewed_terminal_gate if args.gates == "prompt" else None
            input_ref = None if args.resume_token else front_door(args.context)["ref"]
            out = run(
                input_ref,
                node_runner=codex_node_runner,
                gate_handler=handler,
                pause_on_gate=(args.gates == "pause"),
                resume_token=args.resume_token,
                decisions=decision_payload(args.decisions),
                reviewed=True,
                through=args.through,
                topic_ids=args.topic_ids,
            )
        elif args.cmd == "finalize":
            out = finalize(args.bundle)
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=_sys.stderr)
        return 1

    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli(_sys.argv[1:]))
