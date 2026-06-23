"""Generic graph engine — host- and graph-agnostic.

One ``run`` drives any graph defined by a manifest (single source of truth) plus an
``EngineSpec`` that supplies the graph's boundary contracts and the two injection points that
differ per graph: how a node's scoped input is shaped, and the (thin/stub) exit bundle. Graphs
with bespoke human-gate handling (e.g. source selection) attach ``gate_prepare`` / ``gate_finalize``
hooks; everything else — front door, the per-node reviewer/revision loop, user gates
(auto / terminal / pause-resume), checkpointing, freeze + handoff — is generic.

Pure stdlib. ``node_runner(node, ctx, log) -> envelope@1`` is the per-host executor (Claude Task /
Codex exec / stub). ``ctx`` carries ``{"input": <scoped input>, "upstream": {producer: ref}}``.
"""
from __future__ import annotations

import json
import uuid
import sys as _sys
from dataclasses import dataclass
from typing import Any, Callable, Optional

from . import artifacts, contracts, event_log, gate, graphs, handoff, paths, revision
from . import state as st
from . import validate_state as vs

# ReviewDecision@1 uses minor/major/blocker; aliases keep older low/medium/high/critical matrices working.
_SEVERITY_ORDER = {
    "low": 0, "minor": 0, "medium": 1, "major": 2, "high": 2, "critical": 3, "blocker": 3,
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


@dataclass
class EngineSpec:
    """Per-graph configuration the generic engine needs."""
    graph_id: str
    input_contract: str
    output_contract: str
    scoped_input: Callable[[dict, dict], dict]          # (node, graph_input) -> node input
    stub_exit_bundle: Callable[[], dict]                # thin exit artifact, valid vs output_contract
    input_state_field: str                              # state key for the boundary input
    output_state_field: str                             # state key for the exit bundle
    artifact_namespace: str                             # store prefix for node artifacts
    emit_name: str                                      # handoff filename stem
    # Graph-specific human-gate hooks (default None = standard auto/terminal/pause behavior):
    gate_prepare: Optional[Callable[[str, dict, Any], dict]] = None      # -> {"payload": {...}}
    gate_finalize: Optional[Callable[[str, dict, dict, Any], Optional[str]]] = None  # -> approved_ref


def default_stub_runner(node: dict, ctx: dict, log) -> dict:
    """No-op executor: records the context it was handed, returns an empty ok-envelope."""
    name = node["name"]
    log.append(name, "run", detail={
        "kind": node.get("kind"),
        "received_task_id": (ctx.get("input") or {}).get("task_id"),
        "upstream": sorted((ctx.get("upstream") or {})),
        "stub": True,
    })
    return {"status": "ok", "produced": [], "summary": f"{name}: stub no-op", "issues": []}


# ---- boundary seams ------------------------------------------------------

def load_context(spec: EngineSpec, path, *, validate: bool = True) -> dict:
    """Read a boundary-input JSON from disk; validate it against the graph's input contract."""
    seed = json.loads(_read(path))
    if validate:
        res = contracts.validate(seed, spec.input_contract)
        if not res["ok"]:
            raise ValueError(f"context fails {spec.input_contract}: " + "; ".join(res["errors"]))
    return seed


def _read(path) -> str:
    import pathlib
    return pathlib.Path(path).read_text(encoding="utf-8")


def _load_any(spec: EngineSpec, path_or_ref, *, base=None) -> dict:
    """Load + validate boundary input from a file path or an artifact:// ref."""
    if str(path_or_ref).startswith("artifact://"):
        return handoff.load_handoff(path_or_ref, contract_ref=spec.input_contract, base=base)
    return load_context(spec, path_or_ref)


def front_door(spec: EngineSpec, path_or_ref, *, base=None) -> dict:
    """Validate the input context and ensure it is in the artifact store. Returns {ref, task_id}."""
    ctx = _load_any(spec, path_or_ref, base=base)
    ref = (
        path_or_ref if str(path_or_ref).startswith("artifact://")
        else artifacts.store(f"handoffs/{spec.graph_id}_input.json", ctx, base=base)
    )
    return {"ref": ref, "task_id": ctx.get("task_id")}


def finalize(spec: EngineSpec, bundle_path, *, base=None) -> dict:
    """Validate a result bundle against the output contract and emit it as the typed handoff."""
    bundle = json.loads(_read(bundle_path))
    return handoff.emit_handoff(bundle, spec.output_contract, name=spec.emit_name, base=base)


def node_input_map(spec: EngineSpec, rgi: dict, manifest: dict) -> dict:
    """Preview the scoped input each agent node receives (for isolated agent testing)."""
    return {n["name"]: spec.scoped_input(n, rgi)
            for n in graphs.nodes(manifest) if n.get("kind") == "agent"}


# ---- reviewer / revision -------------------------------------------------

def _policy_for(node: dict, manifest: dict) -> dict:
    matrix = manifest.get("retry_matrix", {})
    attempts = matrix.get(node.get("complexity_class"),
                          {"low": 0, "medium": 1, "high": 2, "critical": 3})
    return {
        "retry_scope": node.get("retry_scope", "artifact"),
        "max_revision_attempts": attempts,
        "escalation_after_exhaustion": manifest.get("default_escalation", "user-gate"),
    }


def _max_severity(findings) -> str:
    best, sev = -1, "major"
    for finding in findings or []:
        raw = finding.get("severity", "major")
        rank = _SEVERITY_ORDER.get(raw, _SEVERITY_ORDER["major"])
        if rank > best:
            best, sev = rank, raw
    return sev


def _severity_for_policy(severity: str, policy: dict) -> str:
    attempts = policy.get("max_revision_attempts", {})
    if severity in attempts:
        return severity
    for alias in _POLICY_SEVERITY_ALIASES.get(severity, (severity,)):
        if alias in attempts:
            return alias
    return severity


def _review(reviewer, node, artifact_ref, attempt, prior_findings, node_runner, log, task_id) -> dict:
    """Invoke the universal reviewer through the same node_runner; return ReviewDecision."""
    rnode = {"name": reviewer, "kind": "reviewer", "output_contract": "review_decision@1",
             "review_profile": node.get("review_profile")}
    rctx = {"input": {"task_id": task_id}, "upstream": {node["name"]: artifact_ref},
            "review": {"target": node["name"], "profile": node.get("review_profile"),
                       "artifact_ref": artifact_ref, "attempt": attempt, "prior_findings": prior_findings}}
    env = node_runner(rnode, rctx, log)
    return env.get("artifact") or {}


def _produced_artifact_ref(stored_ref: str, artifact_type: str, contract_ref: str, *, base=None) -> str | None:
    """Resolve a typed artifact ref from a node's persisted artifact or envelope.produced[]."""
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


# ---- checkpoints / gates -------------------------------------------------

def _checkpoint_path(graph_id: str, token: str):
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in token)
    return paths.drafts_dir() / f"{graph_id}.{safe}.checkpoint.json"


def _save_checkpoint(graph_id, token, input_ref, produced_refs, gate_decisions) -> None:
    _checkpoint_path(graph_id, token).write_text(
        json.dumps({"graph": graph_id, "input_ref": input_ref,
                    "produced_refs": produced_refs, "gate_decisions": gate_decisions},
                   ensure_ascii=False, indent=2), encoding="utf-8")


def _load_checkpoint(graph_id, token: str) -> dict:
    return json.loads(_checkpoint_path(graph_id, token).read_text(encoding="utf-8"))


def _clear_checkpoint(graph_id, token: str) -> None:
    _checkpoint_path(graph_id, token).unlink(missing_ok=True)


def terminal_gate_handler(payload: dict) -> dict:
    """Terminal surface: print the gate request, read one JSON line of decisions from stdin."""
    _sys.stderr.write(json.dumps({"gate": payload["gate"],
                                  "required_decisions": payload["required_decisions"]},
                                 ensure_ascii=False, indent=2) + "\n")
    _sys.stderr.write("Enter decision JSON for this gate, then newline:\n")
    _sys.stderr.flush()
    return json.loads(_sys.stdin.readline())


# ---- the engine ----------------------------------------------------------

def run(spec: EngineSpec, input_ref=None, *, base=None, node_runner=None, gate_handler=None,
        pause_on_gate=False, resume_token=None, decisions=None) -> dict:
    """Run a graph; return the output handoff descriptor, or an ``awaiting_user`` request.

    Gates: default auto-approve; ``gate_handler(payload)->decision`` for a synchronous surface;
    ``pause_on_gate=True`` to checkpoint and return an awaiting_user request resumed via
    ``run(spec, resume_token=..., decisions={gate: ...})``.
    """
    log = event_log.open_log(spec.graph_id)
    node_runner = node_runner or default_stub_runner

    if resume_token and input_ref is None:
        cp = _load_checkpoint(spec.graph_id, resume_token)
        input_ref = cp["input_ref"]
        produced_refs = dict(cp["produced_refs"])
        gate_decisions = dict(cp["gate_decisions"])
        token = resume_token
        log.append("ENTRY", "resume", detail={"resume_token": token, "done": sorted(produced_refs)})
    else:
        produced_refs, gate_decisions = {}, {}
        token = resume_token or uuid.uuid4().hex[:12]
    gate_decisions.update(decisions or {})

    rgi = handoff.load_handoff(input_ref, contract_ref=spec.input_contract, base=base)
    ref0 = input_ref.get("ref") if isinstance(input_ref, dict) else input_ref
    log.append("ENTRY", "load_input", detail={"ref": ref0, "task_id": rgi.get("task_id")})

    state = st.new_state(spec.graph_id)
    st.set_field(state, spec.input_state_field, rgi, "confirmed")

    manifest = graphs.load(spec.graph_id)
    reviewer = manifest.get("reviewer")
    task_id = rgi.get("task_id")

    for node in graphs.nodes(manifest):
        kind = node.get("kind")

        if kind == "agent":
            name = node["name"]
            if name in produced_refs:  # resume: already completed
                continue
            policy = _policy_for(node, manifest)
            output_contract = node.get("output_contract")
            attempt, prior_findings, ref = 0, [], None

            while True:
                ctx = {"input": spec.scoped_input(node, rgi), "upstream": dict(produced_refs)}
                if attempt:
                    ctx["revision"] = {"attempt": attempt, "prior_artifact_ref": ref, "items": prior_findings}

                envelope = node_runner(node, ctx, log)
                check = contracts.validate_envelope(envelope)
                if not check["ok"]:
                    log.append(name, "invalid_envelope", status="failed", detail={"errors": check["errors"]})

                artifact = envelope.get("artifact")
                if artifact is not None and output_contract:
                    av = contracts.validate(artifact, output_contract)
                    if not av["ok"]:
                        log.append(name, "invalid_artifact", status="failed",
                                   detail={"contract": output_contract, "errors": av["errors"]})

                ref = artifacts.store(f"{spec.artifact_namespace}/{name}.json",
                                      artifact if artifact is not None else envelope, base=base)
                log.append(name, "persisted",
                           detail={"ref": ref, "contract": output_contract,
                                   "typed": artifact is not None, "attempt": attempt})

                review = _review(reviewer, node, ref, attempt, prior_findings, node_runner, log, task_id)
                review_decision = (review or {}).get("decision", (review or {}).get("verdict", "APPROVED"))
                findings = (review or {}).get("findings", (review or {}).get("issues", []))
                log.append(reviewer, "review", status=review_decision,
                           detail={"target": name, "profile": node.get("review_profile"), "attempt": attempt})

                if review_decision in ("APPROVED", "APPROVED_WITH_WARNINGS"):
                    break

                severity = _max_severity(findings)
                policy_severity = _severity_for_policy(severity, policy)
                if review_decision == "BLOCKED":
                    log.append(name, "escalated", status="blocked",
                               detail={"to": policy.get("escalation_after_exhaustion"),
                                       "severity": severity, "policy_severity": policy_severity})
                    break

                step = revision.decide(policy, policy_severity, approved=False, attempts_used=attempt)
                log.append(name, "revision_decision", status=step["action"],
                           detail={"severity": severity, "policy_severity": policy_severity, "attempt": attempt})
                if step["action"] == "REVISE":
                    attempt += 1
                    prior_findings = findings
                    continue
                log.append(name, "escalated", status="blocked",
                           detail={"to": step.get("to"), "severity": severity, "policy_severity": policy_severity})
                break

            produced_refs[name] = ref

        elif kind == "user-gate":
            gname = node["name"]
            extra = spec.gate_prepare(gname, produced_refs, base) if spec.gate_prepare else {}
            if gname not in gate_decisions:
                payload = {"graph": spec.graph_id, "gate": gname,
                           "required_decisions": node.get("required_decisions", []),
                           "context": {"artifacts": dict(produced_refs)}}
                payload.update((extra or {}).get("payload", {}))
                if gate_handler is not None:                       # synchronous surface (terminal)
                    gate_decisions[gname] = gate_handler(payload)
                elif pause_on_gate:                                # async surface (skill): pause + resume
                    _save_checkpoint(spec.graph_id, token, input_ref, produced_refs, gate_decisions)
                    log.append(gname, "awaiting_user", status="paused", detail={"resume_token": token})
                    return {"status": "awaiting_user", "resume_token": token, **payload}
                else:                                              # default: auto-approve (wiring/harness)
                    gate_decisions[gname] = {"auto": True}

            if spec.gate_finalize:
                approved_ref = spec.gate_finalize(gname, gate_decisions[gname], produced_refs, base)
                if approved_ref:
                    produced_refs[gname] = approved_ref

            log.append(gname, "user_decision", status="APPROVED",
                       detail={"keys": sorted(gate_decisions[gname])
                               if isinstance(gate_decisions[gname], dict) else None})

    st.set_field(state, spec.output_state_field, spec.stub_exit_bundle(), "confirmed")

    def _validator(s):
        return vs.validate_state(s, required=[spec.input_state_field, spec.output_state_field])

    frozen = gate.pass_gate_and_freeze(state, _validator, drop={spec.input_state_field})
    desc = handoff.emit_handoff(frozen[spec.output_state_field], spec.output_contract,
                                name=spec.emit_name, base=base)
    log.append("EXIT", "emit_handoff", detail=desc)
    _clear_checkpoint(spec.graph_id, token)
    return desc


def make_cli(spec: EngineSpec, *, codex_runner=None) -> Callable[[list], int]:
    """Build the deterministic CLI (front-door / inputs / run / run-codex / finalize) for a graph."""
    def cli(argv: list[str]) -> int:
        import argparse
        p = argparse.ArgumentParser(
            prog=f"{spec.graph_id}_flow.py",
            description=f"{spec.graph_id} graph CLI: deterministic seams + stub/codex harness (no LLM by default).")
        sub = p.add_subparsers(dest="cmd", required=True)
        sp = sub.add_parser("front-door"); sp.add_argument("context")
        sp = sub.add_parser("inputs"); sp.add_argument("context"); sp.add_argument("--node")
        sp = sub.add_parser("run"); sp.add_argument("context")
        sp.add_argument("--gates", choices=["auto", "prompt"], default="auto")
        sp = sub.add_parser("run-codex"); sp.add_argument("context")
        sp.add_argument("--gates", choices=["auto", "prompt"], default="prompt")
        sp = sub.add_parser("finalize"); sp.add_argument("bundle")
        args = p.parse_args(argv)
        try:
            if args.cmd == "front-door":
                out = front_door(spec, args.context)
            elif args.cmd == "inputs":
                inputs = node_input_map(spec, _load_any(spec, args.context), graphs.load(spec.graph_id))
                if args.node:
                    if args.node not in inputs:
                        print(f"error: no agent node {args.node!r} (have: {', '.join(inputs)})", file=_sys.stderr)
                        return 1
                    inputs = {args.node: inputs[args.node]}
                out = inputs
            elif args.cmd == "run":
                handler = terminal_gate_handler if args.gates == "prompt" else None
                out = run(spec, front_door(spec, args.context)["ref"], gate_handler=handler)
            elif args.cmd == "run-codex":
                if codex_runner is None:
                    print("error: no codex runner wired for this graph", file=_sys.stderr)
                    return 1
                handler = terminal_gate_handler if args.gates == "prompt" else None
                out = run(spec, front_door(spec, args.context)["ref"],
                          node_runner=codex_runner, gate_handler=handler)
            elif args.cmd == "finalize":
                out = finalize(spec, args.bundle)
        except (OSError, ValueError, KeyError) as exc:
            print(f"error: {exc}", file=_sys.stderr)
            return 1
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0
    return cli
