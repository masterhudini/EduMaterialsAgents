"""Host-driven G02 Scout E2E runner.

This module keeps the historical ``g02.reviewed_flow`` import path, but the active runtime is no
longer the retired A02-A06/A10 reviewed frontier. It is a small deterministic scheduler for the
current manifest path:

    A01 planner -> Scout fanout -> A07 bounded source reviews -> A09 synthesis -> User Gate

The runner pauses only for model work and user decisions. Deterministic operations are executed
in-process through the same modules exposed by the research MCP server.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import pathlib
import re
import time
import uuid

from core import artifacts, contracts, event_log, graphs, paths
from g02 import a07_bridge, a07_runner, a09_synthesis, planner, scout_fanout, synthesis


GRAPH_ID = "g02"
REPORT_CONTRACT = "research_run_report@1"
RESEARCH_GATE = "user-research-gate"
PLANNER_NODE = "g02-a01-planner"
SCOUT_NODE = "research-scout-fanout"
A07_NODE = "g02-a07-paper-review"
A09_NODE = "g02-a09-synthesizer"


def _safe(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or "")).strip("-") or "run"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _issue(issue_type: str, message: str, severity: str = "blocker") -> dict:
    return {"severity": severity, "type": issue_type, "message": message}


def _checkpoint_path(token: str) -> pathlib.Path:
    return paths.drafts_dir() / f"{GRAPH_ID}.reviewed.{_safe(token)}.checkpoint.json"


def _save_checkpoint(token: str, state: dict) -> None:
    path = _checkpoint_path(token)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_checkpoint(token: str) -> dict:
    return json.loads(_checkpoint_path(token).read_text(encoding="utf-8"))


def _clear_checkpoint(token: str) -> None:
    _checkpoint_path(token).unlink(missing_ok=True)


def _node(manifest: dict, name: str) -> dict:
    for node in graphs.nodes(manifest):
        if node.get("name") == name:
            return node
    raise ValueError(f"g02 graph manifest has no node {name!r}")


def _operation(manifest: dict, node_name: str, op_name: str) -> str:
    operations = _node(manifest, node_name).get("operations") or {}
    value = operations.get(op_name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"g02 graph manifest has no operation {node_name}.{op_name}")
    return value


def _profile(manifest: dict) -> dict:
    name = manifest.get("default_execution_profile", "scout_e2e")
    profiles = manifest.get("execution_profiles") if isinstance(manifest.get("execution_profiles"), dict) else {}
    profile = profiles.get(name)
    return profile if isinstance(profile, dict) else {}


def _record(state: dict, node: str, artifact_ref: str | None, *,
            status: str = "approved", topic_id: str | None = None) -> None:
    key = f"{node}:{topic_id}" if topic_id else node
    state.setdefault("records", {})[key] = {
        "node": node,
        "topic_id": topic_id,
        "status": status,
        "artifact_ref": artifact_ref,
        "review_decision_ref": None,
        "revision_completion_ref": None,
    }


def _records_for_report(records: dict[str, dict]) -> list[dict]:
    return [deepcopy(records[key]) for key in sorted(records)]


def _report(state: dict, status: str, *, issues: list[dict] | None = None,
            output_ref: str | None = None, gate: dict | None = None, base=None) -> dict:
    payload = {
        "schema_version": REPORT_CONTRACT,
        "run_id": state["run_id"],
        "graph_id": GRAPH_ID,
        "status": status,
        "through": state.get("through", RESEARCH_GATE),
        "completed": sorted(state.get("records", {})),
        "records": _records_for_report(state.get("records", {})),
        "issues": deepcopy(issues or []),
        "output_ref": output_ref,
        "resume_token": state.get("resume_token") if status == "awaiting_user" else None,
        "gate": deepcopy(gate),
        "trace": event_log.open_log(f"{GRAPH_ID}-reviewed", run_id=state["resume_token"]).summary(),
    }
    checked = contracts.validate(payload, REPORT_CONTRACT)
    if not checked["ok"]:
        raise ValueError("invalid research run report: " + "; ".join(checked["errors"]))
    ref = artifacts.store(f"g02/runs/{_safe(state['run_id'])}.json", payload, base=base)
    payload["report_ref"] = ref
    return payload


def _failure(state: dict, issue_type: str, message: str, *, gate=None, base=None) -> dict:
    return _report(state, "failed", issues=[_issue(issue_type, message)], gate=gate, base=base)


def _produced_path(envelope: dict, schema_version: str, *, artifact_type: str | None = None) -> str:
    if not isinstance(envelope, dict):
        raise ValueError("node result must be an envelope object")
    checked = contracts.validate_envelope(envelope)
    if not checked["ok"]:
        raise ValueError("invalid envelope@1: " + "; ".join(checked["errors"]))
    if envelope.get("status") not in {"ok", "degraded"}:
        raise ValueError(envelope.get("summary") or f"node returned {envelope.get('status')}")
    for descriptor in envelope.get("produced", []):
        if not isinstance(descriptor, dict):
            continue
        if descriptor.get("schema_version") != schema_version:
            continue
        if artifact_type and descriptor.get("type") != artifact_type:
            continue
        path = descriptor.get("path") or descriptor.get("ref")
        if isinstance(path, str) and path:
            return path
    raise ValueError(f"envelope has no produced {schema_version} descriptor")


def _hydrate_if_artifact(ref_or_path: str, *, contract: str | None = None, base=None) -> dict:
    if ref_or_path.startswith(artifacts.SCHEME):
        payload = artifacts.hydrate(ref_or_path, base=base)
    else:
        payload = json.loads(pathlib.Path(ref_or_path).read_text(encoding="utf-8"))
    if contract:
        checked = contracts.validate(payload, contract)
        if not checked["ok"]:
            raise ValueError(f"invalid {contract}: " + "; ".join(checked["errors"]))
    return payload


def _result_for_pending(state: dict, node_results: dict | None, node_failures: dict | None) -> object | None:
    pending = state.get("pending") or {}
    key = pending.get("node_key") or pending.get("node")
    node = pending.get("node")
    failures = node_failures or {}
    if key in failures:
        failure = failures[key]
        raise ValueError(failure.get("summary") or f"{key}: host could not produce")
    if node in failures:
        failure = failures[node]
        raise ValueError(failure.get("summary") or f"{node}: host could not produce")
    results = node_results or {}
    if key in results:
        return results[key]
    if node in results:
        return results[node]
    return None


def _await_node(state: dict, payload: dict, *, log, base=None) -> dict:
    state["pending"] = {
        "kind": "node",
        "node": payload["node"],
        "node_key": payload.get("node_key", payload["node"]),
        "since": time.time(),
    }
    _save_checkpoint(state["resume_token"], state)
    log.append(payload["node"], "awaiting_node", status="paused",
               detail={"resume_token": state["resume_token"], "node_key": state["pending"]["node_key"]})
    return {"status": "awaiting_node", "resume_token": state["resume_token"], **payload}


def _load_input(input_ref: str, *, base=None) -> dict:
    payload = artifacts.hydrate(input_ref, base=base)
    checked = contracts.validate(payload, "research_graph_input@1")
    if not checked["ok"]:
        raise ValueError("invalid research graph input: " + "; ".join(checked["errors"]))
    return payload


def _planner_payload(manifest: dict, state: dict, rgi: dict, *, log, base=None) -> dict:
    prepared = planner.prepare_planner(rgi, execution_profile="scout_e2e")
    return {
        "node": PLANNER_NODE,
        "node_key": PLANNER_NODE,
        "input": prepared,
        "upstream": {},
        "output_contract": "research_plan@1",
        "finalize_op": _operation(manifest, PLANNER_NODE, "finalize"),
        "finalize_args": {
            "input": state["input_ref"],
            "execution_profile": "scout_e2e",
            "plan": "<raw g02-a01-planner JSON>",
        },
    }


def _run_scout(manifest: dict, state: dict, *, base=None) -> None:
    if state.get("scout_run_dir"):
        return
    plan_ref = state["refs"]["research_plan"]
    scout_settings = _profile(manifest).get("scout") if isinstance(_profile(manifest).get("scout"), dict) else {}
    result = scout_fanout.run_scout_fanout(
        plan_ref,
        total_target=scout_settings.get("total_target"),
        max_workers=scout_settings.get("max_parallel_topics"),
    )
    root = pathlib.Path(result["run_directory"]).resolve()
    state["scout_run_dir"] = str(root)
    state["refs"]["scout_run_index"] = str(root / "index.json")
    _record(state, SCOUT_NODE, state["refs"]["scout_run_index"])


def _prepare_a07(state: dict) -> None:
    if state.get("a07_dir"):
        return
    aggregate = a07_bridge.build_a07_reviews(
        state["scout_run_dir"],
        intake_ref=state["input_ref"],
    )
    a07_dir = a07_bridge._default_a07_dir(
        pathlib.Path(state["scout_run_dir"]).resolve(),
        str(aggregate["task_id"]),
    )
    tasks = a07_runner.write_a07_review_tasks(a07_dir, intake=state["input_ref"])
    state["a07_dir"] = tasks["a07_dir"]
    state["a07_tasks"] = tasks["tasks"]
    state["a07_completed"] = []
    state["a07_prepared_count"] = len(aggregate.get("source_reviews", []))


def _next_a07_payload(manifest: dict, state: dict) -> dict | None:
    completed = set(state.get("a07_completed", []))
    for task in state.get("a07_tasks", []):
        node_key = f"{A07_NODE}:{task['topic_id']}:{task['source_id']}"
        if node_key in completed:
            continue
        task_path = pathlib.Path(state["a07_dir"]) / task["task_ref"]
        work_path = pathlib.Path(state["a07_dir"]) / task["work_input_ref"]
        return {
            "node": A07_NODE,
            "node_key": node_key,
            "topic_id": task["topic_id"],
            "source_id": task["source_id"],
            "input": _hydrate_if_artifact(str(task_path), contract="a07_review_task@1"),
            "input_ref": str(task_path),
            "work_input_path": str(work_path),
            "upstream": {
                "research_plan": state["refs"]["research_plan"],
                "scout_run_index": state["refs"]["scout_run_index"],
            },
            "output_contract": "a07_review@1",
            "finalize_op": _operation(manifest, A07_NODE, "partial_finalize"),
            "finalize_args": {
                "work_input_path": str(work_path),
                "output": "<raw g02-a07-paper-review JSON>",
            },
        }
    return None


def _aggregate_a07(state: dict) -> None:
    if state["refs"].get("a07_reviews"):
        return
    envelope = _envelope_from_aggregate(a07_bridge.aggregate_a07_reviews(state["a07_dir"]), state["a07_dir"])
    state["refs"]["a07_reviews"] = _produced_path(
        envelope, a07_bridge.A07_REVIEWS_CONTRACT, artifact_type="a07_reviews"
    )
    _record(state, A07_NODE, state["refs"]["a07_reviews"])


def _envelope_from_aggregate(aggregate: dict, a07_dir: str) -> dict:
    return {
        "schema_version": "envelope@1",
        "status": "ok",
        "summary": "Stored aggregated A07 reviews.",
        "issues": [],
        "produced": [{
            "type": "a07_reviews",
            "path": str(pathlib.Path(a07_dir).resolve() / "reviews.json"),
            "schema_version": a07_bridge.A07_REVIEWS_CONTRACT,
            "artifact_version": aggregate.get("artifact_version", "1.0.0"),
        }],
        "metrics": {},
    }


def _a09_payload(manifest: dict, state: dict) -> dict:
    built = a09_synthesis.prepare_a09_synthesis(
        state["refs"]["a07_reviews"],
        intake=state["input_ref"],
        max_deep_dive_sources=5,
    )
    deep_dive = a09_synthesis.gather_deep_dive_windows(
        built["synthesis_input"]["reviews"],
        built["synthesis_input"]["deep_dive_requests"],
        max_windows=8,
        max_chars=1200,
    )
    task = a09_synthesis.build_a09_synthesis_task(built["synthesis_input"], deep_dive)
    state["a09_deep_dive"] = deep_dive
    return {
        "node": A09_NODE,
        "node_key": A09_NODE,
        "input": task,
        "upstream": {
            "a07_reviews": state["refs"]["a07_reviews"],
            "research_plan": state["refs"]["research_plan"],
        },
        "output_contract": "solution_input_candidate@1",
        "finalize_op": _operation(manifest, A09_NODE, "finalize_solution"),
        "finalize_args": {
            "reviews_json": state["refs"]["a07_reviews"],
            "intake": state["input_ref"],
            "deep_dive": deep_dive,
            "output": "<raw g02-a09-synthesizer JSON or omit for fallback>",
        },
    }


def _finalize_research_state(state: dict, solution_envelope: dict, *, base=None) -> None:
    if state["refs"].get("research_state"):
        return
    solution = _hydrate_if_artifact(
        _produced_path(solution_envelope, a09_synthesis.SOLUTION_CONTRACT,
                       artifact_type="solution_input_candidate"),
        contract=a09_synthesis.SOLUTION_CONTRACT,
        base=base,
    )
    envelope = a09_synthesis.finalize_a09_research_state(solution, base=base)
    state["refs"]["research_state"] = _produced_path(
        envelope, a09_synthesis.RESEARCH_STATE_CONTRACT, artifact_type="research_state"
    )
    _record(state, A09_NODE, state["refs"]["research_state"])


def _gate_payload(state: dict, *, base=None) -> dict:
    payload = synthesis.prepare_human_research_gate(state["refs"]["research_state"], base=base)
    payload["context"]["artifacts"] = deepcopy(state["refs"])
    return payload


def _finalize_gate(state: dict, decision: dict, *, base=None) -> tuple[str | None, dict | None]:
    envelope = synthesis.finalize_research_bundle(
        state["refs"]["research_state"],
        decision,
        base=base,
    )
    if envelope.get("status") != "ok":
        message = envelope.get("summary", "User Research Gate decision was not accepted")
        issue = envelope.get("issues", [{}])[0]
        return None, _issue(
            issue.get("type", "research_gate_not_approved"),
            message,
            issue.get("severity", "major"),
        )
    return _produced_path(envelope, "user_approved_research_bundle@1"), None


def terminal_gate_handler(payload: dict) -> dict:
    import sys
    sys.stderr.write(json.dumps({
        "gate": payload.get("gate"),
        "required_decisions": payload.get("required_decisions"),
        "decision_template": payload.get("decision_template"),
    }, ensure_ascii=False, indent=2) + "\n")
    sys.stderr.write("Enter decision JSON for this gate, then newline:\n")
    sys.stderr.flush()
    return json.loads(sys.stdin.readline())


def _new_state(input_ref: str, *, through: str, topic_ids: list[str] | None,
               resume_token: str | None) -> dict:
    token = resume_token or uuid.uuid4().hex[:12]
    return {
        "schema_version": "g02_scout_hosted_checkpoint@1",
        "run_id": uuid.uuid4().hex[:12],
        "input_ref": input_ref,
        "through": through,
        "requested_topic_ids": deepcopy(topic_ids),
        "records": {},
        "refs": {},
        "resume_token": token,
        "pending": None,
        "created_at": _now(),
    }


def run(input_ref=None, *, node_runner=None, base=None, gate_handler=None, pause_on_gate=False,
        pause_on_node=False, resume_token: str | None = None, decisions: dict | None = None,
        node_results: dict | None = None, node_failures: dict | None = None,
        review_results: dict | None = None, usage_reports: dict | None = None,
        through: str = RESEARCH_GATE, topic_ids: list[str] | None = None) -> dict:
    """Run or resume active G02 as a prompt-assisted hosted workflow.

    ``node_results`` are finalize envelopes produced by the MCP finalizer named in the awaiting
    payload. For multiple A07 tasks, use the returned ``node_key`` as the key. For the nested-Codex
    entrypoint (``node_runner`` supplied) use :func:`run_with_codex`, which drives this same hosted
    protocol in-process and only pauses for user gates.
    """
    del node_runner, review_results  # this single pass is hosted; the Codex driver lives in run_with_codex.
    manifest = graphs.load(GRAPH_ID)
    if through not in {PLANNER_NODE, SCOUT_NODE, A07_NODE, A09_NODE, RESEARCH_GATE}:
        raise ValueError("active g02 hosted flow supports through=g02-a01-planner, "
                         "research-scout-fanout, g02-a07-paper-review, "
                         "g02-a09-synthesizer or user-research-gate")
    if not pause_on_node:
        raise ValueError("active g02 hosted flow requires pause_on_node=True")

    if resume_token and input_ref is None:
        state = _load_checkpoint(resume_token)
        input_ref = state["input_ref"]
    else:
        if not isinstance(input_ref, str) or not input_ref.startswith(artifacts.SCHEME):
            raise ValueError("g02 hosted flow requires an artifact:// research input ref")
        state = _new_state(input_ref, through=through, topic_ids=topic_ids, resume_token=resume_token)

    log = event_log.open_log(f"{GRAPH_ID}-reviewed", run_id=state["resume_token"])
    rgi = _load_input(input_ref, base=base)
    log.append("ENTRY", "run", detail={"task_id": rgi.get("task_id"), "resume_token": state["resume_token"]})

    try:
        pending = state.get("pending")
        if pending:
            result = _result_for_pending(state, node_results, node_failures)
            if result is None:
                _save_checkpoint(state["resume_token"], state)
                return {"status": "awaiting_node", "resume_token": state["resume_token"],
                        "node": pending["node"], "node_key": pending["node_key"]}
            if isinstance(pending.get("since"), (int, float)):
                log.span(pending["node"], pending["node"], kind="agent",
                         duration_ms=(time.time() - pending["since"]) * 1000.0)
            rep = (usage_reports or {}).get(pending["node_key"]) or (usage_reports or {}).get(pending["node"])
            if isinstance(rep, dict):
                log.usage(pending["node"], input_tokens=rep.get("input_tokens"),
                          output_tokens=rep.get("output_tokens"), model=rep.get("model"),
                          source="host_reported")
            if pending["node"] == PLANNER_NODE:
                plan_ref = _produced_path(result, "research_plan@1", artifact_type="research_plan")
                state["refs"]["research_plan"] = plan_ref
                _record(state, PLANNER_NODE, plan_ref)
            elif pending["node"] == A07_NODE:
                partial_ref = _produced_path(result, a07_bridge.A07_PARTIAL_CONTRACT,
                                             artifact_type="a07_review")
                state.setdefault("a07_partial_refs", {})[pending["node_key"]] = partial_ref
                state.setdefault("a07_completed", []).append(pending["node_key"])
            elif pending["node"] == A09_NODE:
                state["refs"]["solution_input_candidate"] = _produced_path(
                    result, a09_synthesis.SOLUTION_CONTRACT,
                    artifact_type="solution_input_candidate",
                )
                state["a09_solution_envelope"] = result
            state["pending"] = None

        if "research_plan" not in state["refs"]:
            return _await_node(state, _planner_payload(manifest, state, rgi, log=log, base=base),
                               log=log, base=base)
        if through == PLANNER_NODE:
            _clear_checkpoint(state["resume_token"])
            return _report(state, "completed", output_ref=state["refs"]["research_plan"], base=base)

        _run_scout(manifest, state, base=base)
        if through == SCOUT_NODE:
            _clear_checkpoint(state["resume_token"])
            return _report(state, "completed", output_ref=state["refs"]["scout_run_index"], base=base)

        _prepare_a07(state)
        next_a07 = _next_a07_payload(manifest, state)
        if next_a07 is not None:
            return _await_node(state, next_a07, log=log, base=base)
        _aggregate_a07(state)
        if through == A07_NODE:
            _clear_checkpoint(state["resume_token"])
            return _report(state, "completed", output_ref=state["refs"]["a07_reviews"], base=base)

        if "solution_input_candidate" not in state["refs"]:
            return _await_node(state, _a09_payload(manifest, state), log=log, base=base)
        _finalize_research_state(state, state["a09_solution_envelope"], base=base)
        if through == A09_NODE:
            _clear_checkpoint(state["resume_token"])
            return _report(state, "completed", output_ref=state["refs"]["research_state"], base=base)

        gate_payload = _gate_payload(state, base=base)
        supplied = (decisions or {}).get(RESEARCH_GATE)
        if supplied is None and gate_handler is not None:
            supplied = gate_handler(gate_payload)
        if supplied is None:
            _save_checkpoint(state["resume_token"], state)
            return _report(
                state,
                "awaiting_user",
                output_ref=state["refs"]["research_state"],
                gate=gate_payload,
                base=base,
            )
        bundle_ref, failure = _finalize_gate(state, supplied, base=base)
        if failure:
            gate_payload["last_decision"] = deepcopy(supplied)
            _save_checkpoint(state["resume_token"], state)
            return _report(
                state,
                "awaiting_user",
                issues=[failure],
                output_ref=state["refs"]["research_state"],
                gate=gate_payload,
                base=base,
            )
        state["refs"]["user_approved_research_bundle"] = bundle_ref
        _record(state, RESEARCH_GATE, bundle_ref)
        _clear_checkpoint(state["resume_token"])
        return _report(state, "completed", output_ref=bundle_ref, base=base)
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        return _failure(state, "g02_hosted_flow_failed", str(exc), base=base)


def _codex_node(payload: dict) -> dict:
    """Reconstruct the minimal node dict a node_runner needs from an awaiting_node payload."""
    return {"name": payload["node"], "output_contract": payload.get("output_contract")}


def _codex_ctx(payload: dict, resume_token: str) -> dict:
    """Build the worker context for one awaiting_node payload."""
    return {
        "input": payload.get("input"),
        "upstream": payload.get("upstream") or {},
        "run_id": resume_token,
    }


def run_with_codex(input_ref=None, *, node_runner, base=None, gate_handler=None,
                   pause_on_gate=False, resume_token: str | None = None,
                   decisions: dict | None = None, through: str = RESEARCH_GATE,
                   topic_ids: list[str] | None = None) -> dict:
    """Drive active G02 with nested Codex workers, mirroring the g01/g03 codex entrypoints.

    Deterministic Scout fanout runs in-process inside :func:`run`; each A01/A07/A09 agent node is
    executed by ``node_runner`` (one isolated ``codex exec`` worker that calls its own finalize op
    and returns the resulting ``envelope@1``). The driver only pauses for the User Research Gate:
    with a ``gate_handler`` it plays the gate inline, otherwise it returns the ``awaiting_user``
    report so the caller can resume with ``decisions``.
    """
    if node_runner is None:
        raise ValueError("run_with_codex requires a node_runner")
    log = event_log.open_log(f"{GRAPH_ID}-reviewed", run_id=resume_token)
    result = run(input_ref, base=base, pause_on_node=True, pause_on_gate=pause_on_gate,
                 resume_token=resume_token, decisions=decisions, through=through,
                 topic_ids=topic_ids)
    while True:
        status = result.get("status")
        if status == "awaiting_node":
            token = result["resume_token"]
            node_key = result.get("node_key", result["node"])
            envelope = node_runner(_codex_node(result), _codex_ctx(result, token), log)
            result = run(base=base, pause_on_node=True, pause_on_gate=pause_on_gate,
                         resume_token=token, node_results={node_key: envelope},
                         through=through)
            continue
        if status == "awaiting_user":
            if gate_handler is None:
                return result  # let the caller resume the gate with explicit decisions
            decision = gate_handler(result.get("gate") or {})
            result = run(base=base, pause_on_node=True, pause_on_gate=pause_on_gate,
                         resume_token=result["resume_token"],
                         decisions={RESEARCH_GATE: decision}, through=through)
            continue
        return result
