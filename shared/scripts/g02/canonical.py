"""Deterministic boundary for G02-A03 Canonical Sources discovery."""
from __future__ import annotations

import re
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path

from core import artifacts, contracts
from g02 import crossref, provider_config, query_planning

CANONICAL_INPUT_CONTRACT = "canonical_research_input@1"
CANONICAL_OUTPUT_CONTRACT = "candidate_sources@1"
DOMAIN_OUTPUT_CONTRACT = "domain_candidate_sources@1"
RESEARCH_PLAN_CONTRACT = "research_plan@1"
SOURCE_RECORD_CONTRACT = "source_record@1"
TOOL_RESULT_CONTRACT = "literature_tool_result@1"
ENVELOPE_CONTRACT = "envelope@1"
CANONICAL_AGENT = "g02-a03-canonical-sources"
REVIEW_PROFILE = "canonical_sources"
PROVIDERS = {"openalex", "semantic_scholar", "arxiv"}
CANONICAL_ROLES = {"canonical", "foundational", "survey", "methodological", "didactic"}
RELATIONS = {"references", "cited_by", "recommendations"}

CANONICAL_ACCEPTANCE_CRITERIA = [
    {
        "criterion_id": "CS-01",
        "description": "Every candidate is an unchanged provider-backed source_record@1 with stable available identifiers and auditable operation provenance.",
        "mandatory": True,
    },
    {
        "criterion_id": "CS-02",
        "description": "Every canonical or foundational assignment states at least two observed signals or one explicit domain-authoritative basis; citation count alone is insufficient.",
        "mandatory": True,
    },
    {
        "criterion_id": "CS-03",
        "description": "Access level and library requirement exactly reflect provider metadata; unseen closed content is never summarized or used as semantic evidence.",
        "mandatory": True,
    },
    {
        "criterion_id": "CS-04",
        "description": "Citation relations retain seed, relation, distance, provider and operation ID, while citation signals remain separate from scientific quality.",
        "mandatory": True,
    },
    {
        "criterion_id": "CS-05",
        "description": "Every source maps to an approved canonical-role requirement or target coverage unit, and unresolved gaps are explicit.",
        "mandatory": True,
    },
    {
        "criterion_id": "CS-06",
        "description": "Accessible surrogates remain separate source identities and are labelled as surrogates rather than equivalents.",
        "mandatory": True,
    },
    {
        "criterion_id": "CS-07",
        "description": "Every non-empty DOI has an auditable Crossref result and identity conflicts are not treated as confirmed metadata.",
        "mandatory": True,
    },
]

CANONICAL_EVIDENCE_REQUIREMENTS = [
    {
        "requirement_id": "CS-E01",
        "description": "Each operation-log entry resolves to one literature_tool_result@1 artifact and exactly preserves its identity, status and record count.",
        "mandatory": True,
    },
    {
        "requirement_id": "CS-E02",
        "description": "Every candidate exactly matches either a reviewed DomainCandidateSources record or a normalized record returned by a referenced canonical operation.",
        "mandatory": True,
    },
    {
        "requirement_id": "CS-E03",
        "description": "Every role, canonicality and coverage annotation cites an observed metadata, abstract, citation-relation or domain-authority basis.",
        "mandatory": True,
    },
]

CANONICAL_PROHIBITED_BEHAVIORS = [
    "Declaring a source canonical solely from citation count, venue prestige or graph centrality.",
    "Modifying provider bibliographic metadata or inventing missing identifiers, access or content.",
    "Attributing arguments to metadata-only or otherwise unseen closed content.",
    "Traversing beyond one authorized citation hop or outside approved topic and provider limits.",
    "Retrieving documents, ranking the combined pool, verifying claims or exposing credentials.",
]

CANONICAL_SEVERITY_RULES = {
    "minor": "A local wording, confidence or surrogate-label defect that does not alter identity or evidence.",
    "major": "Missing role basis, operation provenance, coverage mapping, access statement or bounded search route.",
    "blocker": "Fabricated metadata or content, unapproved scope, modified provider record, invalid citation relation or unreadable evidence artifact.",
}


def _issue(severity: str, issue_type: str, message: str, location: str) -> dict:
    return {"severity": severity, "type": issue_type, "message": message, "location": location}


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
        raise ValueError("invalid canonical envelope: " + "; ".join(checked["errors"]))
    return payload


def failed_envelope(issue_type: str, message: str, location: str = "canonical") -> dict:
    return _envelope(
        "failed", "G02-A03 Canonical Sources did not produce candidate sources.",
        [_issue("blocker", issue_type, message, location)],
    )


def needs_input_envelope(issue_type: str, message: str, location: str) -> dict:
    return _envelope(
        "needs_input", "Canonical discovery is missing an approved upstream artifact.",
        [_issue("blocker", issue_type, message, location)],
    )


def _provider_resolvable(record: dict) -> bool:
    identifiers = record.get("identifiers") if isinstance(record.get("identifiers"), dict) else {}
    return any(isinstance(identifiers.get(field), str) and identifiers[field].strip()
               for field in ("openalex_id", "semantic_scholar_id", "doi", "arxiv_id"))


def _derive_canonical_scope(topic: dict, records: list[dict]) -> dict:
    verified = [record["source_id"] for record in records
                if isinstance(record, dict) and isinstance(record.get("source_id"), str)
                and _provider_resolvable(record)]
    plan_seeds = _strings(topic.get("search_strategy", {}).get("seed_sources"))
    unresolved = [value for value in plan_seeds if value not in set(verified)]
    role_flags = topic.get("source_roles_required") \
        if isinstance(topic.get("source_roles_required"), dict) else {}
    roles = [role for role in ("canonical", "survey", "didactic")
             if role_flags.get(role) is True]
    if "canonical" in roles:
        roles.insert(1, "foundational")
        roles.append("methodological")
    roles = list(dict.fromkeys(roles or ["canonical", "foundational"]))
    coverage = topic.get("coverage_requirements") \
        if isinstance(topic.get("coverage_requirements"), list) else []
    target = [
        item["coverage_id"] for item in coverage if isinstance(item, dict)
        and isinstance(item.get("coverage_id"), str)
        and (set(_strings(item.get("source_roles"))) & set(roles)
             or item.get("mandatory") is True)
    ]
    candidate_limit = topic.get("stop_rule", {}).get("candidate_limit")
    if not isinstance(candidate_limit, int) or isinstance(candidate_limit, bool):
        candidate_limit = 20
    return {
        "verified_seed_ids": verified,
        "unresolved_plan_seed_ids": unresolved,
        "required_roles": roles,
        "target_coverage_units": list(dict.fromkeys(target)),
        "search_limits": {
            "candidate_limit": candidate_limit,
            "citation_depth": 1,
            "per_seed_relation_limit": min(10, candidate_limit),
            "allowed_relations": ["references", "cited_by", "recommendations"],
        },
    }


def validate_canonical_input(canonical_input: object) -> dict:
    issues = _shape_issues(
        canonical_input, CANONICAL_INPUT_CONTRACT, "invalid_canonical_input_contract"
    )
    if not isinstance(canonical_input, dict):
        return {"ok": False, "issues": issues}
    allowed = {
        "schema_version", "task_id", "research_plan_ref", "research_plan_artifact_version",
        "domain_candidates_ref", "domain_candidates_artifact_version", "topic",
        "domain_candidates", "verified_seed_ids", "unresolved_plan_seed_ids",
        "required_roles", "target_coverage_units", "search_limits",
        "provider_capabilities", "output_language",
    }
    unknown = _unknown_fields(canonical_input, allowed)
    if unknown:
        issues.append(_issue(
            "blocker", "unknown_canonical_input_fields",
            f"canonical input contains unsupported fields {unknown}", "canonical_input",
        ))
    for field in (
        "task_id", "research_plan_ref", "research_plan_artifact_version",
        "domain_candidates_ref", "domain_candidates_artifact_version", "output_language",
    ):
        value = canonical_input.get(field)
        if not isinstance(value, str) or not value.strip():
            issues.append(_issue(
                "blocker", "empty_canonical_input_field", f"{field} must not be empty", field
            ))
    for field in ("research_plan_ref", "domain_candidates_ref"):
        value = canonical_input.get(field)
        if isinstance(value, str) and not value.startswith(artifacts.SCHEME):
            issues.append(_issue(
                "blocker", "invalid_canonical_artifact_ref",
                f"{field} must use artifact://", field,
            ))
    topic = canonical_input.get("topic") if isinstance(canonical_input.get("topic"), dict) else {}
    coverage = topic.get("coverage_requirements") \
        if isinstance(topic.get("coverage_requirements"), list) else []
    coverage_ids = {item.get("coverage_id") for item in coverage
                    if isinstance(item, dict) and isinstance(item.get("coverage_id"), str)}
    target = _strings(canonical_input.get("target_coverage_units"))
    if not target or set(target) - coverage_ids or _duplicates(target):
        issues.append(_issue(
            "blocker", "invalid_canonical_target_coverage",
            f"target coverage must be non-empty, unique and approved; unknown={sorted(set(target)-coverage_ids)}",
            "target_coverage_units",
        ))
    roles = _strings(canonical_input.get("required_roles"))
    if not roles or set(roles) - CANONICAL_ROLES or _duplicates(roles):
        issues.append(_issue(
            "blocker", "invalid_canonical_required_roles",
            "required_roles must be non-empty, unique and canonical-role scoped",
            "required_roles",
        ))
    records = canonical_input.get("domain_candidates") \
        if isinstance(canonical_input.get("domain_candidates"), list) else []
    record_ids: list[str] = []
    record_map: dict[str, dict] = {}
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        checked = contracts.validate(record, SOURCE_RECORD_CONTRACT)
        for error in checked["errors"]:
            issues.append(_issue(
                "blocker", "invalid_domain_seed_record", error,
                f"domain_candidates[{index}]",
            ))
        source_id = record.get("source_id")
        if isinstance(source_id, str):
            record_ids.append(source_id)
            record_map[source_id] = record
    if _duplicates(record_ids):
        issues.append(_issue(
            "blocker", "duplicate_domain_seed_record",
            f"domain candidates duplicate IDs {sorted(_duplicates(record_ids))}",
            "domain_candidates",
        ))
    verified = _strings(canonical_input.get("verified_seed_ids"))
    if _duplicates(verified) or not set(verified) <= set(record_ids):
        issues.append(_issue(
            "blocker", "invalid_verified_seed_ids",
            "verified seeds must be unique members of the reviewed domain pool",
            "verified_seed_ids",
        ))
    for source_id in verified:
        if source_id in record_map and not _provider_resolvable(record_map[source_id]):
            issues.append(_issue(
                "blocker", "unresolvable_verified_seed",
                f"verified seed {source_id!r} has no provider-resolvable identifier",
                "verified_seed_ids",
            ))
    unresolved = _strings(canonical_input.get("unresolved_plan_seed_ids"))
    if _duplicates(unresolved) or set(unresolved) & set(verified):
        issues.append(_issue(
            "blocker", "invalid_unresolved_seed_ids",
            "unresolved plan seeds must be unique and separate from verified seeds",
            "unresolved_plan_seed_ids",
        ))
    limits = canonical_input.get("search_limits") \
        if isinstance(canonical_input.get("search_limits"), dict) else {}
    if limits.get("citation_depth") != 1:
        issues.append(_issue(
            "blocker", "invalid_citation_depth", "A03 citation depth must be exactly one",
            "search_limits.citation_depth",
        ))
    for field in ("candidate_limit", "per_seed_relation_limit"):
        value = limits.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            issues.append(_issue(
                "blocker", "invalid_canonical_search_limit",
                f"{field} must be a positive integer", f"search_limits.{field}",
            ))
    relations = _strings(limits.get("allowed_relations"))
    if not relations or set(relations) - RELATIONS or _duplicates(relations):
        issues.append(_issue(
            "blocker", "invalid_citation_relations",
            "allowed_relations must be non-empty, unique and supported",
            "search_limits.allowed_relations",
        ))
    capabilities = canonical_input.get("provider_capabilities") \
        if isinstance(canonical_input.get("provider_capabilities"), list) else []
    provider_names = [item.get("provider") for item in capabilities
                      if isinstance(item, dict) and isinstance(item.get("provider"), str)]
    if _duplicates(provider_names):
        issues.append(_issue(
            "blocker", "duplicate_provider_capability",
            f"duplicate providers {sorted(_duplicates(provider_names))}",
            "provider_capabilities",
        ))
    if not any(isinstance(item, dict) and item.get("enabled") is True
               and item.get("ready") is True for item in capabilities):
        issues.append(_issue(
            "blocker", "no_ready_provider",
            "at least one scholarly provider must be ready", "provider_capabilities",
        ))
    return {"ok": not issues, "issues": issues}


def validate_canonical_basis(canonical_input: object, *, base=None) -> dict:
    """Verify that a scoped input is the exact deterministic projection of its A01/A02 refs."""
    checked = validate_canonical_input(canonical_input)
    issues = list(checked["issues"])
    if not isinstance(canonical_input, dict):
        return {"ok": False, "issues": issues}
    try:
        plan = artifacts.hydrate(canonical_input["research_plan_ref"], base=base)
        domain_pool = artifacts.hydrate(canonical_input["domain_candidates_ref"], base=base)
        for payload, contract_ref in (
            (plan, RESEARCH_PLAN_CONTRACT),
            (domain_pool, DOMAIN_OUTPUT_CONTRACT),
        ):
            shape = contracts.validate(payload, contract_ref)
            if not shape["ok"]:
                raise ValueError("; ".join(shape["errors"]))
    except (OSError, ValueError, KeyError, IndexError) as exc:
        issues.append(_issue(
            "blocker", "unreadable_canonical_basis", str(exc), "canonical_input",
        ))
        return {"ok": False, "issues": issues}
    topic = canonical_input.get("topic") if isinstance(canonical_input.get("topic"), dict) else {}
    topic_id = topic.get("topic_id")
    topics = [item for item in plan.get("topics", [])
              if isinstance(item, dict) and item.get("topic_id") == topic_id]
    if len(topics) != 1 or topics[0] != topic:
        issues.append(_issue(
            "blocker", "canonical_topic_basis_mismatch",
            "scoped topic differs from the approved ResearchPlan", "topic",
        ))
    expected_identity = {
        "task_id": plan.get("task_id"),
        "research_plan_artifact_version": plan.get("artifact_version"),
        "domain_candidates_artifact_version": domain_pool.get("artifact_version"),
        "output_language": plan.get("output_language"),
    }
    for field, expected in expected_identity.items():
        if canonical_input.get(field) != expected:
            issues.append(_issue(
                "blocker", "canonical_basis_identity_mismatch",
                f"{field} differs from approved upstream artifacts", field,
            ))
    if domain_pool.get("task_id") != plan.get("task_id") \
            or domain_pool.get("topic_id") != topic_id \
            or domain_pool.get("research_plan_ref") != canonical_input.get("research_plan_ref"):
        issues.append(_issue(
            "blocker", "canonical_domain_basis_mismatch",
            "DomainCandidateSources does not match the approved plan and topic",
            "domain_candidates_ref",
        ))
    records = domain_pool.get("candidates") if isinstance(domain_pool.get("candidates"), list) else []
    if canonical_input.get("domain_candidates") != records:
        issues.append(_issue(
            "blocker", "canonical_domain_records_modified",
            "scoped domain candidates differ from the reviewed upstream artifact",
            "domain_candidates",
        ))
    expected_scope = _derive_canonical_scope(topic, records)
    for field, expected in expected_scope.items():
        if canonical_input.get(field) != expected:
            issues.append(_issue(
                "blocker", "canonical_scope_projection_mismatch",
                f"{field} differs from the deterministic A03 projection", field,
            ))
    return {"ok": not issues, "issues": issues}


def prepare_canonical(research_plan_ref: str, domain_candidates_ref: str, topic_id: str, *,
                      config_path: str | Path | None = None,
                      runtime_home: str | Path | None = None, artifact_base=None,
                      previous_candidates_ref: str | None = None,
                      revision_items: list[dict] | None = None) -> dict:
    """Hydrate reviewed A01/A02 artifacts and expose only A03-authorized context."""
    for value, field in (
        (research_plan_ref, "research_plan_ref"),
        (domain_candidates_ref, "domain_candidates_ref"),
    ):
        if not isinstance(value, str) or not value.startswith(artifacts.SCHEME):
            return {"ready": False, "envelope": needs_input_envelope(
                "invalid_upstream_ref", f"{field} must use artifact://", field,
            )}
    if not isinstance(topic_id, str) or not topic_id.strip():
        return {"ready": False, "envelope": needs_input_envelope(
            "missing_topic_id", "a non-empty approved topic_id is required", "topic_id",
        )}
    try:
        plan = artifacts.hydrate(research_plan_ref, base=artifact_base)
        domain_pool = artifacts.hydrate(domain_candidates_ref, base=artifact_base)
        for payload, contract_ref in (
            (plan, RESEARCH_PLAN_CONTRACT),
            (domain_pool, DOMAIN_OUTPUT_CONTRACT),
        ):
            checked = contracts.validate(payload, contract_ref)
            if not checked["ok"]:
                raise ValueError("; ".join(checked["errors"]))
    except (OSError, ValueError, KeyError, IndexError) as exc:
        return {"ready": False, "envelope": failed_envelope(
            "invalid_canonical_upstream", str(exc), "upstream_refs",
        )}
    topics = [item for item in plan.get("topics", [])
              if isinstance(item, dict) and item.get("topic_id") == topic_id]
    if len(topics) != 1:
        return {"ready": False, "envelope": needs_input_envelope(
            "unknown_or_duplicate_topic",
            f"expected exactly one topic {topic_id!r}, found {len(topics)}", "topic_id",
        )}
    if domain_pool.get("task_id") != plan.get("task_id") \
            or domain_pool.get("topic_id") != topic_id \
            or domain_pool.get("research_plan_ref") != research_plan_ref:
        return {"ready": False, "envelope": failed_envelope(
            "canonical_upstream_identity_mismatch",
            "DomainCandidateSources does not match the approved plan and topic",
            "domain_candidates_ref",
        )}
    try:
        config = provider_config.load_config(
            config_path, runtime_home=runtime_home, create_dirs=True
        )
    except provider_config.ProviderConfigError as exc:
        return {"ready": False, "envelope": failed_envelope(
            "provider_configuration_error", str(exc), "provider_config",
        )}
    topic = deepcopy(topics[0])
    records = deepcopy(domain_pool.get("candidates", []))
    scope = _derive_canonical_scope(topic, records)
    canonical_input = {
        "schema_version": CANONICAL_INPUT_CONTRACT,
        "task_id": plan["task_id"],
        "research_plan_ref": research_plan_ref,
        "research_plan_artifact_version": plan["artifact_version"],
        "domain_candidates_ref": domain_candidates_ref,
        "domain_candidates_artifact_version": domain_pool["artifact_version"],
        "topic": topic,
        "domain_candidates": records,
        **scope,
        "provider_capabilities": config.public_status()["capabilities"],
        "output_language": plan["output_language"],
    }
    checked = validate_canonical_input(canonical_input)
    if not checked["ok"]:
        return {"ready": False, "envelope": failed_envelope(
            "invalid_scoped_canonical_input",
            "; ".join(item["message"] for item in checked["issues"]),
            "canonical_input",
        )}
    previous = None
    if previous_candidates_ref is not None:
        try:
            if not isinstance(previous_candidates_ref, str) \
                    or not previous_candidates_ref.startswith(artifacts.SCHEME):
                raise ValueError("previous_candidates_ref must use artifact://")
            previous = artifacts.hydrate(previous_candidates_ref, base=artifact_base)
            shape = contracts.validate(previous, CANONICAL_OUTPUT_CONTRACT)
            if not shape["ok"]:
                raise ValueError("; ".join(shape["errors"]))
            if previous.get("stream") != "canonical" \
                    or previous.get("task_id") != plan["task_id"] \
                    or previous.get("topic_id") != topic_id:
                raise ValueError("previous canonical candidates do not match task and topic")
        except (OSError, ValueError, KeyError, IndexError) as exc:
            return {"ready": False, "envelope": failed_envelope(
                "invalid_previous_canonical_candidates", str(exc),
                "previous_candidates_ref",
            )}
    if revision_items and previous is None:
        return {"ready": False, "envelope": failed_envelope(
            "missing_previous_canonical_candidates",
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
        "canonical_input": canonical_input,
        "config_status": config.public_status(),
        "previous_candidates": previous,
        "previous_candidates_ref": previous_candidates_ref,
        "revision_items": deepcopy(revision_items or []),
    }


def _revision_fields(revision_items: list[dict] | None) -> set[str]:
    mutable = {
        "query_plan", "candidates", "doi_verifications", "canonical_annotations", "operation_log",
        "coverage_map", "remaining_coverage_units", "provider_issues",
        "unresolved_seed_ids", "stop_reason",
    }
    targeted: set[str] = set()
    for item in revision_items or []:
        location = item.get("location") if isinstance(item, dict) else None
        if isinstance(location, str):
            targeted.update(field for field in mutable
                            if re.search(rf"(?:^|\.){re.escape(field)}(?:\.|\[|$)", location))
    order = [
        "query_plan", "operation_log", "candidates", "canonical_annotations",
        "coverage_map", "provider_issues", "remaining_coverage_units",
        "unresolved_seed_ids", "stop_reason",
    ]
    expanded = set(targeted)
    for field in targeted:
        if field in order:
            expanded.update(order[order.index(field):])
    return expanded


def _hydrate_operations(output: dict, *, base=None) -> tuple[list[dict], list[dict]]:
    issues: list[dict] = []
    results: list[dict] = []
    for index, entry in enumerate(output.get("operation_log", [])):
        if not isinstance(entry, dict):
            continue
        location = f"operation_log[{index}]"
        ref = entry.get("literature_tool_result_ref")
        if not isinstance(ref, str) or not ref.startswith(artifacts.SCHEME):
            issues.append(_issue(
                "blocker", "invalid_tool_result_ref",
                "operation log result ref must use artifact://",
                f"{location}.literature_tool_result_ref",
            ))
            continue
        try:
            result = artifacts.hydrate(ref, base=base)
            checked = contracts.validate(result, TOOL_RESULT_CONTRACT)
            if not checked["ok"]:
                raise ValueError("; ".join(checked["errors"]))
        except (OSError, ValueError, KeyError, IndexError) as exc:
            issues.append(_issue(
                "blocker", "unreadable_tool_result", str(exc),
                f"{location}.literature_tool_result_ref",
            ))
            continue
        expected = {
            "operation_id": result.get("operation_id"),
            "operation_type": result.get("operation_type"),
            "provider": result.get("provider"),
            "status": result.get("status"),
            "result_count": len(result.get("records", [])),
        }
        request = result.get("request") if isinstance(result.get("request"), dict) else {}
        if result.get("operation_type") == "metadata_search":
            expected.update({"route_id": request.get("route_id"),
                             "query_id": request.get("query_id")})
        elif result.get("operation_type") == "citation_expand":
            expected.update({"seed_source_id": request.get("seed_source_id"),
                             "relation": request.get("relation")})
        for field, value in expected.items():
            if entry.get(field) != value:
                issues.append(_issue(
                    "blocker", "operation_log_mismatch",
                    f"{field} does not match referenced tool result", f"{location}.{field}",
                ))
        results.append(result)
    return results, issues


def validate_canonical_candidates(output: object, canonical_input: dict, *, base=None,
                                  previous_candidates: dict | None = None,
                                  revision_items: list[dict] | None = None) -> dict:
    issues = _shape_issues(
        output, CANONICAL_OUTPUT_CONTRACT, "invalid_canonical_candidates_contract"
    )
    input_checked = validate_canonical_basis(canonical_input, base=base)
    if not input_checked["ok"]:
        issues.extend(input_checked["issues"])
    if not isinstance(output, dict):
        return {"ok": False, "complete": False, "issues": issues}
    allowed_root = {
        "schema_version", "artifact_version", "stream", "task_id", "topic_id",
        "research_plan_ref", "upstream_refs", "query_plan", "candidates", "doi_verifications",
        "canonical_annotations", "operation_log", "coverage_map",
        "remaining_coverage_units", "provider_issues", "unresolved_seed_ids",
        "stop_reason", "review_profile_ref",
    }
    unknown = _unknown_fields(output, allowed_root)
    if unknown:
        issues.append(_issue(
            "major", "unknown_canonical_output_fields",
            f"canonical output contains unsupported fields {unknown}", "canonical_output",
        ))
    if not isinstance(output.get("canonical_annotations"), list):
        issues.append(_issue(
            "blocker", "missing_canonical_annotations",
            "canonical_annotations must be an array", "canonical_annotations",
        ))
    topic = canonical_input.get("topic") if isinstance(canonical_input.get("topic"), dict) else {}
    for field, expected in (
        ("stream", "canonical"),
        ("task_id", canonical_input.get("task_id")),
        ("topic_id", topic.get("topic_id")),
        ("research_plan_ref", canonical_input.get("research_plan_ref")),
        ("review_profile_ref", REVIEW_PROFILE),
    ):
        if output.get(field) != expected:
            issues.append(_issue(
                "blocker", "canonical_output_identity_mismatch",
                f"{field} must equal {expected!r}", field,
            ))
    upstream = output.get("upstream_refs") \
        if isinstance(output.get("upstream_refs"), dict) else {}
    if upstream != {"domain_candidate_sources": canonical_input.get("domain_candidates_ref")}:
        issues.append(_issue(
            "blocker", "canonical_upstream_ref_mismatch",
            "upstream_refs must contain exactly the reviewed DomainCandidateSources ref",
            "upstream_refs",
        ))
    version = output.get("artifact_version")
    if not isinstance(version, str) or not version.strip():
        issues.append(_issue(
            "major", "empty_artifact_version", "artifact_version must not be empty",
            "artifact_version",
        ))
    if previous_candidates is not None and version == previous_candidates.get("artifact_version"):
        issues.append(_issue(
            "major", "artifact_version_not_advanced",
            "a revised canonical artifact must advance artifact_version", "artifact_version",
        ))
    if previous_candidates is not None:
        targeted = _revision_fields(revision_items)
        if targeted:
            for field in output:
                if field != "artifact_version" and field not in targeted \
                        and output.get(field) != previous_candidates.get(field):
                    issues.append(_issue(
                        "major", "unscoped_revision_change",
                        f"untargeted field {field!r} changed during scoped revision", field,
                    ))

    query_plan = output.get("query_plan")
    query_checked = query_planning.validate_query_plan(query_plan, canonical_input)
    for item in query_checked["issues"]:
        issues.append(_issue(
            "major", item["code"], item["message"], f"query_plan.{item['location']}",
        ))
    routes = query_plan.get("routes", []) if isinstance(query_plan, dict) else []
    route_ids = {item.get("route_id") for item in routes if isinstance(item, dict)}
    route_map = {item.get("route_id"): item for item in routes if isinstance(item, dict)}

    tool_results, tool_issues = _hydrate_operations(output, base=base)
    issues.extend(tool_issues)
    result_by_operation = {result.get("operation_id"): result for result in tool_results}
    expected_operation_scope = {
        "input_contract": CANONICAL_INPUT_CONTRACT,
        "task_id": canonical_input.get("task_id"),
        "topic_id": topic.get("topic_id"),
        "research_plan_ref": canonical_input.get("research_plan_ref"),
        "domain_candidates_ref": canonical_input.get("domain_candidates_ref"),
    }
    for index, result in enumerate(tool_results):
        request = result.get("request") if isinstance(result.get("request"), dict) else {}
        if request.get("scope") != expected_operation_scope:
            issues.append(_issue(
                "blocker", "canonical_operation_scope_mismatch",
                "referenced tool result was not executed for this exact A03 scope",
                f"operation_log[{index}].literature_tool_result_ref",
            ))
    expected_provider_issues = [{
        "operation_id": result.get("operation_id"),
        "provider": result.get("provider"),
        "status": result.get("status"),
        "issues": deepcopy(result.get("issues", [])),
    } for result in tool_results if result.get("status") in {"partial", "unavailable", "failed"}]
    if output.get("provider_issues") != expected_provider_issues:
        issues.append(_issue(
            "major", "provider_issues_mismatch",
            "provider_issues must exactly preserve every non-ok operation",
            "provider_issues",
        ))
    log = output.get("operation_log") if isinstance(output.get("operation_log"), list) else []
    operation_ids = [item.get("operation_id") for item in log
                     if isinstance(item, dict) and isinstance(item.get("operation_id"), str)]
    if _duplicates(operation_ids):
        issues.append(_issue(
            "major", "duplicate_operation_id",
            f"operation log duplicates {sorted(_duplicates(operation_ids))}", "operation_log",
        ))
    logged_routes = {item.get("route_id") for item in log if isinstance(item, dict)
                     and item.get("operation_type") == "metadata_search"}
    if route_ids - logged_routes:
        issues.append(_issue(
            "major", "unexecuted_canonical_query_route",
            f"query plan routes lack metadata operations for {sorted(route_ids-logged_routes)}",
            "operation_log",
        ))
    for index, entry in enumerate(log):
        if not isinstance(entry, dict):
            continue
        operation_type = entry.get("operation_type")
        allowed_log_fields = {
            "operation_id", "operation_type", "provider", "status", "result_count",
            "literature_tool_result_ref",
        } | ({"route_id", "query_id"} if operation_type == "metadata_search"
             else {"seed_source_id", "relation"})
        unknown_log = _unknown_fields(entry, allowed_log_fields)
        if unknown_log:
            issues.append(_issue(
                "major", "unknown_operation_log_fields",
                f"operation log contains unsupported fields {unknown_log}",
                f"operation_log[{index}]",
            ))
        result = result_by_operation.get(entry.get("operation_id"), {})
        request = result.get("request") if isinstance(result.get("request"), dict) else {}
        if operation_type == "metadata_search":
            route = route_map.get(entry.get("route_id"))
            if not isinstance(route, dict) or entry.get("query_id") != route.get("query_id"):
                issues.append(_issue(
                    "blocker", "unknown_logged_canonical_query",
                    "metadata operation references a route/query outside QueryPlan",
                    f"operation_log[{index}]",
                ))
            elif request.get("canonical_query") != route.get("canonical_query") \
                    or request.get("filters") != route.get("filters") \
                    or not isinstance(request.get("limit"), int) \
                    or request.get("limit") > route.get("limit", 0) \
                    or entry.get("provider") not in route.get("preferred_providers", []):
                issues.append(_issue(
                    "blocker", "metadata_operation_scope_mismatch",
                    "metadata operation must exactly follow its authorized route and provider",
                    f"operation_log[{index}]",
                ))
        elif operation_type == "citation_expand":
            limit = request.get("limit")
            per_seed_limit = canonical_input.get("search_limits", {}).get(
                "per_seed_relation_limit"
            )
            if entry.get("seed_source_id") not in canonical_input.get("verified_seed_ids", []) \
                    or entry.get("relation") not in canonical_input.get(
                        "search_limits", {}
                    ).get("allowed_relations", []) \
                    or request.get("depth") != 1 \
                    or not isinstance(limit, int) \
                    or not isinstance(per_seed_limit, int) \
                    or limit < 1 or limit > per_seed_limit:
                issues.append(_issue(
                    "blocker", "citation_operation_scope_mismatch",
                    "citation operation exceeds its verified seed, relation, depth or limit scope",
                    f"operation_log[{index}]",
                ))
    result_records: dict[str, list[dict]] = {}
    for record in canonical_input.get("domain_candidates", []):
        if isinstance(record, dict) and isinstance(record.get("source_id"), str):
            result_records.setdefault(record["source_id"], []).append(record)
    for result in tool_results:
        for record in result.get("records", []):
            if isinstance(record, dict) and isinstance(record.get("source_id"), str):
                result_records.setdefault(record["source_id"], []).append(record)

    candidates = output.get("candidates") if isinstance(output.get("candidates"), list) else []
    if "doi_verifications" in output:
        for error in crossref.validate_bindings(
                candidates, output.get("doi_verifications"), base=base):
            issues.append(_issue(
                "blocker", "invalid_doi_verification", error, "doi_verifications"
            ))
    candidate_ids = [item.get("source_id") for item in candidates
                     if isinstance(item, dict) and isinstance(item.get("source_id"), str)]
    candidate_map = {item.get("source_id"): item for item in candidates if isinstance(item, dict)}
    if _duplicates(candidate_ids):
        issues.append(_issue(
            "major", "duplicate_candidate_id",
            f"candidate IDs are duplicated {sorted(_duplicates(candidate_ids))}", "candidates",
        ))
    candidate_limit = canonical_input.get("search_limits", {}).get("candidate_limit")
    if isinstance(candidate_limit, int) and len(candidates) > candidate_limit:
        issues.append(_issue(
            "major", "candidate_limit_exceeded",
            f"candidate count {len(candidates)} exceeds {candidate_limit}", "candidates",
        ))
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            continue
        location = f"candidates[{index}]"
        checked = contracts.validate(candidate, SOURCE_RECORD_CONTRACT)
        for error in checked["errors"]:
            issues.append(_issue("blocker", "invalid_source_record", error, location))
        source_id = candidate.get("source_id")
        if source_id not in result_records:
            issues.append(_issue(
                "blocker", "candidate_without_provider_record",
                "candidate does not occur in reviewed domain or referenced provider results",
                location,
            ))
        elif candidate not in result_records[source_id]:
            issues.append(_issue(
                "blocker", "provider_metadata_modified",
                "candidate differs from every authorized normalized provider record", location,
            ))

    annotations = output.get("canonical_annotations") \
        if isinstance(output.get("canonical_annotations"), list) else []
    annotation_ids = [item.get("source_id") for item in annotations
                      if isinstance(item, dict) and isinstance(item.get("source_id"), str)]
    if _duplicates(annotation_ids) or set(annotation_ids) != set(candidate_ids):
        issues.append(_issue(
            "major", "canonical_annotation_coverage_mismatch",
            "every candidate requires exactly one canonical annotation",
            "canonical_annotations",
        ))
    target_coverage = set(_strings(canonical_input.get("target_coverage_units")))
    required_roles = set(_strings(canonical_input.get("required_roles")))
    operation_id_set = set(operation_ids)
    verified_seed_ids = set(_strings(canonical_input.get("verified_seed_ids")))
    citation_operations_by_source: dict[str, set[str]] = {}
    for result in tool_results:
        if result.get("operation_type") != "citation_expand":
            continue
        operation_id = result.get("operation_id")
        for returned in result.get("records", []):
            source_id = returned.get("source_id") if isinstance(returned, dict) else None
            if isinstance(source_id, str) and isinstance(operation_id, str):
                citation_operations_by_source.setdefault(source_id, set()).add(operation_id)
    annotation_coverage: dict[str, set[str]] = {}
    for index, annotation in enumerate(annotations):
        if not isinstance(annotation, dict):
            continue
        location = f"canonical_annotations[{index}]"
        source_id = annotation.get("source_id")
        record = candidate_map.get(source_id, {})
        assignments = annotation.get("role_assignments") \
            if isinstance(annotation.get("role_assignments"), list) else []
        assigned_roles = {item.get("role") for item in assignments if isinstance(item, dict)}
        if not assignments or not (assigned_roles & required_roles):
            issues.append(_issue(
                "major", "missing_required_canonical_role",
                "candidate needs at least one required canonical role assignment",
                f"{location}.role_assignments",
            ))
        for assignment_index, assignment in enumerate(assignments):
            if not isinstance(assignment, dict):
                continue
            if not _strings(assignment.get("observed_signals")):
                issues.append(_issue(
                    "major", "role_without_observed_signal",
                    "role assignment requires observed signals",
                    f"{location}.role_assignments[{assignment_index}]",
                ))
            if topic.get("topic_id") not in _strings(assignment.get("topic_ids")):
                issues.append(_issue(
                    "major", "role_topic_mismatch",
                    "role assignment must map to the scoped topic",
                    f"{location}.role_assignments[{assignment_index}].topic_ids",
                ))
            assignment_coverage = set(_strings(assignment.get("coverage_unit_ids")))
            if not assignment_coverage or assignment_coverage - target_coverage:
                issues.append(_issue(
                    "major", "canonical_role_coverage_mismatch",
                    "role coverage must be non-empty and target-scoped",
                    f"{location}.role_assignments[{assignment_index}].coverage_unit_ids",
                ))
            access_order = {
                "metadata": 0, "metadata_only": 0, "abstract": 1,
                "table_of_contents": 2, "preview": 3, "partial_text": 4,
                "full_text": 5,
            }
            record_access = record.get("access") if isinstance(record.get("access"), dict) else {}
            if access_order.get(assignment.get("access_basis"), 99) \
                    > access_order.get(record_access.get("access_level"), -1):
                issues.append(_issue(
                    "blocker", "role_access_basis_exceeds_record",
                    "role assignment uses evidence richer than the provider-backed access level",
                    f"{location}.role_assignments[{assignment_index}].access_basis",
                ))
        basis = annotation.get("canonicality_basis") \
            if isinstance(annotation.get("canonicality_basis"), list) else []
        approved_seed_sources = set(
            _strings(topic.get("search_strategy", {}).get("seed_sources"))
        )
        authoritative = any(
            isinstance(item, dict)
            and item.get("signal_type") == "domain_authoritative"
            and item.get("evidence_source") == "domain_authority"
            and source_id in approved_seed_sources
            for item in basis
        )
        if len(basis) < 2 and not authoritative:
            issues.append(_issue(
                "major", "insufficient_canonicality_basis",
                "canonicality requires two observed signals or one domain-authoritative basis",
                f"{location}.canonicality_basis",
            ))
        if any(isinstance(item, dict) and item.get("signal_type") == "citation_count"
               for item in basis):
            signals = record.get("signals") if isinstance(record.get("signals"), dict) else {}
            cited_by_count = signals.get("cited_by_count")
            cited_values = [str(item.get("observed_value", "")) for item in basis
                            if isinstance(item, dict)
                            and item.get("signal_type") == "citation_count"]
            if cited_by_count is None or not all(
                    re.search(rf"(?<!\d){re.escape(str(cited_by_count))}(?!\d)", value)
                    for value in cited_values):
                issues.append(_issue(
                    "blocker", "unobserved_citation_count",
                    "citation_count basis must state the exact provider-observed cited_by_count",
                    f"{location}.canonicality_basis",
                ))
        relations = annotation.get("citation_relations") \
            if isinstance(annotation.get("citation_relations"), list) else []
        for relation_index, relation in enumerate(relations):
            if not isinstance(relation, dict):
                continue
            op_id = relation.get("operation_id")
            result = result_by_operation.get(op_id, {})
            request = result.get("request") if isinstance(result.get("request"), dict) else {}
            if relation.get("distance") != 1 \
                    or relation.get("seed_source_id") not in verified_seed_ids \
                    or op_id not in operation_id_set \
                    or result.get("operation_type") != "citation_expand" \
                    or relation.get("seed_source_id") != request.get("seed_source_id") \
                    or relation.get("relation") != request.get("relation") \
                    or relation.get("provider") != result.get("provider") \
                    or source_id not in {
                        item.get("source_id") for item in result.get("records", [])
                        if isinstance(item, dict)
                    }:
                issues.append(_issue(
                    "blocker", "invalid_citation_relation_provenance",
                    "citation relation must match one authorized one-hop expansion operation",
                    f"{location}.citation_relations[{relation_index}]",
                ))
        actual_relation_operations = {
            item.get("operation_id") for item in relations if isinstance(item, dict)
        }
        expected_relation_operations = citation_operations_by_source.get(source_id, set())
        if expected_relation_operations - actual_relation_operations:
            issues.append(_issue(
                "major", "missing_candidate_citation_provenance",
                "candidate must retain every logged citation operation that returned it",
                f"{location}.citation_relations",
            ))
        content = record.get("content_available") \
            if isinstance(record.get("content_available"), dict) else {}
        for basis_index, item in enumerate(basis):
            if not isinstance(item, dict):
                continue
            evidence_source = item.get("evidence_source")
            signal_type = item.get("signal_type")
            unsupported = (
                evidence_source == "abstract" and not (
                    isinstance(content.get("abstract"), str) and content["abstract"].strip()
                )
            ) or (
                evidence_source == "table_of_contents"
                and content.get("table_of_contents_available") is not True
            ) or (
                (evidence_source == "citation_relation" or signal_type == "citation_relation")
                and not relations
            ) or (
                (evidence_source == "domain_authority"
                 or signal_type == "domain_authoritative")
                and not (
                    evidence_source == "domain_authority"
                    and signal_type == "domain_authoritative"
                    and source_id in approved_seed_sources
                )
            )
            if unsupported:
                issues.append(_issue(
                    "blocker", "unsupported_canonicality_evidence",
                    "canonicality basis cites evidence unavailable for this candidate",
                    f"{location}.canonicality_basis[{basis_index}]",
                ))
        access = annotation.get("access_statement") \
            if isinstance(annotation.get("access_statement"), dict) else {}
        record_access = record.get("access") if isinstance(record.get("access"), dict) else {}
        if access.get("access_level") != record_access.get("access_level") \
                or access.get("library_access_required") \
                != record_access.get("library_access_required"):
            issues.append(_issue(
                "blocker", "access_statement_mismatch",
                "access statement must exactly preserve provider-backed access facts",
                f"{location}.access_statement",
            ))
        surrogate_ids = set(_strings(access.get("accessible_surrogate_source_ids")))
        if source_id in surrogate_ids or not surrogate_ids <= set(candidate_ids):
            issues.append(_issue(
                "major", "invalid_accessible_surrogate",
                "surrogates must be distinct candidates in this artifact",
                f"{location}.access_statement.accessible_surrogate_source_ids",
            ))
        coverage_ids = set(_strings(annotation.get("coverage_unit_ids")))
        if not coverage_ids or coverage_ids - target_coverage:
            issues.append(_issue(
                "major", "invalid_canonical_coverage",
                f"annotation coverage must be non-empty and targeted; unknown={sorted(coverage_ids-target_coverage)}",
                f"{location}.coverage_unit_ids",
            ))
        if isinstance(source_id, str):
            annotation_coverage[source_id] = coverage_ids

    coverage_map = output.get("coverage_map") \
        if isinstance(output.get("coverage_map"), list) else []
    coverage_map_ids = [item.get("source_id") for item in coverage_map
                        if isinstance(item, dict) and isinstance(item.get("source_id"), str)]
    if _duplicates(coverage_map_ids) or set(coverage_map_ids) != set(candidate_ids):
        issues.append(_issue(
            "major", "canonical_coverage_map_mismatch",
            "coverage_map requires exactly one mapping per candidate", "coverage_map",
        ))
    coverage_sources: dict[str, set[str]] = {}
    for index, mapping in enumerate(coverage_map):
        if not isinstance(mapping, dict):
            continue
        source_id = mapping.get("source_id")
        units = set(_strings(mapping.get("coverage_unit_ids")))
        if units != annotation_coverage.get(source_id, set()):
            issues.append(_issue(
                "major", "coverage_annotation_mismatch",
                "coverage_map must exactly match the candidate annotation",
                f"coverage_map[{index}]",
            ))
        if isinstance(source_id, str):
            for coverage_id in units:
                coverage_sources.setdefault(coverage_id, set()).add(source_id)
    requirements = topic.get("coverage_requirements") \
        if isinstance(topic.get("coverage_requirements"), list) else []
    expected_remaining = {
        item["coverage_id"] for item in requirements if isinstance(item, dict)
        and item.get("coverage_id") in target_coverage
        and len(coverage_sources.get(item["coverage_id"], set()))
        < (item.get("minimum_sources") if isinstance(item.get("minimum_sources"), int) else 1)
    }
    remaining = set(_strings(output.get("remaining_coverage_units")))
    if remaining != expected_remaining:
        issues.append(_issue(
            "major", "remaining_coverage_mismatch",
            f"remaining coverage must equal {sorted(expected_remaining)}",
            "remaining_coverage_units",
        ))
    unresolved = _strings(output.get("unresolved_seed_ids"))
    expected_unresolved = _strings(canonical_input.get("unresolved_plan_seed_ids"))
    if unresolved != expected_unresolved:
        issues.append(_issue(
            "major", "unresolved_seed_mismatch",
            "unresolved_seed_ids must preserve the scoped unresolved plan seeds in order",
            "unresolved_seed_ids",
        ))
    stop = output.get("stop_reason")
    if stop == "completed" and (remaining or output.get("provider_issues") or unresolved):
        issues.append(_issue(
            "major", "completed_with_canonical_gaps",
            "completed requires no remaining coverage, provider issues or unresolved seeds",
            "stop_reason",
        ))
    if stop == "candidate_limit" and isinstance(candidate_limit, int) \
            and len(candidates) < candidate_limit:
        issues.append(_issue(
            "major", "candidate_limit_not_reached",
            "candidate_limit requires the configured count to be reached", "stop_reason",
        ))
    if stop == "provider_unavailable" and candidates:
        issues.append(_issue(
            "major", "provider_unavailable_with_candidates",
            "provider_unavailable is reserved for runs without usable candidates", "stop_reason",
        ))
    if stop == "partial_coverage" and not remaining and not output.get("provider_issues"):
        issues.append(_issue(
            "major", "partial_coverage_without_gap",
            "partial_coverage requires a gap or provider issue", "stop_reason",
        ))
    if stop == "unresolved_seed" and not unresolved:
        issues.append(_issue(
            "major", "unresolved_seed_without_seed",
            "unresolved_seed requires at least one preserved unresolved plan seed",
            "stop_reason",
        ))
    if unresolved and stop not in {"unresolved_seed", "partial_coverage", "candidate_limit",
                                   "saturation", "provider_unavailable"}:
        issues.append(_issue(
            "major", "unresolved_seed_stop_reason_mismatch",
            "stop reason must acknowledge preserved unresolved plan seeds", "stop_reason",
        ))
    verification_degraded = any(
        item.get("status") != "ok" or item.get("match_status") == "conflict"
        for item in output.get("doi_verifications", []) if isinstance(item, dict)
    )
    complete = not remaining and not output.get("provider_issues") and not unresolved \
        and not verification_degraded
    return {"ok": not issues, "complete": complete, "issues": issues}


def _safe_segment(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()) or "unknown"


def finalize_canonical_candidates(canonical_input: dict, output: object, *, base=None,
                                  previous_candidates: dict | None = None,
                                  revision_items: list[dict] | None = None) -> dict:
    validation = validate_canonical_candidates(
        output, canonical_input, base=base, previous_candidates=previous_candidates,
        revision_items=revision_items,
    )
    if not validation["ok"]:
        return _envelope(
            "failed", "CanonicalCandidateSources failed deterministic validation.",
            validation["issues"],
        )
    assert isinstance(output, dict)
    task = _safe_segment(output["task_id"])
    topic = _safe_segment(output["topic_id"])
    version = _safe_segment(output["artifact_version"])
    try:
        ref = artifacts.store(
            f"g02/canonical-candidates/{task}.{topic}.{version}.json", output, base=base
        )
    except (OSError, TypeError, ValueError) as exc:
        return failed_envelope(
            "canonical_candidates_store_failed", str(exc), "artifact_store"
        )
    descriptor = {
        "type": "candidate_sources",
        "path": ref,
        "schema_version": CANONICAL_OUTPUT_CONTRACT,
        "artifact_version": output["artifact_version"],
    }
    status = "ok" if validation["complete"] else "degraded"
    return _envelope(
        status,
        f"Stored {len(output['candidates'])} canonical candidates for {output['topic_id']}.",
        [],
        produced=[descriptor],
        metrics={
            "candidate_count": len(output["candidates"]),
            "operation_count": len(output["operation_log"]),
            "remaining_coverage_count": len(output["remaining_coverage_units"]),
            "unresolved_seed_count": len(output["unresolved_seed_ids"]),
        },
        resume_token=ref if status == "degraded" else None,
    )


def build_canonical_review_task(canonical_input: dict, artifact_descriptor: dict, *,
                                review_id: str, attempt: int = 1,
                                previous_decision_ref: str | None = None,
                                producer_revision_response: dict | None = None,
                                base=None) -> dict:
    checked = validate_canonical_basis(canonical_input, base=base)
    if not checked["ok"]:
        raise ValueError("invalid canonical input: " + "; ".join(
            item["message"] for item in checked["issues"]
        ))
    if not isinstance(artifact_descriptor, dict):
        raise ValueError("artifact descriptor must be an object")
    ref = artifact_descriptor.get("path") or artifact_descriptor.get("ref")
    if artifact_descriptor.get("type") != "candidate_sources" \
            or artifact_descriptor.get("schema_version") != CANONICAL_OUTPUT_CONTRACT:
        raise ValueError("artifact descriptor must identify canonical candidate_sources@1")
    if not isinstance(ref, str) or not ref.startswith(artifacts.SCHEME):
        raise ValueError("artifact descriptor must contain an artifact:// path or ref")
    artifact_version = artifact_descriptor.get("artifact_version")
    if not isinstance(artifact_version, str) or not artifact_version.strip():
        raise ValueError("artifact descriptor must contain artifact_version")
    try:
        reviewed_artifact = artifacts.hydrate(ref, base=base)
    except (OSError, ValueError, KeyError, IndexError) as exc:
        raise ValueError(f"cannot hydrate canonical artifact: {exc}") from exc
    artifact_validation = validate_canonical_candidates(
        reviewed_artifact, canonical_input, base=base
    )
    if not artifact_validation["ok"]:
        raise ValueError("canonical artifact is not reviewable: " + "; ".join(
            item["message"] for item in artifact_validation["issues"]
        ))
    if reviewed_artifact.get("artifact_version") != artifact_version:
        raise ValueError("artifact descriptor version differs from stored canonical artifact")
    task = {
        "schema_version": "review_task@1",
        "review_id": review_id,
        "task_id": canonical_input["task_id"],
        "logical_review_node": "g02-a03-canonical-sources-review",
        "producer_agent": CANONICAL_AGENT,
        "attempt": attempt,
        "review_profile": REVIEW_PROFILE,
        "original_task": {
            "objective": "Extend one reviewed domain pool with defensible canonical anchors.",
            "input_contract": CANONICAL_INPUT_CONTRACT,
            "output_contract": CANONICAL_OUTPUT_CONTRACT,
        },
        "producer_input": deepcopy(canonical_input),
        "artifact": {
            "type": "candidate_sources",
            "ref": ref,
            "schema_version": CANONICAL_OUTPUT_CONTRACT,
            "artifact_version": artifact_version,
        },
        "expected_output_contract": CANONICAL_OUTPUT_CONTRACT,
        "acceptance_criteria": deepcopy(CANONICAL_ACCEPTANCE_CRITERIA),
        "evidence_requirements": deepcopy(CANONICAL_EVIDENCE_REQUIREMENTS),
        "prohibited_behaviors": deepcopy(CANONICAL_PROHIBITED_BEHAVIORS),
        "severity_rules": deepcopy(CANONICAL_SEVERITY_RULES),
        "previous_decision_ref": previous_decision_ref,
        "producer_revision_response": producer_revision_response,
    }
    from g02 import review
    validation = review.validate_review_task(task)
    if not validation["ok"]:
        raise ValueError("invalid canonical review task: " + "; ".join(
            item["message"] for item in validation["issues"]
        ))
    return task


def execute_canonical(research_plan_ref: str, domain_candidates_ref: str, topic_id: str,
                      canonical_executor: Callable | None, *, base=None,
                      config_path: str | Path | None = None,
                      runtime_home: str | Path | None = None,
                      previous_candidates_ref: str | None = None,
                      revision_items: list[dict] | None = None) -> dict:
    prepared = prepare_canonical(
        research_plan_ref, domain_candidates_ref, topic_id,
        config_path=config_path, runtime_home=runtime_home, artifact_base=base,
        previous_candidates_ref=previous_candidates_ref, revision_items=revision_items,
    )
    if not prepared["ready"]:
        return prepared["envelope"]
    if canonical_executor is None:
        return failed_envelope(
            "canonical_executor_unavailable", "no G02-A03 host executor is configured"
        )
    try:
        output = canonical_executor(
            prepared["canonical_input"],
            {
                "previous_candidates": prepared["previous_candidates"],
                "previous_candidates_ref": prepared["previous_candidates_ref"],
                "revision_items": prepared["revision_items"],
            },
        )
    except Exception as exc:
        return failed_envelope("canonical_executor_failed", str(exc))
    return finalize_canonical_candidates(
        prepared["canonical_input"], output, base=base,
        previous_candidates=prepared["previous_candidates"],
        revision_items=prepared["revision_items"],
    )
