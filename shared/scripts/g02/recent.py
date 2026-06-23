"""Deterministic boundary for G02-A04 Recent Developments discovery."""
from __future__ import annotations

import re
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from core import artifacts, contracts
from g02 import canonical, crossref, provider_config, query_planning

RECENT_INPUT_CONTRACT = "recent_research_input@1"
RECENT_OUTPUT_CONTRACT = "candidate_sources@1"
DOMAIN_OUTPUT_CONTRACT = "domain_candidate_sources@1"
RESEARCH_PLAN_CONTRACT = "research_plan@1"
SOURCE_RECORD_CONTRACT = "source_record@1"
RECENT_AGENT = "g02-a04-recent-developments"
REVIEW_PROFILE = "recent_developments"
RECENT_ROLES = {
    "current", "rising", "methodological", "claim_specific", "qualifying_or_critical",
}
RELATIONS = {"references", "cited_by", "recommendations"}

RECENT_ACCEPTANCE_CRITERIA = [
    {
        "criterion_id": "RD-01",
        "description": "Every candidate is an unchanged provider record inside the exact intake-derived recency window and approved topic.",
        "mandatory": True,
    },
    {
        "criterion_id": "RD-02",
        "description": "Preprint and peer-review status are explicit, conservative and supported only by available provider metadata.",
        "mandatory": True,
    },
    {
        "criterion_id": "RD-03",
        "description": "Maturity and update class cite observable signals; publication year alone never establishes maturity or a core update.",
        "mandatory": True,
    },
    {
        "criterion_id": "RD-04",
        "description": "Novelty, citation signals, maturity, functional role and scientific quality remain separate judgments.",
        "mandatory": True,
    },
    {
        "criterion_id": "RD-05",
        "description": "Every metadata and citation operation is bounded, persisted and traceable to the approved plan, seed and provider result.",
        "mandatory": True,
    },
    {
        "criterion_id": "RD-06",
        "description": "Coverage gaps, provider failures, preprint limitations and stop reason are explicit and internally consistent.",
        "mandatory": True,
    },
    {
        "criterion_id": "RD-07",
        "description": "Every non-empty DOI has an auditable Crossref result, with conflicts separate from recency and maturity judgments.",
        "mandatory": True,
    },
]

RECENT_EVIDENCE_REQUIREMENTS = [
    {
        "requirement_id": "RD-E01",
        "description": "Every operation-log entry resolves to one unchanged literature_tool_result@1 artifact.",
        "mandatory": True,
    },
    {
        "requirement_id": "RD-E02",
        "description": "Every candidate exactly matches a reviewed A02 record or a record returned by a referenced A04 operation.",
        "mandatory": True,
    },
    {
        "requirement_id": "RD-E03",
        "description": "Role, recency, publication, maturity, update and coverage annotations use only observed metadata, abstract or citation-relation evidence.",
        "mandatory": True,
    },
]

RECENT_PROHIBITED_BEHAVIORS = [
    "Treating publication date, citation velocity, venue or novelty as scientific quality.",
    "Calling a preprint established consensus or a core update without mature observable signals.",
    "Modifying provider metadata, widening the recency window or inventing peer-review status.",
    "Retrieving documents, verifying claims, replacing canonical foundations or exposing credentials.",
]

RECENT_SEVERITY_RULES = {
    "minor": "A local wording or confidence defect that does not alter source identity, maturity or update class.",
    "major": "Missing recency, role, maturity, coverage, search-log or publication-status evidence.",
    "blocker": "Out-of-window or fabricated source, modified provider record, invented peer review, unapproved scope or unreadable evidence artifact.",
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


def _shape_issues(payload: object, contract_ref: str, code: str) -> list[dict]:
    try:
        checked = contracts.validate(payload, contract_ref)
    except (KeyError, ValueError) as exc:
        return [_issue("blocker", "contract_unavailable", str(exc), contract_ref)]
    return [_issue("blocker", code, error, contract_ref) for error in checked["errors"]]


def _envelope(status: str, summary: str, issues: list[dict], *, produced=None,
              metrics=None, resume_token=None) -> dict:
    return canonical._envelope(
        status, summary, issues, produced=produced, metrics=metrics, resume_token=resume_token
    )


def failed_envelope(issue_type: str, message: str, location: str = "recent") -> dict:
    return _envelope(
        "failed", "G02-A04 Recent Developments did not produce candidate sources.",
        [_issue("blocker", issue_type, message, location)],
    )


def needs_input_envelope(issue_type: str, message: str, location: str) -> dict:
    return _envelope(
        "needs_input", "Recent discovery is missing an approved upstream artifact.",
        [_issue("blocker", issue_type, message, location)],
    )


def _scope_not_requested() -> dict:
    return _envelope(
        "ok", "Recent discovery is not requested for this approved topic.", [],
        metrics={"skipped": True},
    )


def _year_window(plan: dict, approved_topic: dict, as_of_year: int) -> dict:
    scope = plan.get("approved_research_scope") \
        if isinstance(plan.get("approved_research_scope"), dict) else {}
    window_years = scope.get("recency_window_years")
    if not isinstance(window_years, int) or isinstance(window_years, bool) or window_years < 1:
        raise ValueError("approved recency_window_years must be a positive integer")
    lower = as_of_year - window_years + 1
    upper = as_of_year
    strategy = approved_topic.get("search_strategy") \
        if isinstance(approved_topic.get("search_strategy"), dict) else {}
    constraints = plan.get("global_constraints") \
        if isinstance(plan.get("global_constraints"), dict) else {}
    lower_bounds = [value for value in (strategy.get("year_from"), constraints.get("year_from"))
                    if isinstance(value, int) and not isinstance(value, bool)]
    upper_bounds = [value for value in (strategy.get("year_to"), constraints.get("year_to"))
                    if isinstance(value, int) and not isinstance(value, bool)]
    if lower_bounds:
        lower = max(lower, *lower_bounds)
    if upper_bounds:
        upper = min(upper, *upper_bounds)
    if lower > upper:
        raise ValueError("approved constraints do not overlap the recency window")
    return {
        "as_of_year": as_of_year,
        "window_years": window_years,
        "year_from": lower,
        "year_to": upper,
        "basis": "approved_research_scope",
    }


def _derive_recent_scope(plan: dict, approved_topic: dict, records: list[dict],
                         as_of_year: int) -> dict:
    window = _year_window(plan, approved_topic, as_of_year)
    topic = deepcopy(approved_topic)
    topic["search_strategy"]["year_from"] = window["year_from"]
    topic["search_strategy"]["year_to"] = window["year_to"]
    roles = ["current", "rising", "methodological"]
    role_flags = approved_topic.get("source_roles_required") \
        if isinstance(approved_topic.get("source_roles_required"), dict) else {}
    if approved_topic.get("related_claims"):
        roles.append("claim_specific")
    if role_flags.get("qualifying_or_critical") is True:
        roles.append("qualifying_or_critical")
    coverage = approved_topic.get("coverage_requirements") \
        if isinstance(approved_topic.get("coverage_requirements"), list) else []
    target = [item["coverage_id"] for item in coverage if isinstance(item, dict)
              and isinstance(item.get("coverage_id"), str)
              and set(_strings(item.get("source_roles"))) & set(roles)]
    candidate_limit = approved_topic.get("stop_rule", {}).get("candidate_limit")
    if not isinstance(candidate_limit, int) or isinstance(candidate_limit, bool):
        candidate_limit = 20
    verified = [record["source_id"] for record in records
                if isinstance(record, dict) and isinstance(record.get("source_id"), str)
                and canonical._provider_resolvable(record)]
    return {
        "topic": topic,
        "verified_seed_ids": verified,
        "recency_window": window,
        "required_roles": list(dict.fromkeys(roles)),
        "target_coverage_units": list(dict.fromkeys(target)),
        "search_limits": {
            "candidate_limit": candidate_limit,
            "citation_depth": 1,
            "per_seed_relation_limit": min(10, candidate_limit),
            "allowed_relations": ["references", "cited_by", "recommendations"],
        },
    }


def validate_recent_input(recent_input: object) -> dict:
    issues = _shape_issues(recent_input, RECENT_INPUT_CONTRACT, "invalid_recent_input_contract")
    if not isinstance(recent_input, dict):
        return {"ok": False, "issues": issues}
    allowed = {
        "schema_version", "task_id", "research_plan_ref", "research_plan_artifact_version",
        "domain_candidates_ref", "domain_candidates_artifact_version", "topic",
        "domain_candidates", "verified_seed_ids", "recency_window", "required_roles",
        "target_coverage_units", "search_limits", "provider_capabilities", "output_language",
    }
    unknown = sorted(set(recent_input) - allowed)
    if unknown:
        issues.append(_issue(
            "blocker", "unknown_recent_input_fields", f"unsupported fields {unknown}",
            "recent_input",
        ))
    for field in (
        "task_id", "research_plan_ref", "research_plan_artifact_version",
        "domain_candidates_ref", "domain_candidates_artifact_version", "output_language",
    ):
        value = recent_input.get(field)
        if not isinstance(value, str) or not value.strip():
            issues.append(_issue(
                "blocker", "empty_recent_input_field", f"{field} must not be empty", field,
            ))
    for field in ("research_plan_ref", "domain_candidates_ref"):
        value = recent_input.get(field)
        if isinstance(value, str) and not value.startswith(artifacts.SCHEME):
            issues.append(_issue(
                "blocker", "invalid_recent_artifact_ref", f"{field} must use artifact://", field,
            ))
    topic = recent_input.get("topic") if isinstance(recent_input.get("topic"), dict) else {}
    coverage = topic.get("coverage_requirements") \
        if isinstance(topic.get("coverage_requirements"), list) else []
    coverage_ids = {item.get("coverage_id") for item in coverage if isinstance(item, dict)}
    target = _strings(recent_input.get("target_coverage_units"))
    if not target or _duplicates(target) or set(target) - coverage_ids:
        issues.append(_issue(
            "blocker", "invalid_recent_target_coverage",
            "target coverage must be non-empty, unique and approved", "target_coverage_units",
        ))
    roles = _strings(recent_input.get("required_roles"))
    if not roles or _duplicates(roles) or set(roles) - RECENT_ROLES:
        issues.append(_issue(
            "blocker", "invalid_recent_required_roles",
            "required roles must be non-empty, unique and recent-role scoped", "required_roles",
        ))
    records = recent_input.get("domain_candidates") \
        if isinstance(recent_input.get("domain_candidates"), list) else []
    record_ids: list[str] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        shape = contracts.validate(record, SOURCE_RECORD_CONTRACT)
        for error in shape["errors"]:
            issues.append(_issue(
                "blocker", "invalid_recent_seed_record", error, f"domain_candidates[{index}]",
            ))
        if isinstance(record.get("source_id"), str):
            record_ids.append(record["source_id"])
    if _duplicates(record_ids):
        issues.append(_issue(
            "blocker", "duplicate_recent_seed_record", "domain seed IDs must be unique",
            "domain_candidates",
        ))
    verified = _strings(recent_input.get("verified_seed_ids"))
    if _duplicates(verified) or not set(verified) <= set(record_ids):
        issues.append(_issue(
            "blocker", "invalid_recent_verified_seeds",
            "verified seeds must be unique members of the reviewed domain pool",
            "verified_seed_ids",
        ))
    window = recent_input.get("recency_window") \
        if isinstance(recent_input.get("recency_window"), dict) else {}
    for field in ("as_of_year", "window_years", "year_from", "year_to"):
        value = window.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            issues.append(_issue(
                "blocker", "invalid_recent_window", f"{field} must be a positive integer",
                f"recency_window.{field}",
            ))
    if isinstance(window.get("year_from"), int) and isinstance(window.get("year_to"), int) \
            and window["year_from"] > window["year_to"]:
        issues.append(_issue(
            "blocker", "invalid_recent_window", "year_from cannot exceed year_to",
            "recency_window",
        ))
    strategy = topic.get("search_strategy") \
        if isinstance(topic.get("search_strategy"), dict) else {}
    if strategy.get("year_from") != window.get("year_from") \
            or strategy.get("year_to") != window.get("year_to"):
        issues.append(_issue(
            "blocker", "recent_topic_window_mismatch",
            "topic filters must exactly equal the frozen recency window", "topic.search_strategy",
        ))
    limits = recent_input.get("search_limits") \
        if isinstance(recent_input.get("search_limits"), dict) else {}
    if limits.get("citation_depth") != 1:
        issues.append(_issue(
            "blocker", "invalid_recent_citation_depth", "citation depth must equal one",
            "search_limits.citation_depth",
        ))
    for field in ("candidate_limit", "per_seed_relation_limit"):
        value = limits.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            issues.append(_issue(
                "blocker", "invalid_recent_search_limit", f"{field} must be positive",
                f"search_limits.{field}",
            ))
    relations = _strings(limits.get("allowed_relations"))
    if not relations or _duplicates(relations) or set(relations) - RELATIONS:
        issues.append(_issue(
            "blocker", "invalid_recent_relations", "allowed citation relations are invalid",
            "search_limits.allowed_relations",
        ))
    capabilities = recent_input.get("provider_capabilities") \
        if isinstance(recent_input.get("provider_capabilities"), list) else []
    if not any(isinstance(item, dict) and item.get("enabled") is True
               and item.get("ready") is True for item in capabilities):
        issues.append(_issue(
            "blocker", "no_ready_recent_provider", "at least one provider must be ready",
            "provider_capabilities",
        ))
    return {"ok": not issues, "issues": issues}


def validate_recent_basis(recent_input: object, *, base=None) -> dict:
    checked = validate_recent_input(recent_input)
    issues = list(checked["issues"])
    if not isinstance(recent_input, dict):
        return {"ok": False, "issues": issues}
    try:
        plan = artifacts.hydrate(recent_input["research_plan_ref"], base=base)
        domain_pool = artifacts.hydrate(recent_input["domain_candidates_ref"], base=base)
        for payload, contract_ref in (
            (plan, RESEARCH_PLAN_CONTRACT), (domain_pool, DOMAIN_OUTPUT_CONTRACT),
        ):
            shape = contracts.validate(payload, contract_ref)
            if not shape["ok"]:
                raise ValueError("; ".join(shape["errors"]))
    except (OSError, ValueError, KeyError, IndexError) as exc:
        issues.append(_issue(
            "blocker", "unreadable_recent_basis", str(exc), "recent_input",
        ))
        return {"ok": False, "issues": issues}
    topic_id = recent_input.get("topic", {}).get("topic_id")
    topics = [item for item in plan.get("topics", []) if isinstance(item, dict)
              and item.get("topic_id") == topic_id]
    if len(topics) != 1:
        issues.append(_issue(
            "blocker", "recent_topic_basis_mismatch", "approved topic cannot be resolved", "topic",
        ))
        return {"ok": False, "issues": issues}
    approved_topic = topics[0]
    if plan.get("approved_research_scope", {}).get("include_recent_developments") is not True \
            or approved_topic.get("source_roles_required", {}).get("current") is not True:
        issues.append(_issue(
            "blocker", "recent_scope_not_approved", "recent discovery is not approved for topic",
            "approved_research_scope",
        ))
    if domain_pool.get("task_id") != plan.get("task_id") \
            or domain_pool.get("topic_id") != topic_id \
            or domain_pool.get("research_plan_ref") != recent_input.get("research_plan_ref"):
        issues.append(_issue(
            "blocker", "recent_domain_basis_mismatch",
            "DomainCandidateSources does not match the approved plan and topic",
            "domain_candidates_ref",
        ))
    records = domain_pool.get("candidates") if isinstance(domain_pool.get("candidates"), list) else []
    if recent_input.get("domain_candidates") != records:
        issues.append(_issue(
            "blocker", "recent_domain_records_modified",
            "scoped domain candidates differ from reviewed A02", "domain_candidates",
        ))
    as_of_year = recent_input.get("recency_window", {}).get("as_of_year")
    if isinstance(as_of_year, int):
        try:
            scope = _derive_recent_scope(plan, approved_topic, records, as_of_year)
        except ValueError as exc:
            issues.append(_issue(
                "blocker", "invalid_recent_scope_projection", str(exc), "recency_window",
            ))
            scope = {}
        for field, expected in scope.items():
            if recent_input.get(field) != expected:
                issues.append(_issue(
                    "blocker", "recent_scope_projection_mismatch",
                    f"{field} differs from deterministic A04 projection", field,
                ))
    for field, expected in (
        ("task_id", plan.get("task_id")),
        ("research_plan_artifact_version", plan.get("artifact_version")),
        ("domain_candidates_artifact_version", domain_pool.get("artifact_version")),
        ("output_language", plan.get("output_language")),
    ):
        if recent_input.get(field) != expected:
            issues.append(_issue(
                "blocker", "recent_basis_identity_mismatch",
                f"{field} differs from approved upstream artifacts", field,
            ))
    if as_of_year != datetime.now(UTC).year:
        issues.append(_issue(
            "blocker", "stale_or_future_recent_window",
            "as_of_year must equal the runtime calendar year", "recency_window.as_of_year",
        ))
    return {"ok": not issues, "issues": issues}


def prepare_recent(research_plan_ref: str, domain_candidates_ref: str, topic_id: str, *,
                   config_path: str | Path | None = None,
                   runtime_home: str | Path | None = None, artifact_base=None,
                   previous_candidates_ref: str | None = None,
                   revision_items: list[dict] | None = None) -> dict:
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
            "missing_topic_id", "a non-empty topic_id is required", "topic_id",
        )}
    try:
        plan = artifacts.hydrate(research_plan_ref, base=artifact_base)
        domain_pool = artifacts.hydrate(domain_candidates_ref, base=artifact_base)
        for payload, contract_ref in (
            (plan, RESEARCH_PLAN_CONTRACT), (domain_pool, DOMAIN_OUTPUT_CONTRACT),
        ):
            shape = contracts.validate(payload, contract_ref)
            if not shape["ok"]:
                raise ValueError("; ".join(shape["errors"]))
    except (OSError, ValueError, KeyError, IndexError) as exc:
        return {"ready": False, "envelope": failed_envelope(
            "invalid_recent_upstream", str(exc), "upstream_refs",
        )}
    topics = [item for item in plan.get("topics", []) if isinstance(item, dict)
              and item.get("topic_id") == topic_id]
    if len(topics) != 1:
        return {"ready": False, "envelope": needs_input_envelope(
            "unknown_or_duplicate_topic",
            f"expected exactly one topic {topic_id!r}, found {len(topics)}", "topic_id",
        )}
    approved_topic = topics[0]
    if domain_pool.get("task_id") != plan.get("task_id") \
            or domain_pool.get("topic_id") != topic_id \
            or domain_pool.get("research_plan_ref") != research_plan_ref:
        return {"ready": False, "envelope": failed_envelope(
            "recent_upstream_identity_mismatch",
            "DomainCandidateSources does not match the approved plan and topic",
            "domain_candidates_ref",
        )}
    scope = plan.get("approved_research_scope") \
        if isinstance(plan.get("approved_research_scope"), dict) else {}
    if scope.get("include_recent_developments") is not True \
            or approved_topic.get("source_roles_required", {}).get("current") is not True:
        return {"ready": False, "skipped": True, "envelope": _scope_not_requested()}
    try:
        config = provider_config.load_config(
            config_path, runtime_home=runtime_home, create_dirs=True
        )
        derived = _derive_recent_scope(
            plan, approved_topic, deepcopy(domain_pool.get("candidates", [])),
            datetime.now(UTC).year,
        )
    except (provider_config.ProviderConfigError, ValueError) as exc:
        return {"ready": False, "envelope": failed_envelope(
            "recent_preparation_failed", str(exc), "recent_scope",
        )}
    recent_input = {
        "schema_version": RECENT_INPUT_CONTRACT,
        "task_id": plan["task_id"],
        "research_plan_ref": research_plan_ref,
        "research_plan_artifact_version": plan["artifact_version"],
        "domain_candidates_ref": domain_candidates_ref,
        "domain_candidates_artifact_version": domain_pool["artifact_version"],
        "domain_candidates": deepcopy(domain_pool.get("candidates", [])),
        **derived,
        "provider_capabilities": config.public_status()["capabilities"],
        "output_language": plan["output_language"],
    }
    checked = validate_recent_input(recent_input)
    if not checked["ok"]:
        return {"ready": False, "envelope": failed_envelope(
            "invalid_scoped_recent_input",
            "; ".join(item["message"] for item in checked["issues"]), "recent_input",
        )}
    previous = None
    if previous_candidates_ref is not None:
        try:
            if not isinstance(previous_candidates_ref, str) \
                    or not previous_candidates_ref.startswith(artifacts.SCHEME):
                raise ValueError("previous_candidates_ref must use artifact://")
            previous = artifacts.hydrate(previous_candidates_ref, base=artifact_base)
            shape = contracts.validate(previous, RECENT_OUTPUT_CONTRACT)
            if not shape["ok"]:
                raise ValueError("; ".join(shape["errors"]))
            if previous.get("stream") != "recent" \
                    or previous.get("task_id") != plan["task_id"] \
                    or previous.get("topic_id") != topic_id \
                    or previous.get("recency_window") != derived["recency_window"]:
                raise ValueError("previous recent candidates do not match task, topic and window")
        except (OSError, ValueError, KeyError, IndexError) as exc:
            return {"ready": False, "envelope": failed_envelope(
                "invalid_previous_recent_candidates", str(exc), "previous_candidates_ref",
            )}
    if revision_items and previous is None:
        return {"ready": False, "envelope": failed_envelope(
            "missing_previous_recent_candidates",
            "revision_items require previous_candidates_ref", "revision_items",
        )}
    if revision_items is not None and (
            not isinstance(revision_items, list)
            or any(not isinstance(item, dict) for item in revision_items)):
        return {"ready": False, "envelope": failed_envelope(
            "invalid_recent_revision_items", "revision_items must be a list of findings",
            "revision_items",
        )}
    for index, item in enumerate(revision_items or []):
        for field in ("finding_id", "location", "required_correction"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                return {"ready": False, "envelope": failed_envelope(
                    "invalid_recent_revision_item",
                    f"revision_items[{index}].{field} must be non-empty", "revision_items",
                )}
    return {
        "ready": True,
        "recent_input": recent_input,
        "config_status": config.public_status(),
        "previous_candidates": previous,
        "previous_candidates_ref": previous_candidates_ref,
        "revision_items": deepcopy(revision_items or []),
    }


def _revision_fields(revision_items: list[dict] | None) -> set[str]:
    mutable = {
        "query_plan", "candidates", "doi_verifications", "recent_annotations", "operation_log", "coverage_map",
        "remaining_coverage_units", "provider_issues", "stop_reason",
    }
    targeted: set[str] = set()
    for item in revision_items or []:
        location = item.get("location") if isinstance(item, dict) else None
        if isinstance(location, str):
            targeted.update(field for field in mutable
                            if re.search(rf"(?:^|\.){re.escape(field)}(?:\.|\[|$)", location))
    order = [
        "query_plan", "operation_log", "candidates", "recent_annotations", "coverage_map",
        "provider_issues", "remaining_coverage_units", "stop_reason",
    ]
    expanded = set(targeted)
    for field in targeted:
        if field in order:
            expanded.update(order[order.index(field):])
    return expanded


def _expected_publication_status(record: dict) -> tuple[str, str]:
    bibliographic = record.get("bibliographic") \
        if isinstance(record.get("bibliographic"), dict) else {}
    work_type = bibliographic.get("work_type")
    if work_type == "preprint":
        return "preprint", "preprint"
    if work_type in {"article", "review", "book", "chapter", "conference"}:
        return "not_preprint", "published_unknown"
    return "unknown", "unknown"


def _access_rank(value: object) -> int:
    return {
        "metadata": 0, "metadata_only": 0, "abstract": 1, "table_of_contents": 2,
        "preview": 3, "partial_text": 4, "full_text": 5,
    }.get(value, 99)


def validate_recent_candidates(output: object, recent_input: dict, *, base=None,
                               previous_candidates: dict | None = None,
                               revision_items: list[dict] | None = None) -> dict:
    issues = _shape_issues(
        output, RECENT_OUTPUT_CONTRACT, "invalid_recent_candidates_contract"
    )
    basis = validate_recent_basis(recent_input, base=base)
    issues.extend(basis["issues"])
    if not isinstance(output, dict):
        return {"ok": False, "complete": False, "issues": issues}
    allowed = {
        "schema_version", "artifact_version", "stream", "task_id", "topic_id",
        "research_plan_ref", "upstream_refs", "recency_window", "query_plan", "candidates", "doi_verifications",
        "recent_annotations", "operation_log", "coverage_map", "remaining_coverage_units",
        "provider_issues", "unresolved_seed_ids", "stop_reason", "review_profile_ref",
    }
    unknown = sorted(set(output) - allowed)
    if unknown:
        issues.append(_issue(
            "major", "unknown_recent_output_fields", f"unsupported fields {unknown}",
            "recent_output",
        ))
    topic = recent_input.get("topic") if isinstance(recent_input.get("topic"), dict) else {}
    for field, expected in (
        ("stream", "recent"), ("task_id", recent_input.get("task_id")),
        ("topic_id", topic.get("topic_id")),
        ("research_plan_ref", recent_input.get("research_plan_ref")),
        ("recency_window", recent_input.get("recency_window")),
        ("review_profile_ref", REVIEW_PROFILE),
    ):
        if output.get(field) != expected:
            issues.append(_issue(
                "blocker", "recent_output_identity_mismatch",
                f"{field} must equal the scoped input", field,
            ))
    if output.get("upstream_refs") != {
        "domain_candidate_sources": recent_input.get("domain_candidates_ref")
    }:
        issues.append(_issue(
            "blocker", "recent_upstream_ref_mismatch",
            "upstream_refs must contain exactly the reviewed A02 ref", "upstream_refs",
        ))
    if not isinstance(output.get("recent_annotations"), list):
        issues.append(_issue(
            "blocker", "missing_recent_annotations",
            "recent_annotations must be an array", "recent_annotations",
        ))
    version = output.get("artifact_version")
    if not isinstance(version, str) or not version.strip():
        issues.append(_issue(
            "major", "empty_recent_artifact_version", "artifact_version must not be empty",
            "artifact_version",
        ))
    if previous_candidates is not None and version == previous_candidates.get("artifact_version"):
        issues.append(_issue(
            "major", "recent_artifact_version_not_advanced",
            "a revision must advance artifact_version", "artifact_version",
        ))
    if previous_candidates is not None:
        targeted = _revision_fields(revision_items)
        if targeted:
            for field in output:
                if field != "artifact_version" and field not in targeted \
                        and output.get(field) != previous_candidates.get(field):
                    issues.append(_issue(
                        "major", "unscoped_recent_revision_change",
                        f"untargeted field {field!r} changed", field,
                    ))
    query_plan = output.get("query_plan")
    query_checked = query_planning.validate_query_plan(query_plan, recent_input)
    for item in query_checked["issues"]:
        issues.append(_issue(
            "major", item["code"], item["message"], f"query_plan.{item['location']}",
        ))
    routes = query_plan.get("routes", []) if isinstance(query_plan, dict) else []
    route_map = {item.get("route_id"): item for item in routes if isinstance(item, dict)}
    window = recent_input.get("recency_window", {})
    for index, route in enumerate(routes):
        filters = route.get("filters") if isinstance(route, dict) \
            and isinstance(route.get("filters"), dict) else {}
        if filters.get("year_from") != window.get("year_from") \
                or filters.get("year_to") != window.get("year_to"):
            issues.append(_issue(
                "blocker", "recent_query_window_mismatch",
                "every A04 route must use the exact frozen recency window",
                f"query_plan.routes[{index}].filters",
            ))
    approved_work_types = set(_strings(topic.get("search_strategy", {}).get("work_types")))
    if "preprint" in approved_work_types and not any(
            "preprint" in _strings(item.get("filters", {}).get("work_types"))
            for item in routes if isinstance(item, dict)):
        issues.append(_issue(
            "major", "missing_recent_preprint_route",
            "A04 must preserve an approved preprint search route", "query_plan.routes",
        ))
    tool_results, tool_issues = canonical._hydrate_operations(output, base=base)
    issues.extend(tool_issues)
    result_by_operation = {item.get("operation_id"): item for item in tool_results}
    expected_operation_scope = {
        "input_contract": RECENT_INPUT_CONTRACT,
        "task_id": recent_input.get("task_id"),
        "topic_id": topic.get("topic_id"),
        "research_plan_ref": recent_input.get("research_plan_ref"),
        "domain_candidates_ref": recent_input.get("domain_candidates_ref"),
    }
    for index, result in enumerate(tool_results):
        request = result.get("request") if isinstance(result.get("request"), dict) else {}
        if request.get("scope") != expected_operation_scope:
            issues.append(_issue(
                "blocker", "recent_operation_scope_mismatch",
                "referenced tool result was not executed for this exact A04 scope",
                f"operation_log[{index}].literature_tool_result_ref",
            ))
    expected_provider_issues = [{
        "operation_id": result.get("operation_id"), "provider": result.get("provider"),
        "status": result.get("status"), "issues": deepcopy(result.get("issues", [])),
    } for result in tool_results if result.get("status") in {"partial", "unavailable", "failed"}]
    if output.get("provider_issues") != expected_provider_issues:
        issues.append(_issue(
            "major", "recent_provider_issues_mismatch",
            "provider_issues must exactly preserve all non-ok operations", "provider_issues",
        ))
    log = output.get("operation_log") if isinstance(output.get("operation_log"), list) else []
    operation_ids = [item.get("operation_id") for item in log if isinstance(item, dict)
                     and isinstance(item.get("operation_id"), str)]
    if _duplicates(operation_ids):
        issues.append(_issue(
            "major", "duplicate_recent_operation", "operation IDs must be unique", "operation_log",
        ))
    logged_routes = {item.get("route_id") for item in log if isinstance(item, dict)
                     and item.get("operation_type") == "metadata_search"}
    if set(route_map) - logged_routes:
        issues.append(_issue(
            "major", "unexecuted_recent_query_route",
            f"routes lack operations {sorted(set(route_map)-logged_routes)}", "operation_log",
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
        unknown_log = sorted(set(entry) - allowed_log_fields)
        if unknown_log:
            issues.append(_issue(
                "major", "unknown_recent_operation_log_fields",
                f"unsupported operation-log fields {unknown_log}", f"operation_log[{index}]",
            ))
        result = result_by_operation.get(entry.get("operation_id"), {})
        request = result.get("request") if isinstance(result.get("request"), dict) else {}
        if entry.get("operation_type") == "metadata_search":
            route = route_map.get(entry.get("route_id"))
            if not isinstance(route, dict) or entry.get("query_id") != route.get("query_id") \
                    or request.get("canonical_query") != route.get("canonical_query") \
                    or request.get("filters") != route.get("filters") \
                    or not isinstance(request.get("limit"), int) \
                    or request.get("limit") < 1 \
                    or request.get("limit") > route.get("limit", 0) \
                    or entry.get("provider") not in route.get("preferred_providers", []):
                issues.append(_issue(
                    "blocker", "recent_metadata_operation_scope_mismatch",
                    "metadata operation differs from its authorized route",
                    f"operation_log[{index}]",
                ))
        elif entry.get("operation_type") == "citation_expand":
            limit = request.get("limit")
            if entry.get("seed_source_id") not in recent_input.get("verified_seed_ids", []) \
                    or request.get("depth") != 1 \
                    or entry.get("relation") not in recent_input.get(
                        "search_limits", {}
                    ).get("allowed_relations", []) \
                    or not isinstance(limit, int) \
                    or limit < 1 \
                    or limit > recent_input.get("search_limits", {}).get(
                        "per_seed_relation_limit", 0
                    ):
                issues.append(_issue(
                    "blocker", "recent_citation_operation_scope_mismatch",
                    "citation operation exceeds A04 seed, relation, depth or limit scope",
                    f"operation_log[{index}]",
                ))
    authorized_records: dict[str, list[dict]] = {}
    for record in recent_input.get("domain_candidates", []):
        if isinstance(record, dict) and isinstance(record.get("source_id"), str):
            authorized_records.setdefault(record["source_id"], []).append(record)
    citation_operations_by_source: dict[str, set[str]] = {}
    for result in tool_results:
        for record in result.get("records", []):
            if isinstance(record, dict) and isinstance(record.get("source_id"), str):
                authorized_records.setdefault(record["source_id"], []).append(record)
                if result.get("operation_type") == "citation_expand":
                    citation_operations_by_source.setdefault(record["source_id"], set()).add(
                        result.get("operation_id")
                    )
    candidates = output.get("candidates") if isinstance(output.get("candidates"), list) else []
    if "doi_verifications" in output:
        for error in crossref.validate_bindings(
                candidates, output.get("doi_verifications"), base=base):
            issues.append(_issue(
                "blocker", "invalid_doi_verification", error, "doi_verifications"
            ))
    candidate_ids = [item.get("source_id") for item in candidates if isinstance(item, dict)
                     and isinstance(item.get("source_id"), str)]
    candidate_map = {item.get("source_id"): item for item in candidates if isinstance(item, dict)}
    if _duplicates(candidate_ids):
        issues.append(_issue(
            "major", "duplicate_recent_candidate", "candidate IDs must be unique", "candidates",
        ))
    limit = recent_input.get("search_limits", {}).get("candidate_limit")
    if isinstance(limit, int) and len(candidates) > limit:
        issues.append(_issue(
            "major", "recent_candidate_limit_exceeded",
            f"candidate count exceeds {limit}", "candidates",
        ))
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            continue
        location = f"candidates[{index}]"
        shape = contracts.validate(candidate, SOURCE_RECORD_CONTRACT)
        for error in shape["errors"]:
            issues.append(_issue("blocker", "invalid_recent_source_record", error, location))
        source_id = candidate.get("source_id")
        if source_id not in authorized_records:
            issues.append(_issue(
                "blocker", "recent_candidate_without_provider_record",
                "candidate is absent from reviewed A02 and referenced operations", location,
            ))
        elif candidate not in authorized_records[source_id]:
            issues.append(_issue(
                "blocker", "recent_provider_metadata_modified",
                "candidate differs from every authorized provider record", location,
            ))
        year = candidate.get("bibliographic", {}).get("year")
        if not isinstance(year, int) or not window.get("year_from", 0) <= year <= window.get(
                "year_to", -1):
            issues.append(_issue(
                "blocker", "recent_candidate_outside_window",
                "candidate publication year must lie inside the frozen window", location,
            ))
    annotations = output.get("recent_annotations") \
        if isinstance(output.get("recent_annotations"), list) else []
    annotation_ids = [item.get("source_id") for item in annotations if isinstance(item, dict)
                      and isinstance(item.get("source_id"), str)]
    if _duplicates(annotation_ids) or set(annotation_ids) != set(candidate_ids):
        issues.append(_issue(
            "major", "recent_annotation_coverage_mismatch",
            "every candidate requires exactly one recent annotation", "recent_annotations",
        ))
    required_roles = set(_strings(recent_input.get("required_roles")))
    target_coverage = set(_strings(recent_input.get("target_coverage_units")))
    known_claims = set(_strings(topic.get("related_claims")))
    annotation_coverage: dict[str, set[str]] = {}
    for index, annotation in enumerate(annotations):
        if not isinstance(annotation, dict):
            continue
        location = f"recent_annotations[{index}]"
        source_id = annotation.get("source_id")
        record = candidate_map.get(source_id, {})
        assignments = annotation.get("role_assignments") \
            if isinstance(annotation.get("role_assignments"), list) else []
        assigned = {item.get("role") for item in assignments if isinstance(item, dict)}
        if not assignments or not assigned & required_roles:
            issues.append(_issue(
                "major", "missing_required_recent_role",
                "candidate needs a required recent role", f"{location}.role_assignments",
            ))
        record_access = record.get("access") if isinstance(record.get("access"), dict) else {}
        for assignment_index, assignment in enumerate(assignments):
            if not isinstance(assignment, dict):
                continue
            if not _strings(assignment.get("observed_signals")):
                issues.append(_issue(
                    "major", "recent_role_without_signal", "role requires observed signals",
                    f"{location}.role_assignments[{assignment_index}]",
                ))
            if topic.get("topic_id") not in _strings(assignment.get("topic_ids")):
                issues.append(_issue(
                    "major", "recent_role_topic_mismatch", "role must map to scoped topic",
                    f"{location}.role_assignments[{assignment_index}].topic_ids",
                ))
            if set(_strings(assignment.get("claim_ids"))) - known_claims:
                issues.append(_issue(
                    "blocker", "recent_role_claim_mismatch", "role contains an unknown claim ID",
                    f"{location}.role_assignments[{assignment_index}].claim_ids",
                ))
            if assignment.get("role") == "claim_specific" \
                    and not _strings(assignment.get("claim_ids")):
                issues.append(_issue(
                    "major", "claim_specific_role_without_claim",
                    "claim_specific requires at least one approved claim ID",
                    f"{location}.role_assignments[{assignment_index}].claim_ids",
                ))
            assignment_coverage = set(_strings(assignment.get("coverage_unit_ids")))
            if not assignment_coverage or assignment_coverage - target_coverage:
                issues.append(_issue(
                    "major", "recent_role_coverage_mismatch",
                    "role coverage must be non-empty and target-scoped",
                    f"{location}.role_assignments[{assignment_index}].coverage_unit_ids",
                ))
            if _access_rank(assignment.get("access_basis")) \
                    > _access_rank(record_access.get("access_level")):
                issues.append(_issue(
                    "blocker", "recent_role_access_exceeded",
                    "role uses evidence richer than provider access", f"{location}.role_assignments",
                ))
        recency = annotation.get("recency_basis") \
            if isinstance(annotation.get("recency_basis"), dict) else {}
        year = record.get("bibliographic", {}).get("year")
        expected_recency = {
            "publication_year": year, "window_year_from": window.get("year_from"),
            "window_year_to": window.get("year_to"), "within_window": True,
        }
        if recency != expected_recency:
            issues.append(_issue(
                "blocker", "recent_recency_basis_mismatch",
                "recency basis must exactly preserve year and window", f"{location}.recency_basis",
            ))
        publication = annotation.get("publication_status") \
            if isinstance(annotation.get("publication_status"), dict) else {}
        expected_preprint, expected_peer = _expected_publication_status(record)
        if publication.get("preprint_status") != expected_preprint \
                or publication.get("peer_review_status") != expected_peer \
                or not isinstance(publication.get("basis"), str) \
                or not publication["basis"].strip():
            issues.append(_issue(
                "blocker", "recent_publication_status_mismatch",
                "preprint and peer-review status must conservatively match provider metadata",
                f"{location}.publication_status",
            ))
        relations = annotation.get("citation_relations") \
            if isinstance(annotation.get("citation_relations"), list) else []
        actual_relation_ops = set()
        for relation_index, relation in enumerate(relations):
            if not isinstance(relation, dict):
                continue
            operation_id = relation.get("operation_id")
            actual_relation_ops.add(operation_id)
            result = result_by_operation.get(operation_id, {})
            request = result.get("request") if isinstance(result.get("request"), dict) else {}
            returned_ids = {item.get("source_id") for item in result.get("records", [])
                            if isinstance(item, dict)}
            if relation.get("distance") != 1 \
                    or relation.get("seed_source_id") not in recent_input.get(
                        "verified_seed_ids", []
                    ) \
                    or result.get("operation_type") != "citation_expand" \
                    or relation.get("seed_source_id") != request.get("seed_source_id") \
                    or relation.get("relation") != request.get("relation") \
                    or relation.get("provider") != result.get("provider") \
                    or source_id not in returned_ids:
                issues.append(_issue(
                    "blocker", "invalid_recent_citation_provenance",
                    "citation relation must match the operation that returned this candidate",
                    f"{location}.citation_relations[{relation_index}]",
                ))
        if citation_operations_by_source.get(source_id, set()) - actual_relation_ops:
            issues.append(_issue(
                "major", "missing_recent_citation_provenance",
                "candidate must retain every introducing citation operation",
                f"{location}.citation_relations",
            ))
        maturity = annotation.get("maturity_assessment") \
            if isinstance(annotation.get("maturity_assessment"), dict) else {}
        signals = maturity.get("observed_signals") \
            if isinstance(maturity.get("observed_signals"), list) else []
        content = record.get("content_available") \
            if isinstance(record.get("content_available"), dict) else {}
        record_signals = record.get("signals") if isinstance(record.get("signals"), dict) else {}
        provenance = record.get("provenance") if isinstance(record.get("provenance"), dict) else {}
        for signal_index, signal in enumerate(signals):
            if not isinstance(signal, dict):
                continue
            kind = signal.get("signal_type")
            observed = str(signal.get("observed_value", ""))
            expected_evidence_source = {
                "citation_count": "metadata",
                "recent_citation_velocity": "metadata",
                "review_work_type": "metadata",
                "multi_provider_presence": "metadata",
                "abstract_scope": "abstract",
                "citation_relation": "citation_relation",
                "publication_status": "metadata",
            }.get(kind)
            unsupported = signal.get("evidence_source") != expected_evidence_source or (
                kind == "citation_count" and (
                    record_signals.get("cited_by_count") is None
                    or not re.search(
                        rf"(?<!\d){re.escape(str(record_signals.get('cited_by_count')))}(?!\d)",
                        observed,
                    )
                )
            ) or (
                kind == "recent_citation_velocity" and (
                    record_signals.get("recent_citation_velocity") is None
                    or str(record_signals.get("recent_citation_velocity")) not in observed
                )
            ) or (kind == "review_work_type" and record.get("bibliographic", {}).get(
                "work_type"
            ) != "review") or (
                kind == "multi_provider_presence"
                and len(_strings(provenance.get("source_apis"))) < 2
            ) or (
                kind == "abstract_scope" and not (
                    isinstance(content.get("abstract"), str) and content["abstract"].strip()
                )
            ) or (kind == "citation_relation" and not relations) or (
                kind == "publication_status"
                and expected_preprint not in observed and expected_peer not in observed
            )
            if unsupported:
                issues.append(_issue(
                    "blocker", "unsupported_recent_maturity_signal",
                    "maturity signal is not present in provider-backed evidence",
                    f"{location}.maturity_assessment.observed_signals[{signal_index}]",
                ))
        level = maturity.get("level")
        signal_types = {item.get("signal_type") for item in signals if isinstance(item, dict)}
        if (level == "established" and len(signals) < 2) \
                or (level in {"emerging", "developing"} and not signals) \
                or (level == "unknown" and signals):
            issues.append(_issue(
                "major", "recent_maturity_signal_count_mismatch",
                "maturity level is inconsistent with observed signals",
                f"{location}.maturity_assessment",
            ))
        update = annotation.get("update_classification") \
            if isinstance(annotation.get("update_classification"), dict) else {}
        update_class = update.get("class")
        if not _strings(update.get("basis")):
            issues.append(_issue(
                "major", "recent_update_without_basis", "update class requires explicit basis",
                f"{location}.update_classification",
            ))
        if update_class == "core_update" and (
                level != "established" or len(signals) < 2
                or "abstract_scope" not in signal_types
                or expected_preprint != "not_preprint"
                or not isinstance(content.get("abstract"), str)
                or not content.get("abstract", "").strip()):
            issues.append(_issue(
                "blocker", "unsupported_core_update",
                "core_update requires established multi-signal, non-preprint abstract evidence",
                f"{location}.update_classification",
            ))
        if annotation.get("quality_status") != "not_assessed":
            issues.append(_issue(
                "blocker", "recent_quality_conflation",
                "A04 must leave scientific quality as not_assessed", f"{location}.quality_status",
            ))
        coverage_ids = set(_strings(annotation.get("coverage_unit_ids")))
        if not coverage_ids or coverage_ids - target_coverage:
            issues.append(_issue(
                "major", "invalid_recent_coverage",
                "annotation coverage must be non-empty and targeted",
                f"{location}.coverage_unit_ids",
            ))
        if isinstance(source_id, str):
            annotation_coverage[source_id] = coverage_ids
    coverage_map = output.get("coverage_map") \
        if isinstance(output.get("coverage_map"), list) else []
    map_ids = [item.get("source_id") for item in coverage_map if isinstance(item, dict)
               and isinstance(item.get("source_id"), str)]
    if _duplicates(map_ids) or set(map_ids) != set(candidate_ids):
        issues.append(_issue(
            "major", "recent_coverage_map_mismatch",
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
                "major", "recent_coverage_annotation_mismatch",
                "coverage map must equal recent annotation", f"coverage_map[{index}]",
            ))
        for unit in units:
            coverage_sources.setdefault(unit, set()).add(source_id)
    requirements = topic.get("coverage_requirements") \
        if isinstance(topic.get("coverage_requirements"), list) else []
    expected_remaining = {item["coverage_id"] for item in requirements if isinstance(item, dict)
                          and item.get("coverage_id") in target_coverage
                          and len(coverage_sources.get(item["coverage_id"], set()))
                          < (item.get("minimum_sources")
                             if isinstance(item.get("minimum_sources"), int) else 1)}
    remaining = set(_strings(output.get("remaining_coverage_units")))
    if remaining != expected_remaining:
        issues.append(_issue(
            "major", "recent_remaining_coverage_mismatch",
            f"remaining coverage must equal {sorted(expected_remaining)}",
            "remaining_coverage_units",
        ))
    if output.get("unresolved_seed_ids") != []:
        issues.append(_issue(
            "major", "unexpected_recent_unresolved_seeds",
            "A04 does not resolve plan seed identities; unresolved_seed_ids must be empty",
            "unresolved_seed_ids",
        ))
    stop = output.get("stop_reason")
    if stop == "completed" and (remaining or output.get("provider_issues")):
        issues.append(_issue(
            "major", "completed_with_recent_gaps",
            "completed requires no coverage gaps or provider issues", "stop_reason",
        ))
    if stop == "candidate_limit" and isinstance(limit, int) and len(candidates) < limit:
        issues.append(_issue(
            "major", "recent_candidate_limit_not_reached",
            "candidate_limit requires the configured count", "stop_reason",
        ))
    if stop == "provider_unavailable" and candidates:
        issues.append(_issue(
            "major", "recent_provider_unavailable_with_candidates",
            "provider_unavailable is reserved for an empty usable pool", "stop_reason",
        ))
    if stop == "partial_coverage" and not remaining and not output.get("provider_issues"):
        issues.append(_issue(
            "major", "recent_partial_without_gap",
            "partial_coverage requires a gap or provider issue", "stop_reason",
        ))
    verification_degraded = any(
        item.get("status") != "ok" or item.get("match_status") == "conflict"
        for item in output.get("doi_verifications", []) if isinstance(item, dict)
    )
    complete = not remaining and not output.get("provider_issues") and not verification_degraded
    return {"ok": not issues, "complete": complete, "issues": issues}


def _safe_segment(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()) or "unknown"


def finalize_recent_candidates(recent_input: dict, output: object, *, base=None,
                               previous_candidates: dict | None = None,
                               revision_items: list[dict] | None = None) -> dict:
    validation = validate_recent_candidates(
        output, recent_input, base=base, previous_candidates=previous_candidates,
        revision_items=revision_items,
    )
    if not validation["ok"]:
        return _envelope(
            "failed", "RecentCandidateSources failed deterministic validation.",
            validation["issues"],
        )
    assert isinstance(output, dict)
    ref = artifacts.store(
        f"g02/recent-candidates/{_safe_segment(output['task_id'])}."
        f"{_safe_segment(output['topic_id'])}.{_safe_segment(output['artifact_version'])}.json",
        output, base=base,
    )
    descriptor = {
        "type": "candidate_sources", "path": ref,
        "schema_version": RECENT_OUTPUT_CONTRACT,
        "artifact_version": output["artifact_version"],
    }
    status = "ok" if validation["complete"] else "degraded"
    return _envelope(
        status,
        f"Stored {len(output['candidates'])} recent candidates for {output['topic_id']}.", [],
        produced=[descriptor],
        metrics={
            "candidate_count": len(output["candidates"]),
            "operation_count": len(output["operation_log"]),
            "remaining_coverage_count": len(output["remaining_coverage_units"]),
        },
        resume_token=ref if status == "degraded" else None,
    )


def build_recent_review_task(recent_input: dict, artifact_descriptor: dict, *, review_id: str,
                             attempt: int = 1, previous_decision_ref: str | None = None,
                             producer_revision_response: dict | None = None, base=None) -> dict:
    basis = validate_recent_basis(recent_input, base=base)
    if not basis["ok"]:
        raise ValueError("invalid recent input: " + "; ".join(
            item["message"] for item in basis["issues"]
        ))
    if not isinstance(artifact_descriptor, dict):
        raise ValueError("artifact descriptor must be an object")
    ref = artifact_descriptor.get("path") or artifact_descriptor.get("ref")
    if artifact_descriptor.get("type") != "candidate_sources" \
            or artifact_descriptor.get("schema_version") != RECENT_OUTPUT_CONTRACT \
            or not isinstance(ref, str) or not ref.startswith(artifacts.SCHEME):
        raise ValueError("artifact descriptor must identify recent candidate_sources@1")
    artifact = artifacts.hydrate(ref, base=base)
    validation = validate_recent_candidates(artifact, recent_input, base=base)
    if not validation["ok"]:
        raise ValueError("recent artifact is not reviewable: " + "; ".join(
            item["message"] for item in validation["issues"]
        ))
    if artifact.get("artifact_version") != artifact_descriptor.get("artifact_version"):
        raise ValueError("artifact descriptor version differs from stored recent artifact")
    task = {
        "schema_version": "review_task@1", "review_id": review_id,
        "task_id": recent_input["task_id"],
        "logical_review_node": "g02-a04-recent-developments-review",
        "producer_agent": RECENT_AGENT, "attempt": attempt,
        "review_profile": REVIEW_PROFILE,
        "original_task": {
            "objective": "Extend one reviewed domain pool with defensible recent developments.",
            "input_contract": RECENT_INPUT_CONTRACT,
            "output_contract": RECENT_OUTPUT_CONTRACT,
        },
        "producer_input": deepcopy(recent_input),
        "artifact": {
            "type": "candidate_sources", "ref": ref,
            "schema_version": RECENT_OUTPUT_CONTRACT,
            "artifact_version": artifact["artifact_version"],
        },
        "expected_output_contract": RECENT_OUTPUT_CONTRACT,
        "acceptance_criteria": deepcopy(RECENT_ACCEPTANCE_CRITERIA),
        "evidence_requirements": deepcopy(RECENT_EVIDENCE_REQUIREMENTS),
        "prohibited_behaviors": deepcopy(RECENT_PROHIBITED_BEHAVIORS),
        "severity_rules": deepcopy(RECENT_SEVERITY_RULES),
        "previous_decision_ref": previous_decision_ref,
        "producer_revision_response": producer_revision_response,
    }
    from g02 import review
    checked = review.validate_review_task(task)
    if not checked["ok"]:
        raise ValueError("invalid recent review task: " + "; ".join(
            item["message"] for item in checked["issues"]
        ))
    return task


def execute_recent(research_plan_ref: str, domain_candidates_ref: str, topic_id: str,
                   recent_executor: Callable | None, *, base=None,
                   config_path: str | Path | None = None,
                   runtime_home: str | Path | None = None,
                   previous_candidates_ref: str | None = None,
                   revision_items: list[dict] | None = None) -> dict:
    prepared = prepare_recent(
        research_plan_ref, domain_candidates_ref, topic_id,
        config_path=config_path, runtime_home=runtime_home, artifact_base=base,
        previous_candidates_ref=previous_candidates_ref, revision_items=revision_items,
    )
    if not prepared["ready"]:
        return prepared["envelope"]
    if recent_executor is None:
        return failed_envelope(
            "recent_executor_unavailable", "no G02-A04 host executor is configured",
        )
    try:
        output = recent_executor(
            prepared["recent_input"],
            {
                "previous_candidates": prepared["previous_candidates"],
                "previous_candidates_ref": prepared["previous_candidates_ref"],
                "revision_items": prepared["revision_items"],
            },
        )
    except Exception as exc:
        return failed_envelope("recent_executor_failed", str(exc))
    return finalize_recent_candidates(
        prepared["recent_input"], output, base=base,
        previous_candidates=prepared["previous_candidates"],
        revision_items=prepared["revision_items"],
    )
