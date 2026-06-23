---
name: g02-a09-synthesize-research-findings
description: Synthesize reviewed A07 evidence cards and coverage into ResearchState, EvidenceMap, a human validation packet and compact Solution Graph handoff in fast mode. Use when A08 is skipped by profile policy; introduce no new evidence, claim verification or slide content.
---

# Synthesize Research Findings

## Contract

Consume `research_synthesis_input@1` from `research_synthesis_prepare`: A07 paper evidence with
validated review-decision provenance,
retrieved corpus refs, candidate index, human source selection, ResearchPlan, source metadata,
approved context and output language. Produce `research_state@1`, `EvidenceMap`,
`UserResearchValidationPacket` and `SolutionInputCandidate`. In `fast`, A08 ClaimAssessment is
absent and must remain explicit as a limitation.

## Workflow

1. Validate that every included A07 review and evidence card belongs to the task and approved corpus.
   If no A07 artifact exists because A06 marked all downloads unavailable, preserve each retrieval
   gap as an unresolved insufficient-evidence item and still finalize A09.
2. Build `EvidenceMap` from claims or topic scope to evidence, sources, coverage and unresolved state.
3. Consolidate findings without erasing differences in scope, method or confidence.
4. Separate required updates, optional improvements, unresolved questions and no-change findings.
5. Link every recommendation to claim IDs and evidence refs. State accepted coverage exceptions.
6. Supply the findings, decisions needed, confidence, consequences of unresolved items and the
   skipped A08 limitation. The deterministic finalizer creates the human validation packet in
   `output_language`.
7. Let the finalizer create a compact Solution Graph candidate containing refs and cards, excluding
   PDFs and verbose reviews.
8. Call `research_synthesis_finalize` and return its exact envelope. The bundle is finalized later by
   `research_bundle_finalize` after Human Research Gate approval.

## Output requirements

- Every recommendation has evidence refs and a priority rationale.
- Unresolved and insufficient-evidence claims remain visible.
- The human packet distinguishes required updates from optional improvements.
- The downstream handoff contains only compact cards and artifact refs.
- Finding statuses are limited to `supported_by_reviewed_source`, `needs_human_check`,
  `insufficient_evidence`, `context_only` and `market_case_signal`.
- No output implies full claim verification when A08 was skipped.

## Boundaries

- Do not add evidence, re-evaluate papers, decide for the human or write final slides.
- Do not pass full documents, full corpus or verbose reviews to Solution Graph.
- Do not convert uncertainty into a definitive recommendation.
- Do not use labels such as "fully verified" in fast mode.

## Failure handling

Return degraded synthesis when some low-priority assessments are unavailable but all omissions are
visible. Return failed when core artifact identity or evidence traceability is broken.

## Resume

Regenerate affected mappings and summaries from revised assessments; preserve unaffected finding IDs.
