---
name: g02-expand-research-query
description: Produce a bounded provider-neutral query_plan@1 from one approved ResearchPlan topic. Use inside authorized domain or recent-discovery agents before deterministic metadata search, preserving topic terms, exclusions, filters, coverage units and neutral complementary routes without calling any provider.
---

# Expand Research Query

## Contract

Consume one scoped topic from `domain_research_input@1`. Produce one `query_plan@1` with stable
route and query IDs, canonical queries, approved origin terms, generated terms with explicit bases,
coverage-unit links, provider preferences, unchanged filters and per-route limits.

## Workflow

1. Copy the topic's core terms as the only allowed `origin_terms`. Preserve every approved
   exclusion.
2. Generate synonyms, spelling variants, acronyms and established technical phrases only within
   `allowed_expansion_areas`. Keep generated terms separate from origin terms. For each generated
   term add exactly one `generated_term_bases` entry containing the term, one or more source origin
   terms used by this route, the exact approved expansion-area value and one relation from
   `synonym`, `spelling_variant`, `acronym` or `established_technical_phrase`.
3. Create a `core` route for the direct investigation.
4. Create a `complementary` route whenever the topic stop rule requires one. Change terminology or
   provider route, while preserving purpose and coverage.
5. Create a neutral `qualifying_or_critical` route when that source role is required. Use boundary,
   limitation, counterexample or comparative terminology without asserting that criticism exists.
6. Link every route to approved `COV_*` units. Cover all mandatory units across the full plan.
7. Copy year, language and work-type filters from the topic without expansion. Keep each route
   limit within the topic candidate limit.
8. Select only ready providers listed in `provider_capabilities`. Provider-specific syntax is added
   later by deterministic adapters. Authorize arXiv only when `preprint` is included in the topic's
   approved work types.

## Output requirements

- Use unique `ROUTE_[A-Z0-9_]+` and `QUERY_[A-Z0-9_]+` IDs.
- Keep `canonical_query` provider-neutral and between 1 and 500 characters.
- Give every generated term exactly one basis. A basis cannot introduce a new term, use an origin
  outside the route or name an expansion area outside the approved topic.
- Include at least one core route and every route required by the topic stop and source-role rules.
- Preserve all exclusions and map each route to at least one approved coverage unit.
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
