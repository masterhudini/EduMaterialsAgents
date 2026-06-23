---
name: g02-expand-research-query
description: Produce a bounded provider-neutral query_plan@1 from one approved domain_research_input@1, recent_research_input@1 or market_case_research_input@1 topic. Use inside A02, A04 or A11 before deterministic search, preserving terms, exclusions, coverage, provider readiness, exact filters and controlled web policy without calling a provider.
---

# Expand Research Query

## Contract

Consume one scoped topic from `domain_research_input@1`, `recent_research_input@1` or
`market_case_research_input@1`. Produce one `query_plan@1` with stable
route and query IDs, canonical queries, approved origin terms, generated terms with explicit bases,
coverage-unit links, provider preferences, unchanged filters and per-route limits.

## Workflow

1. For a scholarly input in the default fast profile, call
   `research_query_plan_generate_fast` first. Return its validated plan unchanged when `ready` is
   true. Continue with manual query construction only for a structured generator gap, changing
   only the named part of the plan. A11 keeps its dedicated controlled web route construction.
2. Copy the topic's core terms as the only allowed `origin_terms`. Preserve every approved
   exclusion.
3. Generate synonyms, spelling variants, acronyms and established technical phrases only within
   `allowed_expansion_areas`. Keep generated terms separate from origin terms. For each generated
   term add exactly one `generated_term_bases` entry containing the term, one or more source origin
   terms used by this route, the exact approved expansion-area value and one relation from
   `synonym`, `spelling_variant`, `acronym` or `established_technical_phrase`.
4. Create a `core` route for the direct investigation.
5. Create a `complementary` route whenever the topic stop rule requires one. Change terminology or
   provider route, while preserving purpose and coverage.
6. Create a neutral `qualifying_or_critical` route when that source role is required. Use boundary,
   limitation, counterexample or comparative terminology without asserting that criticism exists.
7. Link every route to approved `COV_*` units. Cover all mandatory units across the full plan.
8. Copy year, language and work-type filters from the topic without expansion. Keep each route
   limit within the topic candidate limit.
9. Select only ready providers listed in `provider_capabilities`. In the default fast profile, put
   one primary provider in `preferred_providers` for each scholarly route. Prefer `openalex` for
   broad coverage, use `semantic_scholar` when abstract/citation signals are more important or
   OpenAlex is unavailable, and use `arxiv` only when `preprint` is included in the topic's approved
   work types. Add a second provider only when the route explicitly needs fallback coverage.
   Provider-specific syntax is added later by deterministic adapters.
10. For A04, copy `recency_window.year_from` and `year_to` exactly into every route. Preserve at
   least one preprint route when preprints are approved; never recalculate the window.
11. For A11, map routes to `market_case_needs`; use exactly `provider_mode`, the prepared web work
    types and include domains from `source_tier_policy.allowed_domains`. Exclude domains only when
    present in the prepared exclusion policy. Do not invent an endpoint or provider fallback.

## Output requirements

- Use the flat route shape below. Do not create `routes[].queries[]`, `providers` or
  `route_type`; deterministic adapters expect one query directly on each route.

```json
{
  "schema_version": "query_plan@1",
  "artifact_version": "1.0.0",
  "task_id": "TASK_ID",
  "topic_id": "TOPIC_ID",
  "routes": [
    {
      "route_id": "ROUTE_TOPIC_CORE",
      "query_id": "QUERY_TOPIC_CORE",
      "purpose": "core",
      "canonical_query": "approved origin term generated term",
      "origin_terms": ["approved origin term"],
      "generated_terms": ["generated term"],
      "generated_term_bases": [
        {
          "term": "generated term",
          "source_origin_terms": ["approved origin term"],
          "expansion_area": "approved expansion area",
          "relation": "established_technical_phrase"
        }
      ],
      "coverage_unit_ids": ["COV_APPROVED"],
      "preferred_providers": ["openalex"],
      "filters": {
        "year_from": null,
        "year_to": null,
        "languages": ["en"],
        "work_types": ["article", "review"]
      },
      "limit": 8
    }
  ],
  "excluded_terms": []
}
```

- Use unique `ROUTE_[A-Z0-9_]+` and `QUERY_[A-Z0-9_]+` IDs.
- Keep `canonical_query` provider-neutral and between 1 and 500 characters.
- Give every generated term exactly one basis. A basis cannot introduce a new term, use an origin
  outside the route or name an expansion area outside the approved topic.
- Include at least one core route and every route required by the topic stop and source-role rules.
- Preserve all exclusions and map each route to at least one approved coverage unit.
- Every A11 route contains a web block with administrator-allowlisted domains, a tier floor and
  preferred tier, and remains within the prepared query and result budgets.
- Produce no provider response, bibliographic record or claimed search result.

## Boundaries

- Do not execute network calls or use provider-specific identifiers as invented seeds.
- Do not add adjacent domains, new research drivers or broader time and work-type windows.
- Do not bias terms toward supportive evidence or omit qualifying routes.

## Failure handling

Return a structured gap when no approved origin term, ready provider or mandatory coverage mapping
exists. Do not produce a partial query plan that cannot pass deterministic validation.

## Resume

Preserve unchanged route and query IDs. Add new IDs only for revision-driven routes and remove a
route only when a reviewer finding explicitly invalidates it.
