---
name: expand-research-query
description: Generate controlled scholarly search terms and query variants from an approved ResearchPlan topic. Use for domain or recent-literature discovery when every expansion must remain traceable to the topic and must not change research scope.
---

# Expand Research Query

## Contract

Consume one topic's purpose, core terms, allowed expansion areas, exclusions, date and work-type
constraints, plus optional approved seeds. Produce `QueryPlan` with query IDs and terms grouped
by concept, method, population or context, each carrying origin, purpose and target provider.

## Workflow

1. Preserve exact core phrases and generate controlled synonyms, spelling variants, acronyms
   and established technical terms.
2. Add broader or narrower terms only inside `allowed_expansion_areas`.
3. Create complementary queries for qualifying, critical or contradictory evidence when the
   topic requires it.
4. Apply exclusions, date windows, language and work-type filters without encoding an expected
   conclusion.
5. Adapt syntax to provider capabilities only at execution time. Keep a provider-neutral
   canonical query representation.
6. Remove redundant variants and map every query to topic, coverage units and a stated purpose.

## Output requirements

- Every query has `query_id`, `topic_id`, `origin_terms`, `purpose`, `terms`, filters and route.
- Mark generated terms separately from human-approved seed terms.
- Preserve negative and null-result queries in the query log once executed.

## Boundaries

- Do not execute searches or create bibliographic metadata.
- Do not add adjacent domains outside approved expansion areas.
- Do not optimize queries to find only supportive evidence.

## Failure handling

If a topic has no usable terminology, return a structured gap to the caller. If only part of a
query plan can be formed, return it as degraded with uncovered coverage units.

## Resume

Reuse stable query IDs for unchanged canonical queries; add new IDs for revision-driven routes.
