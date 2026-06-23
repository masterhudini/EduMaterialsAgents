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

import sys as _sys
import pathlib as _pl

# Make `core` / `g02` importable whether run as a module or as a script.
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))

from core import artifacts, contracts, engine  # noqa: E402
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
            "evidence_cards": [], "slide_impact_cards": [],
            "source_cards": [], "unresolved_claim_cards": [],
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
    approved_ref = decision.get("human_approved_source_set_ref") if isinstance(decision, dict) else None
    if (isinstance(decision, dict) and not approved_ref
            and isinstance(decision.get("selection"), dict)
            and isinstance(decision.get("confirmation_token"), str)):
        finalized = source_selection.finalize_source_selection(
            ref, decision["selection"], decision["confirmation_token"], base=base)
        approved_ref = next((item.get("path") for item in finalized.get("produced", [])
                             if item.get("type") == "human_approved_source_set"), None)
    if isinstance(approved_ref, str):
        approved_set = artifacts.hydrate(approved_ref, base=base)
        validation = contracts.validate(approved_set, "human_approved_source_set@1")
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

def run(input_ref=None, **kwargs):
    # Reviewed/partial Codex execution of the implemented A01–A06 frontier (through / topic_ids)
    # lives in its own g02-specific module; the generic core.engine stays a stub/wiring walk.
    if kwargs.pop("reviewed", False):
        from g02 import reviewed_flow
        return reviewed_flow.run(input_ref, **kwargs)
    return engine.run(SPEC, input_ref, **kwargs)


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


def _run_stub_harness(
    input_ref=None,
    *,
    base=None,
    node_runner=None,
    gate_handler=None,
    pause_on_gate=False,
    resume_token=None,
    decisions=None,
) -> dict:
    """Run the Research Graph; return the output handoff descriptor, or an awaiting_user request.

    ``node_runner(node, ctx, log) -> envelope`` is the per-host executor (default: no-op stub).
    Gates (one spec per ``user-gate`` node in the manifest, two surfaces):
      - default: auto-approved (wiring/harness);
      - ``gate_handler(payload) -> decision``: synchronous surface (e.g. terminal);
      - ``pause_on_gate=True``: checkpoint and return ``{"status": "awaiting_user", "resume_token",
        "gate", "required_decisions", ...}``; resume via ``run(resume_token=..., decisions={gate: ...})``.
    """
    log = event_log.open_log(GRAPH_ID)
    node_runner = node_runner or stub_node_runner

    if resume_token and input_ref is None:
        cp = _load_checkpoint(resume_token)
        input_ref = cp["input_ref"]
        produced_refs = dict(cp["produced_refs"])
        gate_decisions = dict(cp["gate_decisions"])
        token = resume_token
        log.append("ENTRY", "resume", detail={"resume_token": token, "done": sorted(produced_refs)})
    else:
        produced_refs, gate_decisions = {}, {}
        token = resume_token or uuid.uuid4().hex[:12]

    gate_decisions.update(decisions or {})

    # Front door — load + RE-validate the boundary contract; graph never starts on bad input.
    rgi = handoff.load_handoff(input_ref, contract_ref=INPUT_CONTRACT, base=base)
    ref0 = input_ref.get("ref") if isinstance(input_ref, dict) else input_ref
    log.append("ENTRY", "load_input", detail={"ref": ref0, "task_id": rgi.get("task_id")})

    state = st.new_state(GRAPH_ID)
    st.set_field(state, "research_graph_input", rgi, "confirmed")

    # Walk the manifest — pass the context to each node; agents get a reviewer pass.
    manifest = graphs.load(GRAPH_ID)
    reviewer = manifest.get("reviewer", "g02-a10-output-reviewer")
    task_id = rgi.get("task_id")

    for node in graphs.nodes(manifest):
        kind = node.get("kind")

        if kind == "agent":
            name = node["name"]
            if name in produced_refs:  # resume: this node already completed
                continue

            policy = _policy_for(node, manifest)
            output_contract = node.get("output_contract")
            attempt, prior_findings, ref = 0, [], None

            while True:
                # F1: scoped graph input + refs to upstream artifacts (lazy hydration). On a
                # revision, also hand back the prior artifact ref + the reviewer's findings.
                ctx = {"input": scoped_input(node, rgi), "upstream": dict(produced_refs)}
                if attempt:
                    ctx["revision"] = {
                        "attempt": attempt,
                        "prior_artifact_ref": ref,
                        "items": prior_findings,
                    }

                envelope = node_runner(node, ctx, log)
                check = contracts.validate_envelope(envelope)
                if not check["ok"]:
                    log.append(
                        name,
                        "invalid_envelope",
                        status="failed",
                        detail={"errors": check["errors"]},
                    )

                # F1: persist the TYPED artifact (envelope["artifact"]) validated against the
                # node's output_contract; stubs carry no artifact -> persist the envelope.
                artifact = envelope.get("artifact")
                if artifact is not None and output_contract:
                    av = contracts.validate(artifact, output_contract)
                    if not av["ok"]:
                        log.append(
                            name,
                            "invalid_artifact",
                            status="failed",
                            detail={"contract": output_contract, "errors": av["errors"]},
                        )

                ref = artifacts.store(
                    f"research/{name}.json",
                    artifact if artifact is not None else envelope,
                    base=base,
                )
                log.append(
                    name,
                    "persisted",
                    detail={
                        "ref": ref,
                        "contract": output_contract,
                        "typed": artifact is not None,
                        "attempt": attempt,
                    },
                )

                # A REVISE verdict permits one producer correction. The corrected artifact is
                # accepted after deterministic validation and is never sent to A10 again.
                if attempt == 1:
                    log.append(
                        name,
                        "revision_completed",
                        status="ok",
                        detail={"ref": ref, "finding_count": len(prior_findings)},
                    )
                    break

                # F2: review the artifact; the universal reviewer runs via the same node_runner.
                review = _review(
                    reviewer,
                    node,
                    ref,
                    attempt,
                    prior_findings,
                    node_runner,
                    log,
                    task_id,
                )

                # Current contract: decision/findings. Legacy compatibility: verdict/issues.
                review_decision = (review or {}).get("decision", (review or {}).get("verdict", "APPROVED"))
                findings = (review or {}).get("findings", (review or {}).get("issues", []))

                log.append(
                    reviewer,
                    "review",
                    status=review_decision,
                    detail={
                        "target": name,
                        "profile": node.get("review_profile"),
                        "attempt": attempt,
                    },
                )

                if review_decision in ("APPROVED", "APPROVED_WITH_WARNINGS"):
                    break

                severity = _max_severity(findings)
                policy_severity = _severity_for_policy(severity, policy)

                if review_decision == "BLOCKED":
                    log.append(
                        name,
                        "escalated",
                        status="blocked",
                        detail={
                            "to": policy.get("escalation_after_exhaustion"),
                            "severity": severity,
                            "policy_severity": policy_severity,
                        },
                    )
                    return {
                        "status": "blocked", "node": name,
                        "review_decision": review_decision, "findings": findings,
                    }

                if review_decision == "REVISE":
                    attempt = 1
                    prior_findings = findings
                    continue

                log.append(
                    name,
                    "escalated",
                    status="blocked",
                    detail={
                        "to": policy.get("escalation_after_exhaustion"),
                        "severity": severity,
                        "policy_severity": policy_severity,
                    },
                )
                return {
                    "status": "blocked", "node": name,
                    "review_decision": review_decision, "findings": findings,
                }

            produced_refs[name] = ref

        elif kind == "user-gate":
            gname = node["name"]
            source_index_ref = None
            if gname == "user-source-selection-gate":
                stored = produced_refs.get("g02-a05-candidate-source-index")
                if isinstance(stored, str):
                    source_index_ref = _produced_artifact_ref(
                        stored, "candidate_source_index", "candidate_source_index@1", base=base
                    )
            if gname not in gate_decisions:
                payload = {
                    "graph": GRAPH_ID,
                    "gate": gname,
                    "required_decisions": node.get("required_decisions", []),
                    "context": {"artifacts": dict(produced_refs)},
                }
                if source_index_ref:
                    prepared_gate = source_selection.prepare_source_selection(
                        source_index_ref, base=base
                    )
                    if prepared_gate.get("ready"):
                        payload["source_selection"] = prepared_gate["gate_prompt"]

                if gate_handler is not None:
                    # Synchronous surface, e.g. terminal.
                    gate_decisions[gname] = gate_handler(payload)
                elif pause_on_gate:
                    # Async surface, e.g. skill: pause + resume.
                    _save_checkpoint(token, input_ref, produced_refs, gate_decisions)
                    log.append(
                        gname,
                        "awaiting_user",
                        status="paused",
                        detail={"resume_token": token},
                    )
                    return {"status": "awaiting_user", "resume_token": token, **payload}
                else:
                    # Default: auto-approve for wiring/harness.
                    gate_decisions[gname] = {"auto": True}

            if gname == "user-source-selection-gate" and source_index_ref:
                decision = gate_decisions[gname]
                approved_ref = decision.get("human_approved_source_set_ref") \
                    if isinstance(decision, dict) else None
                if isinstance(decision, dict) and not approved_ref \
                        and isinstance(decision.get("selection"), dict) \
                        and isinstance(decision.get("confirmation_token"), str):
                    finalized = source_selection.finalize_source_selection(
                        source_index_ref, decision["selection"], decision["confirmation_token"],
                        base=base,
                    )
                    approved_ref = next((
                        item.get("path") for item in finalized.get("produced", [])
                        if item.get("type") == "human_approved_source_set"
                    ), None)
                if isinstance(approved_ref, str):
                    approved_set = artifacts.hydrate(approved_ref, base=base)
                    validation = contracts.validate(
                        approved_set, "human_approved_source_set@1"
                    )
                    if not validation["ok"]:
                        raise ValueError("invalid human approved source set: "
                                         + "; ".join(validation["errors"]))
                    produced_refs[gname] = approved_ref

            log.append(
                gname,
                "user_decision",
                status="APPROVED",
                detail={
                    "keys": sorted(gate_decisions[gname])
                    if isinstance(gate_decisions[gname], dict)
                    else None
                },
            )

    # Freeze a stub output bundle and emit it as the typed handoff to Solution.
    st.set_field(state, "user_approved_research_bundle", _stub_bundle(), "confirmed")

    def _validator(s):
        return vs.validate_state(
            s,
            required=["research_graph_input", "user_approved_research_bundle"],
        )

    spec = gate.pass_gate_and_freeze(state, _validator, drop={"research_graph_input"})
    desc = handoff.emit_handoff(
        spec["user_approved_research_bundle"],
        OUTPUT_CONTRACT,
        name="research_bundle",
        base=base,
    )
    log.append("EXIT", "emit_handoff", detail=desc)
    _clear_checkpoint(token)
    return desc


def run(
    input_ref=None,
    *,
    base=None,
    node_runner=None,
    gate_handler=None,
    pause_on_gate=False,
    resume_token=None,
    decisions=None,
    reviewed=False,
    through="g02-a09-synthesizer",
    topic_ids=None,
) -> dict:
    """Dispatch to the no-op wiring harness or the fail-closed reviewed frontier.

    ``reviewed=False`` is intentionally the default for compatibility with deterministic wiring
    tests. Every real host entrypoint must pass ``reviewed=True``.
    """
    if not reviewed:
        return _run_stub_harness(
            input_ref,
            base=base,
            node_runner=node_runner,
            gate_handler=gate_handler,
            pause_on_gate=pause_on_gate,
            resume_token=resume_token,
            decisions=decisions,
        )
    if node_runner is None:
        raise ValueError("reviewed execution requires a real host node_runner")
    from g02 import reviewed_flow

    return reviewed_flow.run(
        input_ref,
        base=base,
        node_runner=node_runner,
        gate_handler=gate_handler,
        pause_on_gate=pause_on_gate,
        resume_token=resume_token,
        decisions=decisions,
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
            from g02.runners.codex import codex_node_runner
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
