---
name: g02-expand-citation-graph
description: Expand verified scholarly seeds from canonical_research_input@1 or recent_research_input@1 through research_citation_expand. Use for bounded A03 or A04 one-hop discovery while preserving seed, relation, provider and result provenance; never infer an edge or content without a returned provider result.
---

# Expand Citation Graph

## Contract

Consume `canonical_research_input@1` or `recent_research_input@1` as `discovery_input`, one member
of `verified_seed_ids`, an allowed relation, provider, cursor and bounded limit. Call
`research_citation_expand`. Receive one persisted
`literature_tool_result@1` with `operation_type: citation_expand` and normalized
`source_record@1` values.

## Workflow

1. Reject a seed absent from `verified_seed_ids`; never recover identity by title similarity.
2. Select only supported combinations: OpenAlex `cited_by`; Semantic Scholar `references`,
   `cited_by` or `recommendations`. Treat arXiv citation expansion as unavailable.
3. Keep depth at one and limit at or below `search_limits.per_seed_relation_limit`.
4. Preserve the complete tool result, including zero records, pagination, cache state, request IDs,
   raw-response refs and structured issues.
5. Require `request.scope` to match the complete prepared input. Never reuse a result from another
   task, topic, ResearchPlan or reviewed A02 artifact.
6. Copy normalized records unchanged. Record the introducing seed, relation, distance one,
   provider and operation ID in the producer annotation.
7. Preserve `canonical_expansion` for A03 and `recent_expansion` for A04 as returned by the runtime.
8. Continue a cursor only while candidate and operation budgets permit it.

## Output requirements

- Every edge resolves to the persisted operation that observed it.
- Citation counts, graph position and recommendations remain discovery signals.
- Preserve duplicate works as separate provider records until G02-A05 deduplication.

## Boundaries

- Do not declare canonicality, scientific quality or semantic agreement from an edge alone.
- Do not traverse closed full text, exceed one hop, call direct HTTP or emulate an unavailable edge.
- Do not expose API keys, contact data or raw response bodies.

## Failure handling

Preserve `partial`, `unavailable` and `failed` results. Continue other authorized seed-relation
pairs when possible. Return an external dependency issue when the MCP operation is unavailable.

## Resume

Reuse completed seed-provider-relation-operation tuples and persisted cursors. Expand only new or
reviewer-targeted tuples.
