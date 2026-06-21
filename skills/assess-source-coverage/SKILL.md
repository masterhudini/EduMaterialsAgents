---
name: assess-source-coverage
description: Assess candidate, human-selection or full-evidence coverage against explicit ResearchPlan units and source-role requirements. Use at candidate indexing, claim verification and synthesis to expose covered, partial, missing and human-accepted exception states.
---

# Assess Source Coverage

## Contract

Consume coverage requirements, relevant source or evidence records, stage (`candidate`, `selection`
or `evidence`) and accepted exceptions. Produce `CoverageMatrix`, warnings, unmet mandatory units
and stop-rule assessment.

## Workflow

1. Enumerate approved coverage units by topic, claim, source role and priority.
2. At candidate stage, count defensible candidate mappings by role without treating metadata as
   evidence.
3. At selection stage, use only human-approved actions and show what DOWNLOAD, LIBRARY, CITATION,
   RESERVE or EXCLUDE leaves uncovered.
4. At evidence stage, count only accepted evidence cards with resolvable locations and suitable
   access; separate supportive, qualifying and critical evidence.
5. Assign `covered`, `partial`, `missing` or `exception_accepted` and cite contributing IDs.
6. Apply configured minimums and saturation rules. A high candidate count cannot replace a missing
   mandatory role.
7. Produce actionable search or review gaps without selecting sources itself.

## Output requirements

- Keep candidate coverage distinct from evidence coverage.
- Every status cites requirement and contributing or missing IDs.
- Human exceptions preserve author, reason and decision reference.
- Report both numeric counts and semantic role gaps.

## Boundaries

- Do not invent mappings, waive mandatory units or override human decisions.
- Do not interpret inaccessible content as evidence.

## Failure handling

Block assessment when requirements are absent or contradictory. Return degraded assessment when
some artifacts are unavailable and state which statuses remain indeterminate.

## Resume

Recalculate only units affected by changed sources, evidence or human decisions; preserve unit IDs.
