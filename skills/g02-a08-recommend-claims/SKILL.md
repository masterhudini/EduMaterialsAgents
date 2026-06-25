---
name: g02-a08-recommend-claims
description: Bind A09's scholarly synthesis (solution_input_candidate@1) and A11's real-world cases (market_case_findings@1) into additive, per-topic recommendations of interesting, well-documented claims worth featuring. Use in g02-a08-claim-verification, last before the User Research Gate. No web search; research/topic level only; recommend, do not critique.
---

# Recommend Claims

## Contract

Consume the `a08_claim_recommend_task@1` payload: `topics`, the `scholarly_synthesis` (A09 suggested
updates with evidence refs), the `web_cases` (A11 findings) and `output_language`. Produce the
additive `recommended_claims` array for `research_a08_finalize` to write back into
`solution_input_candidate@1`. Use no web search — bind only the two supplied streams.

## Workflow

1. Group the scholarly synthesis and web cases by `topic_id`.
2. Per topic, select the interesting, well-documented claims worth featuring. Prefer convergent
   support; set `support_basis: both` when a scholarly finding and a real-world case reinforce each
   other, else `literature` or `web`.
3. Write one `claim` and one `why_interesting` (student value) per recommendation. Cite
   `literature_refs` for scholarly support and `web_case_refs` (A11 `case_id`s) for real-world.
4. Set `confidence` from evidence strength and convergence, not rhetorical certainty.

## Output requirements

- Every recommendation maps to one `topic_id` present in the candidate.
- `support_basis` matches the refs supplied.
- `claim` (what to feature) and `why_interesting` (why) are stated separately.
- `both` is used only when literature and a web case genuinely reinforce the same claim.

## Boundaries

- Use no web search; do not gather new evidence.
- Recommend additions; do not critique the current slides or mark them wrong.
- Do not draft slide text or choose slide placement — that is Graph03's job.
- Do not invent claims unsupported by the supplied synthesis or cases.

## Failure handling

Ground every recommendation in the supplied streams. With no reliable pass, omit the finalize output
so the deterministic fallback derives recommendations from the web cases and top scholarly updates.
