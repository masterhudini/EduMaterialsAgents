---
name: g02-expand-citation-graph
description: Expand approved seed sources through real citation and recommendation relations while preserving why each candidate was reached. Use for canonical discovery or complementary domain and recent searches after seed identity has been verified.
---

# Expand Citation Graph

## Contract

Consume verified seed `SourceRecord` values, topic coverage units, allowed directions and depth
or result limits. Produce `CitationExpansion` with candidates, relation type, seed ID, distance,
provider provenance and inclusion reason.

## Workflow

1. Reject seeds without a provider-resolvable identifier. Never match a seed by title alone when
   the match is ambiguous.
2. Use configured deterministic citation tools for cited-by, references or recommendation edges
   authorized by the strategy.
3. Limit expansion by depth, result count, year and work type. Prefer one-hop evidence unless the
   plan explicitly authorizes more.
4. Keep the edge that introduced each record and map it to a topic or coverage unit.
5. Record graph centrality or citation signals as discovery signals, not quality judgments.
6. Send records through metadata normalization and later deduplication before inclusion.

## Output requirements

- Each candidate includes seed, relation, distance, provider ID, query or operation ID and reason.
- Preserve valid zero-edge results and partial provider errors.
- Do not replace bibliographic fields already supported by stronger provenance.

## Boundaries

- Do not declare a source canonical solely because it is highly cited or graph-central.
- Do not traverse closed full text or infer the semantic content of a citation.
- Do not exceed approved graph depth or scope.

## Failure handling

Return degraded when some seeds or relations cannot be resolved. Return failed only when no seed
can be resolved and no expansion artifact can be formed.

## Resume

Preserve completed seed-operation pairs. On revision, expand only new seeds or specifically
requested relations.
