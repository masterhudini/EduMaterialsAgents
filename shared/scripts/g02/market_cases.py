"""Scoped preparation, validation and review-task construction for G02-A11 Market Cases."""
from __future__ import annotations

import re
from copy import deepcopy
try:
    from datetime import UTC, datetime
except ImportError:  # Python < 3.11
    from datetime import datetime, timezone
    UTC = timezone.utc
from pathlib import Path
from typing import Callable

from core import artifacts, contracts
from g02 import provider_config, query_planning

MARKET_INPUT_CONTRACT = "market_case_research_input@1"
MARKET_OUTPUT_CONTRACT = "candidate_sources@1"
DOMAIN_OUTPUT_CONTRACT = "domain_candidate_sources@1"
RESEARCH_PLAN_CONTRACT = "research_plan@1"
SOURCE_RECORD_CONTRACT = "source_record@1"
WEB_TOOL_RESULT_CONTRACT = "web_case_tool_result@1"
MARKET_AGENT = "g02-a11-market-cases"
REVIEW_PROFILE = "market_cases"
MARKET_ROLES = {"applied_case", "qualifying_or_critical"}
WEB_WORK_TYPES = ["news", "report", "regulatory_filing", "court_document", "annual_report"]
TIERS = {"tier_1_authoritative", "tier_2_reputable_media", "tier_3_signal_only"}

MARKET_ACCEPTANCE_CRITERIA = [
    {
        "criterion_id": "MC-01", "mandatory": True,
        "description": "Every case has an identified institution or event, a date and a higher-tier source, or is explicitly weakly sourced.",
    },
    {
        "criterion_id": "MC-02", "mandatory": True,
        "description": "Every case maps to the approved topic or claim with one explicit didactic mechanism.",
    },
    {
        "criterion_id": "MC-03", "mandatory": True,
        "description": "Provider-observed market facts remain separate from didactic interpretation.",
    },
    {
        "criterion_id": "MC-04", "mandatory": True,
        "description": "Documented events and weak signals are distinguished from anecdotes, which are excluded.",
    },
    {
        "criterion_id": "MC-05", "mandatory": True,
        "description": "Event date and regime context are explicit, including historical-regime limitations.",
    },
    {
        "criterion_id": "MC-06", "mandatory": True,
        "description": "Source tier, absent DOI, provider degradation and provenance are explicit without generated metadata.",
    },
]
MARKET_EVIDENCE_REQUIREMENTS = [
    {
        "requirement_id": "MC-E01", "mandatory": True,
        "description": "Every candidate is byte-for-byte equal to a normalized record in a scoped web operation.",
    },
    {
        "requirement_id": "MC-E02", "mandatory": True,
        "description": "Identity, evidence type, materiality and market fact cite exact title, snippet, date or URL observations.",
    },
    {
        "requirement_id": "MC-E03", "mandatory": True,
        "description": "Every operation ref binds task, topic, ResearchPlan and reviewed A02 artifact exactly.",
    },
]
MARKET_PROHIBITED_BEHAVIORS = [
    "Direct HTTP, WebSearch, WebFetch or browser use by the producer agent.",
    "Extraction of page content before a confirmed Human Source Selection Gate.",
    "Mutation of provider records or generation of missing dates, institutions or metadata.",
    "Use of a random public SearXNG instance or a provider result from another scope.",
    "Presentation of an anecdote or tier-3 signal as a documented market case.",
]
MARKET_SEVERITY_RULES = {
    "minor": "Wording or non-material annotation issue with intact identity and provenance.",
    "major": "Correctable coverage, tier, materiality or mapping defect.",
    "blocker": "Invalid scope, modified record, fabricated observation, unsafe provider path or pre-gate extraction.",
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
        return [_issue("blocker", code, str(exc), contract_ref)]
    return [_issue("blocker", code, error, contract_ref) for error in checked["errors"]]


def _envelope(status: str, summary: str, issues: list[dict], *, produced=None,
              metrics=None, resume_token=None) -> dict:
    result = {
        "status": status, "produced": produced or [], "summary": summary, "issues": issues,
    }
    if metrics is not None:
        result["metrics"] = metrics
    if resume_token is not None:
        result["resume_token"] = resume_token
    return result


def failed_envelope(issue_type: str, message: str, location: str = "market_cases") -> dict:
    return _envelope(
        "failed", "Market-case discovery failed deterministic validation.",
        [_issue("blocker", issue_type, message, location)],
    )


def needs_input_envelope(issue_type: str, message: str, location: str) -> dict:
    return _envelope(
        "needs_input", "Market-case discovery is missing an approved upstream artifact.",
        [_issue("blocker", issue_type, message, location)],
    )


def _scope_not_requested() -> dict:
    return _envelope(
        "ok", "Market-case discovery is not requested for this approved topic.", [],
        metrics={"skipped": True},
    )


def _safe_segment(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()) or "unknown"


def _derive_market_scope(plan: dict, topic: dict,
                         config: provider_config.ProviderRuntimeConfig) -> dict:
    projected_topic = deepcopy(topic)
    strategy = projected_topic.get("search_strategy")
    if not isinstance(strategy, dict):
        raise ValueError("approved topic search_strategy is unavailable")
    strategy["work_types"] = list(WEB_WORK_TYPES)

    requirements = projected_topic.get("coverage_requirements") \
        if isinstance(projected_topic.get("coverage_requirements"), list) else []
    target = [item["coverage_id"] for item in requirements if isinstance(item, dict)
              and isinstance(item.get("coverage_id"), str)]
    if not target:
        raise ValueError("approved topic has no market-case coverage basis")
    linked_claims = list(dict.fromkeys(_strings(topic.get("related_claims"))))
    linked_drivers = _strings(topic.get("linked_driver_ids"))
    linked_updates = _strings(topic.get("related_update_needs"))
    needs = []
    for item in requirements:
        if not isinstance(item, dict) or item.get("coverage_id") not in target:
            continue
        roles = set(_strings(item.get("source_roles")))
        if "qualifying_or_critical" in roles:
            need_type = "failure_or_critical"
        elif "didactic" in roles:
            need_type = "didactic_example"
        else:
            need_type = "applied_use"
        coverage_id = item["coverage_id"]
        needs.append({
            "need_id": f"MC_NEED_{coverage_id}",
            "coverage_unit_id": coverage_id,
            "claim_ids": deepcopy(linked_claims),
            "need_type": need_type,
            "description": str(item.get("description", "")).strip(),
            "origin_ids": list(dict.fromkeys(
                [coverage_id, *linked_claims, *linked_drivers, *linked_updates]
            )),
        })

    role_flags = topic.get("source_roles_required") \
        if isinstance(topic.get("source_roles_required"), dict) else {}
    roles = ["applied_case"]
    if role_flags.get("qualifying_or_critical") is True:
        roles.append("qualifying_or_critical")

    web = config.data.get("web")
    assert isinstance(web, dict)
    limits = web.get("limits")
    tiers = web.get("source_tiers")
    assert isinstance(limits, dict) and isinstance(tiers, dict)
    tier_1 = [item.casefold().rstrip(".") for item in _strings(tiers.get("tier_1_domains"))]
    tier_2 = [item.casefold().rstrip(".") for item in _strings(tiers.get("tier_2_domains"))]
    tier_3 = [item.casefold().rstrip(".") for item in _strings(tiers.get("tier_3_domains"))]
    excluded = [item.casefold().rstrip(".") for item in _strings(tiers.get("excluded_domains"))]
    plan_limit = topic.get("stop_rule", {}).get("candidate_limit")
    if not isinstance(plan_limit, int) or isinstance(plan_limit, bool):
        plan_limit = 20
    route_limit = min(8, int(limits["max_queries_per_task"]))
    result_limit = int(limits["max_results_per_query"])
    no_new = topic.get("stop_rule", {}).get("no_new_coverage_passes")
    if not isinstance(no_new, int) or isinstance(no_new, bool) or no_new < 1:
        no_new = 2
    public_web = config.public_web_status()
    return {
        "topic": projected_topic,
        "linked_claim_ids": linked_claims,
        "market_case_needs": needs,
        "required_roles": roles,
        "target_coverage_units": target,
        "search_limits": {
            "candidate_limit": min(plan_limit, route_limit * result_limit),
            "route_limit": route_limit,
            "max_queries": int(limits["max_queries_per_task"]),
            "max_results_per_route": result_limit,
            "no_new_coverage_passes": no_new,
        },
        "source_tier_policy": {
            "tier_1_domains": tier_1,
            "tier_2_domains": tier_2,
            "tier_3_domains": tier_3,
            "allowed_domains": list(dict.fromkeys([*tier_1, *tier_2, *tier_3])),
            "excluded_domains": excluded,
            "require_higher_tier_confirmation": True,
        },
        "provider_mode": public_web["mode"],
        "provider_capabilities": deepcopy(public_web["capabilities"]),
    }


def validate_market_case_input(market_input: object) -> dict:
    issues = _shape_issues(
        market_input, MARKET_INPUT_CONTRACT, "invalid_market_case_input_contract"
    )
    if not isinstance(market_input, dict):
        return {"ok": False, "issues": issues}
    allowed = {
        "schema_version", "task_id", "research_plan_ref", "research_plan_artifact_version",
        "domain_candidates_ref", "domain_candidates_artifact_version", "topic",
        "linked_claim_ids", "market_case_needs", "required_roles", "target_coverage_units",
        "search_limits", "source_tier_policy", "provider_mode", "provider_capabilities",
        "output_language",
    }
    unknown = sorted(set(market_input) - allowed)
    if unknown:
        issues.append(_issue(
            "blocker", "unknown_market_case_input_fields", f"unsupported fields {unknown}",
            "market_case_input",
        ))
    for field in (
        "task_id", "research_plan_ref", "research_plan_artifact_version",
        "domain_candidates_ref", "domain_candidates_artifact_version", "output_language",
    ):
        value = market_input.get(field)
        if not isinstance(value, str) or not value.strip():
            issues.append(_issue(
                "blocker", "empty_market_case_input_field", f"{field} must not be empty", field,
            ))
    for field in ("research_plan_ref", "domain_candidates_ref"):
        value = market_input.get(field)
        if isinstance(value, str) and not value.startswith(artifacts.SCHEME):
            issues.append(_issue(
                "blocker", "invalid_market_case_artifact_ref", f"{field} must use artifact://",
                field,
            ))
    topic = market_input.get("topic") if isinstance(market_input.get("topic"), dict) else {}
    coverage = topic.get("coverage_requirements") \
        if isinstance(topic.get("coverage_requirements"), list) else []
    coverage_ids = {item.get("coverage_id") for item in coverage if isinstance(item, dict)}
    target = _strings(market_input.get("target_coverage_units"))
    if not target or _duplicates(target) or set(target) - coverage_ids:
        issues.append(_issue(
            "blocker", "invalid_market_case_target_coverage",
            "target coverage must be non-empty, unique and approved", "target_coverage_units",
        ))
    claims = _strings(market_input.get("linked_claim_ids"))
    if _duplicates(claims) or set(claims) != set(_strings(topic.get("related_claims"))):
        issues.append(_issue(
            "blocker", "market_case_claim_scope_mismatch",
            "linked claims must exactly preserve the approved topic claim IDs", "linked_claim_ids",
        ))
    needs = market_input.get("market_case_needs") \
        if isinstance(market_input.get("market_case_needs"), list) else []
    need_ids = [item.get("need_id") for item in needs if isinstance(item, dict)
                and isinstance(item.get("need_id"), str)]
    need_coverage = [item.get("coverage_unit_id") for item in needs if isinstance(item, dict)]
    if not needs or _duplicates(need_ids) or set(need_coverage) != set(target):
        issues.append(_issue(
            "blocker", "invalid_market_case_needs",
            "market-case needs must map uniquely across the target coverage", "market_case_needs",
        ))
    for index, need in enumerate(needs):
        if not isinstance(need, dict):
            continue
        if set(_strings(need.get("claim_ids"))) - set(claims) \
                or not _strings(need.get("origin_ids")) \
                or need.get("coverage_unit_id") not in target:
            issues.append(_issue(
                "blocker", "untraceable_market_case_need",
                "each need must trace to approved claim, driver, update or coverage IDs",
                f"market_case_needs[{index}]",
            ))
    roles = _strings(market_input.get("required_roles"))
    if not roles or _duplicates(roles) or set(roles) - MARKET_ROLES \
            or "applied_case" not in roles:
        issues.append(_issue(
            "blocker", "invalid_market_case_roles", "A11 requires the applied_case role",
            "required_roles",
        ))
    limits = market_input.get("search_limits") \
        if isinstance(market_input.get("search_limits"), dict) else {}
    for field in (
        "candidate_limit", "route_limit", "max_queries", "max_results_per_route",
        "no_new_coverage_passes",
    ):
        value = limits.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            issues.append(_issue(
                "blocker", "invalid_market_case_search_limit", f"{field} must be positive",
                f"search_limits.{field}",
            ))
    if isinstance(limits.get("route_limit"), int) and isinstance(limits.get("max_queries"), int) \
            and limits["route_limit"] > limits["max_queries"]:
        issues.append(_issue(
            "blocker", "market_case_route_budget_mismatch",
            "route_limit cannot exceed max_queries", "search_limits",
        ))
    policy = market_input.get("source_tier_policy") \
        if isinstance(market_input.get("source_tier_policy"), dict) else {}
    tier_sets = [set(_strings(policy.get(field))) for field in (
        "tier_1_domains", "tier_2_domains", "tier_3_domains"
    )]
    allowed_domains = set(_strings(policy.get("allowed_domains")))
    if not allowed_domains or allowed_domains != set().union(*tier_sets):
        issues.append(_issue(
            "blocker", "invalid_market_case_domain_policy",
            "allowed domains must exactly equal the administrator tier lists",
            "source_tier_policy",
        ))
    if any(tier_sets[i] & tier_sets[j] for i in range(3) for j in range(i + 1, 3)):
        issues.append(_issue(
            "blocker", "overlapping_market_case_tiers",
            "a domain cannot appear in multiple source tiers", "source_tier_policy",
        ))
    capabilities = market_input.get("provider_capabilities") \
        if isinstance(market_input.get("provider_capabilities"), list) else []
    capability_names = [item.get("provider") for item in capabilities if isinstance(item, dict)
                        and isinstance(item.get("provider"), str)]
    if _duplicates(capability_names):
        issues.append(_issue(
            "blocker", "duplicate_market_provider_capability",
            "provider capabilities must contain one entry per mode", "provider_capabilities",
        ))
    mode = market_input.get("provider_mode")
    if not any(isinstance(item, dict) and item.get("provider") == mode
               and item.get("enabled") is True and item.get("ready") is True
               for item in capabilities):
        issues.append(_issue(
            "blocker", "no_ready_market_case_provider",
            "the prepared web provider mode must be ready", "provider_capabilities",
        ))
    return {"ok": not issues, "issues": issues}


def validate_market_case_basis(market_input: object, *, base=None,
                               config: provider_config.ProviderRuntimeConfig | None = None,
                               config_path: str | Path | None = None,
                               runtime_home: str | Path | None = None) -> dict:
    checked = validate_market_case_input(market_input)
    issues = list(checked["issues"])
    if not isinstance(market_input, dict):
        return {"ok": False, "issues": issues}
    try:
        active_config = config or provider_config.load_config(
            config_path, runtime_home=runtime_home, create_dirs=True
        )
        plan = artifacts.hydrate(market_input["research_plan_ref"], base=base)
        domain_pool = artifacts.hydrate(market_input["domain_candidates_ref"], base=base)
        for payload, contract_ref in (
            (plan, RESEARCH_PLAN_CONTRACT), (domain_pool, DOMAIN_OUTPUT_CONTRACT),
        ):
            shape = contracts.validate(payload, contract_ref)
            if not shape["ok"]:
                raise ValueError("; ".join(shape["errors"]))
    except (provider_config.ProviderConfigError, OSError, ValueError, KeyError, IndexError) as exc:
        issues.append(_issue(
            "blocker", "unreadable_market_case_basis", str(exc), "market_case_input",
        ))
        return {"ok": False, "issues": issues}
    topic_id = market_input.get("topic", {}).get("topic_id")
    topics = [item for item in plan.get("topics", []) if isinstance(item, dict)
              and item.get("topic_id") == topic_id]
    if len(topics) != 1:
        issues.append(_issue(
            "blocker", "market_case_topic_basis_mismatch",
            "approved topic cannot be resolved", "topic",
        ))
        return {"ok": False, "issues": issues}
    approved_topic = topics[0]
    if plan.get("approved_research_scope", {}).get("include_didactic_examples") is not True:
        issues.append(_issue(
            "blocker", "market_case_scope_not_approved",
            "didactic examples were not approved in intake", "approved_research_scope",
        ))
    if domain_pool.get("task_id") != plan.get("task_id") \
            or domain_pool.get("topic_id") != topic_id \
            or domain_pool.get("research_plan_ref") != market_input.get("research_plan_ref"):
        issues.append(_issue(
            "blocker", "market_case_domain_basis_mismatch",
            "reviewed A02 candidates do not match the plan and topic", "domain_candidates_ref",
        ))
    try:
        derived = _derive_market_scope(plan, approved_topic, active_config)
    except ValueError as exc:
        issues.append(_issue(
            "blocker", "invalid_market_case_scope_projection", str(exc), "market_case_input",
        ))
        derived = {}
    for field, expected in derived.items():
        if market_input.get(field) != expected:
            issues.append(_issue(
                "blocker", "market_case_scope_projection_mismatch",
                f"{field} differs from the deterministic A11 projection", field,
            ))
    for field, expected in (
        ("task_id", plan.get("task_id")),
        ("research_plan_artifact_version", plan.get("artifact_version")),
        ("domain_candidates_artifact_version", domain_pool.get("artifact_version")),
        ("output_language", plan.get("output_language")),
    ):
        if market_input.get(field) != expected:
            issues.append(_issue(
                "blocker", "market_case_basis_identity_mismatch",
                f"{field} differs from approved upstream artifacts", field,
            ))
    return {"ok": not issues, "issues": issues}


def prepare_market_cases(research_plan_ref: str, domain_candidates_ref: str, topic_id: str, *,
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
            "invalid_market_case_upstream", str(exc), "upstream_refs",
        )}
    topics = [item for item in plan.get("topics", []) if isinstance(item, dict)
              and item.get("topic_id") == topic_id]
    if len(topics) != 1:
        return {"ready": False, "envelope": needs_input_envelope(
            "unknown_or_duplicate_topic",
            f"expected exactly one topic {topic_id!r}, found {len(topics)}", "topic_id",
        )}
    topic = topics[0]
    if domain_pool.get("task_id") != plan.get("task_id") \
            or domain_pool.get("topic_id") != topic_id \
            or domain_pool.get("research_plan_ref") != research_plan_ref:
        return {"ready": False, "envelope": failed_envelope(
            "market_case_upstream_identity_mismatch",
            "DomainCandidateSources does not match the approved plan and topic",
            "domain_candidates_ref",
        )}
    role_flags = topic.get("source_roles_required") \
        if isinstance(topic.get("source_roles_required"), dict) else {}
    approved = plan.get("approved_research_scope", {}).get("include_didactic_examples") is True
    requested = bool(_strings(topic.get("related_claims"))) \
        or role_flags.get("didactic") is True \
        or role_flags.get("qualifying_or_critical") is True
    if not approved or not requested:
        return {"ready": False, "skipped": True, "envelope": _scope_not_requested()}
    try:
        config = provider_config.load_config(
            config_path, runtime_home=runtime_home, create_dirs=True
        )
        derived = _derive_market_scope(plan, topic, config)
    except (provider_config.ProviderConfigError, ValueError) as exc:
        return {"ready": False, "envelope": failed_envelope(
            "market_case_preparation_failed", str(exc), "market_case_scope",
        )}
    market_input = {
        "schema_version": MARKET_INPUT_CONTRACT,
        "task_id": plan["task_id"],
        "research_plan_ref": research_plan_ref,
        "research_plan_artifact_version": plan["artifact_version"],
        "domain_candidates_ref": domain_candidates_ref,
        "domain_candidates_artifact_version": domain_pool["artifact_version"],
        **derived,
        "output_language": plan["output_language"],
    }
    checked = validate_market_case_input(market_input)
    if not checked["ok"]:
        return {"ready": False, "envelope": failed_envelope(
            "invalid_scoped_market_case_input",
            "; ".join(item["message"] for item in checked["issues"]), "market_case_input",
        )}
    previous = None
    if previous_candidates_ref is not None:
        try:
            if not isinstance(previous_candidates_ref, str) \
                    or not previous_candidates_ref.startswith(artifacts.SCHEME):
                raise ValueError("previous_candidates_ref must use artifact://")
            previous = artifacts.hydrate(previous_candidates_ref, base=artifact_base)
            shape = contracts.validate(previous, MARKET_OUTPUT_CONTRACT)
            if not shape["ok"]:
                raise ValueError("; ".join(shape["errors"]))
            if previous.get("stream") != "market_cases" \
                    or previous.get("task_id") != plan["task_id"] \
                    or previous.get("topic_id") != topic_id:
                raise ValueError("previous market candidates do not match task and topic")
        except (OSError, ValueError, KeyError, IndexError) as exc:
            return {"ready": False, "envelope": failed_envelope(
                "invalid_previous_market_candidates", str(exc), "previous_candidates_ref",
            )}
    if revision_items and previous is None:
        return {"ready": False, "envelope": failed_envelope(
            "missing_previous_market_candidates",
            "revision_items require previous_candidates_ref", "revision_items",
        )}
    if revision_items is not None and (
            not isinstance(revision_items, list)
            or any(not isinstance(item, dict) for item in revision_items)):
        return {"ready": False, "envelope": failed_envelope(
            "invalid_market_revision_items", "revision_items must be a list of findings",
            "revision_items",
        )}
    for index, item in enumerate(revision_items or []):
        for field in ("finding_id", "location", "required_correction"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                return {"ready": False, "envelope": failed_envelope(
                    "invalid_market_revision_item",
                    f"revision_items[{index}].{field} must be non-empty", "revision_items",
                )}
    return {
        "ready": True, "market_case_input": market_input,
        "config_status": config.public_status(), "previous_candidates": previous,
        "previous_candidates_ref": previous_candidates_ref,
        "revision_items": deepcopy(revision_items or []),
    }


def _revision_fields(revision_items: list[dict] | None) -> set[str]:
    mutable = {
        "query_plan", "candidates", "market_case_annotations", "operation_log",
        "coverage_map", "remaining_coverage_units", "provider_issues", "stop_reason",
    }
    targeted: set[str] = set()
    for item in revision_items or []:
        location = item.get("location") if isinstance(item, dict) else None
        if isinstance(location, str):
            targeted.update(field for field in mutable
                            if re.search(rf"(?:^|\.){re.escape(field)}(?:\.|\[|$)", location))
    order = [
        "query_plan", "operation_log", "candidates", "market_case_annotations",
        "coverage_map", "provider_issues", "remaining_coverage_units", "stop_reason",
    ]
    expanded = set(targeted)
    for field in targeted:
        if field in order:
            expanded.update(order[order.index(field):])
    return expanded


def _hydrate_operations(output: dict, *, base=None) -> tuple[list[dict], list[dict]]:
    results: list[dict] = []
    issues: list[dict] = []
    for index, entry in enumerate(output.get("operation_log", [])):
        if not isinstance(entry, dict):
            continue
        ref = entry.get("web_case_tool_result_ref")
        location = f"operation_log[{index}]"
        if not isinstance(ref, str) or not ref.startswith(artifacts.SCHEME):
            issues.append(_issue(
                "blocker", "invalid_web_case_tool_result_ref",
                "web operation result ref must use artifact://",
                f"{location}.web_case_tool_result_ref",
            ))
            continue
        try:
            result = artifacts.hydrate(ref, base=base)
            shape = contracts.validate(result, WEB_TOOL_RESULT_CONTRACT)
            if not shape["ok"]:
                raise ValueError("; ".join(shape["errors"]))
        except (OSError, ValueError, KeyError, IndexError) as exc:
            issues.append(_issue(
                "blocker", "unreadable_web_case_tool_result", str(exc),
                f"{location}.web_case_tool_result_ref",
            ))
            continue
        expected = {
            "operation_id": result.get("operation_id"),
            "operation_type": result.get("operation_type"),
            "provider": result.get("provider"),
            "status": result.get("status"),
            "result_count": len(result.get("records", [])),
            "route_id": result.get("request", {}).get("route_id"),
            "query_id": result.get("request", {}).get("query_id"),
        }
        for field, value in expected.items():
            if entry.get(field) != value:
                issues.append(_issue(
                    "blocker", "market_operation_log_mismatch",
                    f"{field} does not match referenced web result", f"{location}.{field}",
                ))
        results.append(result)
    return results, issues


def _observation_text(record: dict, source_field: object) -> str | None:
    if source_field == "title":
        value = record.get("bibliographic", {}).get("title")
    elif source_field == "snippet":
        value = record.get("content_available", {}).get("abstract")
    elif source_field == "provider_date":
        value = record.get("web_case", {}).get("provider_date")
    elif source_field == "source_url":
        value = record.get("access", {}).get("publisher_url")
    else:
        return None
    return value if isinstance(value, str) and value.strip() else None


def _basis_supported(items: object, record: dict) -> bool:
    if not isinstance(items, list) or not items:
        return False
    for item in items:
        if not isinstance(item, dict):
            return False
        observed = _observation_text(record, item.get("source_field"))
        evidence = item.get("evidence_text")
        if observed is None or not isinstance(evidence, str) or not evidence.strip() \
                or evidence.casefold() not in observed.casefold():
            return False
    return True


def validate_market_case_candidates(output: object, market_input: dict, *, base=None,
                                    config_path: str | Path | None = None,
                                    runtime_home: str | Path | None = None,
                                    previous_candidates: dict | None = None,
                                    revision_items: list[dict] | None = None) -> dict:
    issues = _shape_issues(
        output, MARKET_OUTPUT_CONTRACT, "invalid_market_candidates_contract"
    )
    basis = validate_market_case_basis(
        market_input, base=base, config_path=config_path, runtime_home=runtime_home
    )
    issues.extend(basis["issues"])
    if not isinstance(output, dict):
        return {"ok": False, "complete": False, "issues": issues}
    allowed = {
        "schema_version", "artifact_version", "stream", "task_id", "topic_id",
        "research_plan_ref", "upstream_refs", "query_plan", "candidates",
        "market_case_annotations", "operation_log", "coverage_map",
        "remaining_coverage_units", "provider_issues", "unresolved_seed_ids",
        "stop_reason", "review_profile_ref",
    }
    unknown = sorted(set(output) - allowed)
    if unknown:
        issues.append(_issue(
            "major", "unknown_market_output_fields", f"unsupported fields {unknown}",
            "market_output",
        ))
    topic = market_input.get("topic") if isinstance(market_input.get("topic"), dict) else {}
    for field, expected in (
        ("stream", "market_cases"), ("task_id", market_input.get("task_id")),
        ("topic_id", topic.get("topic_id")),
        ("research_plan_ref", market_input.get("research_plan_ref")),
        ("review_profile_ref", REVIEW_PROFILE),
    ):
        if output.get(field) != expected:
            issues.append(_issue(
                "blocker", "market_output_identity_mismatch",
                f"{field} must equal the scoped input", field,
            ))
    if output.get("upstream_refs") != {
        "domain_candidate_sources": market_input.get("domain_candidates_ref")
    }:
        issues.append(_issue(
            "blocker", "market_upstream_ref_mismatch",
            "upstream_refs must contain exactly the reviewed A02 ref", "upstream_refs",
        ))
    if not isinstance(output.get("market_case_annotations"), list):
        issues.append(_issue(
            "blocker", "missing_market_case_annotations",
            "market_case_annotations must be an array", "market_case_annotations",
        ))
    version = output.get("artifact_version")
    if not isinstance(version, str) or not version.strip():
        issues.append(_issue(
            "major", "empty_market_artifact_version", "artifact_version must not be empty",
            "artifact_version",
        ))
    if previous_candidates is not None and version == previous_candidates.get("artifact_version"):
        issues.append(_issue(
            "major", "market_artifact_version_not_advanced",
            "a revision must advance artifact_version", "artifact_version",
        ))
    if previous_candidates is not None:
        targeted = _revision_fields(revision_items)
        if revision_items and not targeted:
            issues.append(_issue(
                "major", "invalid_market_revision_target",
                "review findings do not identify an A11 output field that may be revised",
                "revision_items",
            ))
        for field in output:
            if field != "artifact_version" and field not in targeted \
                    and output.get(field) != previous_candidates.get(field):
                issues.append(_issue(
                    "major", "unscoped_market_revision_change",
                    f"untargeted field {field!r} changed", field,
                ))

    query_plan = output.get("query_plan")
    query_checked = query_planning.validate_query_plan(query_plan, market_input)
    for item in query_checked["issues"]:
        issues.append(_issue(
            "major", item["code"], item["message"], f"query_plan.{item['location']}",
        ))
    routes = query_plan.get("routes", []) if isinstance(query_plan, dict) else []
    route_map = {item.get("route_id"): item for item in routes if isinstance(item, dict)}

    tool_results, tool_issues = _hydrate_operations(output, base=base)
    issues.extend(tool_issues)
    result_by_operation = {item.get("operation_id"): item for item in tool_results}
    expected_scope = {
        "input_contract": MARKET_INPUT_CONTRACT,
        "task_id": market_input.get("task_id"),
        "topic_id": topic.get("topic_id"),
        "research_plan_ref": market_input.get("research_plan_ref"),
        "domain_candidates_ref": market_input.get("domain_candidates_ref"),
    }
    for index, result in enumerate(tool_results):
        request = result.get("request") if isinstance(result.get("request"), dict) else {}
        if request.get("scope") != expected_scope:
            issues.append(_issue(
                "blocker", "market_operation_scope_mismatch",
                "referenced web result was not executed for this exact A11 scope",
                f"operation_log[{index}].web_case_tool_result_ref",
            ))
    expected_provider_issues = [{
        "operation_id": result.get("operation_id"), "provider": result.get("provider"),
        "status": result.get("status"), "issues": deepcopy(result.get("issues", [])),
    } for result in tool_results if result.get("status") in {"partial", "unavailable", "failed"}]
    if output.get("provider_issues") != expected_provider_issues:
        issues.append(_issue(
            "major", "market_provider_issues_mismatch",
            "provider_issues must exactly preserve every non-ok web operation", "provider_issues",
        ))
    log = output.get("operation_log") if isinstance(output.get("operation_log"), list) else []
    operation_ids = [item.get("operation_id") for item in log if isinstance(item, dict)
                     and isinstance(item.get("operation_id"), str)]
    if _duplicates(operation_ids):
        issues.append(_issue(
            "major", "duplicate_market_operation", "operation IDs must be unique", "operation_log",
        ))
    logged_routes = {item.get("route_id") for item in log if isinstance(item, dict)}
    logged_route_values = [item.get("route_id") for item in log if isinstance(item, dict)
                           and isinstance(item.get("route_id"), str)]
    if _duplicates(logged_route_values) or logged_routes != set(route_map):
        issues.append(_issue(
            "major", "unexecuted_market_query_route",
            "every route requires exactly one operation and no extra route may be logged",
            "operation_log",
        ))
    for index, entry in enumerate(log):
        if not isinstance(entry, dict):
            continue
        allowed_log = {
            "operation_id", "operation_type", "provider", "status", "result_count",
            "web_case_tool_result_ref", "route_id", "query_id",
        }
        unknown_log = sorted(set(entry) - allowed_log)
        if unknown_log:
            issues.append(_issue(
                "major", "unknown_market_operation_log_fields",
                f"unsupported operation-log fields {unknown_log}", f"operation_log[{index}]",
            ))
        result = result_by_operation.get(entry.get("operation_id"), {})
        request = result.get("request") if isinstance(result.get("request"), dict) else {}
        route = route_map.get(entry.get("route_id"))
        if entry.get("operation_type") != "web_case_search" \
                or not isinstance(route, dict) \
                or entry.get("query_id") != route.get("query_id") \
                or entry.get("provider") != market_input.get("provider_mode") \
                or request.get("canonical_query") != route.get("canonical_query") \
                or request.get("filters") != route.get("filters") \
                or request.get("web") != route.get("web") \
                or request.get("limit", 0) > route.get("limit", 0):
            issues.append(_issue(
                "blocker", "market_web_operation_route_mismatch",
                "web operation differs from its authorized A11 route", f"operation_log[{index}]",
            ))

    authorized_records: dict[str, list[dict]] = {}
    for result in tool_results:
        for record in result.get("records", []):
            if isinstance(record, dict) and isinstance(record.get("source_id"), str):
                authorized_records.setdefault(record["source_id"], []).append(record)
    candidates = output.get("candidates") if isinstance(output.get("candidates"), list) else []
    candidate_ids = [item.get("source_id") for item in candidates if isinstance(item, dict)
                     and isinstance(item.get("source_id"), str)]
    candidate_map = {item.get("source_id"): item for item in candidates if isinstance(item, dict)}
    if _duplicates(candidate_ids):
        issues.append(_issue(
            "major", "duplicate_market_candidate", "candidate IDs must be unique", "candidates",
        ))
    candidate_limit = market_input.get("search_limits", {}).get("candidate_limit")
    if isinstance(candidate_limit, int) and len(candidates) > candidate_limit:
        issues.append(_issue(
            "major", "market_candidate_limit_exceeded",
            f"candidate count exceeds {candidate_limit}", "candidates",
        ))
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            continue
        location = f"candidates[{index}]"
        shape = contracts.validate(candidate, SOURCE_RECORD_CONTRACT)
        for error in shape["errors"]:
            issues.append(_issue("blocker", "invalid_market_source_record", error, location))
        source_id = candidate.get("source_id")
        if source_id not in authorized_records:
            issues.append(_issue(
                "blocker", "market_candidate_without_provider_record",
                "candidate is absent from referenced web operations", location,
            ))
        elif candidate not in authorized_records[source_id]:
            issues.append(_issue(
                "blocker", "market_provider_record_modified",
                "candidate differs from every authorized provider record", location,
            ))
        if candidate.get("record_type") != "market_case" \
                or candidate.get("access", {}).get("access_level") != "web_page":
            issues.append(_issue(
                "blocker", "invalid_market_record_type",
                "A11 candidates must be provider-backed market_case web records", location,
            ))

    annotations = output.get("market_case_annotations") \
        if isinstance(output.get("market_case_annotations"), list) else []
    annotation_ids = [item.get("source_id") for item in annotations if isinstance(item, dict)
                      and isinstance(item.get("source_id"), str)]
    if _duplicates(annotation_ids) or set(annotation_ids) != set(candidate_ids):
        issues.append(_issue(
            "major", "market_annotation_identity_mismatch",
            "every candidate requires exactly one market-case annotation",
            "market_case_annotations",
        ))
    target_coverage = set(_strings(market_input.get("target_coverage_units")))
    known_claims = set(_strings(market_input.get("linked_claim_ids")))
    annotation_coverage: dict[str, set[str]] = {}
    material_candidates: set[str] = set()
    for index, annotation in enumerate(annotations):
        if not isinstance(annotation, dict):
            continue
        location = f"market_case_annotations[{index}]"
        source_id = annotation.get("source_id")
        record = candidate_map.get(source_id)
        if not isinstance(record, dict):
            continue
        assignments = annotation.get("role_assignments") \
            if isinstance(annotation.get("role_assignments"), list) else []
        if not assignments:
            issues.append(_issue(
                "major", "market_role_missing", "each case requires a supported role", location,
            ))
        for assignment_index, assignment in enumerate(assignments):
            if not isinstance(assignment, dict):
                continue
            if assignment.get("role") not in set(_strings(market_input.get("required_roles"))) \
                    or topic.get("topic_id") not in _strings(assignment.get("topic_ids")) \
                    or set(_strings(assignment.get("claim_ids"))) - known_claims \
                    or not _strings(assignment.get("observed_signals")):
                issues.append(_issue(
                    "major", "invalid_market_role_assignment",
                    "role must use supported observations and approved topic/claim IDs",
                    f"{location}.role_assignments[{assignment_index}]",
                ))
            assignment_coverage = set(_strings(assignment.get("coverage_unit_ids")))
            if not assignment_coverage or assignment_coverage - target_coverage:
                issues.append(_issue(
                    "major", "invalid_market_role_coverage",
                    "role coverage must be non-empty and A11-scoped",
                    f"{location}.role_assignments[{assignment_index}].coverage_unit_ids",
                ))
        identity = annotation.get("case_identity") \
            if isinstance(annotation.get("case_identity"), dict) else {}
        event_date = identity.get("event_date")
        identity_basis = identity.get("observed_basis") \
            if isinstance(identity.get("observed_basis"), list) else []
        date_observed = any(
            isinstance(item, dict) and isinstance(item.get("evidence_text"), str)
            and isinstance(event_date, str)
            and (event_date in item["evidence_text"] or event_date[:4] in item["evidence_text"])
            for item in identity_basis
        )
        if not isinstance(identity.get("institution_or_event"), str) \
                or not identity.get("institution_or_event", "").strip() \
                or not isinstance(identity.get("event_label"), str) \
                or not identity.get("event_label", "").strip() \
                or not isinstance(event_date, str) \
                or not re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", event_date) \
                or not _basis_supported(identity_basis, record) or not date_observed:
            issues.append(_issue(
                "blocker", "unsupported_market_case_identity",
                "institution/event, label and date require exact provider-observation basis",
                f"{location}.case_identity",
            ))
        evidence = annotation.get("evidence_type") \
            if isinstance(annotation.get("evidence_type"), dict) else {}
        if not _basis_supported(evidence.get("basis"), record):
            issues.append(_issue(
                "blocker", "unsupported_market_evidence_type",
                "evidence type requires exact provider-observation basis",
                f"{location}.evidence_type",
            ))
        assessment = annotation.get("source_assessment") \
            if isinstance(annotation.get("source_assessment"), dict) else {}
        record_tier = record.get("web_case", {}).get("source_tier")
        corroborators = _strings(assessment.get("corroborating_source_ids"))
        high_tier_corroborators = [item for item in corroborators
                                   if candidate_map.get(item, {}).get("web_case", {}).get(
                                       "source_tier") in {
                                           "tier_1_authoritative", "tier_2_reputable_media"
                                       }]
        expected_weak = record_tier == "tier_3_signal_only" and not high_tier_corroborators
        if assessment.get("source_tier") != record_tier \
                or assessment.get("weakly_sourced") is not expected_weak \
                or set(corroborators) - set(candidate_ids) \
                or not isinstance(assessment.get("tier_basis"), str) \
                or not assessment.get("tier_basis", "").strip():
            issues.append(_issue(
                "blocker", "market_source_tier_mismatch",
                "tier and weak-source status must preserve provider observations",
                f"{location}.source_assessment",
            ))
        materiality = annotation.get("materiality_assessment") \
            if isinstance(annotation.get("materiality_assessment"), dict) else {}
        higher_expected = record_tier in {
            "tier_1_authoritative", "tier_2_reputable_media"
        } or bool(high_tier_corroborators)
        passes_expected = materiality.get("scale_observed") is True \
            and materiality.get("real_consequence_observed") is True \
            and higher_expected
        if materiality.get("higher_tier_confirmation") is not higher_expected \
                or materiality.get("passes_threshold") is not passes_expected \
                or not _basis_supported(materiality.get("basis"), record):
            issues.append(_issue(
                "blocker", "unsupported_market_materiality",
                "materiality must preserve observed scale, consequence and higher-tier confirmation",
                f"{location}.materiality_assessment",
            ))
        if passes_expected and isinstance(source_id, str):
            material_candidates.add(source_id)
        documentation = annotation.get("documentation_status")
        expected_documentation = "documented" if passes_expected else "weak_signal"
        if documentation != expected_documentation or documentation == "anecdote":
            issues.append(_issue(
                "blocker", "market_documentation_status_mismatch",
                "material cases are documented, non-material tier-3 results remain weak signals, and anecdotes are excluded",
                f"{location}.documentation_status",
            ))
        market_fact = annotation.get("market_fact") \
            if isinstance(annotation.get("market_fact"), dict) else {}
        interpretation = annotation.get("didactic_interpretation") \
            if isinstance(annotation.get("didactic_interpretation"), dict) else {}
        if not isinstance(market_fact.get("statement"), str) \
                or not market_fact.get("statement", "").strip() \
                or not _basis_supported(market_fact.get("basis"), record):
            issues.append(_issue(
                "blocker", "unsupported_market_fact",
                "market fact requires exact provider-observation basis", f"{location}.market_fact",
            ))
        interpretation_topics = _strings(interpretation.get("topic_ids"))
        interpretation_claims = _strings(interpretation.get("claim_ids"))
        if not isinstance(interpretation.get("mechanism"), str) \
                or not interpretation.get("mechanism", "").strip() \
                or topic.get("topic_id") not in interpretation_topics \
                or set(interpretation_claims) - known_claims \
                or (not interpretation_claims and not interpretation_topics) \
                or interpretation.get("mechanism", "").strip() == market_fact.get(
                    "statement", ""
                ).strip():
            issues.append(_issue(
                "major", "invalid_market_didactic_mapping",
                "didactic mechanism must be separate from fact and map to approved topic or claim",
                f"{location}.didactic_interpretation",
            ))
        regime = annotation.get("regime_context") \
            if isinstance(annotation.get("regime_context"), dict) else {}
        event_year = int(event_date[:4]) if isinstance(event_date, str) \
            and re.match(r"^\d{4}", event_date) else None
        old_case = isinstance(event_year, int) and event_year < datetime.now(UTC).year - 10
        if not isinstance(regime.get("note"), str) or not regime.get("note", "").strip() \
                or not isinstance(regime.get("basis"), str) or not regime.get("basis", "").strip() \
                or (old_case and regime.get("status") == "current_regime"):
            issues.append(_issue(
                "major", "invalid_market_regime_context",
                "regime context must be explicit and older cases cannot claim the current regime without evidence",
                f"{location}.regime_context",
            ))
        coverage_ids = set(_strings(annotation.get("coverage_unit_ids")))
        record_coverage = set(_strings(record.get("inclusion", {}).get("coverage_units")))
        if not coverage_ids or coverage_ids - target_coverage \
                or coverage_ids - record_coverage:
            issues.append(_issue(
                "major", "invalid_market_coverage",
                "annotation coverage must be non-empty, targeted and introduced by its route",
                f"{location}.coverage_unit_ids",
            ))
        if annotation.get("quality_status") != "not_assessed" \
                or annotation.get("doi_status") != "absent" \
                or record.get("identifiers", {}).get("doi") is not None:
            issues.append(_issue(
                "blocker", "market_quality_or_doi_conflation",
                "A11 leaves scientific quality unassessed and records the absent DOI explicitly",
                location,
            ))
        if isinstance(source_id, str):
            annotation_coverage[source_id] = coverage_ids

    coverage_map = output.get("coverage_map") \
        if isinstance(output.get("coverage_map"), list) else []
    map_ids = [item.get("source_id") for item in coverage_map if isinstance(item, dict)
               and isinstance(item.get("source_id"), str)]
    if _duplicates(map_ids) or set(map_ids) != set(candidate_ids):
        issues.append(_issue(
            "major", "market_coverage_map_mismatch",
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
                "major", "market_coverage_annotation_mismatch",
                "coverage map must equal the market annotation", f"coverage_map[{index}]",
            ))
        if source_id in material_candidates:
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
            "major", "market_remaining_coverage_mismatch",
            f"remaining coverage must equal {sorted(expected_remaining)}",
            "remaining_coverage_units",
        ))
    if output.get("unresolved_seed_ids") != []:
        issues.append(_issue(
            "major", "unexpected_market_unresolved_seeds",
            "A11 has no scholarly seed resolution; unresolved_seed_ids must be empty",
            "unresolved_seed_ids",
        ))
    stop = output.get("stop_reason")
    if stop == "completed" and (remaining or output.get("provider_issues")):
        issues.append(_issue(
            "major", "completed_with_market_gaps",
            "completed requires no coverage gaps or provider issues", "stop_reason",
        ))
    if stop == "candidate_limit" and isinstance(candidate_limit, int) \
            and len(candidates) < candidate_limit:
        issues.append(_issue(
            "major", "market_candidate_limit_not_reached",
            "candidate_limit requires the configured count", "stop_reason",
        ))
    if stop == "provider_unavailable" and candidates:
        issues.append(_issue(
            "major", "market_provider_unavailable_with_candidates",
            "provider_unavailable is reserved for an empty usable pool", "stop_reason",
        ))
    if stop == "partial_coverage" and not remaining and not output.get("provider_issues"):
        issues.append(_issue(
            "major", "market_partial_without_gap",
            "partial_coverage requires a gap or provider issue", "stop_reason",
        ))
    complete = not remaining and not output.get("provider_issues")
    return {"ok": not issues, "complete": complete, "issues": issues}


def finalize_market_case_candidates(market_input: dict, output: object, *, base=None,
                                    config_path: str | Path | None = None,
                                    runtime_home: str | Path | None = None,
                                    previous_candidates: dict | None = None,
                                    revision_items: list[dict] | None = None) -> dict:
    validation = validate_market_case_candidates(
        output, market_input, base=base, config_path=config_path, runtime_home=runtime_home,
        previous_candidates=previous_candidates, revision_items=revision_items,
    )
    if not validation["ok"]:
        return _envelope(
            "failed", "MarketCaseCandidateSources failed deterministic validation.",
            validation["issues"],
        )
    assert isinstance(output, dict)
    ref = artifacts.store(
        f"g02/market-case-candidates/{_safe_segment(output['task_id'])}."
        f"{_safe_segment(output['topic_id'])}.{_safe_segment(output['artifact_version'])}.json",
        output, base=base,
    )
    descriptor = {
        "type": "candidate_sources", "path": ref,
        "schema_version": MARKET_OUTPUT_CONTRACT,
        "artifact_version": output["artifact_version"],
    }
    status = "ok" if validation["complete"] else "degraded"
    return _envelope(
        status,
        f"Stored {len(output['candidates'])} market-case candidates for {output['topic_id']}.",
        [], produced=[descriptor],
        metrics={
            "candidate_count": len(output["candidates"]),
            "operation_count": len(output["operation_log"]),
            "remaining_coverage_count": len(output["remaining_coverage_units"]),
        },
        resume_token=ref if status == "degraded" else None,
    )


def build_market_case_review_task(market_input: dict, artifact_descriptor: dict, *,
                                  review_id: str, attempt: int = 1,
                                  previous_decision_ref: str | None = None,
                                  producer_revision_response: dict | None = None,
                                  base=None, config_path: str | Path | None = None,
                                  runtime_home: str | Path | None = None) -> dict:
    basis = validate_market_case_basis(
        market_input, base=base, config_path=config_path, runtime_home=runtime_home
    )
    if not basis["ok"]:
        raise ValueError("invalid market-case input: " + "; ".join(
            item["message"] for item in basis["issues"]
        ))
    if not isinstance(artifact_descriptor, dict):
        raise ValueError("artifact descriptor must be an object")
    ref = artifact_descriptor.get("path") or artifact_descriptor.get("ref")
    if artifact_descriptor.get("type") != "candidate_sources" \
            or artifact_descriptor.get("schema_version") != MARKET_OUTPUT_CONTRACT \
            or not isinstance(ref, str) or not ref.startswith(artifacts.SCHEME):
        raise ValueError("artifact descriptor must identify market candidate_sources@1")
    artifact = artifacts.hydrate(ref, base=base)
    validation = validate_market_case_candidates(
        artifact, market_input, base=base, config_path=config_path, runtime_home=runtime_home
    )
    if not validation["ok"]:
        raise ValueError("market artifact is not reviewable: " + "; ".join(
            item["message"] for item in validation["issues"]
        ))
    if artifact.get("artifact_version") != artifact_descriptor.get("artifact_version"):
        raise ValueError("artifact descriptor version differs from stored market artifact")
    task = {
        "schema_version": "review_task@1", "review_id": review_id,
        "task_id": market_input["task_id"],
        "logical_review_node": "g02-a11-market-cases-review",
        "producer_agent": MARKET_AGENT, "attempt": attempt,
        "review_profile": REVIEW_PROFILE,
        "original_task": {
            "objective": "Find auditable real, dated market cases for one reviewed research topic.",
            "input_contract": MARKET_INPUT_CONTRACT,
            "output_contract": MARKET_OUTPUT_CONTRACT,
        },
        "producer_input": deepcopy(market_input),
        "artifact": {
            "type": "candidate_sources", "ref": ref,
            "schema_version": MARKET_OUTPUT_CONTRACT,
            "artifact_version": artifact["artifact_version"],
        },
        "expected_output_contract": MARKET_OUTPUT_CONTRACT,
        "acceptance_criteria": deepcopy(MARKET_ACCEPTANCE_CRITERIA),
        "evidence_requirements": deepcopy(MARKET_EVIDENCE_REQUIREMENTS),
        "prohibited_behaviors": deepcopy(MARKET_PROHIBITED_BEHAVIORS),
        "severity_rules": deepcopy(MARKET_SEVERITY_RULES),
        "previous_decision_ref": previous_decision_ref,
        "producer_revision_response": producer_revision_response,
    }
    from g02 import review
    checked = review.validate_review_task(task)
    if not checked["ok"]:
        raise ValueError("invalid market review task: " + "; ".join(
            item["message"] for item in checked["issues"]
        ))
    return task


def execute_market_cases(research_plan_ref: str, domain_candidates_ref: str, topic_id: str,
                         market_executor: Callable | None, *, base=None,
                         config_path: str | Path | None = None,
                         runtime_home: str | Path | None = None,
                         previous_candidates_ref: str | None = None,
                         revision_items: list[dict] | None = None) -> dict:
    prepared = prepare_market_cases(
        research_plan_ref, domain_candidates_ref, topic_id,
        config_path=config_path, runtime_home=runtime_home, artifact_base=base,
        previous_candidates_ref=previous_candidates_ref, revision_items=revision_items,
    )
    if not prepared["ready"]:
        return prepared["envelope"]
    if market_executor is None:
        return failed_envelope(
            "market_case_executor_unavailable", "no G02-A11 host executor is configured",
        )
    try:
        output = market_executor(
            prepared["market_case_input"],
            {
                "previous_candidates": prepared["previous_candidates"],
                "previous_candidates_ref": prepared["previous_candidates_ref"],
                "revision_items": prepared["revision_items"],
            },
        )
    except Exception as exc:
        return failed_envelope("market_case_executor_failed", str(exc))
    return finalize_market_case_candidates(
        prepared["market_case_input"], output, base=base,
        config_path=config_path, runtime_home=runtime_home,
        previous_candidates=prepared["previous_candidates"],
        revision_items=prepared["revision_items"],
    )
