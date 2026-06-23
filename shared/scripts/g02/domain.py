"""Deterministic boundary for G02-A02 Domain discovery."""
from __future__ import annotations

import re
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path

from core import artifacts, contracts
from g02 import crossref, provider_config, query_planning

DOMAIN_INPUT_CONTRACT = "domain_research_input@1"
DOMAIN_OUTPUT_CONTRACT = "domain_candidate_sources@1"
RESEARCH_PLAN_CONTRACT = "research_plan@1"
SOURCE_RECORD_CONTRACT = "source_record@1"
TOOL_RESULT_CONTRACT = "literature_tool_result@1"
ENVELOPE_CONTRACT = "envelope@1"
DOMAIN_AGENT = "g02-a02-domain"
REVIEW_PROFILE = "domain_candidates"
PROVIDERS = {"openalex", "semantic_scholar", "arxiv"}

DOMAIN_ACCEPTANCE_CRITERIA = [
    {
        "criterion_id": "DR-01",
        "description": "Every query route maps to the approved topic purpose and coverage units, and every generated term is traced to approved origin terms and an approved expansion area.",
        "mandatory": True,
    },
    {
        "criterion_id": "DR-02",
        "description": "Every candidate is a real provider-backed source_record@1 with query and raw-response provenance.",
        "mandatory": True,
    },
    {
        "criterion_id": "DR-03",
        "description": "Missing metadata remains null and provider metadata is not reconstructed or altered by the agent.",
        "mandatory": True,
    },
    {
        "criterion_id": "DR-04",
        "description": "The query log preserves successful, failed and valid zero-result provider operations.",
        "mandatory": True,
    },
    {
        "criterion_id": "DR-05",
        "description": "The plan includes neutral complementary and qualifying-or-critical routes when the topic requires them.",
        "mandatory": True,
    },
    {
        "criterion_id": "DR-06",
        "description": "Stop reason, provider failures and remaining coverage units are explicit.",
        "mandatory": True,
    },
    {
        "criterion_id": "DR-07",
        "description": "Every non-empty DOI has an auditable Crossref result; identity conflicts remain visible and provider metadata is unchanged.",
        "mandatory": True,
    },
]

DOMAIN_EVIDENCE_REQUIREMENTS = [
    {
        "requirement_id": "DR-E01",
        "description": "Each query-log entry resolves to one literature_tool_result@1 artifact.",
        "mandatory": True,
    },
    {
        "requirement_id": "DR-E02",
        "description": "Every candidate exactly matches a normalized provider record referenced by the query log.",
        "mandatory": True,
    },
    {
        "requirement_id": "DR-E03",
        "description": "Coverage mappings identify whether metadata, title or abstract supported the mapping.",
        "mandatory": True,
    },
]

DOMAIN_PROHIBITED_BEHAVIORS = [
    "Inventing or completing bibliographic metadata absent from provider results.",
    "Using an untraceable generated query term or an expansion outside the approved topic.",
    "Assigning final source roles, ranking scientific quality or deciding claim stance.",
    "Searching outside the approved topic, filters, providers or candidate limits.",
    "Downloading documents, interpreting full text or exposing credentials.",
]

DOMAIN_SEVERITY_RULES = {
    "minor": "A local explanation or coverage-label defect that does not alter provider facts.",
    "major": "Missing route, provenance, coverage mapping, stop reason or usable provider result.",
    "blocker": "Fabricated metadata, unapproved scope, invalid provider evidence or unreadable artifacts.",
}


def _issue(severity: str, issue_type: str, message: str, location: str) -> dict:
    return {
        "severity": severity,
        "type": issue_type,
        "message": message,
        "location": location,
    }


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _duplicates(values: list[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def _unknown_fields(value: object, allowed: set[str]) -> list[str]:
    return sorted(set(value) - allowed) if isinstance(value, dict) else []


def _revision_fields(revision_items: list[dict] | None) -> set[str]:
    mutable = {
        "query_plan", "candidates", "doi_verifications", "query_log", "coverage_map", "stop_reason",
        "remaining_coverage_units", "provider_issues",
    }
    targeted: set[str] = set()
    for item in revision_items or []:
        location = item.get("location") if isinstance(item, dict) else None
        if not isinstance(location, str):
            continue
        targeted.update(
            field for field in mutable
            if re.search(rf"(?:^|\.){re.escape(field)}(?:\.|\[|$)", location)
        )
    dependency_order = [
        "query_plan", "query_log", "candidates", "coverage_map", "provider_issues",
        "remaining_coverage_units", "stop_reason",
    ]
    expanded = set(targeted)
    for field in targeted:
        if field in dependency_order:
            expanded.update(dependency_order[dependency_order.index(field):])
    return expanded


def _shape_issues(payload: object, contract_ref: str, code: str) -> list[dict]:
    try:
        result = contracts.validate(payload, contract_ref)
    except (KeyError, ValueError) as exc:
        return [_issue("blocker", "contract_unavailable", str(exc), contract_ref)]
    return [_issue("blocker", code, error, contract_ref) for error in result["errors"]]


def _envelope(status: str, summary: str, issues: list[dict], *, produced=None,
              metrics=None, resume_token=None) -> dict:
    payload = {
        "status": status,
        "produced": produced or [],
        "summary": summary,
        "issues": [{
            "severity": item["severity"],
            "type": item["type"],
            "message": f"{item['message']} (location: {item['location']})",
        } for item in issues],
        "metrics": metrics or {},
        "resume_token": resume_token,
    }
    checked = contracts.validate(payload, ENVELOPE_CONTRACT)
    if not checked["ok"]:
        raise ValueError("invalid domain envelope: " + "; ".join(checked["errors"]))
    return payload


def failed_envelope(issue_type: str, message: str, location: str = "domain") -> dict:
    return _envelope(
        "failed", "G02-A02 Domain did not produce candidate sources.",
        [_issue("blocker", issue_type, message, location)],
    )


def needs_input_envelope(issue_type: str, message: str, location: str) -> dict:
    return _envelope(
        "needs_input", "Domain input is missing an approved topic decision.",
        [_issue("blocker", issue_type, message, location)],
    )


def validate_domain_input(domain_input: object) -> dict:
    issues = _shape_issues(
        domain_input, DOMAIN_INPUT_CONTRACT, "invalid_domain_input_contract"
    )
    if not isinstance(domain_input, dict):
        return {"ok": False, "issues": issues}
    unknown_root = _unknown_fields(
        domain_input,
        {"schema_version", "task_id", "research_plan_ref", "research_plan_artifact_version",
         "topic", "provider_capabilities", "output_language"},
    )
    if unknown_root:
        issues.append(_issue(
            "blocker", "unknown_domain_input_fields",
            f"domain input contains unsupported fields {unknown_root}", "domain_input",
        ))
    for field in ("task_id", "research_plan_ref", "research_plan_artifact_version",
                  "output_language"):
        value = domain_input.get(field)
        if not isinstance(value, str) or not value.strip():
            issues.append(_issue(
                "blocker", "empty_domain_input_field", f"{field} must not be empty", field
            ))
    ref = domain_input.get("research_plan_ref")
    if isinstance(ref, str) and not ref.startswith(artifacts.SCHEME):
        issues.append(_issue(
            "blocker", "invalid_research_plan_ref",
            "research_plan_ref must use artifact://", "research_plan_ref",
        ))
    topic = domain_input.get("topic")
    required_topic_fields = (
        "topic_id", "purpose", "linked_driver_ids", "approved_domains",
        "search_strategy", "coverage_requirements", "stop_rule",
    )
    if isinstance(topic, dict):
        for field in required_topic_fields:
            if field not in topic:
                issues.append(_issue(
                    "blocker", "incomplete_domain_topic",
                    f"scoped topic is missing {field}", f"topic.{field}",
                ))
    capabilities = domain_input.get("provider_capabilities")
    capabilities = capabilities if isinstance(capabilities, list) else []
    provider_names = [item.get("provider") for item in capabilities
                      if isinstance(item, dict) and isinstance(item.get("provider"), str)]
    for index, item in enumerate(capabilities):
        unknown_capability = _unknown_fields(
            item, {"provider", "enabled", "ready", "authentication"}
        )
        if unknown_capability:
            issues.append(_issue(
                "blocker", "unknown_provider_capability_fields",
                f"provider capability contains unsupported fields {unknown_capability}",
                f"provider_capabilities[{index}]",
            ))
    if _duplicates(provider_names):
        issues.append(_issue(
            "blocker", "duplicate_provider_capability",
            f"duplicate providers {sorted(_duplicates(provider_names))}",
            "provider_capabilities",
        ))
    ready = [item for item in capabilities
             if isinstance(item, dict) and item.get("enabled") is True
             and item.get("ready") is True]
    if not ready:
        issues.append(_issue(
            "blocker", "no_ready_provider",
            "at least one configured scholarly provider must be ready",
            "provider_capabilities",
        ))
    return {"ok": not issues, "issues": issues}


def prepare_domain(research_plan_ref: str, topic_id: str, *,
                   config_path: str | Path | None = None,
                   runtime_home: str | Path | None = None, artifact_base=None,
                   previous_candidates_ref: str | None = None,
                   revision_items: list[dict] | None = None) -> dict:
    """Hydrate one approved plan topic and bind secret-free provider capabilities."""
    if not isinstance(research_plan_ref, str) or not research_plan_ref.startswith(artifacts.SCHEME):
        return {"ready": False, "envelope": needs_input_envelope(
            "invalid_research_plan_ref", "an artifact:// ResearchPlan ref is required",
            "research_plan_ref",
        )}
    if not isinstance(topic_id, str) or not topic_id.strip():
        return {"ready": False, "envelope": needs_input_envelope(
            "missing_topic_id", "a non-empty approved topic_id is required", "topic_id"
        )}
    try:
        plan = artifacts.hydrate(research_plan_ref, base=artifact_base)
        shape = contracts.validate(plan, RESEARCH_PLAN_CONTRACT)
        if not shape["ok"]:
            raise ValueError("; ".join(shape["errors"]))
    except (OSError, ValueError, KeyError, IndexError) as exc:
        return {"ready": False, "envelope": failed_envelope(
            "invalid_research_plan", str(exc), "research_plan_ref"
        )}
    topics = [item for item in plan.get("topics", [])
              if isinstance(item, dict) and item.get("topic_id") == topic_id]
    if len(topics) != 1:
        return {"ready": False, "envelope": needs_input_envelope(
            "unknown_or_duplicate_topic",
            f"expected exactly one topic {topic_id!r}, found {len(topics)}", "topic_id",
        )}
    try:
        config = provider_config.load_config(
            config_path, runtime_home=runtime_home, create_dirs=True
        )
    except provider_config.ProviderConfigError as exc:
        return {"ready": False, "envelope": failed_envelope(
            "provider_configuration_error", str(exc), "provider_config"
        )}
    domain_input = {
        "schema_version": DOMAIN_INPUT_CONTRACT,
        "task_id": plan["task_id"],
        "research_plan_ref": research_plan_ref,
        "research_plan_artifact_version": plan["artifact_version"],
        "topic": deepcopy(topics[0]),
        "provider_capabilities": config.public_status()["capabilities"],
        "output_language": plan["output_language"],
    }
    checked = validate_domain_input(domain_input)
    if not checked["ok"]:
        return {"ready": False, "envelope": failed_envelope(
            "invalid_scoped_domain_input",
            "; ".join(item["message"] for item in checked["issues"]), "domain_input",
        )}

    previous = None
    if previous_candidates_ref is not None:
        try:
            if not isinstance(previous_candidates_ref, str) \
                    or not previous_candidates_ref.startswith(artifacts.SCHEME):
                raise ValueError("previous_candidates_ref must use artifact://")
            previous = artifacts.hydrate(previous_candidates_ref, base=artifact_base)
            previous_shape = contracts.validate(previous, DOMAIN_OUTPUT_CONTRACT)
            if not previous_shape["ok"]:
                raise ValueError("; ".join(previous_shape["errors"]))
            if previous.get("task_id") != plan["task_id"] \
                    or previous.get("topic_id") != topic_id:
                raise ValueError("previous candidates do not match the task and topic")
        except (OSError, ValueError, KeyError, IndexError) as exc:
            return {"ready": False, "envelope": failed_envelope(
                "invalid_previous_domain_candidates", str(exc), "previous_candidates_ref"
            )}
    if revision_items and previous is None:
        return {"ready": False, "envelope": failed_envelope(
            "missing_previous_domain_candidates",
            "revision_items require previous_candidates_ref", "revision_items",
        )}
    if revision_items is not None and (
            not isinstance(revision_items, list)
            or any(not isinstance(item, dict) for item in revision_items)):
        return {"ready": False, "envelope": failed_envelope(
            "invalid_revision_items", "revision_items must be a list of findings",
            "revision_items",
        )}
    for index, item in enumerate(revision_items or []):
        for field in ("finding_id", "location", "required_correction"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                return {"ready": False, "envelope": failed_envelope(
                    "invalid_revision_item",
                    f"revision_items[{index}].{field} must be a non-empty string",
                    "revision_items",
                )}
    return {
        "ready": True,
        "domain_input": domain_input,
        "config_status": config.public_status(),
        "previous_candidates": previous,
        "previous_candidates_ref": previous_candidates_ref,
        "revision_items": deepcopy(revision_items or []),
    }


def _hydrate_tool_results(output: dict, *, base=None) -> tuple[list[dict], list[dict]]:
    issues: list[dict] = []
    results: list[dict] = []
    for index, entry in enumerate(output.get("query_log", [])):
        if not isinstance(entry, dict):
            continue
        ref = entry.get("literature_tool_result_ref")
        location = f"query_log[{index}]"
        if not isinstance(ref, str) or not ref.startswith(artifacts.SCHEME):
            issues.append(_issue(
                "blocker", "invalid_tool_result_ref",
                "query log result ref must use artifact://", f"{location}.literature_tool_result_ref",
            ))
            continue
        try:
            result = artifacts.hydrate(ref, base=base)
            shape = contracts.validate(result, TOOL_RESULT_CONTRACT)
            if not shape["ok"]:
                raise ValueError("; ".join(shape["errors"]))
        except (OSError, ValueError, KeyError, IndexError) as exc:
            issues.append(_issue(
                "blocker", "unreadable_tool_result", str(exc),
                f"{location}.literature_tool_result_ref",
            ))
            continue
        expected = {
            "operation_id": result.get("operation_id"),
            "query_id": result.get("request", {}).get("query_id"),
            "route_id": result.get("request", {}).get("route_id"),
            "provider": result.get("provider"),
            "status": result.get("status"),
            "result_count": len(result.get("records", [])),
        }
        for field, value in expected.items():
            if entry.get(field) != value:
                issues.append(_issue(
                    "blocker", "query_log_mismatch",
                    f"{field} does not match referenced tool result",
                    f"{location}.{field}",
                ))
        results.append(result)
    return results, issues


def validate_domain_candidates(output: object, domain_input: dict, *, base=None,
                               previous_candidates: dict | None = None,
                               revision_items: list[dict] | None = None) -> dict:
    issues = _shape_issues(
        output, DOMAIN_OUTPUT_CONTRACT, "invalid_domain_candidates_contract"
    )
    input_checked = validate_domain_input(domain_input)
    if not input_checked["ok"]:
        issues.extend(input_checked["issues"])
    if not isinstance(output, dict):
        return {"ok": False, "complete": False, "issues": issues}
    unknown_root = _unknown_fields(
        output,
        {"schema_version", "artifact_version", "task_id", "topic_id", "research_plan_ref",
         "query_plan", "candidates", "doi_verifications", "query_log", "coverage_map", "stop_reason",
         "remaining_coverage_units", "provider_issues", "review_profile_ref"},
    )
    if unknown_root:
        issues.append(_issue(
            "major", "unknown_domain_output_fields",
            f"domain output contains unsupported fields {unknown_root}", "domain_output",
        ))
    topic = domain_input.get("topic") if isinstance(domain_input.get("topic"), dict) else {}
    for field, expected in (
        ("task_id", domain_input.get("task_id")),
        ("topic_id", topic.get("topic_id")),
        ("research_plan_ref", domain_input.get("research_plan_ref")),
        ("review_profile_ref", REVIEW_PROFILE),
    ):
        if output.get(field) != expected:
            issues.append(_issue(
                "blocker", "domain_output_identity_mismatch",
                f"{field} must equal {expected!r}", field,
            ))
    version = output.get("artifact_version")
    if not isinstance(version, str) or not version.strip():
        issues.append(_issue(
            "major", "empty_artifact_version", "artifact_version must not be empty",
            "artifact_version",
        ))
    if previous_candidates is not None \
            and version == previous_candidates.get("artifact_version"):
        issues.append(_issue(
            "major", "artifact_version_not_advanced",
            "a revised domain artifact must advance artifact_version", "artifact_version",
        ))
    if previous_candidates is not None:
        targeted_fields = _revision_fields(revision_items)
        if targeted_fields:
            for field in output:
                if field != "artifact_version" and field not in targeted_fields \
                        and output.get(field) != previous_candidates.get(field):
                    issues.append(_issue(
                        "major", "unscoped_revision_change",
                        f"untargeted field {field!r} changed during a scoped revision", field,
                    ))

    query_plan = output.get("query_plan")
    plan_checked = query_planning.validate_query_plan(query_plan, domain_input)
    for item in plan_checked["issues"]:
        issues.append(_issue(
            "major", item["code"], item["message"], f"query_plan.{item['location']}"
        ))
    routes = query_plan.get("routes", []) if isinstance(query_plan, dict) else []
    route_ids = {item.get("route_id") for item in routes if isinstance(item, dict)}
    query_ids = {item.get("query_id") for item in routes if isinstance(item, dict)}
    coverage_requirements = topic.get("coverage_requirements") \
        if isinstance(topic.get("coverage_requirements"), list) else []
    coverage_ids = {item.get("coverage_id") for item in coverage_requirements
                    if isinstance(item, dict)}

    tool_results, tool_issues = _hydrate_tool_results(output, base=base)
    issues.extend(tool_issues)
    expected_provider_issues = [
        {
            "operation_id": result.get("operation_id"),
            "provider": result.get("provider"),
            "status": result.get("status"),
            "issues": deepcopy(result.get("issues", [])),
        }
        for result in tool_results
        if result.get("status") in {"partial", "unavailable", "failed"}
    ]
    if output.get("provider_issues") != expected_provider_issues:
        issues.append(_issue(
            "major", "provider_issues_mismatch",
            "provider_issues must exactly preserve every non-ok referenced tool result",
            "provider_issues",
        ))
    log = output.get("query_log") if isinstance(output.get("query_log"), list) else []
    operation_ids = [item.get("operation_id") for item in log
                     if isinstance(item, dict) and isinstance(item.get("operation_id"), str)]
    if _duplicates(operation_ids):
        issues.append(_issue(
            "major", "duplicate_operation_id",
            f"query log duplicates {sorted(_duplicates(operation_ids))}", "query_log",
        ))
    logged_query_ids = {item.get("query_id") for item in log if isinstance(item, dict)}
    if query_ids - logged_query_ids:
        issues.append(_issue(
            "major", "unexecuted_query_route",
            f"query plan routes lack logs for {sorted(query_ids-logged_query_ids)}", "query_log",
        ))
    for index, entry in enumerate(log):
        if not isinstance(entry, dict):
            continue
        unknown_log = _unknown_fields(
            entry,
            {"operation_id", "route_id", "query_id", "provider", "status",
             "result_count", "literature_tool_result_ref"},
        )
        if unknown_log:
            issues.append(_issue(
                "major", "unknown_query_log_fields",
                f"query log contains unsupported fields {unknown_log}", f"query_log[{index}]",
            ))
        if entry.get("route_id") not in route_ids or entry.get("query_id") not in query_ids:
            issues.append(_issue(
                "blocker", "unknown_logged_query",
                "query log references a route or query outside QueryPlan", f"query_log[{index}]",
            ))
        if entry.get("provider") not in PROVIDERS:
            issues.append(_issue(
                "blocker", "unknown_logged_provider",
                "query log provider is not supported", f"query_log[{index}].provider",
            ))

    provider_records: dict[str, list[dict]] = {}
    for result in tool_results:
        for record in result.get("records", []):
            if isinstance(record, dict) and isinstance(record.get("source_id"), str):
                provider_records.setdefault(record["source_id"], []).append(record)
    candidates = output.get("candidates") if isinstance(output.get("candidates"), list) else []
    if "doi_verifications" in output:
        for error in crossref.validate_bindings(
                candidates, output.get("doi_verifications"), base=base):
            issues.append(_issue(
                "blocker", "invalid_doi_verification", error, "doi_verifications"
            ))
    candidate_ids = [item.get("source_id") for item in candidates
                     if isinstance(item, dict) and isinstance(item.get("source_id"), str)]
    if _duplicates(candidate_ids):
        issues.append(_issue(
            "major", "duplicate_candidate_id",
            f"candidate IDs are duplicated {sorted(_duplicates(candidate_ids))}", "candidates",
        ))
    candidate_limit = topic.get("stop_rule", {}).get("candidate_limit") \
        if isinstance(topic.get("stop_rule"), dict) else None
    if isinstance(candidate_limit, int) and len(candidates) > candidate_limit:
        issues.append(_issue(
            "major", "candidate_limit_exceeded",
            f"candidate count {len(candidates)} exceeds {candidate_limit}", "candidates",
        ))
    for index, candidate in enumerate(candidates):
        location = f"candidates[{index}]"
        if not isinstance(candidate, dict):
            continue
        shape = contracts.validate(candidate, SOURCE_RECORD_CONTRACT)
        for error in shape["errors"]:
            issues.append(_issue(
                "blocker", "invalid_source_record", error, location
            ))
        source_id = candidate.get("source_id")
        if source_id not in provider_records:
            issues.append(_issue(
                "blocker", "candidate_without_provider_record",
                "candidate does not occur in referenced provider results", location,
            ))
        elif candidate not in provider_records[source_id]:
            issues.append(_issue(
                "blocker", "provider_metadata_modified",
                "candidate differs from every referenced normalized provider record", location,
            ))
        classification = candidate.get("classification") \
            if isinstance(candidate.get("classification"), dict) else {}
        if classification.get("source_roles") not in ([], None):
            issues.append(_issue(
                "major", "premature_source_role",
                "G02-A02 cannot assign final source roles", f"{location}.classification.source_roles",
            ))
        if topic.get("topic_id") not in _strings(classification.get("related_topics")):
            issues.append(_issue(
                "major", "candidate_topic_missing",
                "candidate must retain the scoped topic ID", f"{location}.classification.related_topics",
            ))

    coverage_map = output.get("coverage_map") \
        if isinstance(output.get("coverage_map"), list) else []
    mapped_sources: list[str] = []
    coverage_sources: dict[str, set[str]] = {}
    for index, mapping in enumerate(coverage_map):
        if not isinstance(mapping, dict):
            continue
        unknown_mapping = _unknown_fields(
            mapping, {"source_id", "coverage_unit_ids", "basis"}
        )
        if unknown_mapping:
            issues.append(_issue(
                "major", "unknown_coverage_mapping_fields",
                f"coverage mapping contains unsupported fields {unknown_mapping}",
                f"coverage_map[{index}]",
            ))
        source_id = mapping.get("source_id")
        if isinstance(source_id, str):
            mapped_sources.append(source_id)
        if source_id not in set(candidate_ids):
            issues.append(_issue(
                "major", "coverage_unknown_candidate",
                "coverage map references an unknown candidate", f"coverage_map[{index}].source_id",
            ))
        units = set(_strings(mapping.get("coverage_unit_ids")))
        if isinstance(source_id, str):
            for coverage_id in units:
                coverage_sources.setdefault(coverage_id, set()).add(source_id)
        if not units or units - coverage_ids:
            issues.append(_issue(
                "major", "coverage_unknown_unit",
                f"coverage map must use approved units; unknown={sorted(units-coverage_ids)}",
                f"coverage_map[{index}].coverage_unit_ids",
            ))
    if _duplicates(mapped_sources):
        issues.append(_issue(
            "minor", "duplicate_coverage_mapping",
            f"sources have repeated coverage mappings {sorted(_duplicates(mapped_sources))}",
            "coverage_map",
        ))
    remaining = set(_strings(output.get("remaining_coverage_units")))
    if remaining - coverage_ids:
        issues.append(_issue(
            "major", "unknown_remaining_coverage",
            f"remaining coverage contains unknown IDs {sorted(remaining-coverage_ids)}",
            "remaining_coverage_units",
        ))
    expected_remaining = {
        item.get("coverage_id") for item in coverage_requirements
        if isinstance(item, dict) and isinstance(item.get("coverage_id"), str)
        and len(coverage_sources.get(item["coverage_id"], set()))
        < (item.get("minimum_sources") if isinstance(item.get("minimum_sources"), int) else 1)
    }
    if remaining != expected_remaining:
        issues.append(_issue(
            "major", "remaining_coverage_mismatch",
            "remaining coverage must reflect source-count requirements; "
            f"expected={sorted(expected_remaining)}, actual={sorted(remaining)}",
            "remaining_coverage_units",
        ))
    if output.get("stop_reason") == "completed" and remaining:
        issues.append(_issue(
            "major", "completed_with_coverage_gaps",
            "completed stop reason requires no remaining coverage units", "stop_reason",
        ))
    if output.get("stop_reason") == "provider_unavailable" and candidates:
        issues.append(_issue(
            "major", "provider_unavailable_with_candidates",
            "provider_unavailable is reserved for runs without usable candidates", "stop_reason",
        ))
    if output.get("stop_reason") == "provider_unavailable" and tool_results \
            and any(result.get("status") in {"ok", "partial"} for result in tool_results):
        issues.append(_issue(
            "major", "provider_unavailable_with_usable_operation",
            "provider_unavailable requires every executed provider operation to be unavailable or failed",
            "stop_reason",
        ))
    if output.get("stop_reason") == "candidate_limit" \
            and isinstance(candidate_limit, int) and len(candidates) < candidate_limit:
        issues.append(_issue(
            "major", "candidate_limit_not_reached",
            "candidate_limit stop reason requires the topic candidate limit to be reached",
            "stop_reason",
        ))
    if output.get("stop_reason") == "partial_coverage" and not remaining \
            and not output.get("provider_issues"):
        issues.append(_issue(
            "major", "partial_coverage_without_gap",
            "partial_coverage requires remaining coverage or a provider issue", "stop_reason",
        ))
    if not remaining and not output.get("provider_issues") \
            and output.get("stop_reason") != "completed":
        issues.append(_issue(
            "minor", "noncanonical_complete_stop_reason",
            "a complete pool without provider issues must use stop_reason completed", "stop_reason",
        ))
    verification_degraded = any(
        item.get("status") != "ok" or item.get("match_status") == "conflict"
        for item in output.get("doi_verifications", []) if isinstance(item, dict)
    )
    complete = not remaining and not output.get("provider_issues") and not verification_degraded
    return {"ok": not issues, "complete": complete, "issues": issues}


def _safe_segment(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()) or "unknown"


def finalize_domain_candidates(domain_input: dict, output: object, *, base=None,
                               previous_candidates: dict | None = None,
                               revision_items: list[dict] | None = None) -> dict:
    validation = validate_domain_candidates(
        output, domain_input, base=base, previous_candidates=previous_candidates,
        revision_items=revision_items,
    )
    if not validation["ok"]:
        return _envelope(
            "failed", "DomainCandidateSources failed deterministic validation.",
            validation["issues"],
        )
    assert isinstance(output, dict)
    task = _safe_segment(output["task_id"])
    topic = _safe_segment(output["topic_id"])
    version = _safe_segment(output["artifact_version"])
    try:
        ref = artifacts.store(
            f"g02/domain-candidates/{task}.{topic}.{version}.json", output, base=base
        )
    except (OSError, TypeError, ValueError) as exc:
        return failed_envelope("domain_candidates_store_failed", str(exc), "artifact_store")
    descriptor = {
        "type": "domain_candidate_sources",
        "path": ref,
        "schema_version": DOMAIN_OUTPUT_CONTRACT,
        "artifact_version": output["artifact_version"],
    }
    status = "ok" if validation["complete"] else "degraded"
    return _envelope(
        status,
        f"Stored {len(output['candidates'])} domain candidates for {output['topic_id']}.",
        [],
        produced=[descriptor],
        metrics={
            "candidate_count": len(output["candidates"]),
            "query_operation_count": len(output["query_log"]),
            "remaining_coverage_count": len(output["remaining_coverage_units"]),
        },
        resume_token=ref if status == "degraded" else None,
    )


def build_domain_review_task(domain_input: dict, artifact_descriptor: dict, *,
                             review_id: str, attempt: int = 1,
                             previous_decision_ref: str | None = None,
                             producer_revision_response: dict | None = None) -> dict:
    checked = validate_domain_input(domain_input)
    if not checked["ok"]:
        raise ValueError("invalid domain input: " + "; ".join(
            item["message"] for item in checked["issues"]
        ))
    if not isinstance(artifact_descriptor, dict):
        raise ValueError("artifact descriptor must be an object")
    ref = artifact_descriptor.get("path") or artifact_descriptor.get("ref")
    if artifact_descriptor.get("type") != "domain_candidate_sources" \
            or artifact_descriptor.get("schema_version") != DOMAIN_OUTPUT_CONTRACT:
        raise ValueError("artifact descriptor must identify domain_candidate_sources@1")
    if not isinstance(ref, str) or not ref.startswith(artifacts.SCHEME):
        raise ValueError("artifact descriptor must contain an artifact:// path or ref")
    artifact_version = artifact_descriptor.get("artifact_version")
    if not isinstance(artifact_version, str) or not artifact_version.strip():
        raise ValueError("artifact descriptor must contain artifact_version")
    task = {
        "schema_version": "review_task@1",
        "review_id": review_id,
        "task_id": domain_input["task_id"],
        "logical_review_node": "g02-a02-domain-review",
        "producer_agent": DOMAIN_AGENT,
        "attempt": attempt,
        "review_profile": REVIEW_PROFILE,
        "original_task": {
            "objective": "Build a neutral provider-backed base pool for one approved topic.",
            "input_contract": DOMAIN_INPUT_CONTRACT,
            "output_contract": DOMAIN_OUTPUT_CONTRACT,
        },
        "producer_input": deepcopy(domain_input),
        "artifact": {
            "type": "domain_candidate_sources",
            "ref": ref,
            "schema_version": DOMAIN_OUTPUT_CONTRACT,
            "artifact_version": artifact_version,
        },
        "expected_output_contract": DOMAIN_OUTPUT_CONTRACT,
        "acceptance_criteria": deepcopy(DOMAIN_ACCEPTANCE_CRITERIA),
        "evidence_requirements": deepcopy(DOMAIN_EVIDENCE_REQUIREMENTS),
        "prohibited_behaviors": deepcopy(DOMAIN_PROHIBITED_BEHAVIORS),
        "severity_rules": deepcopy(DOMAIN_SEVERITY_RULES),
        "previous_decision_ref": previous_decision_ref,
        "producer_revision_response": producer_revision_response,
    }
    from g02 import review
    validation = review.validate_review_task(task)
    if not validation["ok"]:
        raise ValueError("invalid domain review task: " + "; ".join(
            item["message"] for item in validation["issues"]
        ))
    return task


def execute_domain(research_plan_ref: str, topic_id: str,
                   domain_executor: Callable | None, *, base=None,
                   config_path: str | Path | None = None,
                   runtime_home: str | Path | None = None,
                   previous_candidates_ref: str | None = None,
                   revision_items: list[dict] | None = None) -> dict:
    prepared = prepare_domain(
        research_plan_ref,
        topic_id,
        config_path=config_path,
        runtime_home=runtime_home,
        artifact_base=base,
        previous_candidates_ref=previous_candidates_ref,
        revision_items=revision_items,
    )
    if not prepared["ready"]:
        return prepared["envelope"]
    if domain_executor is None:
        return failed_envelope(
            "domain_executor_unavailable", "no G02-A02 host executor is configured"
        )
    try:
        output = domain_executor(
            prepared["domain_input"],
            {
                "previous_candidates": prepared["previous_candidates"],
                "previous_candidates_ref": prepared["previous_candidates_ref"],
                "revision_items": prepared["revision_items"],
            },
        )
    except Exception as exc:
        return failed_envelope("domain_executor_failed", str(exc))
    return finalize_domain_candidates(
        prepared["domain_input"], output, base=base,
        previous_candidates=prepared["previous_candidates"],
        revision_items=prepared["revision_items"],
    )
