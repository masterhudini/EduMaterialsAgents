"""Fail-closed execution of the implemented G02 fast frontier through reviewed A09.

The historical ``g02_flow.run`` stub remains a wiring harness. This module is the real host-runner
path: every producer receives a deterministically prepared scope, must return a finalized typed
artifact, and receives at most one validated A10 decision. APPROVED continues directly, BLOCKED
stops, and REVISE permits one producer correction without another reviewer invocation. The
corrected artifact must pass deterministic finalization and receives an auditable revision receipt.
Fast mode skips A08 explicitly, pauses at Human Research Gate after A09, and finalizes the compact
Graph03 bundle only after a resume decision from the user.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
import pathlib
import re
import uuid

from core import artifacts, contracts, event_log, graphs, paths
from g02 import (
    candidate_index,
    canonical,
    domain,
    market_cases,
    paper_review,
    planner,
    recent,
    retrieval,
    review,
    source_selection,
    synthesis,
)


GRAPH_ID = "g02"
REPORT_CONTRACT = "research_run_report@1"
REVIEWER = "g02-a10-output-reviewer"
SOURCE_GATE = "user-source-selection-gate"
RESEARCH_GATE = "user-research-gate"
CLAIM_VERIFICATION_AGENT = "g02-a08-claim-verification"

STAGES = (
    planner.PLANNER_AGENT,
    domain.DOMAIN_AGENT,
    canonical.CANONICAL_AGENT,
    recent.RECENT_AGENT,
    market_cases.MARKET_AGENT,
    candidate_index.AGENT,
    SOURCE_GATE,
    retrieval.AGENT,
    paper_review.AGENT,
    CLAIM_VERIFICATION_AGENT,
    synthesis.AGENT,
    RESEARCH_GATE,
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
        "research_provider_status", "research_domain_prepare",
        "research_query_plan_generate_fast", "research_metadata_search",
        "research_doi_verify", "research_doi_verify_batch", "research_domain_finalize",
        "research_domain_finalize_from_results",
    ],
    canonical.CANONICAL_AGENT: [
        "research_canonical_prepare", "research_query_plan_generate_fast",
        "research_citation_expand", "research_metadata_search",
        "research_doi_verify", "research_doi_verify_batch", "research_canonical_finalize",
    ],
    recent.RECENT_AGENT: [
        "research_recent_prepare", "research_query_plan_generate_fast",
        "research_metadata_search", "research_doi_verify",
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
    paper_review.AGENT: [
        "research_paper_review_prepare", "research_document_text_index",
        "research_document_text_window", "research_paper_review_finalize",
    ],
    synthesis.AGENT: [
        "research_synthesis_prepare", "research_synthesis_finalize",
    ],
}


def _issue(issue_type: str, message: str, severity: str = "blocker") -> dict:
    return {"severity": severity, "type": issue_type, "message": message}


def _record_key(node: str, topic_id: str | None = None) -> str:
    return f"{node}:{topic_id}" if topic_id else node


def _safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-") or "run"


def _next_artifact_version(value: object) -> str:
    """Return a deterministic patch-version for the single allowed correction."""
    text = str(value or "").strip()
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", text)
    if match:
        major, minor, patch = (int(part) for part in match.groups())
        return f"{major}.{minor}.{patch + 1}"
    return f"{text or '1.0.0'}.revision-1"


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


def _active_profile(manifest: dict) -> dict:
    requested = os.environ.get("EMAGENTS_G02_PROFILE", "").strip()
    name = requested or manifest.get("default_execution_profile", "strict")
    profiles = manifest.get("execution_profiles")
    if isinstance(name, str) and isinstance(profiles, dict):
        profile = profiles.get(name)
        if isinstance(profile, dict):
            return profile
    return {}


def _requires_a10_review(manifest: dict, node_name: str, producer_envelope: dict) -> bool:
    """Return whether the active profile requires a semantic A10 call for this artifact."""
    policy = _active_profile(manifest).get("review_policy")
    if not isinstance(policy, dict):
        return True
    required = set(policy.get("required", [])) if isinstance(policy.get("required"), list) else set()
    conditional = set(policy.get("conditional", [])) \
        if isinstance(policy.get("conditional"), list) else set()
    if node_name in required:
        return True
    if node_name in conditional:
        if producer_envelope.get("status") != "ok":
            return True
        if node_name == "g02-a07-paper-review":
            metrics = producer_envelope.get("metrics")
            metrics = metrics if isinstance(metrics, dict) else {}
            count_fields = (
                "missing_location_count", "conflicting_evidence_count",
                "prompt_injection_flag_count",
            )
            if any(isinstance(metrics.get(field), int) and metrics[field] > 0
                   for field in count_fields):
                return True
            if metrics.get("central_document") is True:
                return True
            issue_types = {
                str(item.get("type", "")).casefold()
                for item in producer_envelope.get("issues", []) if isinstance(item, dict)
            }
            triggers = ("missing_location", "conflict", "prompt_injection", "central_document")
            if any(any(trigger in issue_type for trigger in triggers)
                   for issue_type in issue_types):
                return True
        return False
    return True


def _fast_track_review_decision(task: dict, *, base=None) -> tuple[dict, str]:
    """Persist a review_decision@1 proving deterministic fast-track approval without A10."""
    decision = {
        "schema_version": "review_decision@1",
        "review_id": task["review_id"],
        "task_id": task["task_id"],
        "logical_review_node": task["logical_review_node"],
        "reviewer_agent": REVIEWER,
        "producer_agent": task["producer_agent"],
        "artifact_ref": task["artifact"]["ref"],
        "artifact_version": task["artifact"]["artifact_version"],
        "review_profile": task["review_profile"],
        "decision": "APPROVED",
        "findings": [],
        "advisories": [{
            "criterion_id": "REVIEW_BASIS",
            "location": "review_policy.fast",
            "observation": (
                "A10 semantic review was skipped by the fast execution profile because "
                "deterministic finalization returned status ok."
            ),
        }],
        "closed_finding_ids": [],
        "revision_scope": None,
        "root_cause": None,
        "confidence": "medium",
        "attempt": task["attempt"],
        "summary": (
            "Fast-track deterministic approval: artifact passed finalization with status ok; "
            "A10 semantic review was not invoked."
        ),
    }
    envelope = review.finalize_review_decision(task, decision, base=base)
    return _decision_from_envelope(task, envelope, base=base)


def _store_revision_completion(state: dict, node: dict, decision: dict, decision_ref: str,
                               original_descriptor: dict, revised_descriptor: dict, *,
                               base=None) -> str:
    """Persist proof that one producer correction passed deterministic finalization."""
    if original_descriptor.get("path") == revised_descriptor.get("path"):
        raise ValueError("a correction must produce a new artifact ref")
    if original_descriptor.get("artifact_version") == revised_descriptor.get("artifact_version"):
        raise ValueError("a correction must advance artifact_version")
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


def _prepare(node_name: str, topic_id: str | None, state: dict, rgi: dict, *, manifest: dict,
             base=None,
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
        finalize = {
            "operation": "research_domain_finalize_from_results",
            "fixed_arguments": deepcopy(prepare_args),
            "generated_arguments": [
                "query_plan", "literature_tool_result_refs",
                "doi_verification_result_refs", "coverage_assignments",
                "selected_source_ids", "artifact_version",
            ],
        }
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
        active = _active_profile(manifest)
        selection_profile = deepcopy(active.get("candidate_index")) \
            if isinstance(active.get("candidate_index"), dict) else {}
        if isinstance(active.get("required_stream_policy"), str):
            selection_profile.setdefault(
                "required_stream_policy", active["required_stream_policy"]
            )
        selection_profile = selection_profile or None
        prepared = candidate_index.prepare_candidate_index(
            plan_ref, reviewed, selection_profile=selection_profile,
            previous_index_ref=previous_ref, artifact_base=base
        )
        scoped = prepared.get("candidate_index_input")
        prepare_args = {
            "research_plan_ref": plan_ref,
            "reviewed_upstreams": reviewed,
            "selection_profile": deepcopy(selection_profile),
        }
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
    elif node_name == paper_review.AGENT:
        corpus_record = records.get(retrieval.AGENT)
        corpus_ref = corpus_record.get("artifact_ref") if corpus_record else None
        candidate_record = records.get(candidate_index.AGENT)
        candidate_ref = candidate_record.get("artifact_ref") if candidate_record else None
        prepared = paper_review.prepare_paper_review(
            corpus_ref, topic_id, research_plan_ref=plan_ref,
            candidate_source_index_ref=candidate_ref, previous_review_ref=previous_ref,
            revision_items=revision_items, artifact_base=base,
        )
        scoped = prepared.get("paper_review_input")
        prepare_args = {
            "retrieved_corpus_ref": corpus_ref,
            "source_id": topic_id,
            "research_plan_ref": plan_ref,
            "candidate_source_index_ref": candidate_ref,
        }
        finalize = {"operation": "research_paper_review_finalize",
                    "fixed_arguments": deepcopy(prepare_args),
                    "generated_argument": "output"}
    elif node_name == synthesis.AGENT:
        candidate_record = records.get(candidate_index.AGENT)
        gate_record = records.get(SOURCE_GATE)
        corpus_record = records.get(retrieval.AGENT)
        paper_records = sorted((
            item for item in records.values()
            if item.get("node") == paper_review.AGENT
            and item.get("status") in {"approved", "revised_after_review"}
            and isinstance(item.get("artifact_ref"), str)
        ), key=lambda item: str(item.get("topic_id") or item.get("artifact_ref")))
        paper_refs = [item["artifact_ref"] for item in paper_records]
        reviewed_paper_reviews = [{
            "paper_review_ref": item["artifact_ref"],
            "review_decision_ref": item.get("review_decision_ref"),
            "revision_completion_ref": item.get("revision_completion_ref"),
        } for item in paper_records]
        active = _active_profile(manifest)
        prepared = synthesis.prepare_synthesis(
            plan_ref,
            candidate_record.get("artifact_ref") if candidate_record else None,
            gate_record.get("artifact_ref") if gate_record else None,
            corpus_record.get("artifact_ref") if corpus_record else None,
            paper_refs,
            profile=active,
            reviewed_paper_reviews=reviewed_paper_reviews,
            previous_state_ref=previous_ref,
            revision_items=revision_items,
            base=base,
        )
        scoped = prepared.get("synthesis_input")
        prepare_args = {
            "research_plan_ref": plan_ref,
            "candidate_source_index_ref": candidate_record.get("artifact_ref") if candidate_record else None,
            "approved_source_set_ref": gate_record.get("artifact_ref") if gate_record else None,
            "retrieved_corpus_ref": corpus_record.get("artifact_ref") if corpus_record else None,
            "paper_review_refs": paper_refs,
            "reviewed_paper_reviews": reviewed_paper_reviews,
            "profile": deepcopy(active),
        }
        finalize = {"operation": "research_synthesis_finalize",
                    "fixed_arguments": deepcopy(prepare_args),
                    "generated_argument": "output"}
    else:
        raise ValueError(f"no execution adapter for {node_name}")

    if previous_ref and node_name != planner.PLANNER_AGENT:
        field = (
            "previous_corpus_ref" if node_name == retrieval.AGENT else
            "previous_index_ref" if node_name == candidate_index.AGENT else
            "previous_review_ref" if node_name == paper_review.AGENT else
            "previous_state_ref" if node_name == synthesis.AGENT else
            "previous_candidates_ref"
        )
        prepare_args[field] = previous_ref
        finalize["fixed_arguments"][field] = previous_ref
        if node_name not in {candidate_index.AGENT, retrieval.AGENT}:
            prepare_args["revision_items"] = revision_items
            finalize["fixed_arguments"]["revision_items"] = revision_items

    if previous_ref:
        previous_artifact = artifacts.hydrate(previous_ref, base=base)
        required_version = _next_artifact_version(previous_artifact.get("artifact_version"))
        if node_name in {
                candidate_index.AGENT, retrieval.AGENT, paper_review.AGENT, synthesis.AGENT}:
            finalize["fixed_arguments"]["artifact_version"] = required_version

    prepare_operation = (
        "research_planner_prepare" if node_name == planner.PLANNER_AGENT else
        "research_domain_prepare" if node_name == domain.DOMAIN_AGENT else
        prepare_op if node_name in {canonical.CANONICAL_AGENT, recent.RECENT_AGENT,
                                    market_cases.MARKET_AGENT} else
        "research_candidate_index_prepare" if node_name == candidate_index.AGENT else
        "research_retrieval_prepare" if node_name == retrieval.AGENT else
        "research_paper_review_prepare" if node_name == paper_review.AGENT else
        "research_synthesis_prepare"
    )
    protocol = {
        "prepare": {"operation": prepare_operation, "arguments": prepare_args},
        "allowed_operations": ALLOWED_OPERATIONS[node_name],
        "finalize": finalize,
        "rules": [
            "Call the prepare operation first and stop if it is not ready.",
            "Use only allowed_operations; never use direct web, shell HTTP or an unlisted MCP tool.",
            "Return the exact envelope produced by finalize as the final message.",
        ],
    }
    if previous_ref:
        protocol["required_artifact_version"] = required_version
        protocol["rules"].append(
            f"This is the only correction attempt; emit artifact_version {required_version} and change only the listed revision items."
        )
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
    if node_name == paper_review.AGENT:
        return paper_review.build_paper_review_task(
            prepared_input, descriptor, base=base, **common
        )
    if node_name == synthesis.AGENT:
        return synthesis.build_synthesis_review_task(
            prepared_input, descriptor, base=base, **common
        )
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
            node["name"], topic_id, state, rgi, manifest=manifest, base=base,
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
        task = review.apply_review_mode(
            task, _active_profile(manifest).get("review_mode", "standard")
        )
        if not _requires_a10_review(manifest, node["name"], envelope):
            try:
                decision, decision_ref = _fast_track_review_decision(task, base=base)
            except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
                return None, _issue("fast_track_review_rejected", f"{node['name']}: {exc}")
            record = {
                "node": node["name"], "topic_id": topic_id, "status": "approved",
                "artifact_ref": descriptor["path"], "artifact_descriptor": descriptor,
                "review_decision_ref": decision_ref,
                "revision_completion_ref": None,
            }
            state["records"][key] = record
            log.append(REVIEWER, "fast_track_review", status=decision["decision"], detail={
                "target": node["name"], "topic_id": topic_id,
                "artifact_ref": descriptor["path"], "review_decision_ref": decision_ref,
            })
            return record, None

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
                "rules": [
                    "Call review prepare and use its deterministic preflight summary first.",
                    "Follow review_mode and review_guidance from the supplied task.",
                    "Review only the supplied artifact and return the exact finalize envelope.",
                ],
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
        if node["name"] == candidate_index.AGENT:
            return None, _issue(
                "deterministic_index_revision_requires_input_change",
                "A05 is derived deterministically from reviewed upstreams and profile settings; "
                "a REVISE decision requires an upstream/search/profile change, not an identical rerun.",
            )
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


def _skip_nodes(manifest: dict) -> set[str]:
    active = _active_profile(manifest)
    values = active.get("skip_nodes") if isinstance(active, dict) else []
    return {item for item in values if isinstance(item, str)}


def _accepted_review_source_ids(corpus: dict) -> list[str]:
    result = []
    for field in ("documents", "market_cases"):
        for item in corpus.get(field, []):
            if not isinstance(item, dict):
                continue
            if item.get("status") in {"accepted", "duplicate"} \
                    and isinstance(item.get("source_id"), str):
                result.append(item["source_id"])
    return list(dict.fromkeys(result))


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
        candidate = artifacts.hydrate(candidate_ref, base=base)
        if approved.get("candidate_source_index_ref") != candidate_ref \
                or approved.get("task_id") != candidate.get("task_id") \
                or approved.get("final_confirmation") is not True:
            return None, _issue(
                "invalid_human_approved_source_set",
                "approved source set is not finally confirmed and bound to this candidate index",
            )
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


def _research_gate_payload(research_state_ref: str, state: dict, *, base=None) -> dict:
    payload = synthesis.prepare_human_research_gate(research_state_ref, base=base)
    payload["context"] = {**payload.get("context", {}), "run_id": state["run_id"]}
    return payload


def _finalize_research_gate(research_state_ref: str, decision: dict, *,
                            base=None) -> tuple[str | None, dict | None]:
    envelope = synthesis.finalize_research_bundle(research_state_ref, decision, base=base)
    if envelope.get("status") == "needs_input":
        return None, _issue(
            "research_gate_not_approved",
            envelope.get("summary", "Human Research Gate approval is required"),
            "major",
        )
    if envelope.get("status") != "ok":
        return None, _issue(
            "research_bundle_finalize_failed",
            envelope.get("summary", "research bundle finalization failed") + ": "
            + "; ".join(item.get("message", "") for item in envelope.get("issues", [])),
        )
    ref = next((item.get("path") for item in envelope.get("produced", [])
                if item.get("type") == "user_approved_research_bundle"), None)
    if not isinstance(ref, str):
        return None, _issue("research_gate_output_missing",
                            "finalized research gate produced no bundle")
    return ref, None


def _source_terminal_gate_handler(payload: dict) -> dict:
    """Two-step source gate with numbered sources and a separate confirmation."""
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


def _research_terminal_gate_handler(payload: dict) -> dict:
    """Collect the explicit decisions required to freeze the Graph03 research bundle."""
    import sys

    packet = payload.get("human_validation_packet", {})
    # Prefer the canonical executive digest (research_summary@1); fall back to the validation packet.
    digest = payload.get("research_summary") or {}
    language = str(packet.get("output_language") or "English")
    polish = language.casefold().startswith("pl") or "pol" in language.casefold()
    summary = {
        "gate": payload.get("gate"),
        "task_id": payload.get("context", {}).get("task_id"),
        "synthesis_mode": digest.get("synthesis_mode") or payload.get("context", {}).get("synthesis_mode"),
        "instructions": packet.get("instructions"),
        "required_updates": digest.get("required_updates", packet.get("required_updates", [])),
        "optional_improvements": digest.get("optional_improvements", packet.get("optional_improvements", [])),
        "unresolved_items": digest.get("unresolved", packet.get("unresolved", [])),
        "confidence": digest.get("confidence", packet.get("confidence")),
        "fast_mode_limitation": digest.get("fast_mode_limitation", packet.get("fast_mode_limitation")),
    }
    sys.stderr.write(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")

    def ask(message: str) -> bool:
        sys.stderr.write(message + " [yes/no]: ")
        sys.stderr.flush()
        answer = sys.stdin.readline().strip().casefold()
        return answer in {"yes", "y", "tak", "t"}

    required = ask(
        "Zatwierdzić wszystkie wymagane aktualizacje?" if polish
        else "Approve all required updates?"
    )
    optional = ask(
        "Dołączyć opcjonalne usprawnienia?" if polish
        else "Include optional improvements?"
    )
    sys.stderr.write(
        ("Obsługa nierozstrzygniętych pozycji [keep/exclude/return]: " if polish else
         "Unresolved item handling [keep/exclude/return]: ")
    )
    sys.stderr.flush()
    action = sys.stdin.readline().strip().casefold()
    actions = {
        "keep": "keep_as_unresolved_items",
        "zachowaj": "keep_as_unresolved_items",
        "exclude": "exclude_from_graph03_handoff",
        "pomiń": "exclude_from_graph03_handoff",
        "return": "return_for_research",
        "wróć": "return_for_research",
    }
    unresolved = actions.get(action)
    if unresolved is None:
        raise ValueError("unsupported unresolved item handling")
    expected = "POTWIERDZAM" if polish else "CONFIRM"
    sys.stderr.write(
        (f"Wpisz {expected}, aby zatwierdzić tę decyzję końcową: " if polish else
         f"Type {expected} to approve this final decision: ")
    )
    sys.stderr.flush()
    confirmed = sys.stdin.readline().strip().upper() in {expected, "CONFIRM", "POTWIERDZAM"}
    status = "approved" if confirmed and required and unresolved != "return_for_research" \
        else "needs_changes"
    return {
        "status": status,
        "approve_required_updates": required,
        "approve_optional_improvements": optional,
        "unresolved_claim_handling": unresolved,
    }


def terminal_gate_handler(payload: dict) -> dict:
    """Dispatch the terminal UI to the source or final research gate."""
    gate_name = payload.get("gate") if isinstance(payload, dict) else None
    if gate_name == SOURCE_GATE:
        return _source_terminal_gate_handler(payload)
    if gate_name == RESEARCH_GATE:
        return _research_terminal_gate_handler(payload)
    raise ValueError(f"unsupported terminal gate {gate_name!r}")


def run(input_ref=None, *, node_runner, base=None, gate_handler=None, pause_on_gate=False,
        resume_token: str | None = None, decisions: dict | None = None,
        through: str = synthesis.AGENT, topic_ids: list[str] | None = None) -> dict:
    """Run the implemented, reviewed G02 frontier and return research_run_report@1."""
    manifest = graphs.load(GRAPH_ID)
    _stage_rank(through)
    log = event_log.open_log(f"{GRAPH_ID}-reviewed")

    if resume_token and input_ref is None:
        state = _load_checkpoint(resume_token)
        input_ref = state["input_ref"]
        if through != synthesis.AGENT and through != state["through"]:
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

    if SOURCE_GATE in state["records"]:
        approved_ref = state["records"][SOURCE_GATE]["artifact_ref"]
    else:
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
    corpus_ref = state["records"][retrieval.AGENT]["artifact_ref"]
    output = corpus_ref
    if through == retrieval.AGENT:
        _clear_checkpoint(state["resume_token"])
        return _report(state, "completed", output_ref=output, base=base)

    corpus = artifacts.hydrate(corpus_ref, base=base)
    source_ids = _accepted_review_source_ids(corpus)
    if _stage_rank(through) >= _stage_rank(paper_review.AGENT):
        review_node = _node(manifest, paper_review.AGENT)
        for source_id in source_ids:
            _, failure = _run_stage(
                review_node, source_id, state, rgi, node_runner, log, manifest, base=base
            )
            if failure:
                return _failure_report(state, failure, base=base)
        if through == paper_review.AGENT:
            output = (
                state["records"][_record_key(paper_review.AGENT, source_ids[-1])]["artifact_ref"]
                if source_ids else corpus_ref
            )
            _clear_checkpoint(state["resume_token"])
            return _report(state, "completed", output_ref=output, base=base)

    if CLAIM_VERIFICATION_AGENT not in _skip_nodes(manifest) \
            and _stage_rank(through) >= _stage_rank(CLAIM_VERIFICATION_AGENT):
        return _report(state, "failed", issues=[_issue(
            "unsupported_claim_verification_profile",
            "A08 remains present in the graph but has no fast runtime; use a profile that skips it.",
        )], output_ref=output, base=base)

    synthesis_node = _node(manifest, synthesis.AGENT)
    _, failure = _run_stage(synthesis_node, None, state, rgi, node_runner, log, manifest, base=base)
    if failure:
        return _failure_report(state, failure, base=base)
    research_state_ref = state["records"][synthesis.AGENT]["artifact_ref"]
    output = research_state_ref
    if _stage_rank(through) < _stage_rank(RESEARCH_GATE):
        research_gate = _research_gate_payload(research_state_ref, state, base=base)
        supplied = (decisions or {}).get(RESEARCH_GATE)
        if supplied is None and gate_handler is not None:
            supplied = gate_handler(research_gate)
        if supplied is None:
            _save_checkpoint(state["resume_token"], state)
            return _report(
                state, "awaiting_user", output_ref=research_state_ref,
                gate=research_gate, base=base
            )
        bundle_ref, failure = _finalize_research_gate(research_state_ref, supplied, base=base)
        if failure:
            pending_gate = deepcopy(research_gate)
            pending_gate["last_decision"] = deepcopy(supplied)
            _save_checkpoint(state["resume_token"], state)
            return _report(
                state, "awaiting_user", output_ref=research_state_ref,
                issues=[failure], gate=pending_gate, base=base
            )
        state["records"][RESEARCH_GATE] = {
            "node": RESEARCH_GATE, "topic_id": None, "status": "approved",
            "artifact_ref": bundle_ref, "review_decision_ref": None,
            "revision_completion_ref": None,
        }
        _clear_checkpoint(state["resume_token"])
        return _report(state, "completed", output_ref=bundle_ref, base=base)

    research_gate = _research_gate_payload(research_state_ref, state, base=base)
    supplied = (decisions or {}).get(RESEARCH_GATE)
    if supplied is None and gate_handler is not None:
        supplied = gate_handler(research_gate)
    if supplied is None:
        _save_checkpoint(state["resume_token"], state)
        return _report(
            state, "awaiting_user", output_ref=research_state_ref,
            gate=research_gate, base=base
        )
    bundle_ref, failure = _finalize_research_gate(research_state_ref, supplied, base=base)
    if failure:
        pending_gate = deepcopy(research_gate)
        pending_gate["last_decision"] = deepcopy(supplied)
        _save_checkpoint(state["resume_token"], state)
        return _report(
            state, "awaiting_user", output_ref=research_state_ref,
            issues=[failure], gate=pending_gate, base=base
        )
    state["records"][RESEARCH_GATE] = {
        "node": RESEARCH_GATE, "topic_id": None, "status": "approved",
        "artifact_ref": bundle_ref, "review_decision_ref": None,
        "revision_completion_ref": None,
    }
    _clear_checkpoint(state["resume_token"])
    return _report(state, "completed", output_ref=bundle_ref, base=base)
