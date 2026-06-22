"""Deterministic boundary for G02-A01 Planner.

The module scopes and validates planner input, checks ``research_plan@1`` artifacts, persists
valid plans, prepares the universal reviewer task and standardizes the agent envelope. Semantic
topic grouping remains the responsibility of G02-A01 and its planning skill.

Pure stdlib. Host adapters call ``prepare_planner`` before the agent and
``finalize_research_plan`` after receiving its structured plan.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from copy import deepcopy

from core import artifacts, contracts

GRAPH_INPUT_CONTRACT = "research_graph_input@1"
PLANNER_INPUT_CONTRACT = "research_planner_input@1"
RESEARCH_PLAN_CONTRACT = "research_plan@1"
ENVELOPE_CONTRACT = "envelope@1"
PLANNER_AGENT = "g02-a01-planner"
REVIEWER_AGENT = "g02-a10-output-reviewer"
REVIEW_PROFILE = "research_plan"

PLANNER_FIELDS = (
    "task_id",
    "user_approved_context",
    "approved_domains",
    "approved_research_scope",
    "research_drivers",
    "claim_cards",
    "concept_context_cards",
    "selected_flow_issue_cards",
    "selected_update_need_cards",
    "existing_source_cards",
    "constraints",
    "selection_profile",
    "locked_sections",
    "artifact_refs_for_lazy_hydration",
    "output_language",
)

SOURCE_ROLES = {
    "canonical",
    "current",
    "survey",
    "didactic",
    "qualifying_or_critical",
}
PRIORITY_RANK = {"high": 3, "medium": 2, "low": 1}
TOPIC_ID_RE = re.compile(r"^TOPIC_[A-Z0-9][A-Z0-9_]*$")
COVERAGE_ID_RE = re.compile(r"^COV_[A-Z0-9][A-Z0-9_]*$")
FORBIDDEN_PLAN_KEYS = {
    "abstract",
    "authors",
    "bibliographic",
    "bibliography",
    "citation",
    "doi",
    "isbn",
    "publisher",
    "publications",
    "source_records",
    "title",
    "venue",
    "claim_verdict",
    "claim_verdicts",
    "slide_changes",
    "slide_edits",
}

RESEARCH_PLAN_ACCEPTANCE_CRITERIA = [
    {
        "criterion_id": "RP-01",
        "description": (
            "Every topic has a stable ID, bounded purpose, priority and at least one approved "
            "research driver."
        ),
        "mandatory": True,
    },
    {
        "criterion_id": "RP-02",
        "description": (
            "Every approved driver is covered by a topic or declared as an input issue; all "
            "high-priority drivers are covered before approval."
        ),
        "mandatory": True,
    },
    {
        "criterion_id": "RP-03",
        "description": (
            "Every topic declares required source roles and observable coverage units linked "
            "to the approved investigation."
        ),
        "mandatory": True,
    },
    {
        "criterion_id": "RP-04",
        "description": (
            "Every search strategy contains core terms, bounded expansions, exclusions and "
            "applicable date, language and work-type constraints."
        ),
        "mandatory": True,
    },
    {
        "criterion_id": "RP-05",
        "description": (
            "Every topic has configured candidate and saturation limits and requires a "
            "complementary search route before saturation."
        ),
        "mandatory": True,
    },
    {
        "criterion_id": "RP-06",
        "description": (
            "The plan preserves approved scope and contains no publication records, claim "
            "verdicts or slide solutions."
        ),
        "mandatory": True,
    },
]

RESEARCH_PLAN_EVIDENCE_REQUIREMENTS = [
    {
        "requirement_id": "RP-E01",
        "description": "Topic driver IDs resolve to the scoped planner input.",
        "mandatory": True,
    },
    {
        "requirement_id": "RP-E02",
        "description": "All upstream claim, concept, flow and update IDs remain unchanged.",
        "mandatory": True,
    },
    {
        "requirement_id": "RP-E03",
        "description": "Limits and allowed values can be traced to approved constraints.",
        "mandatory": True,
    },
    {
        "requirement_id": "RP-E04",
        "description": "Uncovered drivers point to explicit input issues and consequences.",
        "mandatory": True,
    },
]

RESEARCH_PLAN_PROHIBITED_BEHAVIORS = [
    "Expanding beyond approved domains, drivers, constraints or locked decisions.",
    "Inventing publication records or presenting search strategy as completed search.",
    "Verifying claims, judging evidence or proposing slide changes.",
    "Changing upstream identifiers or hiding uncovered drivers.",
]

RESEARCH_PLAN_SEVERITY_RULES = {
    "minor": "A local clarity or traceability defect that does not alter scope or coverage.",
    "major": "Missing driver coverage, source role, coverage unit, constraint or stop condition.",
    "blocker": (
        "Invalid approved input, scope expansion, fabricated records, contradictory review basis "
        "or an unreadable artifact."
    ),
}


def _issue(severity: str, issue_type: str, message: str, location: str) -> dict:
    return {
        "severity": severity,
        "type": issue_type,
        "message": message,
        "location": location,
    }


def _duplicates(values: list[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if _nonempty(item)]


def _card_ids(items: object, field: str) -> list[str]:
    if not isinstance(items, list):
        return []
    return [item[field] for item in items
            if isinstance(item, dict) and _nonempty(item.get(field))]


def _shape_issues(payload: object, contract_ref: str, issue_type: str) -> list[dict]:
    try:
        result = contracts.validate(payload, contract_ref)
    except (KeyError, ValueError) as exc:
        return [_issue("blocker", "contract_unavailable", str(exc), "schema_version")]
    return [
        _issue("blocker", issue_type, error, contract_ref)
        for error in result["errors"]
    ]


def scope_planner_input(graph_input: object) -> dict:
    """Validate the boundary shape and copy only fields authorized for G02-A01."""
    issues = _shape_issues(
        graph_input, GRAPH_INPUT_CONTRACT, "invalid_research_graph_input_contract"
    )
    if issues:
        raise ValueError("; ".join(item["message"] for item in issues))
    assert isinstance(graph_input, dict)
    scoped = {
        "schema_version": PLANNER_INPUT_CONTRACT,
        "source_input_contract": GRAPH_INPUT_CONTRACT,
    }
    for field in PLANNER_FIELDS:
        scoped[field] = deepcopy(graph_input[field])
    return scoped


def validate_planner_input(planner_input: object) -> dict:
    """Validate planner input shape and semantic completeness without hydrating artifacts."""
    issues = _shape_issues(
        planner_input, PLANNER_INPUT_CONTRACT, "invalid_planner_input_contract"
    )
    if not isinstance(planner_input, dict):
        return {"ok": False, "issues": issues}

    for field in ("task_id", "output_language"):
        if not _nonempty(planner_input.get(field)):
            issues.append(_issue(
                "blocker", "empty_required_value", f"{field} must not be empty", field
            ))

    context = planner_input.get("user_approved_context")
    if isinstance(context, dict):
        for field in ("audience_level", "course_name", "teaching_goal"):
            if not _nonempty(context.get(field)):
                issues.append(_issue(
                    "blocker", "incomplete_approved_context",
                    f"user_approved_context.{field} must not be empty",
                    f"user_approved_context.{field}",
                ))

    scope = planner_input.get("approved_research_scope")
    if not isinstance(scope, dict) or not scope:
        issues.append(_issue(
            "blocker", "missing_approved_research_scope",
            "approved_research_scope must be a non-empty object",
            "approved_research_scope",
        ))
    elif scope.get("include_recent_developments") is True:
        window = scope.get("recency_window_years")
        if not isinstance(window, int) or isinstance(window, bool) or window < 1:
            issues.append(_issue(
                "blocker", "invalid_recency_window",
                "recency_window_years must be a positive integer when recent discovery is enabled",
                "approved_research_scope.recency_window_years",
            ))

    domains = planner_input.get("approved_domains")
    domain_ids = _card_ids(domains, "domain_id")
    if not domain_ids:
        issues.append(_issue(
            "blocker", "missing_approved_domains",
            "at least one approved domain is required", "approved_domains",
        ))
    for duplicate in sorted(_duplicates(domain_ids)):
        issues.append(_issue(
            "blocker", "duplicate_domain_id", f"duplicate domain ID {duplicate!r}",
            "approved_domains",
        ))
    if isinstance(domains, list):
        for index, domain in enumerate(domains):
            if not isinstance(domain, dict) or not _nonempty(domain.get("domain_id")) \
                    or not _nonempty(domain.get("label")):
                issues.append(_issue(
                    "blocker", "invalid_approved_domain",
                    "every approved domain needs a non-empty domain_id and label",
                    f"approved_domains[{index}]",
                ))

    id_fields = {
        "related_claims": ("claim_cards", "claim_id"),
        "related_concepts": ("concept_context_cards", "concept_id"),
        "related_flow_issues": ("selected_flow_issue_cards", "issue_id"),
        "related_update_needs": ("selected_update_need_cards", "update_need_id"),
    }
    descriptive_fields = {
        "claim_cards": "text",
        "concept_context_cards": "label",
        "selected_flow_issue_cards": "summary",
        "selected_update_need_cards": "summary",
    }
    available: dict[str, set[str]] = {}
    for relation, (collection, id_field) in id_fields.items():
        cards = planner_input.get(collection)
        ids = _card_ids(cards, id_field)
        available[relation] = set(ids)
        if isinstance(cards, list):
            for index, card in enumerate(cards):
                if not isinstance(card, dict) or not _nonempty(card.get(id_field)):
                    issues.append(_issue(
                        "blocker", "invalid_upstream_card",
                        f"every {collection} item needs a non-empty {id_field}",
                        f"{collection}[{index}]",
                    ))
                elif not _nonempty(card.get(descriptive_fields[collection])):
                    issues.append(_issue(
                        "blocker", "incomplete_upstream_card",
                        f"every {collection} item needs a non-empty "
                        f"{descriptive_fields[collection]}",
                        f"{collection}[{index}].{descriptive_fields[collection]}",
                    ))
        for duplicate in sorted(_duplicates(ids)):
            issues.append(_issue(
                "blocker", "duplicate_upstream_id",
                f"duplicate {id_field} {duplicate!r}", collection,
            ))

    source_ids = _card_ids(planner_input.get("existing_source_cards"), "source_id")
    sources = planner_input.get("existing_source_cards")
    if isinstance(sources, list):
        for index, source in enumerate(sources):
            if not isinstance(source, dict) or not _nonempty(source.get("source_id")) \
                    or not _nonempty(source.get("label")):
                issues.append(_issue(
                    "blocker", "invalid_existing_source_card",
                    "every existing source card needs a non-empty source_id and label",
                    f"existing_source_cards[{index}]",
                ))
    for duplicate in sorted(_duplicates(source_ids)):
        issues.append(_issue(
            "blocker", "duplicate_source_id", f"duplicate source ID {duplicate!r}",
            "existing_source_cards",
        ))

    drivers = planner_input.get("research_drivers")
    drivers = drivers if isinstance(drivers, list) else []
    driver_ids = _card_ids(drivers, "driver_id")
    if not driver_ids:
        issues.append(_issue(
            "blocker", "missing_research_drivers",
            "at least one human-approved research driver is required", "research_drivers",
        ))
    for duplicate in sorted(_duplicates(driver_ids)):
        issues.append(_issue(
            "blocker", "duplicate_driver_id", f"duplicate driver ID {duplicate!r}",
            "research_drivers",
        ))
    for index, driver in enumerate(drivers):
        if not isinstance(driver, dict):
            issues.append(_issue(
                "blocker", "invalid_research_driver",
                "every research driver must be an object", f"research_drivers[{index}]",
            ))
            continue
        location = f"research_drivers[{index}]"
        if not _nonempty(driver.get("driver_id")):
            issues.append(_issue(
                "blocker", "empty_driver_id", "driver_id must not be empty",
                f"{location}.driver_id",
            ))
        if driver.get("driver_type") not in {
                "claim", "concept", "flow_issue", "update_need", "mixed"}:
            issues.append(_issue(
                "blocker", "invalid_driver_type", "driver_type is not supported",
                f"{location}.driver_type",
            ))
        if driver.get("priority") not in PRIORITY_RANK:
            issues.append(_issue(
                "blocker", "invalid_driver_priority", "driver priority is not supported",
                f"{location}.priority",
            ))
        if not _nonempty(driver.get("purpose")):
            issues.append(_issue(
                "blocker", "empty_driver_purpose", "driver purpose must not be empty",
                f"{location}.purpose",
            ))
        links = 0
        for relation in id_fields:
            values = driver.get(relation)
            if not isinstance(values, list):
                issues.append(_issue(
                    "blocker", "invalid_driver_links", f"{relation} must be an array",
                    f"{location}.{relation}",
                ))
                continue
            if any(not _nonempty(value) for value in values):
                issues.append(_issue(
                    "blocker", "empty_driver_link",
                    f"{relation} contains an empty or non-string ID",
                    f"{location}.{relation}",
                ))
            duplicates = sorted(_duplicates(_string_list(values)))
            if duplicates:
                issues.append(_issue(
                    "blocker", "duplicate_driver_link",
                    f"{relation} contains duplicate IDs {duplicates}",
                    f"{location}.{relation}",
                ))
            links += len(values)
            unknown = sorted({
                value for value in values
                if isinstance(value, str) and value not in available[relation]
            })
            if unknown:
                issues.append(_issue(
                    "blocker", "unknown_upstream_reference",
                    f"{relation} contains unknown IDs {unknown}", f"{location}.{relation}",
                ))
        if links == 0:
            issues.append(_issue(
                "blocker", "unlinked_research_driver",
                "every driver must link to at least one approved upstream card", location,
            ))
        primary_relation = {
            "claim": "related_claims",
            "concept": "related_concepts",
            "flow_issue": "related_flow_issues",
            "update_need": "related_update_needs",
        }.get(driver.get("driver_type"))
        if primary_relation and not _string_list(driver.get(primary_relation)):
            issues.append(_issue(
                "blocker", "driver_type_link_mismatch",
                f"driver_type {driver.get('driver_type')!r} requires {primary_relation}",
                f"{location}.{primary_relation}",
            ))

    constraints = planner_input.get("constraints")
    if isinstance(constraints, dict):
        for field in ("max_topics", "candidate_limit_per_topic", "no_new_coverage_passes"):
            value = constraints.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                issues.append(_issue(
                    "blocker", "invalid_planning_limit", f"{field} must be a positive integer",
                    f"constraints.{field}",
                ))
        year_from, year_to = constraints.get("year_from"), constraints.get("year_to")
        if isinstance(year_from, int) and isinstance(year_to, int) and year_from > year_to:
            issues.append(_issue(
                "blocker", "invalid_date_window", "year_from must not exceed year_to",
                "constraints",
            ))
        for field in ("allowed_languages", "allowed_work_types"):
            values = constraints.get(field)
            if not isinstance(values, list) or not values or not all(_nonempty(x) for x in values):
                issues.append(_issue(
                    "blocker", "empty_allowed_values", f"{field} must contain non-empty values",
                    f"constraints.{field}",
                ))

    selection = planner_input.get("selection_profile")
    if isinstance(selection, dict):
        for field in ("candidate_pool_target_per_topic", "minimum_sources_per_required_role"):
            value = selection.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                issues.append(_issue(
                    "blocker", "invalid_selection_limit",
                    f"selection_profile.{field} must be a positive integer",
                    f"selection_profile.{field}",
                ))
        if isinstance(constraints, dict):
            target = selection.get("candidate_pool_target_per_topic")
            limit = constraints.get("candidate_limit_per_topic")
            if isinstance(target, int) and isinstance(limit, int) and target > limit:
                issues.append(_issue(
                    "blocker", "selection_target_exceeds_limit",
                    "candidate pool target cannot exceed candidate limit",
                    "selection_profile.candidate_pool_target_per_topic",
                ))
        if selection.get("open_access_preference") not in {"required", "preferred", "neutral"}:
            issues.append(_issue(
                "blocker", "invalid_open_access_preference",
                "open_access_preference must be required, preferred or neutral",
                "selection_profile.open_access_preference",
            ))

    refs = planner_input.get("artifact_refs_for_lazy_hydration")
    if isinstance(refs, dict):
        for key, value in refs.items():
            if not _nonempty(value) or not value.startswith(artifacts.SCHEME):
                issues.append(_issue(
                    "blocker", "invalid_artifact_ref",
                    f"artifact ref {key!r} must use artifact://", 
                    f"artifact_refs_for_lazy_hydration.{key}",
                ))

    return {"ok": not issues, "issues": issues}


def _find_forbidden_keys(value: object, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key in FORBIDDEN_PLAN_KEYS:
                found.append(child_path)
            found.extend(_find_forbidden_keys(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_find_forbidden_keys(child, f"{path}[{index}]"))
    return found


def _topic_map(plan: dict) -> dict[str, dict]:
    topics = plan.get("topics")
    if not isinstance(topics, list):
        return {}
    return {
        item["topic_id"]: item for item in topics
        if isinstance(item, dict) and _nonempty(item.get("topic_id"))
    }


def _targeted_topic_ids(revision_items: list[dict] | None) -> set[str]:
    targeted: set[str] = set()
    for item in revision_items or []:
        if not isinstance(item, dict):
            continue
        location = item.get("location")
        if isinstance(location, str):
            targeted.update(re.findall(r"TOPIC_[A-Z0-9][A-Z0-9_]*", location))
    return targeted


def validate_research_plan(plan: object, planner_input: dict, *,
                           previous_plan: dict | None = None,
                           revision_items: list[dict] | None = None) -> dict:
    """Check plan shape, traceability, constraints and minimal revision preservation."""
    issues = _shape_issues(plan, RESEARCH_PLAN_CONTRACT, "invalid_research_plan_contract")
    if not isinstance(plan, dict):
        return {"ok": False, "complete": False, "issues": issues}

    input_validation = validate_planner_input(planner_input)
    if not input_validation["ok"]:
        issues.extend(input_validation["issues"])
        return {"ok": False, "complete": False, "issues": issues}

    if plan.get("task_id") != planner_input.get("task_id"):
        issues.append(_issue(
            "blocker", "task_id_mismatch", "plan task_id must match planner input",
            "task_id",
        ))
    if not _nonempty(plan.get("artifact_version")):
        issues.append(_issue(
            "major", "empty_artifact_version", "artifact_version must not be empty",
            "artifact_version",
        ))
    if plan.get("output_language") != planner_input.get("output_language"):
        issues.append(_issue(
            "blocker", "output_language_changed",
            "plan output_language must preserve the approved value", "output_language",
        ))
    if plan.get("approved_research_scope") != planner_input.get("approved_research_scope"):
        issues.append(_issue(
            "blocker", "approved_research_scope_changed",
            "approved_research_scope must be copied unchanged from the planner input",
            "approved_research_scope",
        ))
    if plan.get("global_constraints") != planner_input.get("constraints"):
        issues.append(_issue(
            "blocker", "constraints_changed",
            "global_constraints must preserve the approved planner constraints",
            "global_constraints",
        ))
    if plan.get("review_profile_ref") != REVIEW_PROFILE:
        issues.append(_issue(
            "blocker", "wrong_review_profile", "review_profile_ref must be research_plan",
            "review_profile_ref",
        ))

    for location in _find_forbidden_keys(plan):
        issues.append(_issue(
            "blocker", "prohibited_output_content",
            "ResearchPlan cannot contain publication records, claim verdicts or slide changes",
            location,
        ))

    drivers = planner_input["research_drivers"]
    driver_map = {item["driver_id"]: item for item in drivers}
    known_driver_ids = set(driver_map)
    known_domains = set(_card_ids(planner_input["approved_domains"], "domain_id"))
    relation_sets = {
        "related_claims": set(_card_ids(planner_input["claim_cards"], "claim_id")),
        "related_concepts": set(_card_ids(
            planner_input["concept_context_cards"], "concept_id"
        )),
        "related_flow_issues": set(_card_ids(
            planner_input["selected_flow_issue_cards"], "issue_id"
        )),
        "related_update_needs": set(_card_ids(
            planner_input["selected_update_need_cards"], "update_need_id"
        )),
    }
    known_sources = set(_card_ids(planner_input["existing_source_cards"], "source_id"))
    constraints = planner_input["constraints"]
    topics = plan.get("topics") if isinstance(plan.get("topics"), list) else []
    if not topics:
        issues.append(_issue(
            "blocker", "empty_research_plan", "ResearchPlan must contain at least one topic",
            "topics",
        ))
    if len(topics) > constraints["max_topics"]:
        issues.append(_issue(
            "blocker", "topic_limit_exceeded",
            f"plan has {len(topics)} topics but max_topics is {constraints['max_topics']}",
            "topics",
        ))

    topic_ids = _card_ids(topics, "topic_id")
    for duplicate in sorted(_duplicates(topic_ids)):
        issues.append(_issue(
            "blocker", "duplicate_topic_id", f"duplicate topic ID {duplicate!r}", "topics",
        ))
    covered_drivers: set[str] = set()
    coverage_ids: list[str] = []

    for index, topic in enumerate(topics):
        if not isinstance(topic, dict):
            continue
        location = f"topics[{index}]"
        topic_id = topic.get("topic_id")
        if not _nonempty(topic_id) or not TOPIC_ID_RE.fullmatch(topic_id):
            issues.append(_issue(
                "major", "invalid_topic_id", "topic_id must match TOPIC_[A-Z0-9_]",
                f"{location}.topic_id",
            ))
        for field in ("name", "purpose"):
            if not _nonempty(topic.get(field)):
                issues.append(_issue(
                    "major", "empty_topic_field", f"topic {field} must not be empty",
                    f"{location}.{field}",
                ))

        linked = _string_list(topic.get("linked_driver_ids"))
        if not linked:
            issues.append(_issue(
                "major", "topic_without_driver",
                "every topic must link at least one approved driver",
                f"{location}.linked_driver_ids",
            ))
        if _duplicates(linked):
            issues.append(_issue(
                "major", "duplicate_topic_driver_link",
                f"linked_driver_ids contains duplicates {sorted(_duplicates(linked))}",
                f"{location}.linked_driver_ids",
            ))
        unknown_drivers = sorted(set(linked) - known_driver_ids)
        if unknown_drivers:
            issues.append(_issue(
                "blocker", "unknown_driver_reference",
                f"topic references unknown drivers {unknown_drivers}",
                f"{location}.linked_driver_ids",
            ))
        covered_drivers.update(set(linked) & known_driver_ids)
        linked_priorities = [driver_map[item]["priority"] for item in linked
                             if item in driver_map]
        if linked_priorities:
            highest = max(linked_priorities, key=PRIORITY_RANK.get)
            topic_priority = topic.get("priority")
            if topic_priority in PRIORITY_RANK \
                    and PRIORITY_RANK[topic_priority] < PRIORITY_RANK[highest]:
                issues.append(_issue(
                    "major", "driver_priority_lowered",
                    f"topic priority {topic_priority!r} is below linked driver priority {highest!r}",
                    f"{location}.priority",
                ))

        for relation, allowed in relation_sets.items():
            values = _string_list(topic.get(relation))
            if _duplicates(values):
                issues.append(_issue(
                    "major", "duplicate_topic_upstream_link",
                    f"{relation} contains duplicates {sorted(_duplicates(values))}",
                    f"{location}.{relation}",
                ))
            unknown = sorted(set(values) - allowed)
            if unknown:
                issues.append(_issue(
                    "blocker", "unknown_upstream_reference",
                    f"{relation} contains unknown IDs {unknown}", f"{location}.{relation}",
                ))

        domains = _string_list(topic.get("approved_domains"))
        if not domains:
            issues.append(_issue(
                "major", "topic_without_domain",
                "every topic must contain at least one approved domain",
                f"{location}.approved_domains",
            ))
        if _duplicates(domains):
            issues.append(_issue(
                "major", "duplicate_topic_domain",
                f"approved_domains contains duplicates {sorted(_duplicates(domains))}",
                f"{location}.approved_domains",
            ))
        unknown_domains = sorted(set(domains) - known_domains)
        if unknown_domains:
            issues.append(_issue(
                "blocker", "unapproved_domain",
                f"topic contains unapproved domains {unknown_domains}",
                f"{location}.approved_domains",
            ))

        roles = topic.get("source_roles_required")
        if isinstance(roles, dict) and not any(roles.get(role) is True for role in SOURCE_ROLES):
            issues.append(_issue(
                "major", "missing_required_source_role",
                "at least one source role must be required", f"{location}.source_roles_required",
            ))

        strategy = topic.get("search_strategy")
        if isinstance(roles, dict) and roles.get("current") is True \
                and planner_input.get("approved_research_scope", {}).get(
                    "include_recent_developments"
                ) is True \
                and "preprint" in constraints.get("allowed_work_types", []) \
                and isinstance(strategy, dict) \
                and "preprint" not in strategy.get("work_types", []):
            issues.append(_issue(
                "major", "recent_topic_omits_preprint_route",
                "a current-source topic must preserve the approved preprint route",
                f"{location}.search_strategy.work_types",
            ))
        if isinstance(strategy, dict):
            core_terms = _string_list(strategy.get("core_terms"))
            if not core_terms:
                issues.append(_issue(
                    "major", "missing_core_terms", "search strategy needs core terms",
                    f"{location}.search_strategy.core_terms",
                ))
            for field in ("core_terms", "allowed_expansion_areas", "excluded_terms"):
                raw_values = strategy.get(field)
                clean_values = _string_list(raw_values)
                if isinstance(raw_values, list) and len(clean_values) != len(raw_values):
                    issues.append(_issue(
                        "major", "empty_search_term",
                        f"search strategy {field} contains an empty value",
                        f"{location}.search_strategy.{field}",
                    ))
                if _duplicates(clean_values):
                    issues.append(_issue(
                        "minor", "duplicate_search_term",
                        f"search strategy {field} contains duplicates",
                        f"{location}.search_strategy.{field}",
                    ))
            for field, constraint_field in (
                ("languages", "allowed_languages"), ("work_types", "allowed_work_types")
            ):
                values = _string_list(strategy.get(field))
                if not values:
                    issues.append(_issue(
                        "major", "missing_search_constraint",
                        f"search strategy {field} must not be empty",
                        f"{location}.search_strategy.{field}",
                    ))
                outside = sorted(set(values) - set(constraints[constraint_field]))
                if outside:
                    issues.append(_issue(
                        "blocker", "search_constraint_expansion",
                        f"{field} contains unapproved values {outside}",
                        f"{location}.search_strategy.{field}",
                    ))
            for field in ("year_from", "year_to"):
                approved = constraints[field]
                actual = strategy.get(field)
                if approved is not None and actual is not None:
                    outside = actual < approved if field == "year_from" else actual > approved
                    if outside:
                        issues.append(_issue(
                            "blocker", "date_window_expansion",
                            f"search strategy {field} exceeds approved constraints",
                            f"{location}.search_strategy.{field}",
                        ))
            year_from, year_to = strategy.get("year_from"), strategy.get("year_to")
            if isinstance(year_from, int) and isinstance(year_to, int) and year_from > year_to:
                issues.append(_issue(
                    "major", "invalid_topic_date_window", "year_from must not exceed year_to",
                    f"{location}.search_strategy",
                ))
            seeds = _string_list(strategy.get("seed_sources"))
            if _duplicates(seeds):
                issues.append(_issue(
                    "major", "duplicate_seed_source",
                    f"seed_sources contains duplicates {sorted(_duplicates(seeds))}",
                    f"{location}.search_strategy.seed_sources",
                ))
            unknown_seeds = sorted(set(seeds) - known_sources)
            if unknown_seeds:
                issues.append(_issue(
                    "blocker", "unapproved_seed_source",
                    f"seed_sources contains unknown IDs {unknown_seeds}",
                    f"{location}.search_strategy.seed_sources",
                ))

        coverage = topic.get("coverage_requirements")
        coverage = coverage if isinstance(coverage, list) else []
        if not coverage:
            issues.append(_issue(
                "major", "missing_coverage_requirements",
                "every topic must declare at least one coverage requirement",
                f"{location}.coverage_requirements",
            ))
        for cov_index, requirement in enumerate(coverage):
            if not isinstance(requirement, dict):
                continue
            cov_location = f"{location}.coverage_requirements[{cov_index}]"
            coverage_id = requirement.get("coverage_id")
            if _nonempty(coverage_id):
                coverage_ids.append(coverage_id)
            if not _nonempty(coverage_id) or not COVERAGE_ID_RE.fullmatch(coverage_id):
                issues.append(_issue(
                    "major", "invalid_coverage_id",
                    "coverage_id must match COV_[A-Z0-9_]", f"{cov_location}.coverage_id",
                ))
            if not _nonempty(requirement.get("description")):
                issues.append(_issue(
                    "major", "empty_coverage_description",
                    "coverage description must not be empty", f"{cov_location}.description",
                ))
            cov_roles = _string_list(requirement.get("source_roles"))
            if not cov_roles or set(cov_roles) - SOURCE_ROLES:
                issues.append(_issue(
                    "major", "invalid_coverage_source_roles",
                    "coverage source_roles must contain known roles",
                    f"{cov_location}.source_roles",
                ))
            if isinstance(roles, dict):
                disabled = sorted(role for role in cov_roles if roles.get(role) is not True)
                if disabled:
                    issues.append(_issue(
                        "major", "coverage_role_not_required",
                        f"coverage uses roles not enabled for the topic: {disabled}",
                        f"{cov_location}.source_roles",
                    ))
            minimum = requirement.get("minimum_sources")
            if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 1:
                issues.append(_issue(
                    "major", "invalid_minimum_sources",
                    "minimum_sources must be a positive integer",
                    f"{cov_location}.minimum_sources",
                ))
            elif minimum < planner_input["selection_profile"][
                    "minimum_sources_per_required_role"]:
                issues.append(_issue(
                    "major", "minimum_sources_below_selection_profile",
                    "minimum_sources is below the approved per-role minimum",
                    f"{cov_location}.minimum_sources",
                ))

        stop = topic.get("stop_rule")
        if isinstance(stop, dict):
            limit = stop.get("candidate_limit")
            if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 \
                    or limit > constraints["candidate_limit_per_topic"]:
                issues.append(_issue(
                    "major", "invalid_candidate_limit",
                    "candidate_limit must be positive and within approved constraints",
                    f"{location}.stop_rule.candidate_limit",
                ))
            elif limit < planner_input["selection_profile"][
                    "candidate_pool_target_per_topic"]:
                issues.append(_issue(
                    "major", "candidate_limit_below_selection_target",
                    "candidate_limit cannot be below the approved candidate pool target",
                    f"{location}.stop_rule.candidate_limit",
                ))
            passes = stop.get("no_new_coverage_passes")
            if passes != constraints["no_new_coverage_passes"]:
                issues.append(_issue(
                    "major", "saturation_rule_changed",
                    "no_new_coverage_passes must match approved constraints",
                    f"{location}.stop_rule.no_new_coverage_passes",
                ))
            if stop.get("complementary_search_route_required") is not True:
                issues.append(_issue(
                    "major", "missing_complementary_route",
                    "a complementary search route must be required before saturation",
                    f"{location}.stop_rule.complementary_search_route_required",
                ))

    for duplicate in sorted(_duplicates(coverage_ids)):
        issues.append(_issue(
            "major", "duplicate_coverage_id", f"duplicate coverage ID {duplicate!r}",
            "topics.coverage_requirements",
        ))

    uncovered = _string_list(plan.get("uncovered_driver_ids"))
    unknown_uncovered = sorted(set(uncovered) - known_driver_ids)
    if unknown_uncovered:
        issues.append(_issue(
            "blocker", "unknown_uncovered_driver",
            f"uncovered_driver_ids contains unknown IDs {unknown_uncovered}",
            "uncovered_driver_ids",
        ))
    overlap = covered_drivers & set(uncovered)
    if overlap:
        issues.append(_issue(
            "major", "driver_both_covered_and_uncovered",
            f"drivers cannot be both covered and uncovered: {sorted(overlap)}",
            "uncovered_driver_ids",
        ))
    unaccounted = known_driver_ids - covered_drivers - set(uncovered)
    if unaccounted:
        issues.append(_issue(
            "major", "unaccounted_driver",
            f"drivers are neither covered nor explicitly uncovered: {sorted(unaccounted)}",
            "topics",
        ))

    input_issues = plan.get("input_issues")
    input_issues = input_issues if isinstance(input_issues, list) else []
    input_issue_ids = _card_ids(input_issues, "issue_id")
    for duplicate in sorted(_duplicates(input_issue_ids)):
        issues.append(_issue(
            "major", "duplicate_input_issue_id",
            f"duplicate input issue ID {duplicate!r}", "input_issues",
        ))
    for index, item in enumerate(input_issues):
        if isinstance(item, dict) and (
                not _nonempty(item.get("issue_id")) or not _nonempty(item.get("message"))):
            issues.append(_issue(
                "major", "incomplete_input_issue",
                "every input issue needs a non-empty issue_id and message",
                f"input_issues[{index}]",
            ))
    issue_driver_ids = {
        driver_id
        for item in input_issues if isinstance(item, dict)
        for driver_id in _string_list(item.get("related_driver_ids"))
        if isinstance(driver_id, str)
    }
    if set(uncovered) - issue_driver_ids:
        missing = sorted(set(uncovered) - issue_driver_ids)
        issues.append(_issue(
            "major", "unexplained_uncovered_driver",
            f"uncovered drivers lack explicit input issues: {missing}", "input_issues",
        ))
    unknown_issue_drivers = sorted(issue_driver_ids - known_driver_ids)
    if unknown_issue_drivers:
        issues.append(_issue(
            "blocker", "input_issue_unknown_driver",
            f"input issues reference unknown drivers {unknown_issue_drivers}", "input_issues",
        ))
    if any(item.get("severity") == "blocker" for item in input_issues
           if isinstance(item, dict)):
        issues.append(_issue(
            "blocker", "plan_contains_blocking_input_issue",
            "a plan with a blocking input issue must return needs_input without an artifact",
            "input_issues",
        ))
    for driver_id in sorted(set(uncovered)):
        priority = driver_map[driver_id]["priority"]
        issues.append(_issue(
            "major" if priority == "high" else "minor",
            "uncovered_driver",
            f"approved {priority}-priority driver {driver_id!r} is explicitly uncovered",
            "uncovered_driver_ids",
        ))

    if previous_plan is not None:
        if plan.get("artifact_version") == previous_plan.get("artifact_version"):
            issues.append(_issue(
                "major", "artifact_version_not_advanced",
                "a revised plan must use a new artifact_version", "artifact_version",
            ))
        targeted = _targeted_topic_ids(revision_items)
        if targeted:
            old_topics = _topic_map(previous_plan)
            new_topics = _topic_map(plan)
            for topic_id, old_topic in old_topics.items():
                if topic_id not in targeted and new_topics.get(topic_id) != old_topic:
                    issues.append(_issue(
                        "major", "unscoped_revision_change",
                        f"unaffected topic {topic_id!r} changed during a scoped revision",
                        f"topics.{topic_id}",
                    ))

    permitted = {"uncovered_driver"}
    invalid_issues = [item for item in issues if item["type"] not in permitted]
    complete = not uncovered and not input_issues
    return {"ok": not invalid_issues, "complete": complete, "issues": issues}


def _envelope(status: str, summary: str, issues: list[dict], *, produced=None,
              metrics=None, resume_token=None) -> dict:
    normalized_issues = [
        {
            "severity": item["severity"],
            "type": item["type"],
            "message": (
                f"{item['message']} (location: {item['location']})"
                if item.get("location") else item["message"]
            ),
        }
        for item in issues
    ]
    result = {
        "status": status,
        "produced": produced or [],
        "summary": summary,
        "issues": normalized_issues,
        "metrics": metrics or {},
        "resume_token": resume_token,
    }
    validation = contracts.validate(result, ENVELOPE_CONTRACT)
    if not validation["ok"]:
        raise ValueError("invalid planner envelope: " + "; ".join(validation["errors"]))
    return result


def failed_envelope(issue_type: str, message: str) -> dict:
    return _envelope(
        "failed", "G02-A01 Planner did not produce a ResearchPlan.",
        [_issue("blocker", issue_type, message, "planner")],
    )


def needs_input_envelope(issues: list[dict]) -> dict:
    return _envelope(
        "needs_input", "Planner input is incomplete or contradictory.", issues
    )


def prepare_planner(payload: object, *, previous_plan_ref: str | None = None,
                    revision_items: list[dict] | None = None, base=None) -> dict:
    """Prepare a first run or revision without invoking the reasoning agent."""
    try:
        if isinstance(payload, dict) and payload.get("schema_version") == PLANNER_INPUT_CONTRACT:
            planner_input = deepcopy(payload)
        else:
            planner_input = scope_planner_input(payload)
    except (KeyError, ValueError) as exc:
        issue = _issue(
            "blocker", "invalid_research_graph_input", str(exc), "research_graph_input"
        )
        return {"ready": False, "envelope": needs_input_envelope([issue])}

    validation = validate_planner_input(planner_input)
    if not validation["ok"]:
        return {"ready": False, "envelope": needs_input_envelope(validation["issues"])}

    previous_plan = None
    if previous_plan_ref is not None:
        try:
            if not isinstance(previous_plan_ref, str) \
                    or not previous_plan_ref.startswith(artifacts.SCHEME):
                raise ValueError("previous_plan_ref must use artifact://")
            previous_plan = artifacts.hydrate(previous_plan_ref, base=base)
            shape = contracts.validate(previous_plan, RESEARCH_PLAN_CONTRACT)
            if not shape["ok"]:
                raise ValueError("; ".join(shape["errors"]))
            if previous_plan.get("task_id") != planner_input["task_id"]:
                raise ValueError("previous plan task_id does not match planner input")
        except (OSError, ValueError, KeyError, IndexError) as exc:
            return {"ready": False, "envelope": failed_envelope(
                "invalid_previous_plan", str(exc)
            )}

    if revision_items and previous_plan is None:
        return {"ready": False, "envelope": failed_envelope(
            "missing_previous_plan", "revision_items require previous_plan_ref"
        )}
    if revision_items is not None and (
            not isinstance(revision_items, list)
            or any(not isinstance(item, dict) for item in revision_items)):
        return {"ready": False, "envelope": failed_envelope(
            "invalid_revision_items", "revision_items must be a list of finding objects"
        )}

    return {
        "ready": True,
        "planner_input": planner_input,
        "previous_plan": previous_plan,
        "previous_plan_ref": previous_plan_ref,
        "revision_items": deepcopy(revision_items or []),
    }


def _safe_segment(value: str) -> str:
    segment = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return segment or "unknown"


def finalize_research_plan(planner_input: dict, plan: object, *, base=None,
                           previous_plan: dict | None = None,
                           revision_items: list[dict] | None = None) -> dict:
    """Validate and persist one plan, then return its universal agent envelope."""
    validation = validate_research_plan(
        plan, planner_input, previous_plan=previous_plan, revision_items=revision_items
    )
    if not validation["ok"]:
        return _envelope(
            "failed", "ResearchPlan failed deterministic validation.",
            validation["issues"],
        )
    assert isinstance(plan, dict)
    task = _safe_segment(plan["task_id"])
    version = _safe_segment(plan["artifact_version"])
    try:
        ref = artifacts.store(f"g02/research-plans/{task}.{version}.json", plan, base=base)
    except (OSError, TypeError, ValueError) as exc:
        return failed_envelope("research_plan_store_failed", str(exc))
    descriptor = {
        "type": "research_plan",
        "path": ref,
        "schema_version": RESEARCH_PLAN_CONTRACT,
        "artifact_version": plan["artifact_version"],
    }
    status = "ok" if validation["complete"] else "degraded"
    summary = (
        f"ResearchPlan {plan['artifact_version']} stored with {len(plan['topics'])} topics."
    )
    return _envelope(
        status,
        summary,
        validation["issues"],
        produced=[descriptor],
        metrics={
            "topic_count": len(plan["topics"]),
            "covered_driver_count": len({
                driver_id for topic in plan["topics"]
                for driver_id in topic["linked_driver_ids"]
            }),
            "uncovered_driver_count": len(plan["uncovered_driver_ids"]),
        },
        resume_token=ref if status == "degraded" else None,
    )


def build_research_plan_review_task(planner_input: dict, artifact_descriptor: dict, *,
                                    review_id: str, attempt: int = 1,
                                    previous_decision_ref: str | None = None,
                                    producer_revision_response: dict | None = None) -> dict:
    """Freeze the research_plan review profile for one produced artifact."""
    input_validation = validate_planner_input(planner_input)
    if not input_validation["ok"]:
        raise ValueError("invalid planner input: " + "; ".join(
            item["message"] for item in input_validation["issues"]
        ))
    if not _nonempty(review_id):
        raise ValueError("review_id must not be empty")
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
        raise ValueError("attempt must be a positive integer")
    if not isinstance(artifact_descriptor, dict):
        raise ValueError("artifact_descriptor must be an object")
    if artifact_descriptor.get("type") != "research_plan":
        raise ValueError("artifact descriptor type must be research_plan")
    if artifact_descriptor.get("schema_version") != RESEARCH_PLAN_CONTRACT:
        raise ValueError("artifact descriptor schema_version must be research_plan@1")
    artifact_ref = artifact_descriptor.get("path") or artifact_descriptor.get("ref")
    if not _nonempty(artifact_ref) or not artifact_ref.startswith(artifacts.SCHEME):
        raise ValueError("artifact descriptor must contain an artifact:// path or ref")
    artifact_version = artifact_descriptor.get("artifact_version")
    if not _nonempty(artifact_version):
        raise ValueError("artifact descriptor must contain artifact_version")

    task = {
        "schema_version": "review_task@1",
        "review_id": review_id,
        "task_id": planner_input["task_id"],
        "logical_review_node": "g02-a01-planner-review",
        "producer_agent": PLANNER_AGENT,
        "attempt": attempt,
        "review_profile": REVIEW_PROFILE,
        "original_task": {
            "objective": "Create a bounded ResearchPlan from approved research drivers.",
            "input_contract": PLANNER_INPUT_CONTRACT,
            "output_contract": RESEARCH_PLAN_CONTRACT,
        },
        "producer_input": deepcopy(planner_input),
        "artifact": {
            "type": "research_plan",
            "ref": artifact_ref,
            "schema_version": RESEARCH_PLAN_CONTRACT,
            "artifact_version": artifact_version,
        },
        "expected_output_contract": RESEARCH_PLAN_CONTRACT,
        "acceptance_criteria": deepcopy(RESEARCH_PLAN_ACCEPTANCE_CRITERIA),
        "evidence_requirements": deepcopy(RESEARCH_PLAN_EVIDENCE_REQUIREMENTS),
        "prohibited_behaviors": deepcopy(RESEARCH_PLAN_PROHIBITED_BEHAVIORS),
        "severity_rules": deepcopy(RESEARCH_PLAN_SEVERITY_RULES),
        "previous_decision_ref": previous_decision_ref,
        "producer_revision_response": producer_revision_response,
    }
    from . import review
    validation = review.validate_review_task(task)
    if not validation["ok"]:
        raise ValueError("invalid research plan review task: " + "; ".join(
            item["message"] for item in validation["issues"]
        ))
    return task


def execute_planner(payload: object, planner_executor: Callable | None, *, base=None,
                    previous_plan_ref: str | None = None,
                    revision_items: list[dict] | None = None) -> dict:
    """Prepare, invoke an injected host executor and finalize its ResearchPlan object."""
    prepared = prepare_planner(
        payload,
        previous_plan_ref=previous_plan_ref,
        revision_items=revision_items,
        base=base,
    )
    if not prepared["ready"]:
        return prepared["envelope"]
    if planner_executor is None:
        return failed_envelope(
            "planner_executor_unavailable", "no G02-A01 host executor is configured"
        )
    try:
        plan = planner_executor(
            prepared["planner_input"],
            {
                "previous_plan": prepared["previous_plan"],
                "previous_plan_ref": prepared["previous_plan_ref"],
                "revision_items": prepared["revision_items"],
            },
        )
    except Exception as exc:
        return failed_envelope("planner_executor_failed", str(exc))
    return finalize_research_plan(
        prepared["planner_input"],
        plan,
        base=base,
        previous_plan=prepared["previous_plan"],
        revision_items=prepared["revision_items"],
    )
