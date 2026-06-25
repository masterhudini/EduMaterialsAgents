# shared/contracts — typed handoff artifacts

Versioned JSON-Schema files (a small subset: `type`, `required`, `properties`, `items`,
`enum`) validated offline by `core/contracts.py`. One file per artifact type:
`<type>.schema.json`. A reference is `"<type>@<major>"`; `x-major` in the file sets the major.

## Already here

- `envelope.schema.json` — **universal subagent return envelope** (`envelope@1`). Every
  isolated agent returns this shape: `{status, produced[], summary, issues[], metrics?,
  resume_token?}`. Reusable, domain-agnostic. Do not change without bumping `x-major`.
- `research_graph_input.schema.json` — approved Research Graph boundary input
  (`research_graph_input@1`, version 1.1 requires explicit recent-discovery policy).
- `pdf_extract_result.schema.json` — optional local G01 PDF text extraction result
  (`pdf_extract_result@1`). It is valid both for successful `pypdf` extraction and for explicit
  dependency-missing or parser-failed states, so hosts do not silently fabricate slide text.
- `research_planner_input.schema.json` — isolated G02-A01 input projected from the approved
  boundary (`research_planner_input@1`).
- `research_plan.schema.json` — bounded, versioned G02-A01 output (`research_plan@1`, version 1.1
  preserves the unchanged approved research scope used by downstream discovery).
- `scout_search_request.schema.json` is the deterministic per-topic request derived from A01.
  `scout_retrieved_corpus.schema.json` and `scout_run_index.schema.json` describe the persistent
  pre-A07 PDF handoff produced by the parallel Scout profile. They are deliberately distinct from
  A06 `retrieved_corpus@1`, which remains tied to human source selection and validated A06 policy.
- `scout_a07_reviews.schema.json` describes the bounded Scout-to-A07 light-review handoff. It
  records per-topic/source work items, parallel partial-output locations, presentation update
  candidates, lookup pointers, coverage gaps and irrelevant sources before A09 prepares the final
  Graph03 handoff.
- `scout_a07_partial_review.schema.json` is the single-worker A07 result for one Scout
  `(topic_id, source_id)` work item. Workers write these under `partial/<topic>/<source>.review.json`;
  the parent aggregator rebuilds `scout_a07_reviews@1` from them.
- `scout_a07_model_task.schema.json` is the compact host-model task for one Scout A07 light review.
  It carries one immutable work item, selected PDF windows and only the linked intake cards needed
  to decide whether the source adds presentation-facing substance.
- `scout_a07_deep_dive.schema.json` is the bounded A09 follow-up package for at most five selected
  A07 lookup pointers. It records the selection criterion, up to twelve additional windows per
  source and explicit fail-open limitations before deterministic finalization.
- `scout_a09_model_task.schema.json` is the compact host-model task for the obligatory G02-A09
  scout_fast pass (opus/medium). It carries the deterministic baseline plan to verify and refine,
  the A07 candidates, linked intake cards and bounded deep-dive windows (at most five sources,
  eight windows and 1200 characters per window), with full-PDF reading forbidden.
- `literature_provider_config.schema.json` defines the secret-free G02 provider profile. Version
  1.2 adds Crossref readiness and rate policy beside the web and retrieval sections; credentials
  and the required contact email remain environment-only.
- `doi_verification_result.schema.json` records Crossref DOI registry status, conservative
  bibliographic comparisons, conflicts and raw-response provenance without overwriting provider
  metadata.
- `domain_research_input.schema.json` is the isolated G02-A02 input for one approved topic.
- `query_plan.schema.json` defines bounded, provider-neutral search routes (`query_plan@1`, contract
  version 1.3 within major 1), including semantic bases and controlled Tavily, SearXNG or
  `auto_budgeted` A11 routes.
- `source_record.schema.json` is the normalized provider record shared by discovery agents. Version
  1.2 keeps the optional `market_case` block and separates provider publication/result date from
  semantically supported event date, preventing deterministic normalization from conflating them.
- `literature_tool_result.schema.json` records one deterministic provider operation and provenance;
  version 1.1 also binds every search result to the exact scoped discovery input identity.
- `domain_candidate_sources.schema.json` is the reviewed G02-A02 output
  (`domain_candidate_sources@1`).
- `canonical_research_input.schema.json` is the isolated G02-A03 input projected from one approved
  topic and one reviewed DomainCandidateSources artifact (`canonical_research_input@1`).
- `recent_research_input.schema.json` is the isolated G02-A04 input. Its inclusive calendar window
  is projected from the ResearchPlan copy of intake `recency_window_years` and one reviewed A02
  artifact (`recent_research_input@1`).
- `market_case_research_input.schema.json` is the minimal G02-A11 input projected from one approved
  topic and reviewed A02 identity. It contains traceable needs, tier policy, limits and redacted
  provider capabilities, without the whole intake or scholarly candidate records.
- `web_case_tool_result.schema.json` records one scoped A11 discovery operation, underlying
  provider runs, public budget counters, normalized records and provenance.
- `candidate_sources.schema.json` defines the reviewed discovery-stream artifact
  (`candidate_sources@1`). Version 1.3 freezes canonical, recent and market-case variants with
  unchanged provider records and separate stream annotations.
- `human_source_selection.schema.json` freezes the human authorization dependency required by A11
  extraction. A05 remains responsible for producing and confirming this artifact.
- `web_case_extract_result.schema.json` returns only a bounded untrusted-content descriptor, hash,
  provenance and safety flags after the gate; full page text is not returned inline.
- `retrieved_corpus.schema.json` version 1.2 represents each accepted market case as a bundle with
  a human-readable Markdown ref and checksum plus a separate machine JSON ref and checksum. The
  document is rendered from reviewed A11 semantics and the gated untrusted extraction.
- `retrieval_directory.schema.json` describes the stable A06 run folder, its manifest, scholarly
  document directory and gated market-case directory without embedding local filesystem paths.
- `paper_review.schema.json` version 1.2 is the compact A07 per-source evidence review. It binds
  source ID, reviewed document ref, topic and claim IDs, evidence cards, locations, confidence,
  evidence access level, prompt-injection flags and `review_profile_ref: paper_evidence`.
- `research_state.schema.json` version 1.2 is the A09 fast synthesis artifact. It keeps conservative
  finding statuses, compact evidence refs, the human validation packet, SolutionInputCandidate and
  an explicit `claim_assessment_performed: false` limitation when A08 is skipped.
- `evidence_map.schema.json`, `user_research_validation_packet.schema.json`,
  `solution_input_candidate.schema.json` and `research_summary.schema.json` freeze the compact
  auxiliary A09 artifacts emitted beside `research_state@1`. Version 1.2 of
  `solution_input_candidate.schema.json` gives every Scout `slide_update_plan` item a concrete
  target with backward-compatible `affected_slides`/`section_hint` and canonical
  `slide_ids`/`section`/`placement` fields, plus A09 model-pass audit fields. Version 1.4 makes the
  Scout G02 handoff self-contained for Graph03: each `suggested_updates`/`optional_improvements`
  item carries the analyzed-article opinion (`finding`, `rationale`, `extension_relation`,
  `confidence`) with `evidence_refs` quotes and object `source_refs`; `coverage_summary` records a
  per-claim/driver `covered`/`partial`/`uncovered` status with source counts; `slide_ids` are
  coerced to strings; and `presentation_context`/`intake_ref` accept null for the no-intake path.
- `review_task.schema.json` — one universal reviewer invocation (`review_task@1`) with one
  artifact, an explicit profile and observable review criteria.
- `review_decision.schema.json` — auditable universal reviewer result (`review_decision@1`).
- `revision_completion.schema.json` proves deterministic completion of the one allowed producer
  correction after a `REVISE` decision, without a second reviewer invocation.
- `research_run_report.schema.json` — fail-closed status and approved artifact/review refs for a
  bounded real-host run of the implemented fast frontier through reviewed A09
  (`research_run_report@1`).
- `user_approved_research_bundle.schema.json` version 1.2 is the compact Research Graph handoff to
  Solution/Graph03 (`user_approved_research_bundle@1`). It stores the exact three-part Human
  Research Gate decision and is created only after explicit approval.

For `envelope@1.produced[]`, `path` carries the `artifact://` URI of the produced artifact.
Typed handoff descriptors returned by `core/handoff.py` remain a separate boundary shape using
`ref`; they are not embedded unchanged in an agent envelope.

## To add for the Research Graph (from docs/research graph project.md)

Input bundles (cards, not full states) and output artifacts per node, e.g.:

- `research_graph_input` — §8.2 (approved context, domains, scope, claim/concept/flow cards).
- `claim_verification_state`,
  `recent_developments_state`, `selected_sources`,
  `retrieved_corpus`, `paper_review`, `research_state`, `evidence_map`.
- `user_research_validation_packet` / `user_approved_research_bundle` — §9.

Keep these as **contracts of the handoff**, not full domain models — the graph passes cards
and `artifact://` refs, not entire states (§8.3).
