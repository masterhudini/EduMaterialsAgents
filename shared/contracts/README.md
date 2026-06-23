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
- `review_task.schema.json` — one universal reviewer invocation (`review_task@1`) with one
  artifact, an explicit profile and observable review criteria.
- `review_decision.schema.json` — auditable universal reviewer result (`review_decision@1`).
- `revision_completion.schema.json` proves deterministic completion of the one allowed producer
  correction after a `REVISE` decision, without a second reviewer invocation.
- `research_run_report.schema.json` — fail-closed status and approved artifact/review refs for a
  bounded real-host run of the implemented A01–A06 frontier (`research_run_report@1`).
- `user_approved_research_bundle.schema.json` — compact Research Graph handoff to Solution
  (`user_approved_research_bundle@1`).

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
