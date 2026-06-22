---
name: g02-search-scholarly-metadata
description: Execute approved query_plan@1 routes through the deterministic research_metadata_search MCP operation and consume provider-backed literature_tool_result@1 records. Use in authorized discovery agents for OpenAlex, Semantic Scholar or arXiv metadata, with cache, retry, pagination and provenance controlled by the runtime.
---

# Search Scholarly Metadata

## Contract

Consume a validated `query_plan@1`, one `route_id`, one authorized provider, an optional cursor and
exactly one scoped `domain_input`, `canonical_input` or `recent_input`.
Call `research_metadata_search`. Receive one `literature_tool_result@1` plus its persisted artifact
reference. The result contains normalized `source_record@1` values, pagination state, raw-response
references, cache status, provider request IDs and explicit issues.

## Workflow

1. Confirm provider readiness through the scoped capabilities or `research_provider_status`.
2. Call `research_metadata_search` with structured input. Do not construct URLs, headers or API
   keys in the agent context.
3. Preserve the returned result even when it contains zero records, partial status, rate limiting
   or provider failure.
4. Require `request.scope` to match the supplied scoped input exactly. Never reuse a result from
   another task, topic, ResearchPlan or reviewed A02 artifact.
5. Continue from `pagination.next_cursor` only when the topic limit and saturation rule permit it.
6. Copy normalized records unchanged. The provider layer alone maps external payloads into
   `source_record@1`.
7. Put the operation ID, route, query, provider, status, record count and result artifact reference
   into the owning Domain, Canonical or Recent operation log.
8. For each `partial`, `unavailable` or `failed` result, copy the operation ID, provider, status and
   complete structured issue list into `provider_issues` without rewriting messages.

## Output requirements

- Every accepted record has provider ID, query ID, retrieval time and raw-response reference.
- Preserve null metadata. Do not transform a missing field into a model-generated value.
- Distinguish valid zero results from unavailable or failed provider operations.
- Preserve `provider_filter_unverifiable` when an index cannot enforce an approved filter; never
  fill missing language metadata or claim that the filter was guaranteed.
- Preserve cursors and cache information needed for resume and audit.

## Boundaries

- Do not use WebSearch, WebFetch or direct HTTP as an alternative provider path.
- Do not bypass rate limits, retries, enabled-provider configuration or endpoint allowlists.
- Do not place contact email or API keys in prompts, output artifacts or logs.
- Do not rank quality, classify final source roles, verify claims or interpret full text.

## Failure handling

Propagate structured provider issues. A successful route with zero records is valid. Mark the
producer degraded when another route is usable; fail the producer when no auditable provider result
can support a candidate artifact.

## Resume

Reuse cached results and persisted operation references. Continue from a valid cursor or rerun the
same route; retain stable provider source IDs and defer cross-provider deduplication to G02-A05.
