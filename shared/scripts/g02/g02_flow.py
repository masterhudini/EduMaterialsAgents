"""Thin runnable Research Graph — stub nodes so the whole graph executes end-to-end without
an LLM.

Every node is a no-op that returns an empty ``envelope@1`` (the "pass"). The flow exercises
the REAL runtime seams, though: it loads + re-validates the boundary input contract, walks the
manifest node sequence (single source of truth: shared/graphs/g02.graph.json), logs each
step, then freezes a stub UserApprovedResearchBundle and emits it as a typed handoff.

Replace each stub with a real agent invocation as the graph is fleshed out. Pure stdlib.

Run it directly:
    python3 shared/scripts/g02/g02_flow.py run tests/fixtures/research_graph_input.example.json
"""
from __future__ import annotations

import json
import uuid
import sys as _sys
import pathlib as _pl

# Make `core` importable whether run as a module or as a script.
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))

from core import artifacts, contracts, event_log, gate, graphs, handoff, paths  # noqa: E402
from core import state as st  # noqa: E402
from core import validate_state as vs  # noqa: E402
from g02.runners.stub import stub_node_runner  # noqa: E402
from g02 import planner  # noqa: E402
from g02 import source_selection  # noqa: E402

GRAPH_ID = "g02"
INPUT_CONTRACT = "research_graph_input@1"
OUTPUT_CONTRACT = "user_approved_research_bundle@1"

# ReviewDecision@1 uses minor/major/blocker. The aliases keep the runner compatible with
# older retry matrices that still use low/medium/high/critical.
_SEVERITY_ORDER = {
    "low": 0,
    "minor": 0,
    "medium": 1,
    "major": 2,
    "high": 2,
    "critical": 3,
    "blocker": 3,
}

_POLICY_SEVERITY_ALIASES = {
    "minor": ("minor", "low"),
    "major": ("major", "high", "medium"),
    "blocker": ("blocker", "critical", "high"),
    "low": ("low", "minor"),
    "medium": ("medium", "major"),
    "high": ("high", "major"),
    "critical": ("critical", "blocker"),
}


def _stub_bundle() -> dict:
    """Minimal UserApprovedResearchBundle that satisfies the output contract."""
    return {
        "approved_research_summary_ref": "artifact://g02/research_summary.approved.md",
        "approved_update_findings": [],
        "approved_optional_findings": [],
        "rejected_findings": [],
        "unresolved_claim_policy": {"action": "move_to_speaker_note_or_remove"},
        "solution_handoff": {
            "evidence_cards": [],
            "slide_impact_cards": [],
            "source_cards": [],
            "unresolved_claim_cards": [],
        },
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

    SINGLE place where boundary-only harness scoping lives. G02-A01 receives a validated
    ``research_planner_input@1``. Dependency-based producers still receive the full boundary input
    inside this no-op wiring harness because their approved upstream artifacts do not exist here.
    Real G02-A02 execution must use ``research_domain_prepare`` with an approved ResearchPlan ref.
    """
    if node.get("name") == planner.PLANNER_AGENT:
        return planner.scope_planner_input(rgi)
    return rgi


def node_input_map(rgi: dict, manifest: dict) -> dict:
    """Preview no-op harness inputs; dependency-based real runs use their prepare operation."""
    return {
        n["name"]: scoped_input(n, rgi)
        for n in graphs.nodes(manifest)
        if n.get("kind") == "agent"
    }


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
    ctx = _load_any(path_or_ref, base=base)
    ref = (
        path_or_ref
        if str(path_or_ref).startswith("artifact://")
        else artifacts.store("handoffs/research_graph_input.json", ctx, base=base)
    )
    return {"ref": ref, "task_id": ctx.get("task_id")}


def finalize(bundle_path, *, base=None) -> dict:
    """Validate a result bundle against the output contract and emit it as the typed handoff."""
    bundle = json.loads(_pl.Path(bundle_path).read_text(encoding="utf-8"))
    return handoff.emit_handoff(bundle, OUTPUT_CONTRACT, name="research_bundle", base=base)


def _policy_for(node: dict, manifest: dict) -> dict:
    """Per-node revision policy derived from complexity_class + the graph's retry matrix."""
    matrix = manifest.get("retry_matrix", {})
    attempts = matrix.get(
        node.get("complexity_class"),
        {"low": 0, "medium": 1, "high": 2, "critical": 3},
    )
    return {
        "retry_scope": node.get("retry_scope", "artifact"),
        "max_revision_attempts": attempts,
        "escalation_after_exhaustion": manifest.get(
            "default_escalation",
            "user-research-gate",
        ),
    }


def _max_severity(findings) -> str:
    """Return the highest finding severity.

    Supports the current ReviewDecision@1 taxonomy (minor/major/blocker) and the legacy
    low/medium/high/critical taxonomy so older fixtures do not break the harness.
    """
    best, sev = -1, "major"  # default when a non-approval omits severities
    for finding in findings or []:
        raw = finding.get("severity", "major")
        rank = _SEVERITY_ORDER.get(raw, _SEVERITY_ORDER["major"])
        if rank > best:
            best, sev = rank, raw
    return sev


def _severity_for_policy(severity: str, policy: dict) -> str:
    """Map reviewer severity to a key accepted by the active retry policy."""
    attempts = policy.get("max_revision_attempts", {})
    if severity in attempts:
        return severity
    for alias in _POLICY_SEVERITY_ALIASES.get(severity, (severity,)):
        if alias in attempts:
            return alias
    return severity


def _review(
    reviewer: str,
    node: dict,
    artifact_ref: str,
    attempt: int,
    prior_findings: list,
    node_runner,
    log,
    task_id,
) -> dict:
    """Invoke the universal reviewer through the same node_runner; return ReviewDecision."""
    rnode = {
        "name": reviewer,
        "kind": "reviewer",
        "output_contract": "review_decision@1",
        "review_profile": node.get("review_profile"),
    }
    rctx = {
        "input": {"task_id": task_id},
        "upstream": {node["name"]: artifact_ref},
        "review": {
            "target": node["name"],
            "profile": node.get("review_profile"),
            "artifact_ref": artifact_ref,
            "attempt": attempt,
            "prior_findings": prior_findings,
        },
    }
    env = node_runner(rnode, rctx, log)
    return env.get("artifact") or {}


def _checkpoint_path(token: str):
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in token)
    return paths.drafts_dir() / f"{GRAPH_ID}.{safe}.checkpoint.json"


def _save_checkpoint(token, input_ref, produced_refs, gate_decisions) -> None:
    _checkpoint_path(token).write_text(
        json.dumps(
            {
                "graph": GRAPH_ID,
                "input_ref": input_ref,
                "produced_refs": produced_refs,
                "gate_decisions": gate_decisions,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _load_checkpoint(token: str) -> dict:
    return json.loads(_checkpoint_path(token).read_text(encoding="utf-8"))


def _clear_checkpoint(token: str) -> None:
    _checkpoint_path(token).unlink(missing_ok=True)


def terminal_gate_handler(payload: dict) -> dict:
    """Terminal surface: print the gate request, read one JSON line of decisions from stdin."""
    _sys.stderr.write(
        json.dumps(
            {
                "gate": payload["gate"],
                "required_decisions": payload["required_decisions"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    _sys.stderr.write("Enter decision JSON for this gate, then newline:\n")
    _sys.stderr.flush()
    return json.loads(_sys.stdin.readline())


def _produced_artifact_ref(stored_ref: str, artifact_type: str, contract_ref: str,
                           *, base=None) -> str | None:
    """Resolve a typed artifact from a node's persisted artifact or envelope."""
    try:
        value = artifacts.hydrate(stored_ref, base=base)
    except (OSError, ValueError, KeyError, IndexError):
        return None
    if isinstance(value, dict) and value.get("schema_version") == contract_ref:
        return stored_ref
    for descriptor in value.get("produced", []) if isinstance(value, dict) else []:
        if not isinstance(descriptor, dict) or descriptor.get("type") != artifact_type:
            continue
        ref = descriptor.get("path") or descriptor.get("ref")
        if isinstance(ref, str) and ref.startswith(artifacts.SCHEME):
            return ref
    return None


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
    through="g02-a06-paper-retrieval",
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
    sp.add_argument("context", help="path or artifact:// ref to a research_graph_input bundle")
    sp.add_argument(
        "--gates",
        choices=["prompt", "pause"],
        default="prompt",
        help="prompt for the two-step gate on stdin (default) or return a pause/resume token",
    )
    sp.add_argument(
        "--through",
        default="g02-a06-paper-retrieval",
        choices=[
            "g02-a01-planner", "g02-a02-domain", "g02-a03-canonical-sources",
            "g02-a04-recent-developments", "g02-a11-market-cases",
            "g02-a05-candidate-source-index", "user-source-selection-gate",
            "g02-a06-paper-retrieval",
        ],
        help="stop after this implemented stage (default: A06)",
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

            handler = reviewed_terminal_gate if args.gates == "prompt" else None
            out = run(
                front_door(args.context)["ref"],
                node_runner=codex_node_runner,
                gate_handler=handler,
                pause_on_gate=(args.gates == "pause"),
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
