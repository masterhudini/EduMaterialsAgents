---
name: g02-a05-annotate-source-candidates
description: Create concise human-readable scholarly and market-case descriptions grounded only in available metadata, abstract or reviewed A11 annotations. Use when generating candidate_source_review.md before the human download decision, respecting output_language and explicit access limitations.
---

# Annotate Source Candidates

## Contract

Consume a ranked `SourceRecord`, topic and coverage mapping, role assignments, access level and
`output_language`. Produce a short annotation, relevance reason, limitations and recommended human
action.

## Workflow

1. Identify the strongest available content basis: abstract or metadata for scholarly sources, and
   reviewed A11 market fact plus didactic mechanism for market cases.
2. Summarize only information visible at that access level. For metadata-only records, describe
   bibliographic role and discovery signals without asserting arguments or findings.
3. Explain why the source may help a named topic, claim or coverage unit.
4. Store `description_basis` and the bounded `basis_excerpt`. State access restrictions, preprint
   or version status, missing abstract and uncertainty. For a market case, state that the page has
   not been extracted before the gate.
5. Translate human-readable prose into `output_language`; preserve IDs, status values and field names.
6. Keep the annotation short enough for comparison across the candidate list.

## Output requirements

- Distinguish `what is known` from `why it may be useful`.
- A metadata-only description must explicitly say that it does not summarize publication contents.
- Keep market source tier, market materiality and scientific quality as separate fields.
- Include source ID, role, access, coverage contribution and recommended action.
- Never use generic praise or unsupported quality language.

## Boundaries

- Do not read or imply unavailable full text.
- Do not verify claims, make the human decision or fabricate an abstract.

## Failure handling

When no abstract exists, produce a metadata-only annotation with a visible warning. Fail only when
source identity or topic mapping is unusable.

## Resume

Regenerate when source metadata, access level, mapping or output language changes.
