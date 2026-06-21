---
name: normalize-source-metadata
description: Normalize real provider records into the Research Graph SourceRecord schema while preserving provenance and nulls. Use before cross-provider deduplication, ranking or candidate-index generation; never invent missing bibliographic data.
---

# Normalize Source Metadata

## Contract

Consume provider records plus raw-response refs. Produce normalized `SourceRecord` values with
identifiers, bibliographic fields, available content, signals, access data and provenance.

## Workflow

1. Preserve the raw provider record reference and retrieval metadata.
2. Normalize DOI casing and URL prefixes, provider IDs, whitespace, Unicode, author ordering,
   dates, language and work-type vocabulary.
3. Keep provider-specific values when the shared schema lacks an exact mapping; do not coerce them
   into a false category.
4. Reconcile fields only when provenance identifies the same work. Prefer authoritative identifier
   registries for identifiers and publisher or repository data for version and access statements.
5. Represent absent or conflicting values as null or an explicit conflict entry.

## Output requirements

- Preserve all source APIs, query IDs, retrieval time and raw refs.
- Keep abstract text linked to its provider and access level.
- Emit deterministic normalization warnings for malformed identifiers and conflicts.

## Boundaries

- Do not infer missing metadata from general knowledge.
- Do not deduplicate distinct works, assign roles or assess relevance.

## Failure handling

Return a degraded record when identity is usable but optional fields conflict. Reject records with
no defensible title or stable provider identity and report them separately.

## Resume

Normalization is idempotent. Re-run when provider data or normalization rules change.
