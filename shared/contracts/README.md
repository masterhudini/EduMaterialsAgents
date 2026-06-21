# shared/contracts — typed handoff artifacts

Versioned JSON-Schema files (a small subset: `type`, `required`, `properties`, `items`,
`enum`) validated offline by `core/contracts.py`. One file per artifact type:
`<type>.schema.json`. A reference is `"<type>@<major>"`; `x-major` in the file sets the major.

## Already here

- `envelope.schema.json` — **universal subagent return envelope** (`envelope@1`). Every
  isolated agent returns this shape: `{status, produced[], summary, issues[], metrics?,
  resume_token?}`. Reusable, domain-agnostic. Do not change without bumping `x-major`.
- `research_graph_input.schema.json` — approved Research Graph boundary input
  (`research_graph_input@1`).
- `review_task.schema.json` — one universal reviewer invocation (`review_task@1`) with one
  artifact, an explicit profile and observable review criteria.
- `review_decision.schema.json` — auditable universal reviewer result (`review_decision@1`).
- `user_approved_research_bundle.schema.json` — compact Research Graph handoff to Solution
  (`user_approved_research_bundle@1`).

For `envelope@1.produced[]`, `path` carries the `artifact://` URI of the produced artifact.
Typed handoff descriptors returned by `core/handoff.py` remain a separate boundary shape using
`ref`; they are not embedded unchanged in an agent envelope.

## To add for the Research Graph (from docs/research graph project.md)

Input bundles (cards, not full states) and output artifacts per node, e.g.:

- `research_graph_input` — §8.2 (approved context, domains, scope, claim/concept/flow cards).
- `research_plan`, `candidate_sources`, `claim_verification_state`,
  `recent_developments_state`, `canonical_sources_state`, `selected_sources`,
  `retrieved_corpus`, `paper_review`, `research_state`, `evidence_map`.
- `user_research_validation_packet` / `user_approved_research_bundle` — §9.

Keep these as **contracts of the handoff**, not full domain models — the graph passes cards
and `artifact://` refs, not entire states (§8.3).
