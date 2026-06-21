---
name: g02-a05-rank-source-candidates
description: Rank Research Graph source candidates for human review using explicit relevance, role, coverage, access, canonical and recency signals. Use after normalization and deduplication; keep component scores visible and never collapse citation count into quality.
---

# Rank Source Candidates

## Contract

Consume deduplicated `SourceRecord` values, ResearchPlan coverage requirements, role assignments,
selection profile and limits. Produce component scores, rank, recommended action and rationale.

## Workflow

1. Reject records outside approved topic or with unresolved identity before scoring.
2. Score separate dimensions: topic and claim relevance, uncovered coverage contribution, required
   role fit, canonical signal, recent or rising signal, accessible-content level and redundancy.
3. Apply configured weights and caps. Keep canonical and rising scores separate.
4. Penalize redundancy after coverage contribution, not merely similarity of titles.
5. Promote qualifying or critical evidence when required coverage lacks it.
6. Assign `DOWNLOAD`, `LIBRARY`, `CITATION`, `RESERVE` or `EXCLUDE` as a recommendation for human
   review, never as the final decision.

## Output requirements

- Preserve every component score, weight, missing signal and ranking explanation.
- A metadata-only canonical anchor may rank for `LIBRARY` or `CITATION`, not as downloadable proof.
- Ties remain explicit and deterministically ordered by stable source ID.

## Boundaries

- Do not use citation count as a quality verdict or hide configured weighting.
- Do not exceed display limits or download anything.
- Do not convert recommendations into human approval.

## Failure handling

Rank with available dimensions and mark degraded confidence when optional signals are missing.
Block ranking when the selection profile or mandatory coverage units are absent.

## Resume

Recompute affected ranks when records, weights, roles or coverage change; preserve source IDs.
