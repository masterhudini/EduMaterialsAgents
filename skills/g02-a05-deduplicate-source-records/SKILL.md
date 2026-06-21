---
name: g02-a05-deduplicate-source-records
description: Merge duplicate scholarly SourceRecords across providers using stable identifiers and conservative bibliographic matching. Use when combining domain, canonical and recent candidate pools while preserving all provenance and avoiding false merges.
---

# Deduplicate Source Records

## Contract

Consume normalized `SourceRecord` values and produce canonical records, merge groups, unresolved
possible-duplicate groups and a deterministic merge log.

## Workflow

1. Match exact normalized DOI first, then trusted provider crosswalks, arXiv identifiers and ISBN
   plus edition rules.
2. For records without stable crosswalks, compare normalized title, author overlap, year, venue and
   work type. Use conservative thresholds and never merge on title similarity alone.
3. Keep editions, translations, preprint-to-version-of-record relations and book chapters as
   distinct records unless the contract explicitly defines an equivalence relation.
4. Merge field values by provenance priority, preserving conflicts and every provider ID, query ID
   and raw record reference.
5. Assign or retain one stable `source_id` per canonical work and record `merged_from_records`.
6. Send ambiguous groups to manual or later semantic resolution without losing either record.

## Output requirements

- Every merge has a rule, matched evidence and input IDs.
- No source provenance, role signal or query relation is dropped.
- Ambiguous candidates remain separate and are visibly linked as possible duplicates.

## Boundaries

- Do not merge merely to reduce count.
- Do not rank, summarize or decide scientific equivalence of versions.

## Failure handling

Return unmerged records with warnings when identity is ambiguous. Fail only if stable source IDs or
the merge log cannot be produced.

## Resume

Use the prior merge map. Re-evaluate only new records and groups affected by corrected identifiers.
