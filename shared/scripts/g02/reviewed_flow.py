"""Fail-closed execution of the implemented G02 frontier (A01 through A06).

The historical ``g02_flow.run`` stub remains a wiring harness. This module is the real host-runner
path: every producer receives a deterministically prepared scope, must return a finalized typed
artifact, and receives at most one validated A10 decision. APPROVED continues directly, BLOCKED
stops, and REVISE permits one producer correction without another reviewer invocation. The
corrected artifact must pass deterministic finalization and receives an auditable revision receipt.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import pathlib
import re
import uuid

from core import artifacts, contracts, event_log, graphs, paths
from g02 import (
    candidate_index,
    canonical,
    domain,
    market_cases,
    planner,
    recent,
    retrieval,
    review,
    source_selection,
)


GRAPH_ID = "g02"
REPORT_CONTRACT = "research_run_report@1"
REVIEWER = "g02-a10-output-reviewer"
SOURCE_GATE = "user-source-selection-gate"

STAGES = (
    planner.PLANNER_AGENT,
    domain.DOMAIN_AGENT,
    canonical.CANONICAL_AGENT,
    recent.RECENT_AGENT,
    market_cases.MARKET_AGENT,
    candidate_index.AGENT,
    SOURCE_GATE,
    retrieval.AGENT,
)
TOPIC_STAGES = {
    domain.DOMAIN_AGENT,
    canonical.CANONICAL_AGENT,
    recent.RECENT_AGENT,
    market_cases.MARKET_AGENT,
}
STREAMS = {
    domain.DOMAIN_AGENT: "domain",
    canonical.CANONICAL_AGENT: "canonical",
    recent.RECENT_AGENT: "recent",
    market_cases.MARKET_AGENT: "market_cases",
}
ALLOWED_OPERATIONS = {
    planner.PLANNER_AGENT: [
        "research_planner_prepare", "research_planner_finalize",
    ],
    domain.DOMAIN_AGENT: [
        "research_provider_status", "research_domain_prepare", "research_metadata_search",
        "research_doi_verify", "research_doi_verify_batch", "research_domain_finalize",
    ],
    canonical.CANONICAL_AGENT: [
        "research_canonical_prepare", "research_citation_expand", "research_metadata_search",
        "research_doi_verify", "research_doi_verify_batch", "research_canonical_finalize",
    ],
    recent.RECENT_AGENT: [
        "research_recent_prepare", "research_metadata_search", "research_doi_verify",
        "research_doi_verify_batch", "research_recent_finalize",
    ],
    market_cases.MARKET_AGENT: [
        "research_market_cases_prepare", "research_web_case_search",
        "research_market_cases_finalize",
    ],
    candidate_index.AGENT: [
        "research_candidate_index_prepare", "research_doi_verify", "research_doi_verify_batch",
        "research_candidate_index_finalize",
    ],
    retrieval.AGENT: [
        "research_retrieval_prepare", "research_oa_resolve", "research_document_retrieve",
        "research_document_validate", "research_doi_verify", "research_doi_verify_batch",
        "research_web_case_extract", "research_retrieval_finalize",
    ],
}


def _issue(issue_type: str, message: str, severity: str = "blocker") -> dict:
    return {"severity": severity, "type": issue_type, "message": message}


def _record_key(node: str, topic_id: str | None = None) -> str:
    return f"{node}:{topic_id}" if topic_id else node


def _safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-") or "run"


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


def _records_for_report(records: dict[str, dict]) -> list[dict]:
    result = []
    for key in sorted(records):
        item = records[key]
        result.append({
            "node": item["node"],
            "topic_id": item.get("topic_id"),
            "status": item.get("status", "approved"),
            "artifact_ref": item.get("artifact_ref"),
            "review_decision_ref": item.get("review_decision_ref"),
            "revision_completion_ref": item.get("revision_completion_ref"),
        })
    return result


def _report(state: dict, status: str, *, issues: list[dict] | None = None,
            output_ref: str | None = None, gate: dict | None = None, base=None) -> dict:
    payload = {
        "schema_version": REPORT_CONTRACT,
        "run_id": state["run_id"],
        "graph_id": GRAPH_ID,
        "status": status,
        "through": state["through"],
        "completed": sorted(state["records"]),
        "records": _records_for_report(state["records"]),
        "issues": deepcopy(issues or []),
        "output_ref": output_ref,
        "resume_token": state.get("resume_token") if status == "awaiting_user" else None,
        "gate": deepcopy(gate),
    }
    checked = contracts.validate(payload, REPORT_CONTRACT)
    if not checked["ok"]:
        raise ValueError("invalid research run report: " + "; ".join(checked["errors"]))
    ref = artifacts.store(f"g02/runs/{_safe(state['run_id'])}.json", payload, base=base)
    payload["report_ref"] = ref
    return payload


def _failure_report(state: dict, failure: dict, *, gate=None, base=None) -> dict:
    status = "blocked" if failure.get("type") == "review_blocked" else "failed"
    return _report(state, status, issues=[failure], gate=gate, base=base)


def _stage_rank(name: str) -> int:
    try:
        return STAGES.index(name)
    except ValueError as exc:
        raise ValueError(f"unsupported through stage {name!r}; choose one of {', '.join(STAGES)}") from exc


def _node(manifest: dict, name: str) -> dict:
    found = next((item for item in graphs.nodes(manifest) if item.get("name") == name), None)
    if found is None:
        raise ValueError(f"graph manifest has no node {name!r}")
    return found


def _artifact_descriptor(envelope: dict, node: dict, task_id: str, *, base=None) -> tuple[dict, dict]:
    if "artifact" in envelope:
        raise ValueError("worker envelope must not contain an inline artifact")
    checked = contracts.validate_envelope(envelope)
    if not checked["ok"]:
        raise ValueError("invalid envelope@1: " + "; ".join(checked["errors"]))
    if envelope.get("status") not in {"ok", "degraded"}:
        raise ValueError(f"producer returned terminal status {envelope.get('status')!r}: {envelope.get('summary')}")
    contract = node.get("output_contract")
    matches = [item for item in envelope.get("produced", [])
               if isinstance(item, dict) and item.get("schema_version") == contract]
    if len(matches) != 1:
        raise ValueError(f"producer must return exactly one primary {contract} descriptor")
    descriptor = matches[0]
    ref = descriptor.get("path")
    if not isinstance(ref, str) or not ref.startswith(artifacts.SCHEME):
        raise ValueError("primary artifact descriptor must contain an artifact:// path")
    version = descriptor.get("artifact_version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("primary artifact descriptor must contain artifact_version")
    artifact = artifacts.hydrate(ref, base=base)
    shape = contracts.validate(artifact, contract)
    if not shape["ok"]:
        raise ValueError(f"stored artifact fails {contract}: " + "; ".join(shape["errors"]))
    if artifact.get("task_id") != task_id:
        raise ValueError("stored artifact belongs to another task")
    if artifact.get("artifact_version") != version:
        raise ValueError("descriptor artifact_version differs from stored artifact")
    return deepcopy(descriptor), artifact


def _decision_from_envelope(task: dict, envelope: dict, *, base=None) -> tuple[dict, str]:
    checked = review.validate_reviewer_envelope(task, envelope, base=base)
    if checked.get("status") != "ok":
        raise ValueError(checked.get("summary", "reviewer execution failed") + ": " + "; ".join(
            item.get("message", "") for item in checked.get("issues", [])
        ))
    descriptor = checked["produced"][0]
    ref = descriptor.get("path")
    decision = artifacts.hydrate(ref, base=base)
    return decision, ref


def _store_revision_completion(state: dict, node: dict, decision: dict, decision_ref: str,
                               original_descriptor: dict, revised_descriptor: dict, *,
                               base=None) -> str:
    """Persist proof that one producer correction passed deterministic finalization."""
    receipt = {
        "schema_version": "revision_completion@1",
        "review_decision_ref": decision_ref,
        "review_id": decision["review_id"],
        "task_id": decision["task_id"],
        "producer_agent": node["name"],
        "original_artifact_ref": original_descriptor["path"],
        "original_artifact_version": original_descriptor["artifact_version"],
        "revised_artifact_ref": revised_descriptor["path"],
        "revised_artifact_version": revised_descriptor["artifact_version"],
        "finding_ids": [item["finding_id"] for item in decision["findings"]],
        "deterministic_validation_passed": True,
        "completed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    checked = contracts.validate(receipt, "revision_completion@1")
    if not checked["ok"]:
        raise ValueError("invalid revision completion: " + "; ".join(checked["errors"]))
    name = f"{_safe(state['run_id'])}.{_safe(node['name'])}.{_safe(decision['review_id'])}.json"
    return artifacts.store(f"g02/revision-completions/{name}", receipt, base=base)


def _previous(records: dict[str, dict], node: str, topic_id: str | None) -> dict | None:
    return records.get(_record_key(node, topic_id))


def _prepare(node_name: str, topic_id: str | None, state: dict, rgi: dict, *, base=None,
             previous: dict | None = None, findings: list[dict] | None = None) -> dict:
    records = state["records"]
    plan_record = records.get(planner.PLANNER_AGENT)
    plan_ref = plan_record.get("artifact_ref") if plan_record else None
    previous_ref = previous.get("artifact_ref") if previous else None
    revision_items = findings or []

    if node_name == planner.PLANNER_AGENT:
        prepared = planner.prepare_planner(
            rgi, previous_plan_ref=previous_ref, revision_items=revision_items, base=base
        )
        scoped = prepared.get("planner_input")
        prepare_args = {"input": state["input_ref"]}
        finalize = {"operation": "research_planner_finalize", "fixed_arguments": {
            "input": state["input_ref"],
        }, "generated_argument": "plan"}
        if previous_ref:
            prepare_args.update(previous_plan_ref=previous_ref, revision_items=revision_items)
            finalize["fixed_arguments"].update(
                previous_plan_ref=previous_ref, revision_items=revision_items
            )
    elif node_name == domain.DOMAIN_AGENT:
        prepared = domain.prepare_domain(
            plan_ref, topic_id, artifact_base=base,
            previous_candidates_ref=previous_ref, revision_items=revision_items,
        )
        scoped = prepared.get("domain_input")
        prepare_args = {"research_plan_ref": plan_ref, "topic_id": topic_id}
        finalize = {"operation": "research_domain_finalize", "fixed_arguments": deepcopy(prepare_args),
                    "generated_argument": "output"}
    elif node_name in {canonical.CANONICAL_AGENT, recent.RECENT_AGENT, market_cases.MARKET_AGENT}:
        domain_record = records.get(_record_key(domain.DOMAIN_AGENT, topic_id))
        domain_ref = domain_record.get("artifact_ref") if domain_record else None
        common = {"research_plan_ref": plan_ref, "domain_candidates_ref": domain_ref,
                  "topic_id": topic_id}
        if node_name == canonical.CANONICAL_AGENT:
            prepared = canonical.prepare_canonical(
                plan_ref, domain_ref, topic_id, artifact_base=base,
                previous_candidates_ref=previous_ref, revision_items=revision_items,
            )
            scoped = prepared.get("canonical_input")
            prepare_op, finalize_op = "research_canonical_prepare", "research_canonical_finalize"
        elif node_name == recent.RECENT_AGENT:
            prepared = recent.prepare_recent(
                plan_ref, domain_ref, topic_id, artifact_base=base,
                previous_candidates_ref=previous_ref, revision_items=revision_items,
            )
            scoped = prepared.get("recent_input")
            prepare_op, finalize_op = "research_recent_prepare", "research_recent_finalize"
        else:
            prepared = market_cases.prepare_market_cases(
                plan_ref, domain_ref, topic_id, artifact_base=base,
                previous_candidates_ref=previous_ref, revision_items=revision_items,
            )
            scoped = prepared.get("market_case_input")
            prepare_op, finalize_op = "research_market_cases_prepare", "research_market_cases_finalize"
        prepare_args = common
        finalize = {"operation": finalize_op, "fixed_arguments": deepcopy(common),
                    "generated_argument": "output"}
    elif node_name == candidate_index.AGENT:
        reviewed = []
        for item in records.values():
            if item.get("node") not in STREAMS \
                    or item.get("status") not in {"approved", "revised_after_review"}:
                continue
            reviewed.append({
                "stream": STREAMS[item["node"]],
                "artifact_ref": item["artifact_ref"],
                "review_decision_ref": item["review_decision_ref"],
                "revision_completion_ref": item.get("revision_completion_ref"),
            })
        prepared = candidate_index.prepare_candidate_index(
            plan_ref, reviewed, previous_index_ref=previous_ref, artifact_base=base
        )
        scoped = prepared.get("candidate_index_input")
        prepare_args = {"research_plan_ref": plan_ref, "reviewed_upstreams": reviewed}
        finalize = {"operation": "research_candidate_index_finalize",
                    "fixed_arguments": deepcopy(prepare_args)}
    elif node_name == retrieval.AGENT:
        gate_record = records.get(SOURCE_GATE)
        approved_ref = gate_record.get("artifact_ref") if gate_record else None
        prepared = retrieval.prepare_retrieval(
            approved_ref, previous_corpus_ref=previous_ref, artifact_base=base
        )
        scoped = prepared.get("retrieval_input")
        prepare_args = {"approved_source_set_ref": approved_ref}
        finalize = {"operation": "research_retrieval_finalize", "fixed_arguments": deepcopy(prepare_args),
                    "generated_argument": "result_refs"}
    else:
        raise ValueError(f"no execution adapter for {node_name}")

    if previous_ref and node_name != planner.PLANNER_AGENT:
        field = "previous_corpus_ref" if node_name == retrieval.AGENT else (
            "previous_index_ref" if node_name == candidate_index.AGENT else "previous_candidates_ref"
        )
        prepare_args[field] = previous_ref
        finalize["fixed_arguments"][field] = previous_ref
        if node_name not in {candidate_index.AGENT, retrieval.AGENT}:
            prepare_args["revision_items"] = revision_items
            finalize["fixed_arguments"]["revision_items"] = revision_items

    protocol = {
        "prepare": {"operation": (
            "research_planner_prepare" if node_name == planner.PLANNER_AGENT else
            "research_domain_prepare" if node_name == domain.DOMAIN_AGENT else
            prepare_op if node_name in {canonical.CANONICAL_AGENT, recent.RECENT_AGENT,
                                        market_cases.MARKET_AGENT} else
            "research_candidate_index_prepare" if node_name == candidate_index.AGENT else
            "research_retrieval_prepare"
        ), "arguments": prepare_args},
        "allowed_operations": ALLOWED_OPERATIONS[node_name],
        "finalize": finalize,
        "rules": [
            "Call the prepare operation first and stop if it is not ready.",
            "Use only allowed_operations; never use direct web, shell HTTP or an unlisted MCP tool.",
            "Return the exact envelope produced by finalize as the final message.",
        ],
    }
    return {"prepared": prepared, "input": scoped, "protocol": protocol}


def _build_review_task(node_name: str, prepared_input: dict, descriptor: dict, *,
                       review_id: str, attempt: int, previous_decision_ref: str | None,
                       findings: list[dict], base=None) -> dict:
    common = {
        "review_id": review_id,
        "attempt": attempt,
        "previous_decision_ref": previous_decision_ref,
        "producer_revision_response": (
            {"finding_ids": [item.get("finding_id") for item in findings],
             "summary": "Producer was asked to address the listed findings."}
            if findings else None
        ),
    }
    if node_name == planner.PLANNER_AGENT:
        return planner.build_research_plan_review_task(prepared_input, descriptor, **common)
    if node_name == domain.DOMAIN_AGENT:
        return domain.build_domain_review_task(prepared_input, descriptor, **common)
    if node_name == canonical.CANONICAL_AGENT:
        return canonical.build_canonical_review_task(prepared_input, descriptor, base=base, **common)
    if node_name == recent.RECENT_AGENT:
        return recent.build_recent_review_task(prepared_input, descriptor, base=base, **common)
    if node_name == market_cases.MARKET_AGENT:
        return market_cases.build_market_case_review_task(prepared_input, descriptor, base=base, **common)
    if node_name == candidate_index.AGENT:
        return candidate_index.build_candidate_index_review_task(
            prepared_input, descriptor, base=base, **common
        )
    if node_name == retrieval.AGENT:
        return retrieval.build_retrieval_review_task(prepared_input, descriptor, base=base, **common)
    raise ValueError(f"no review adapter for {node_name}")


def _upstream_refs(records: dict[str, dict]) -> dict[str, object]:
    result: dict[str, object] = {}
    for item in records.values():
        if not item.get("artifact_ref"):
            continue
        key = item["node"]
        value = {
            "artifact_ref": item["artifact_ref"],
            "review_decision_ref": item.get("review_decision_ref"),
            "revision_completion_ref": item.get("revision_completion_ref"),
            "topic_id": item.get("topic_id"),
        }
        if key in result:
            if not isinstance(result[key], list):
                result[key] = [result[key]]
            result[key].append(value)
        else:
            result[key] = value
    return result


def _run_stage(node: dict, topic_id: str | None, state: dict, rgi: dict, node_runner, log,
               manifest: dict, *, base=None) -> tuple[dict | None, dict | None]:
    key = _record_key(node["name"], topic_id)
    if key in state["records"]:
        return state["records"][key], None
    previous = None
    decision_ref = None
    decision = None
    original_descriptor = None
    findings: list[dict] = []
    review_id = f"REV_{_safe(state['run_id'])}_{_safe(node['name'])}_{_safe(topic_id or 'all')}"

    for attempt in range(1, 3):
        execution = _prepare(
            node["name"], topic_id, state, rgi, base=base,
            previous=previous, findings=findings,
        )
        prepared = execution["prepared"]
        if not prepared.get("ready"):
            if prepared.get("skipped"):
                record = {"node": node["name"], "topic_id": topic_id, "status": "skipped",
                          "artifact_ref": None, "review_decision_ref": None,
                          "revision_completion_ref": None}
                state["records"][key] = record
                log.append(node["name"], "skipped", status="ok", detail={"topic_id": topic_id})
                return record, None
            envelope = prepared.get("envelope") or {}
            return None, _issue(
                "stage_prepare_failed",
                f"{node['name']} prepare failed: {envelope.get('summary', 'unknown error')} "
                + "; ".join(item.get("message", "") for item in envelope.get("issues", [])),
            )

        ctx = {
            "run_id": state["run_id"],
            "input": execution["input"],
            "upstream": _upstream_refs(state["records"]),
            "protocol": execution["protocol"],
        }
        if findings:
            ctx["revision"] = {
                "attempt": attempt,
                "prior_artifact_ref": previous["artifact_ref"],
                "items": findings,
            }
        envelope = node_runner(node, ctx, log)
        try:
            descriptor, _ = _artifact_descriptor(
                envelope, node, rgi["task_id"], base=base
            )
        except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
            log.append(node["name"], "producer_rejected", status="failed",
                       detail={"topic_id": topic_id, "error": str(exc)})
            return None, _issue("producer_output_rejected", f"{node['name']}: {exc}")

        if attempt == 2:
            try:
                completion_ref = _store_revision_completion(
                    state, node, decision, decision_ref, original_descriptor, descriptor,
                    base=base,
                )
            except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
                return None, _issue(
                    "revision_completion_rejected", f"{node['name']}: {exc}"
                )
            record = {
                "node": node["name"], "topic_id": topic_id,
                "status": "revised_after_review",
                "artifact_ref": descriptor["path"], "artifact_descriptor": descriptor,
                "review_decision_ref": decision_ref,
                "revision_completion_ref": completion_ref,
            }
            state["records"][key] = record
            log.append(node["name"], "revision_completed", status="ok", detail={
                "topic_id": topic_id, "artifact_ref": descriptor["path"],
                "review_decision_ref": decision_ref,
                "revision_completion_ref": completion_ref,
            })
            return record, None

        task = _build_review_task(
            node["name"], execution["input"], descriptor,
            review_id=review_id, attempt=1, previous_decision_ref=None,
            findings=[], base=base,
        )

        reviewer_node = {
            "name": REVIEWER,
            "kind": "reviewer",
            "complexity_class": manifest.get("reviewer_complexity_class"),
            "output_contract": "review_decision@1",
            "review_profile": node.get("review_profile"),
        }
        reviewer_ctx = {
            "run_id": state["run_id"],
            "input": {"task_id": rgi["task_id"]},
            "upstream": {node["name"]: descriptor["path"]},
            "review_task": task,
            "protocol": {
                "prepare": {"operation": "research_review_prepare", "arguments": {"task": task}},
                "allowed_operations": ["research_review_prepare", "research_review_finalize"],
                "finalize": {"operation": "research_review_finalize",
                             "fixed_arguments": {"task": task},
                             "generated_argument": "decision"},
                "rules": ["Review only the supplied artifact and return the exact finalize envelope."],
            },
        }
        review_envelope = node_runner(reviewer_node, reviewer_ctx, log)
        try:
            decision, decision_ref = _decision_from_envelope(task, review_envelope, base=base)
        except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
            log.append(REVIEWER, "review_rejected", status="failed",
                       detail={"target": node["name"], "error": str(exc)})
            return None, _issue("review_output_rejected", f"{node['name']}: {exc}")

        artifact_ref = descriptor["path"]
        log.append(REVIEWER, "review", status=decision["decision"], detail={
            "target": node["name"], "topic_id": topic_id, "attempt": attempt,
            "artifact_ref": artifact_ref, "review_decision_ref": decision_ref,
        })
        if decision["decision"] == "APPROVED":
            record = {
                "node": node["name"], "topic_id": topic_id, "status": "approved",
                "artifact_ref": artifact_ref, "artifact_descriptor": descriptor,
                "review_decision_ref": decision_ref,
                "revision_completion_ref": None,
            }
            state["records"][key] = record
            return record, None
        if decision["decision"] == "BLOCKED":
            return None, _issue(
                "review_blocked", f"{node['name']} review BLOCKED: {decision['summary']}"
            )
        if decision["decision"] != "REVISE":
            return None, _issue("invalid_review_decision", f"unsupported decision {decision['decision']!r}")
        original_descriptor = deepcopy(descriptor)
        previous = {"artifact_ref": artifact_ref}
        findings = deepcopy(decision["findings"])

    return None, _issue("revision_failed", f"{node['name']} did not produce one valid correction")


def _topic_ids(plan: dict, requested: list[str] | None) -> list[str]:
    available = [item.get("topic_id") for item in plan.get("topics", [])
                 if isinstance(item, dict) and isinstance(item.get("topic_id"), str)]
    if not available or len(available) != len(set(available)):
        raise ValueError("ResearchPlan contains no unique topic IDs")
    if not requested:
        return available
    result = []
    for item in requested:
        if item not in available:
            raise ValueError(f"requested topic {item!r} is not in ResearchPlan")
        if item not in result:
            result.append(item)
    return result


def _gate_payload(candidate_ref: str, state: dict, *, base=None) -> dict:
    prepared = source_selection.prepare_source_selection(candidate_ref, base=base)
    if not prepared.get("ready"):
        envelope = prepared.get("envelope") or {}
        raise ValueError(envelope.get("summary", "source gate preparation failed"))
    return {
        "graph": GRAPH_ID,
        "gate": SOURCE_GATE,
        "candidate_source_index_ref": candidate_ref,
        "required_decisions": ["source_actions", "final_confirmation"],
        "source_selection": prepared["gate_prompt"],
        "user_prompt": prepared["user_prompt"],
        "context": {"run_id": state["run_id"]},
    }


def _finalize_gate(candidate_ref: str, decision: dict, *, base=None) -> tuple[str | None, dict | None]:
    approved_ref = decision.get("human_approved_source_set_ref") if isinstance(decision, dict) else None
    if isinstance(approved_ref, str):
        approved = artifacts.hydrate(approved_ref, base=base)
        checked = contracts.validate(approved, "human_approved_source_set@1")
        if not checked["ok"]:
            return None, _issue("invalid_human_approved_source_set", "; ".join(checked["errors"]))
        return approved_ref, None
    if not isinstance(decision, dict) or not isinstance(decision.get("selection"), dict) \
            or not isinstance(decision.get("confirmation_token"), str):
        return None, _issue("source_gate_incomplete", "selection and confirmation_token are required")
    finalized = source_selection.finalize_source_selection(
        candidate_ref, decision["selection"], decision["confirmation_token"], base=base
    )
    if finalized.get("status") != "ok":
        return None, _issue(
            "source_gate_not_approved",
            finalized.get("summary", "source selection did not authorize retrieval") + ": "
            + "; ".join(item.get("message", "") for item in finalized.get("issues", [])),
        )
    ref = next((item.get("path") for item in finalized.get("produced", [])
                if item.get("type") == "human_approved_source_set"), None)
    if not isinstance(ref, str):
        return None, _issue("source_gate_output_missing", "finalized gate produced no approved set")
    return ref, None


def terminal_gate_handler(payload: dict) -> dict:
    """Two-step terminal gate with numbered sources and a separate final confirmation."""
    import sys

    prompt = payload["source_selection"]
    language = str(prompt.get("output_language", "English"))
    polish = language.casefold().startswith("pl") or "pol" in language.casefold()
    sys.stderr.write(source_selection.render_gate_prompt(prompt) + "\n")
    sys.stderr.write(
        ("Zakończ wpisywanie pustą linią lub słowem END.\n" if polish else
         "Finish with an empty line or END.\n")
    )
    sys.stderr.flush()
    lines = []
    while True:
        line = sys.stdin.readline()
        if line == "":
            break
        line = line.rstrip("\r\n")
        if not line.strip() or line.strip().upper() == "END":
            break
        lines.append(line)
    if not lines:
        raise ValueError("source selection was empty")
    validated = source_selection.validate_source_selection(
        payload["candidate_source_index_ref"], response_text="\n".join(lines)
    )
    sys.stderr.write(source_selection.render_selection_summary(
        validated["summary"], polish=polish
    ) + "\n")
    expected = "POTWIERDZAM" if polish else "CONFIRM"
    sys.stderr.write(
        (f"Wpisz {expected}, aby zatwierdzić dokładnie ten wybór. Inny tekst anuluje.\n"
         if polish else
         f"Type {expected} to authorize exactly this selection. Any other text cancels.\n")
    )
    sys.stderr.flush()
    if sys.stdin.readline().strip().upper() not in {expected, "CONFIRM", "POTWIERDZAM"}:
        raise ValueError("source selection was not finally confirmed")
    draft = validated["selection_draft"]
    draft["final_confirmation"] = True
    return {"selection": draft, "confirmation_token": validated["confirmation_token"]}


def run(input_ref=None, *, node_runner, base=None, gate_handler=None, pause_on_gate=False,
        resume_token: str | None = None, decisions: dict | None = None,
        through: str = retrieval.AGENT, topic_ids: list[str] | None = None) -> dict:
    """Run the implemented, reviewed G02 frontier and return research_run_report@1."""
    manifest = graphs.load(GRAPH_ID)
    _stage_rank(through)
    log = event_log.open_log(f"{GRAPH_ID}-reviewed")

    if resume_token and input_ref is None:
        state = _load_checkpoint(resume_token)
        input_ref = state["input_ref"]
        if through != retrieval.AGENT and through != state["through"]:
            raise ValueError("through cannot change while resuming a run")
        through = state["through"]
        topic_ids = state.get("requested_topic_ids")
    else:
        if not isinstance(input_ref, str) or not input_ref.startswith(artifacts.SCHEME):
            raise ValueError("reviewed flow requires an artifact:// research input ref")
        state = {
            "run_id": uuid.uuid4().hex[:12], "input_ref": input_ref,
            "through": through, "requested_topic_ids": deepcopy(topic_ids),
            "records": {}, "resume_token": resume_token or uuid.uuid4().hex[:12],
        }
    rgi = artifacts.hydrate(input_ref, base=base)
    checked = contracts.validate(rgi, "research_graph_input@1")
    if not checked["ok"]:
        raise ValueError("invalid research graph input: " + "; ".join(checked["errors"]))

    plan_node = _node(manifest, planner.PLANNER_AGENT)
    _, failure = _run_stage(plan_node, None, state, rgi, node_runner, log, manifest, base=base)
    if failure:
        return _failure_report(state, failure, base=base)
    if through == planner.PLANNER_AGENT:
        return _report(state, "completed", output_ref=state["records"][planner.PLANNER_AGENT]["artifact_ref"], base=base)

    plan = artifacts.hydrate(state["records"][planner.PLANNER_AGENT]["artifact_ref"], base=base)
    selected_topics = _topic_ids(plan, topic_ids)
    if _stage_rank(through) >= _stage_rank(candidate_index.AGENT) \
            and set(selected_topics) != {item["topic_id"] for item in plan["topics"]}:
        return _report(state, "failed", issues=[_issue(
            "partial_topic_set_before_candidate_index",
            "A05 requires every ResearchPlan topic; use --through before A05 or run all topics.",
        )], base=base)

    for stage in (domain.DOMAIN_AGENT, canonical.CANONICAL_AGENT,
                  recent.RECENT_AGENT, market_cases.MARKET_AGENT):
        if _stage_rank(through) < _stage_rank(stage):
            break
        node = _node(manifest, stage)
        for topic_id in selected_topics:
            _, failure = _run_stage(node, topic_id, state, rgi, node_runner, log, manifest, base=base)
            if failure:
                return _failure_report(state, failure, base=base)
        if through == stage:
            output = state["records"][_record_key(stage, selected_topics[-1])].get("artifact_ref")
            return _report(state, "completed", output_ref=output, base=base)

    index_node = _node(manifest, candidate_index.AGENT)
    _, failure = _run_stage(index_node, None, state, rgi, node_runner, log, manifest, base=base)
    if failure:
        return _failure_report(state, failure, base=base)
    candidate_ref = state["records"][candidate_index.AGENT]["artifact_ref"]
    if through == candidate_index.AGENT:
        return _report(state, "completed", output_ref=candidate_ref, base=base)

    gate_payload = _gate_payload(candidate_ref, state, base=base)
    supplied = (decisions or {}).get(SOURCE_GATE)
    if supplied is None and gate_handler is not None:
        supplied = gate_handler(gate_payload)
    if supplied is None:
        _save_checkpoint(state["resume_token"], state)
        return _report(state, "awaiting_user", gate=gate_payload, base=base)
    pending_status = supplied.get("selection", {}).get("status") \
        if isinstance(supplied, dict) and isinstance(supplied.get("selection"), dict) else None
    if pending_status in {"needs_more_search", "cancelled"}:
        finalized = source_selection.finalize_source_selection(
            candidate_ref, supplied["selection"], supplied.get("confirmation_token"), base=base
        )
        if finalized.get("status") == "failed":
            message = finalized.get("summary", "source selection could not be validated")
            return _failure_report(
                state, _issue("source_gate_invalid", message), gate=gate_payload, base=base
            )
        pending_gate = deepcopy(gate_payload)
        pending_gate["last_decision"] = {
            "status": pending_status,
            "requested_search_extensions": deepcopy(
                supplied["selection"].get("requested_search_extensions", [])
            ),
            "message": (
                "Search extension was recorded; discovery must be resumed with the requested scope."
                if pending_status == "needs_more_search" else
                "Source selection was cancelled; no retrieval was authorized."
            ),
        }
        _save_checkpoint(state["resume_token"], state)
        return _report(
            state, "awaiting_user", output_ref=candidate_ref, gate=pending_gate, base=base
        )
    approved_ref, failure = _finalize_gate(candidate_ref, supplied, base=base)
    if failure:
        return _failure_report(state, failure, gate=gate_payload, base=base)
    state["records"][SOURCE_GATE] = {
        "node": SOURCE_GATE, "topic_id": None, "status": "approved",
        "artifact_ref": approved_ref, "review_decision_ref": None,
        "revision_completion_ref": None,
    }
    if through == SOURCE_GATE:
        _clear_checkpoint(state["resume_token"])
        return _report(state, "completed", output_ref=approved_ref, base=base)

    retrieval_node = _node(manifest, retrieval.AGENT)
    _, failure = _run_stage(retrieval_node, None, state, rgi, node_runner, log, manifest, base=base)
    if failure:
        return _failure_report(state, failure, base=base)
    output = state["records"][retrieval.AGENT]["artifact_ref"]
    _clear_checkpoint(state["resume_token"])
    return _report(state, "completed", output_ref=output, base=base)
