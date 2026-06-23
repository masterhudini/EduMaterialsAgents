"""Deterministic generation and validation of provider-neutral query plans."""
from __future__ import annotations

import re
from copy import deepcopy

from core import contracts

QUERY_PLAN_CONTRACT = "query_plan@1"
DOMAIN_INPUT_CONTRACT = "domain_research_input@1"
CANONICAL_INPUT_CONTRACT = "canonical_research_input@1"
RECENT_INPUT_CONTRACT = "recent_research_input@1"
MARKET_INPUT_CONTRACT = "market_case_research_input@1"
SCHOLARLY_PROVIDERS = {"openalex", "semantic_scholar", "arxiv"}
WEB_PROVIDERS = {"tavily", "searxng", "auto_budgeted"}
PROVIDERS = SCHOLARLY_PROVIDERS | WEB_PROVIDERS
MAX_ROUTES = 12
MAX_TERMS_PER_ROUTE = 20
MAX_TERM_LENGTH = 120
GENERATED_TERM_RELATIONS = {
    "synonym", "spelling_variant", "acronym", "established_technical_phrase",
}
ROUTE_ID_RE = re.compile(r"^ROUTE_[A-Z0-9][A-Z0-9_]*$")
QUERY_ID_RE = re.compile(r"^QUERY_[A-Z0-9][A-Z0-9_]*$")
FAST_DEFAULT_LIMIT = 8
FAST_DEFAULT_MAX_ROUTES = 3


def _issue(code: str, message: str, location: str) -> dict:
    return {"code": code, "message": message, "location": location}


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


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


def _discovery_input_contract(discovery_input: object) -> str:
    if isinstance(discovery_input, dict):
        version = discovery_input.get("schema_version")
        if version in {CANONICAL_INPUT_CONTRACT, RECENT_INPUT_CONTRACT, MARKET_INPUT_CONTRACT}:
            return version
    return DOMAIN_INPUT_CONTRACT


def _positive_int(value: object, fallback: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else fallback


def _stable_id(value: object) -> str:
    token = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "TOPIC").upper()).strip("_")
    return token or "TOPIC"


def _ready_scholarly_provider(discovery_input: dict, strategy: dict,
                                discovery_profile: dict) -> str | None:
    ready = {
        item.get("provider") for item in discovery_input.get("provider_capabilities", [])
        if isinstance(item, dict) and item.get("enabled") is True and item.get("ready") is True
    } & SCHOLARLY_PROVIDERS
    preferred = discovery_profile.get("default_provider", "openalex")
    order = [preferred, "openalex", "semantic_scholar", "arxiv"]
    work_types = set(_strings(strategy.get("work_types")))
    for provider in dict.fromkeys(order):
        if provider not in ready:
            continue
        if provider == "arxiv" and "preprint" not in work_types:
            continue
        return provider
    return None


def _route_filters(discovery_input: dict, strategy: dict) -> dict:
    filters = {
        "year_from": strategy.get("year_from"),
        "year_to": strategy.get("year_to"),
        "languages": deepcopy(_strings(strategy.get("languages"))),
        "work_types": deepcopy(_strings(strategy.get("work_types"))),
    }
    recency = discovery_input.get("recency_window")
    if discovery_input.get("schema_version") == RECENT_INPUT_CONTRACT \
            and isinstance(recency, dict):
        filters["year_from"] = recency.get("year_from")
        filters["year_to"] = recency.get("year_to")
    return filters


def _generated_basis(term: str, origin: str, expansion_area: str) -> dict:
    return {
        "term": term,
        "source_origin_terms": [origin],
        "expansion_area": expansion_area,
        "relation": "established_technical_phrase",
    }


def generate_fast_query_plan(discovery_input: object, profile: dict | None = None) -> dict:
    """Build the common fast scholarly plan without asking an agent to invent its shape.

    The generator never broadens scope. It copies approved terms, exclusions, coverage units and
    filters, selects one ready scholarly provider, then runs the normal query-plan validator.
    Structured gaps are returned for inputs that require semantic adjustment.
    """
    contract_ref = _discovery_input_contract(discovery_input)
    if contract_ref == MARKET_INPUT_CONTRACT:
        return {
            "ready": False,
            "issues": [_issue(
                "unsupported_fast_query_domain",
                "The fast generator currently supports scholarly A02/A03/A04 inputs only.",
                "discovery_input.schema_version",
            )],
        }
    try:
        checked = contracts.validate(discovery_input, contract_ref)
    except (KeyError, ValueError) as exc:
        return {"ready": False, "issues": [_issue("contract_unavailable", str(exc), contract_ref)]}
    if not checked["ok"] or not isinstance(discovery_input, dict):
        return {
            "ready": False,
            "issues": [
                _issue("invalid_discovery_input_contract", error, contract_ref)
                for error in checked["errors"]
            ],
        }

    topic = discovery_input.get("topic")
    topic = topic if isinstance(topic, dict) else {}
    strategy = topic.get("search_strategy")
    strategy = strategy if isinstance(strategy, dict) else {}
    core_terms = _strings(strategy.get("core_terms"))
    expansions = [item for item in _strings(strategy.get("allowed_expansion_areas"))
                  if item not in set(core_terms)]
    coverage = topic.get("coverage_requirements")
    coverage_ids = [
        item.get("coverage_id") for item in coverage or []
        if isinstance(item, dict) and isinstance(item.get("coverage_id"), str)
        and item.get("coverage_id").strip()
    ]
    gaps: list[dict] = []
    if not core_terms:
        gaps.append(_issue("missing_core_terms", "No approved core terms are available.",
                           "topic.search_strategy.core_terms"))
    if not coverage_ids:
        gaps.append(_issue("missing_coverage_units", "No approved coverage units are available.",
                           "topic.coverage_requirements"))

    root_profile = profile if isinstance(profile, dict) else {}
    discovery_profile = root_profile.get("discovery") \
        if isinstance(root_profile.get("discovery"), dict) else root_profile
    provider = _ready_scholarly_provider(discovery_input, strategy, discovery_profile)
    if provider is None:
        gaps.append(_issue(
            "no_compatible_ready_provider",
            "No ready scholarly provider is compatible with the approved work types.",
            "provider_capabilities",
        ))
    if gaps:
        return {"ready": False, "issues": gaps}

    assert provider is not None
    stop_rule = topic.get("stop_rule") if isinstance(topic.get("stop_rule"), dict) else {}
    roles = topic.get("source_roles_required") \
        if isinstance(topic.get("source_roles_required"), dict) else {}
    purposes = ["core"]
    if stop_rule.get("complementary_search_route_required") is True:
        purposes.append("complementary")
    if roles.get("qualifying_or_critical") is True:
        purposes.append("qualifying_or_critical")
    max_routes = _positive_int(
        discovery_profile.get("max_routes_per_topic"), FAST_DEFAULT_MAX_ROUTES
    )
    if len(purposes) > min(max_routes, FAST_DEFAULT_MAX_ROUTES):
        return {
            "ready": False,
            "issues": [_issue(
                "required_routes_exceed_fast_limit",
                f"The approved topic requires {len(purposes)} routes but the fast limit is "
                f"{min(max_routes, FAST_DEFAULT_MAX_ROUTES)}.",
                "topic.stop_rule",
            )],
        }

    ceilings = [
        _positive_int(discovery_profile.get("max_records_per_query"), FAST_DEFAULT_LIMIT),
        _positive_int(discovery_profile.get("route_limit"), FAST_DEFAULT_LIMIT),
    ]
    for value in (
        stop_rule.get("candidate_limit"),
        discovery_input.get("search_limits", {}).get("candidate_limit")
        if isinstance(discovery_input.get("search_limits"), dict) else None,
    ):
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            ceilings.append(value)
    route_limit = min(ceilings)
    topic_token = _stable_id(topic.get("topic_id"))
    filters = _route_filters(discovery_input, strategy)
    routes = []
    used_expansions: set[str] = set()
    qualifier_words = ("limit", "critic", "risk", "bias", "fail", "diagnos", "conflict")
    for index, purpose in enumerate(purposes):
        if purpose == "core":
            origins = core_terms[:3]
            generated: list[str] = []
            bases: list[dict] = []
        else:
            origins = [core_terms[min(index - 1, len(core_terms) - 1)]]
            candidates = [item for item in expansions if item not in used_expansions]
            if purpose == "qualifying_or_critical":
                candidates.sort(key=lambda item: (
                    not any(word in item.casefold() for word in qualifier_words),
                    expansions.index(item),
                ))
            generated = candidates[:1]
            used_expansions.update(generated)
            bases = [_generated_basis(term, origins[0], term) for term in generated]
        declared = [*origins, *generated]
        suffix = "QUALIFYING" if purpose == "qualifying_or_critical" else purpose.upper()
        routes.append({
            "route_id": f"ROUTE_{topic_token}_{suffix}",
            "query_id": f"QUERY_{topic_token}_{suffix}",
            "purpose": purpose,
            "canonical_query": " AND ".join(f'"{term}"' for term in declared),
            "origin_terms": deepcopy(origins),
            "generated_terms": deepcopy(generated),
            "generated_term_bases": bases,
            "coverage_unit_ids": deepcopy(coverage_ids),
            "preferred_providers": [provider],
            "filters": deepcopy(filters),
            "limit": route_limit,
        })

    plan = {
        "schema_version": QUERY_PLAN_CONTRACT,
        "artifact_version": "1.0.0",
        "task_id": discovery_input.get("task_id"),
        "topic_id": topic.get("topic_id"),
        "routes": routes,
        "excluded_terms": deepcopy(_strings(strategy.get("excluded_terms"))),
    }
    validation = validate_query_plan(
        plan, discovery_input, max_records_per_query=route_limit
    )
    if not validation["ok"]:
        return {"ready": False, "issues": validation["issues"], "query_plan": plan}
    return {
        "ready": True,
        "query_plan": plan,
        "provider": provider,
        "route_count": len(routes),
        "limit_per_route": route_limit,
    }


def validate_query_plan(query_plan: object, domain_input: object, *,
                        max_records_per_query: int | None = None) -> dict:
    """Check structure, scope preservation, route coverage and provider authorization."""
    issues: list[dict] = []
    for payload, contract_ref, code in (
        (query_plan, QUERY_PLAN_CONTRACT, "invalid_query_plan_contract"),
        (domain_input, _discovery_input_contract(domain_input),
         "invalid_discovery_input_contract"),
    ):
        try:
            shape = contracts.validate(payload, contract_ref)
        except (KeyError, ValueError) as exc:
            issues.append(_issue("contract_unavailable", str(exc), contract_ref))
            continue
        for error in shape["errors"]:
            issues.append(_issue(code, error, contract_ref))
    if not isinstance(query_plan, dict) or not isinstance(domain_input, dict):
        return {"ok": False, "issues": issues}
    unknown_root = _unknown_fields(
        query_plan,
        {"schema_version", "artifact_version", "task_id", "topic_id", "routes",
         "excluded_terms"},
    )
    if unknown_root:
        issues.append(_issue(
            "unknown_query_plan_fields", f"unsupported fields {unknown_root}", "query_plan"
        ))

    topic = domain_input.get("topic")
    if not isinstance(topic, dict):
        return {"ok": False, "issues": issues}
    if query_plan.get("task_id") != domain_input.get("task_id"):
        issues.append(_issue(
            "task_id_mismatch", "query plan task_id must match scoped discovery input", "task_id"
        ))
    if query_plan.get("topic_id") != topic.get("topic_id"):
        issues.append(_issue(
            "topic_id_mismatch", "query plan topic_id must match scoped topic", "topic_id"
        ))
    version = query_plan.get("artifact_version")
    if not isinstance(version, str) or not version.strip():
        issues.append(_issue(
            "empty_artifact_version", "artifact_version must not be empty", "artifact_version"
        ))

    strategy = topic.get("search_strategy") if isinstance(topic.get("search_strategy"), dict) else {}
    approved_core = set(_strings(strategy.get("core_terms")))
    approved_expansions = set(_strings(strategy.get("allowed_expansion_areas")))
    approved_exclusions = set(_strings(strategy.get("excluded_terms")))
    plan_exclusions = set(_strings(query_plan.get("excluded_terms")))
    exclusion_values = _strings(query_plan.get("excluded_terms"))
    if _duplicates(exclusion_values):
        issues.append(_issue(
            "duplicate_exclusion", "excluded_terms must not contain duplicates",
            "excluded_terms",
        ))
    if approved_exclusions != plan_exclusions:
        issues.append(_issue(
            "changed_approved_exclusions",
            "query plan exclusions must exactly match the approved topic exclusions; "
            f"missing={sorted(approved_exclusions-plan_exclusions)}, "
            f"added={sorted(plan_exclusions-approved_exclusions)}",
            "excluded_terms",
        ))
    coverage = topic.get("coverage_requirements")
    coverage_ids = {
        item.get("coverage_id") for item in coverage or []
        if isinstance(item, dict) and isinstance(item.get("coverage_id"), str)
    }
    ready_providers = {
        item.get("provider") for item in domain_input.get("provider_capabilities", [])
        if isinstance(item, dict) and item.get("enabled") is True and item.get("ready") is True
    }
    topic_stop = topic.get("stop_rule") if isinstance(topic.get("stop_rule"), dict) else {}
    topic_limit = topic_stop.get("candidate_limit")

    is_market = domain_input.get("schema_version") == MARKET_INPUT_CONTRACT
    market_limits = domain_input.get("search_limits") \
        if is_market and isinstance(domain_input.get("search_limits"), dict) else {}
    routes = query_plan.get("routes") if isinstance(query_plan.get("routes"), list) else []
    if not routes:
        issues.append(_issue("empty_query_plan", "at least one query route is required", "routes"))
    if len(routes) > MAX_ROUTES:
        issues.append(_issue(
            "query_route_limit_exceeded", f"query plan cannot exceed {MAX_ROUTES} routes",
            "routes",
        ))
    if is_market and isinstance(market_limits.get("route_limit"), int) \
            and len(routes) > market_limits["route_limit"]:
        issues.append(_issue(
            "market_query_route_limit_exceeded",
            f"market query plan cannot exceed {market_limits['route_limit']} scoped routes",
            "routes",
        ))
    if is_market and isinstance(market_limits.get("max_queries"), int) \
            and len(routes) > market_limits["max_queries"]:
        issues.append(_issue(
            "market_query_budget_exceeded",
            "market query plan exceeds the scoped per-task query budget", "routes",
        ))
    route_ids: list[str] = []
    query_ids: list[str] = []
    purposes: set[str] = set()
    covered_units: set[str] = set()
    for index, route in enumerate(routes):
        if not isinstance(route, dict):
            continue
        location = f"routes[{index}]"
        unknown_route = _unknown_fields(
            route,
            {"route_id", "query_id", "purpose", "canonical_query", "origin_terms",
             "generated_terms", "generated_term_bases", "coverage_unit_ids",
             "preferred_providers", "web", "filters", "limit"},
        )
        if unknown_route:
            issues.append(_issue(
                "unknown_query_route_fields", f"unsupported fields {unknown_route}", location
            ))
        route_id = route.get("route_id")
        query_id = route.get("query_id")
        if isinstance(route_id, str):
            route_ids.append(route_id)
        if not isinstance(route_id, str) or not ROUTE_ID_RE.fullmatch(route_id):
            issues.append(_issue(
                "invalid_route_id", "route_id must match ROUTE_[A-Z0-9_]",
                f"{location}.route_id",
            ))
        elif len(route_id) > 120:
            issues.append(_issue(
                "route_id_too_long", "route_id cannot exceed 120 characters",
                f"{location}.route_id",
            ))
        if isinstance(query_id, str):
            query_ids.append(query_id)
        if not isinstance(query_id, str) or not QUERY_ID_RE.fullmatch(query_id):
            issues.append(_issue(
                "invalid_query_id", "query_id must match QUERY_[A-Z0-9_]",
                f"{location}.query_id",
            ))
        elif len(query_id) > 120:
            issues.append(_issue(
                "query_id_too_long", "query_id cannot exceed 120 characters",
                f"{location}.query_id",
            ))
        purpose = route.get("purpose")
        if isinstance(purpose, str):
            purposes.add(purpose)
        canonical = route.get("canonical_query")
        if not isinstance(canonical, str) or not canonical.strip() or len(canonical) > 500:
            issues.append(_issue(
                "invalid_canonical_query",
                "canonical_query must contain 1 to 500 characters",
                f"{location}.canonical_query",
            ))
        elif any(character in canonical for character in (":", "&", "?", "#", "/", "\\")) \
                or any(ord(character) < 32 for character in canonical):
            issues.append(_issue(
                "provider_specific_query_syntax",
                "canonical_query must remain provider-neutral and cannot contain URL or field syntax",
                f"{location}.canonical_query",
            ))
        origins = _strings(route.get("origin_terms"))
        if not origins:
            issues.append(_issue(
                "missing_origin_terms", "each route requires approved origin terms",
                f"{location}.origin_terms",
            ))
        unknown_origins = sorted(set(origins) - approved_core)
        if unknown_origins:
            issues.append(_issue(
                "unapproved_origin_term",
                f"origin_terms contain values outside topic core terms {unknown_origins}",
                f"{location}.origin_terms",
            ))
        generated = _strings(route.get("generated_terms"))
        bases = route.get("generated_term_bases") \
            if isinstance(route.get("generated_term_bases"), list) else []
        basis_terms: list[str] = []
        for basis_index, basis in enumerate(bases):
            basis_location = f"{location}.generated_term_bases[{basis_index}]"
            if not isinstance(basis, dict):
                continue
            unknown_basis = _unknown_fields(
                basis, {"term", "source_origin_terms", "expansion_area", "relation"}
            )
            if unknown_basis:
                issues.append(_issue(
                    "unknown_generated_term_basis_fields",
                    f"unsupported fields {unknown_basis}", basis_location,
                ))
            term = basis.get("term")
            if isinstance(term, str) and term.strip():
                term = term.strip()
                basis_terms.append(term)
            else:
                issues.append(_issue(
                    "invalid_generated_term_basis",
                    "term must be a non-empty string", f"{basis_location}.term",
                ))
            source_origins = _strings(basis.get("source_origin_terms"))
            unknown_source_origins = sorted(set(source_origins) - set(origins))
            if not source_origins or unknown_source_origins:
                issues.append(_issue(
                    "invalid_generated_term_origin",
                    "source_origin_terms must be non-empty and belong to this route's "
                    f"approved origin_terms; unknown={unknown_source_origins}",
                    f"{basis_location}.source_origin_terms",
                ))
            if _duplicates(source_origins):
                issues.append(_issue(
                    "duplicate_generated_term_origin",
                    f"source_origin_terms contains duplicates {sorted(_duplicates(source_origins))}",
                    f"{basis_location}.source_origin_terms",
                ))
            expansion_area = basis.get("expansion_area")
            if not isinstance(expansion_area, str) \
                    or expansion_area.strip() not in approved_expansions:
                issues.append(_issue(
                    "unapproved_generated_term_expansion",
                    "expansion_area must exactly match an approved allowed_expansion_areas value",
                    f"{basis_location}.expansion_area",
                ))
            relation = basis.get("relation")
            if relation not in GENERATED_TERM_RELATIONS:
                issues.append(_issue(
                    "invalid_generated_term_relation",
                    f"relation must be one of {sorted(GENERATED_TERM_RELATIONS)}",
                    f"{basis_location}.relation",
                ))
        duplicate_basis_terms = sorted(_duplicates(basis_terms))
        if duplicate_basis_terms:
            issues.append(_issue(
                "duplicate_generated_term_basis",
                f"generated terms have multiple bases {duplicate_basis_terms}",
                f"{location}.generated_term_bases",
            ))
        missing_bases = sorted(set(generated) - set(basis_terms))
        extra_bases = sorted(set(basis_terms) - set(generated))
        if missing_bases or extra_bases or len(basis_terms) != len(generated):
            issues.append(_issue(
                "generated_term_basis_mismatch",
                "every generated term requires exactly one basis and bases cannot introduce "
                f"new terms; missing={missing_bases}, extra={extra_bases}",
                f"{location}.generated_term_bases",
            ))
        if len(origins) + len(generated) > MAX_TERMS_PER_ROUTE:
            issues.append(_issue(
                "query_term_limit_exceeded",
                f"a route cannot exceed {MAX_TERMS_PER_ROUTE} declared terms",
                location,
            ))
        overlong_terms = [value for value in origins + generated
                          if len(value) > MAX_TERM_LENGTH]
        if overlong_terms:
            issues.append(_issue(
                "query_term_too_long",
                f"query terms cannot exceed {MAX_TERM_LENGTH} characters",
                location,
            ))
        for field, values in (
            ("origin_terms", origins),
            ("generated_terms", generated),
            ("coverage_unit_ids", _strings(route.get("coverage_unit_ids"))),
            ("preferred_providers", _strings(route.get("preferred_providers"))),
        ):
            if _duplicates(values):
                issues.append(_issue(
                    "duplicate_query_route_value",
                    f"{field} contains duplicates {sorted(_duplicates(values))}",
                    f"{location}.{field}",
                ))
        overlap = sorted(set(origins) & set(generated))
        if overlap:
            issues.append(_issue(
                "origin_generated_overlap",
                f"generated_terms must not repeat origin_terms {overlap}",
                f"{location}.generated_terms",
            ))
        if isinstance(canonical, str):
            declared_words = {
                token.casefold() for value in origins + generated
                for token in re.findall(r"[\w]+", value, flags=re.UNICODE)
            }
            canonical_words = {
                token.casefold() for token in re.findall(r"[\w]+", canonical, flags=re.UNICODE)
                if token.upper() not in {"AND", "OR", "ANDNOT"}
            }
            undeclared = sorted(canonical_words - declared_words)
            if undeclared:
                issues.append(_issue(
                    "undeclared_query_term",
                    f"canonical_query contains terms absent from origin_terms/generated_terms {undeclared}",
                    f"{location}.canonical_query",
                ))
        route_coverage = _strings(route.get("coverage_unit_ids"))
        covered_units.update(route_coverage)
        unknown_coverage = sorted(set(route_coverage) - coverage_ids)
        if not route_coverage or unknown_coverage:
            issues.append(_issue(
                "invalid_route_coverage",
                f"coverage_unit_ids must be non-empty and approved; unknown={unknown_coverage}",
                f"{location}.coverage_unit_ids",
            ))
        providers = _strings(route.get("preferred_providers"))
        unauthorized = sorted(set(providers) - ready_providers)
        if not providers or set(providers) - PROVIDERS or unauthorized:
            issues.append(_issue(
                "invalid_provider_route",
                f"preferred providers must be configured and ready; unauthorized={unauthorized}",
                f"{location}.preferred_providers",
            ))
        if is_market:
            mode = domain_input.get("provider_mode")
            if providers != [mode]:
                issues.append(_issue(
                    "market_provider_mode_mismatch",
                    "each A11 route must use exactly the prepared provider mode",
                    f"{location}.preferred_providers",
                ))
        elif set(providers) & WEB_PROVIDERS:
            issues.append(_issue(
                "web_provider_outside_market_scope",
                "web providers are authorized only for market_case_research_input@1",
                f"{location}.preferred_providers",
            ))
        if "arxiv" in providers and "preprint" not in set(_strings(strategy.get("work_types"))):
            issues.append(_issue(
                "provider_route_incompatible",
                "arxiv requires preprint to be allowed by the topic work_types",
                f"{location}.preferred_providers",
            ))
        web_route = route.get("web")
        if is_market:
            if not isinstance(web_route, dict):
                issues.append(_issue(
                    "missing_market_web_policy", "every A11 route requires a web policy",
                    f"{location}.web",
                ))
                web_route = {}
            unknown_web = _unknown_fields(
                web_route,
                {"include_domains", "exclude_domains", "source_tier_floor", "preferred_tier"},
            )
            if unknown_web:
                issues.append(_issue(
                    "unknown_market_web_fields", f"unsupported fields {unknown_web}",
                    f"{location}.web",
                ))
            policy = domain_input.get("source_tier_policy") \
                if isinstance(domain_input.get("source_tier_policy"), dict) else {}
            allowed_domains = set(_strings(policy.get("allowed_domains")))
            approved_excluded_domains = set(_strings(policy.get("excluded_domains")))
            include_domains = _strings(web_route.get("include_domains"))
            exclude_domains = _strings(web_route.get("exclude_domains"))
            if not include_domains or _duplicates(include_domains) \
                    or set(include_domains) - allowed_domains:
                issues.append(_issue(
                    "invalid_market_include_domains",
                    "include_domains must be unique, non-empty and administrator-allowlisted",
                    f"{location}.web.include_domains",
                ))
            if _duplicates(exclude_domains) \
                    or set(exclude_domains) - approved_excluded_domains:
                issues.append(_issue(
                    "invalid_market_exclude_domains",
                    "exclude_domains must stay inside the administrator exclusion policy",
                    f"{location}.web.exclude_domains",
                ))
            if set(include_domains) & set(exclude_domains):
                issues.append(_issue(
                    "market_domain_policy_conflict",
                    "a domain cannot be included and excluded on the same route",
                    f"{location}.web",
                ))
            tiers = {"tier_1_authoritative", "tier_2_reputable_media", "tier_3_signal_only"}
            if web_route.get("source_tier_floor") not in tiers \
                    or web_route.get("preferred_tier") not in tiers:
                issues.append(_issue(
                    "invalid_market_source_tier",
                    "source tier floor and preferred tier must use the approved vocabulary",
                    f"{location}.web",
                ))
        elif web_route is not None:
            issues.append(_issue(
                "market_web_policy_outside_scope",
                "the web route block is authorized only for G02-A11", f"{location}.web",
            ))
        filters = route.get("filters") if isinstance(route.get("filters"), dict) else {}
        unknown_filters = _unknown_fields(
            filters, {"year_from", "year_to", "languages", "work_types"}
        )
        if unknown_filters:
            issues.append(_issue(
                "unknown_query_filter_fields", f"unsupported fields {unknown_filters}",
                f"{location}.filters",
            ))
        for field in ("languages", "work_types"):
            values = set(_strings(filters.get(field)))
            approved = set(_strings(strategy.get(field)))
            if not values or values - approved:
                issues.append(_issue(
                    "filter_scope_expansion",
                    f"{field} must be non-empty and stay within topic constraints",
                    f"{location}.filters.{field}",
                ))
        for field in ("year_from", "year_to"):
            approved = strategy.get(field)
            actual = filters.get(field)
            if isinstance(approved, int) and isinstance(actual, int):
                outside = actual < approved if field == "year_from" else actual > approved
                if outside:
                    issues.append(_issue(
                        "date_scope_expansion", f"{field} exceeds topic constraints",
                        f"{location}.filters.{field}",
                    ))
        year_from, year_to = filters.get("year_from"), filters.get("year_to")
        if isinstance(year_from, int) and isinstance(year_to, int) and year_from > year_to:
            issues.append(_issue(
                "invalid_date_window", "year_from cannot exceed year_to",
                f"{location}.filters",
            ))
        limit = route.get("limit")
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            issues.append(_issue(
                "invalid_route_limit", "route limit must be a positive integer",
                f"{location}.limit",
            ))
        else:
            ceilings = [value for value in (topic_limit, max_records_per_query)
                        if isinstance(value, int)]
            if is_market and isinstance(market_limits.get("max_results_per_route"), int):
                ceilings.append(market_limits["max_results_per_route"])
            if ceilings and limit > min(ceilings):
                issues.append(_issue(
                    "route_limit_exceeded", f"route limit exceeds {min(ceilings)}",
                    f"{location}.limit",
                ))

    for duplicate in sorted(_duplicates(route_ids)):
        issues.append(_issue("duplicate_route_id", f"duplicate route ID {duplicate!r}", "routes"))
    for duplicate in sorted(_duplicates(query_ids)):
        issues.append(_issue("duplicate_query_id", f"duplicate query ID {duplicate!r}", "routes"))
    if "core" not in purposes:
        issues.append(_issue("missing_core_route", "query plan requires a core route", "routes"))
    if topic_stop.get("complementary_search_route_required") is True \
            and "complementary" not in purposes:
        issues.append(_issue(
            "missing_complementary_route", "topic requires a complementary query route", "routes"
        ))
    roles = topic.get("source_roles_required")
    if isinstance(roles, dict) and roles.get("qualifying_or_critical") is True \
            and "qualifying_or_critical" not in purposes:
        issues.append(_issue(
            "missing_qualifying_route",
            "topic requires a neutral qualifying-or-critical route",
            "routes",
        ))
    mandatory_coverage = {
        item.get("coverage_id") for item in coverage or []
        if isinstance(item, dict) and item.get("mandatory") is True
    }
    if not mandatory_coverage <= covered_units:
        issues.append(_issue(
            "unplanned_mandatory_coverage",
            f"routes omit mandatory coverage {sorted(mandatory_coverage-covered_units)}",
            "routes",
        ))
    return {"ok": not issues, "issues": issues}


def route_by_id(query_plan: dict, route_id: str) -> dict:
    matches = [item for item in query_plan.get("routes", [])
               if isinstance(item, dict) and item.get("route_id") == route_id]
    if len(matches) != 1:
        raise KeyError(f"expected exactly one route {route_id!r}, found {len(matches)}")
    return matches[0]
