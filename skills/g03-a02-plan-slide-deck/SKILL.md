---
name: g03-a02-plan-slide-deck
description: Plan the new lecture deck for Graph03 — assign a change status to every existing slide and propose new slides (grounded only in g02 coverage gaps, unresolved items, optional improvements, topics, recommended claims and market-case findings) interleaved between them, producing slide_plan@1. Executable procedure run by g03-a02; not interactive.
---

# Plan Slide Deck

## Contract

Consume the G03 boundary (`solution_graph_input@1`) plus g03-a01's `solution_blueprint@1`. Hydrate the
blueprint, the lecture baseline and the research candidate. Produce a `slide_plan@1`: the ordered
skeleton of the NEW deck (existing slides with a change status, plus proposed new slides), persisted
through `solution_slide_plan_finalize`. Plan only — no slide content, no evidence beyond the candidate.

## Workflow

1. Start from the `solution_slide_plan_build` deterministic draft (existing slides default `KEEP`,
   `UPDATE` where g03-a01 applied a research update, one `ADD` per candidate
   gap/unresolved/optional/recommended-claim/market-case item).
2. For each existing slide confirm or adjust the status: `KEEP` (good as-is), `UPDATE` (research
   changes it), `MERGE`/`SPLIT`/`REORDER` (didactics), `REMOVE` (rare, with a reason). Be conservative.
   Never touch a `locked` slide or locked section.
3. For each proposed new slide, keep/merge/drop it so it carries genuinely new, useful information from
   `coverage_gaps` / `unresolved_items` / `optional_improvements` / `topics_covered` /
   `recommended_claims` / hydrated `market_case_findings_ref`; record the source in
   `evidence_basis`; place it at a sensible position that respects prerequisite order. Keep proposals
   loose: `working_title`, `rationale`, `content_pointers.add` — not finished slide text.
   Treat `recommended_claim:*` and `market_case:*` basis values as additive enrichment material; merge
   or drop them when redundant. Never create a slide from `market_case_ref:unavailable`.
4. Carry `deferred_items` and `source_attribution` from the blueprint; recompute `change_stats`.
5. Persist with `solution_slide_plan_finalize` and return its envelope.

## Output requirements

A validated `slide_plan@1`: ordered `slots[]` with statuses, `content_pointers`, `evidence_basis`,
`source_refs`, `locked`; plus `deferred_items`, `source_attribution`, `change_stats`. In the lecture
language.

## Boundaries

No slide content/design/notes; no prompt building; no evidence or sources beyond the candidate; no
locked-slide changes; no calls to G01/G02; no PDF reading.

## Failure handling

`needs_input` on absent/contradictory upstream refs. A candidate item with no plausible anchor becomes
a `deferred_item` with a reason — never a guessed slide.

## Resume

Stateless; regenerate only the affected slots on revision.

{{HOST_ADAPTER}}
