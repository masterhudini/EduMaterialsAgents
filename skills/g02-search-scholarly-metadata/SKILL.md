---
name: g02-search-scholarly-metadata
description: Search real scholarly indexes through configured deterministic Research Graph tools and return provenance-preserving SourceRecords. Use for approved QueryPlans in domain, canonical or recent discovery; never use model-generated bibliographic facts.
---

# Search Scholarly Metadata

## Contract

Consume an approved `QueryPlan`, provider routes and result limits. Call configured deterministic
metadata adapters and produce `SearchBatch` containing raw record refs, normalized preliminary
`SourceRecord` values, query logs, pagination state and provider issues.

## Workflow

1. Select configured provider routes suited to the query, beginning with the plan's preferred
   route and using a complementary index where required.
2. Submit the canonical query and filters to the deterministic adapter. Never synthesize a
   record when a provider returns no result.
3. Continue pagination within the per-query and global raw-pool limits. Stop on explicit limit,
   exhausted cursor or the topic's stop rule.
4. Preserve provider IDs, returned metadata, retrieval time, query ID and raw-response reference.
5. Map provider data to preliminary `SourceRecord`; represent unavailable values as null.
6. Record unsuccessful queries, rate limits and partial provider failures. Use another approved
   route when available and retain both outcomes.

## Output requirements

- Every record names its source API, provider ID and query IDs.
- Title, authors, year, identifiers and abstract are copied or normalized from provider data.
- Search logs include query, filters, provider, page or cursor, timestamp and result count.
- Separate provider failure from a valid zero-result search.

## Boundaries

- Do not infer missing DOI, authors, publication year or abstract.
- Do not rank scientific quality or interpret full text.
- Do not bypass provider limits, authentication or access controls.

## Failure handling

Return degraded results when at least one approved route succeeds and list failed routes. Return
failed only when no usable provider response or valid record can be produced.

## Resume

Resume from stored provider cursor when valid. Otherwise rerun the query and deduplicate later by
stable identifiers; never silently append duplicates.
