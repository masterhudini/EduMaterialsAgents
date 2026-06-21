---
name: assess-claim-evidence
description: Assess one approved claim or tight claim group from reviewed evidence cards using separate evidence, currency, pedagogical, controversy and confidence dimensions. Use after Paper Review; preserve contrary evidence and unresolved states.
---

# Assess Claim Evidence

## Contract

Resolve `[TK-DECISION: CLAIM-ASSESSMENT-MODEL]` with TK during the 1b1 review of this skill and
`research-claim-verification` before freezing field values or compatibility mappings.

Consume original claim cards, accepted paper reviews and evidence cards, evidence coverage, audience
context and the configured claim-assessment model. Produce one `ClaimAssessment` per claim.

## Workflow

1. Validate evidence identity, location and relation. Exclude rejected or inaccessible-content assertions.
2. Group independent supporting, contradicting, qualifying and contextual evidence. Consider method fit,
   population, date, limitations and dependence between sources.
3. Assign `evidence_status`: supported, mixed, unsupported or insufficient_evidence.
4. Assess `currency_status`, `pedagogical_status` and `controversy_status` independently. Do not derive
   one dimension automatically from another.
5. Assign confidence from evidence quality, independence, consistency and coverage; explain uncertainty.
6. Select a bounded recommended action and lecture implication without drafting replacement slides.
7. Preserve unresolved questions and all contrary evidence refs.

## Output requirements

- Every dimension includes allowed value, rationale and relevant evidence refs.
- `insufficient_evidence` remains a valid outcome and cannot be converted to support by plausibility.
- Contested claims represent competing positions fairly.
- Keep compatibility labels derived and secondary when the system requests them.

## Boundaries

- Do not search for new sources, reread unassigned full texts or change the original claim.
- Do not treat citation count or reviewer approval as claim evidence.
- Do not hide accepted coverage exceptions.

## Failure handling

Return unresolved or insufficient evidence when coverage cannot support a verdict. Block when the
configured assessment model is contradictory or required claim identity is missing.

## Resume

Reassess only claims affected by new evidence, corrected cards, coverage changes or review findings.
