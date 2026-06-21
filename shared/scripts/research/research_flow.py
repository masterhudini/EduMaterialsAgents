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
import uuid
import sys as _sys
import pathlib as _pl

# Make `core` importable whether run as a module or as a script.
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))

from core import artifacts, contracts, event_log, gate, graphs, handoff, paths, revision  # noqa: E402
from core import state as st  # noqa: E402
from core import validate_state as vs  # noqa: E402
from research.runners.stub import stub_node_runner  # noqa: E402

_SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

GRAPH_ID = "research"
INPUT_CONTRACT = "research_graph_input@1"
OUTPUT_CONTRACT = "user_approved_research_bundle@1"


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
    ctx = _load_any(path_or_ref, base=base)
    ref = (path_or_ref if str(path_or_ref).startswith("artifact://")
           else artifacts.store("handoffs/research_graph_input.json", ctx, base=base))
    return {"ref": ref, "task_id": ctx.get("task_id")}


def finalize(bundle_path, *, base=None) -> dict:
    """Validate a result bundle against the output contract and emit it as the typed handoff."""
    bundle = json.loads(_pl.Path(bundle_path).read_text(encoding="utf-8"))
    return handoff.emit_handoff(bundle, OUTPUT_CONTRACT, name="research_bundle", base=base)


def _policy_for(node: dict, manifest: dict) -> dict:
    """Per-node revision policy derived from complexity_class + the graph's retry matrix."""
    matrix = manifest.get("retry_matrix", {})
    attempts = matrix.get(node.get("complexity_class"),
                          {"low": 0, "medium": 1, "high": 2, "critical": 3})
    return {"retry_scope": node.get("retry_scope", "artifact"),
            "max_revision_attempts": attempts,
            "escalation_after_exhaustion": manifest.get("default_escalation", "user-research-gate")}


def _max_severity(issues) -> str:
    best, sev = -1, "high"  # default when a non-approval omits severities
    for issue in issues or []:
        rank = _SEVERITY_ORDER.get(issue.get("severity", "high"), 2)
        if rank > best:
            best, sev = rank, issue.get("severity", "high")
    return sev


def _review(reviewer: str, node: dict, artifact_ref: str, attempt: int, prior_findings: list,
            node_runner, log, task_id) -> dict:
    """Invoke the universal reviewer (same node_runner) for one artifact; return ReviewDecision."""
    rnode = {"name": reviewer, "kind": "reviewer", "output_contract": "review_decision@1",
             "review_profile": node.get("review_profile")}
    rctx = {"input": {"task_id": task_id}, "upstream": {node["name"]: artifact_ref},
            "review": {"target": node["name"], "profile": node.get("review_profile"),
                       "artifact_ref": artifact_ref, "attempt": attempt,
                       "prior_findings": prior_findings}}
    env = node_runner(rnode, rctx, log)
    return env.get("artifact") or {}


def _checkpoint_path(token: str):
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in token)
    return paths.drafts_dir() / f"{GRAPH_ID}.{safe}.checkpoint.json"


def _save_checkpoint(token, input_ref, produced_refs, gate_decisions) -> None:
    _checkpoint_path(token).write_text(
        json.dumps({"graph": GRAPH_ID, "input_ref": input_ref,
                    "produced_refs": produced_refs, "gate_decisions": gate_decisions},
                   ensure_ascii=False, indent=2), encoding="utf-8")


def _load_checkpoint(token: str) -> dict:
    return json.loads(_checkpoint_path(token).read_text(encoding="utf-8"))


def _clear_checkpoint(token: str) -> None:
    _checkpoint_path(token).unlink(missing_ok=True)


def terminal_gate_handler(payload: dict) -> dict:
    """Terminal surface: print the gate request, read one JSON line of decisions from stdin."""
    _sys.stderr.write(json.dumps({"gate": payload["gate"],
                                  "required_decisions": payload["required_decisions"]},
                                 ensure_ascii=False, indent=2) + "\n")
    _sys.stderr.write("Enter decision JSON for this gate, then newline:\n")
    _sys.stderr.flush()
    return json.loads(_sys.stdin.readline())


def run(input_ref=None, *, base=None, node_runner=None, gate_handler=None,
        pause_on_gate=False, resume_token=None, decisions=None) -> dict:
    """Run the Research Graph; return the output handoff descriptor, or an ``awaiting_user`` request.

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

    # front door — load + RE-validate the boundary contract (graph never starts on bad input)
    rgi = handoff.load_handoff(input_ref, contract_ref=INPUT_CONTRACT, base=base)
    ref0 = input_ref.get("ref") if isinstance(input_ref, dict) else input_ref
    log.append("ENTRY", "load_input", detail={"ref": ref0, "task_id": rgi.get("task_id")})
    state = st.new_state(GRAPH_ID)
    st.set_field(state, "research_graph_input", rgi, "confirmed")

    # 3. walk the manifest — pass the context to each node; agents get a reviewer pass
    manifest = graphs.load(GRAPH_ID)
    reviewer = manifest.get("reviewer", "research-output-reviewer")
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
                    ctx["revision"] = {"attempt": attempt, "prior_artifact_ref": ref,
                                       "items": prior_findings}
                envelope = node_runner(node, ctx, log)
                check = contracts.validate_envelope(envelope)
                if not check["ok"]:
                    log.append(name, "invalid_envelope", status="failed",
                               detail={"errors": check["errors"]})
                # F1: persist the TYPED artifact (envelope["artifact"]) validated against the
                # node's output_contract; stubs carry no artifact -> persist the envelope.
                artifact = envelope.get("artifact")
                if artifact is not None and output_contract:
                    av = contracts.validate(artifact, output_contract)
                    if not av["ok"]:
                        log.append(name, "invalid_artifact", status="failed",
                                   detail={"contract": output_contract, "errors": av["errors"]})
                ref = artifacts.store(f"research/{name}.json",
                                      artifact if artifact is not None else envelope, base=base)
                log.append(name, "persisted",
                           detail={"ref": ref, "contract": output_contract,
                                   "typed": artifact is not None, "attempt": attempt})

                # F2: review the artifact; the universal reviewer runs via the same node_runner.
                decision = _review(reviewer, node, ref, attempt, prior_findings, node_runner, log, task_id)
                verdict = (decision or {}).get("verdict", "APPROVED")
                log.append(reviewer, "review", status=verdict,
                           detail={"target": name, "profile": node.get("review_profile"), "attempt": attempt})
                if verdict in ("APPROVED", "APPROVED_WITH_WARNINGS"):
                    break
                severity = _max_severity(decision.get("issues"))
                step = revision.decide(policy, severity, approved=False, attempts_used=attempt)
                log.append(name, "revision_decision", status=step["action"],
                           detail={"severity": severity, "attempt": attempt})
                if step["action"] == "REVISE":
                    attempt += 1
                    prior_findings = decision.get("issues", [])
                    continue
                log.append(name, "escalated", status="blocked",
                           detail={"to": step.get("to"), "severity": severity})
                break
            produced_refs[name] = ref
        elif kind == "user-gate":
            gname = node["name"]
            if gname not in gate_decisions:
                payload = {"graph": GRAPH_ID, "gate": gname,
                           "required_decisions": node.get("required_decisions", []),
                           "context": {"artifacts": dict(produced_refs)}}
                if gate_handler is not None:                  # synchronous surface (terminal)
                    gate_decisions[gname] = gate_handler(payload)
                elif pause_on_gate:                           # async surface (skill): pause + resume
                    _save_checkpoint(token, input_ref, produced_refs, gate_decisions)
                    log.append(gname, "awaiting_user", status="paused", detail={"resume_token": token})
                    return {"status": "awaiting_user", "resume_token": token, **payload}
                else:                                         # default: auto-approve (wiring/harness)
                    gate_decisions[gname] = {"auto": True}
            log.append(gname, "user_decision", status="APPROVED",
                       detail={"keys": sorted(gate_decisions[gname])
                               if isinstance(gate_decisions[gname], dict) else None})

    # 4. freeze a stub output bundle and emit it as the typed handoff to Solution
    st.set_field(state, "user_approved_research_bundle", _stub_bundle(), "confirmed")

    def _validator(s):
        return vs.validate_state(s, required=["research_graph_input",
                                              "user_approved_research_bundle"])

    spec = gate.pass_gate_and_freeze(state, _validator, drop={"research_graph_input"})
    desc = handoff.emit_handoff(spec["user_approved_research_bundle"], OUTPUT_CONTRACT,
                                name="research_bundle", base=base)
    log.append("EXIT", "emit_handoff", detail=desc)
    _clear_checkpoint(token)
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
    sp.add_argument("--gates", choices=["auto", "prompt"], default="auto",
                    help="auto-approve gates (default) or prompt for each on stdin")

    sp = sub.add_parser("run-codex",
                        help="run the whole graph with Codex workers (codex exec) + terminal gates")
    sp.add_argument("context", help="path or artifact:// ref to a research_graph_input bundle")
    sp.add_argument("--gates", choices=["auto", "prompt"], default="prompt",
                    help="prompt for each gate on stdin (default) or auto-approve")

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
            handler = terminal_gate_handler if args.gates == "prompt" else None
            out = run(front_door(args.context)["ref"], gate_handler=handler)
        elif args.cmd == "run-codex":
            from research.runners.codex import codex_node_runner
            handler = terminal_gate_handler if args.gates == "prompt" else None
            out = run(front_door(args.context)["ref"], node_runner=codex_node_runner, gate_handler=handler)
        elif args.cmd == "finalize":
            out = finalize(args.bundle)
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=_sys.stderr)
        return 1
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli(_sys.argv[1:]))
