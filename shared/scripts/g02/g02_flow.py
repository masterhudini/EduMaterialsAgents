"""g02 (Research Graph) flow — a thin wrapper over the generic ``core.engine``.

The engine drives the manifest (single source of truth: shared/graphs/g02.graph.json) and the
gate/checkpoint machinery. This module supplies only what is g02-specific: the boundary contracts,
the per-node scoped input (G02-A01 gets a typed research_planner_input@1) and the thin stub exit
bundle. The active Scout path (A01 -> Scout -> A07 -> A09 -> User Research Gate) is hosted-only and
runs through ``reviewed_flow`` when ``run(reviewed=True, pause_on_node=True)``. The public API
(run / front_door / finalize / node_input_map / load_context / scoped_input / _load_any /
terminal_gate_handler / GRAPH_ID / INPUT_CONTRACT / OUTPUT_CONTRACT / _cli) is preserved for the
MCP server and the tests.

Run it directly:
    python3 shared/scripts/g02/g02_flow.py run mocks/g02/research_graph_input.json
"""
from __future__ import annotations

import json
import sys as _sys
import pathlib as _pl

# Make `core` / `g02` importable whether run as a module or as a script.
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))

from core import engine, graphs  # noqa: E402
from g02 import planner  # noqa: E402

GRAPH_ID = "g02"
INPUT_CONTRACT = "research_graph_input@1"
OUTPUT_CONTRACT = "user_approved_research_bundle@1"


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
    through="user-research-gate",
    topic_ids=None,
) -> dict:
    """Dispatch to the no-op wiring harness or the active Scout flow.

    ``reviewed=False`` is intentionally the default for compatibility with deterministic wiring
    tests. Every real host entrypoint must pass ``reviewed=True``. The active Scout flow runs in two
    parities, exactly like g01/g03: a nested-Codex run (pass ``node_runner``) drives every A01/A07/A09
    agent through an isolated ``codex exec`` worker in-process, and a host-driven run
    (``pause_on_node=True``) yields each node to the host.
    """
    if not reviewed:
        return engine.run(
            SPEC, input_ref, base=base, node_runner=node_runner,
            gate_handler=gate_handler, pause_on_gate=pause_on_gate,
            resume_token=resume_token, decisions=decisions,
        )
    from g02 import reviewed_flow

    if node_runner is not None:
        return reviewed_flow.run_with_codex(
            input_ref,
            node_runner=node_runner,
            base=base,
            gate_handler=gate_handler,
            pause_on_gate=pause_on_gate,
            resume_token=resume_token,
            decisions=decisions,
            through=through,
            topic_ids=topic_ids,
        )
    if not pause_on_node:
        raise ValueError(
            "active reviewed (Scout) execution needs either a node_runner (nested Codex) "
            "or pause_on_node=True (host-driven)"
        )

    return reviewed_flow.run(
        input_ref,
        base=base,
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


def make_g02_codex_runner(**options):
    """Codex runner for g02. The deterministic Scout fanout runs in-process inside reviewed_flow;
    every A01/A07/A09 agent node is an isolated codex worker, so this reuses the shared runner."""
    from runners.codex import make_codex_runner
    return make_codex_runner(GRAPH_ID, **options)


_CODEX_THROUGH = [
    "g02-a01-planner", "research-scout-fanout", "g02-a07-paper-review",
    "g02-a09-synthesizer", "user-research-gate",
]


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
            "Research Graph CLI: deterministic seams (front-door / inputs / finalize), "
            "a stub harness (run, no LLM) and a nested-Codex run (run-codex). The host-driven "
            "Scout flow is driven through the research MCP server (research_run_hosted / "
            "research_resume)."
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
        help="run the active Scout flow with nested Codex workers (codex exec) + terminal gate",
    )
    sp.add_argument(
        "context", nargs="?",
        help="path or artifact:// ref to research_graph_input; omit when --resume-token is used",
    )
    sp.add_argument(
        "--gates",
        choices=["prompt", "pause"],
        default="prompt",
        help="prompt for the User Research Gate on stdin (default) or return a pause/resume token",
    )
    sp.add_argument("--resume-token", help="resume token returned by an awaiting_user report")
    sp.add_argument(
        "--decisions",
        help="gate decisions as a JSON object or a path to JSON, keyed by gate name",
    )
    sp.add_argument(
        "--through",
        default="user-research-gate",
        choices=_CODEX_THROUGH,
        help="stop after this active stage (default: User Research Gate)",
    )
    sp.add_argument(
        "--topic-id",
        action="append",
        dest="topic_ids",
        help="restrict Scout discovery to one or more ResearchPlan topics",
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
            from g02.reviewed_flow import terminal_gate_handler as reviewed_terminal_gate

            if args.resume_token and args.context:
                raise ValueError("omit context when resuming with --resume-token")
            if not args.resume_token and not args.context:
                raise ValueError("context is required for a new run")
            handler = reviewed_terminal_gate if args.gates == "prompt" else None
            input_ref = None if args.resume_token else front_door(args.context)["ref"]
            out = run(
                input_ref,
                node_runner=make_g02_codex_runner(),
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
