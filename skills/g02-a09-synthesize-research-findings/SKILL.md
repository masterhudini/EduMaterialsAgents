---
name: g02-a09-synthesize-research-findings
description: Synthesize reviewed claim assessments, evidence cards and coverage into ResearchState, EvidenceMap, a human validation packet and compact Solution Graph handoff. Use after claim verification; introduce no new evidence or slide content.
---

# Synthesize Research Findings

## Contract

Consume reviewed claim assessments, accepted paper evidence, evidence coverage, source metadata,
approved context and output language. Produce `ResearchState`, `EvidenceMap`,
`UserResearchValidationPacket` and `SolutionInputCandidate`.

## Workflow

1. Validate that every included assessment and evidence card belongs to the task and approved corpus.
2. Build `EvidenceMap` from claims to assessment, evidence, sources, coverage and unresolved state.
3. Consolidate findings without erasing differences in scope, method or confidence.
4. Separate required updates, optional improvements, unresolved questions and no-change findings.
5. Link every recommendation to claim IDs and evidence cards. State accepted coverage exceptions.
6. Create the human validation packet in `output_language` with plain instructions, decisions needed,
   confidence and consequences of unresolved items.
7. Create a compact Solution Graph candidate containing cards and refs, excluding PDFs and verbose reviews.

## Output requirements

- Every recommendation has evidence refs and a priority rationale.
- Unresolved and insufficient-evidence claims remain visible.
- The human packet distinguishes required updates from optional improvements.
- The downstream handoff contains only compact cards and artifact refs.

## Boundaries

- Do not add evidence, re-evaluate papers, decide for the human or write final slides.
- Do not pass full documents, full corpus or verbose reviews to Solution Graph.
- Do not convert uncertainty into a definitive recommendation.

## Failure handling

Return degraded synthesis when some low-priority assessments are unavailable but all omissions are
visible. Return failed when core artifact identity or evidence traceability is broken.

## Resume

Regenerate affected mappings and summaries from revised assessments; preserve unaffected finding IDs.
