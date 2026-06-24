---
name: g02-orchestrate-research
description: Run the complete Research Graph from an approved input bundle through isolated producer agents, one universal reviewer, the human source-selection gate and the human research gate. Use as the graph's only conversational surface and final handoff coordinator.
---

# Orchestrate Research

Drive the Research Graph without performing producer work. Read
`shared/graphs/g02.graph.json` as the node and contract source of truth. Agents never address
the user; relay their questions and explain every required human action.

## Semantic Entry

- Treat "zrob research", "zrób research", "run research" and "run the research graph" as requests
  to run this workflow when the user provides, references or can supply a `research_graph_input@1`
  bundle.
- Claude may enter through `/research`; Codex enters semantically through this skill and the
  `research_run_codex` MCP tool when available.
- If the input bundle path or `artifact://` ref is missing, ask for exactly that value before
  starting the graph.

## Contract

- Consume a path or artifact reference satisfying `research_graph_input@1`.
- Produce only a validated `user_approved_research_bundle@1` descriptor after final human approval.
- Persist intermediate artifacts and carry refs instead of full documents in orchestration context.
- Use `envelope@1` for execution status, `review_task@1` for reviewer input and
  `review_decision@1` for reviewer verdicts.

The installed `research_graph_input@1` schema is approved and authoritative. Do not rename or
extend its fields inside the orchestrator.

## Workflow

1. Validate and register the input through the deterministic research front door. Stop on contract
   failure and explain the missing fields without inventing them.
2. Load the manifest and create the smallest authorized input bundle for each node. Do not pass the
   complete graph input when the agent needs only a topic, source set, document or claim group.
   For G02-A01 call `research_planner_prepare` before producer execution, pass only
   `research_planner_input@1` plus the allowed protocol, require the producer to return the exact
   envelope from `research_planner_finalize`, then build its review through
   `research_plan_review_task`.
3. Before G02-A02, call `research_provider_status`. For each approved topic call
   `research_domain_prepare`, pass only `domain_research_input@1`, and let the producer create one
   provider-neutral `query_plan@1`. In `fast`, call `research_query_plan_generate_fast` first and
   use the validated result unless it reports a structured gap. Require the producer to execute
   each authorized route through
   `research_metadata_search`; the agent never sends HTTP itself. Verify every returned valid DOI
   through `research_doi_verify` or `research_doi_verify_batch`, preserving conflicts and registry
   failures without overwriting provider metadata. The producer passes persisted search/DOI refs,
   selected source IDs and minimal semantic coverage assignments to
   `research_domain_finalize_from_results`; it never hand-builds the technical A02 wrapper. Build
   review or fast-track approval from the returned descriptor.
   - Pass the **entire `domain_research_input@1`** object from `research_domain_prepare` to the
     A02 agent without selecting, renaming or removing any field. In particular, never truncate
     `provider_capabilities`: include every entry returned by `research_domain_prepare`, including
     disabled providers (e.g. crossref with `enabled: false`). Omitting any entry causes
     `invalid_discovery_input_basis` on every `research_metadata_search` call.
4. From the reviewed A02 ref, run A03 through `research_canonical_prepare`, A04 through
   `research_recent_prepare`, and A11 through `research_market_cases_prepare`, with their matching
   finalize and review-task operations. A03 and A04 reuse exact upstream Crossref bindings and
   verify new DOI-bearing candidates. A11 executes only `research_web_case_search` in Tavily mode.
   SearXNG remains disabled and has no trusted endpoint catalog. The three discovery streams are logically independent but the current
   scheduler remains serial. Pass every available reviewed ref to A05; never browse when the A11
   operation reports an unavailable provider. In `fast`, A02 is required per topic while missing
   A03, A04 or A11 streams remain explicit optional warnings unless `mandatory_streams` requires
   them.
5. Review only through the deterministic review-task builders. Do not hand-build, trim or rename
   fields inside `review_task@1`. For A01 call `research_plan_review_task`; for other reviewed
   stages call the matching `*_review_task` operation.
   - Pass the **entire object** returned by any `*_review_task` call to `research_review_prepare`
     without selecting, renaming or removing any field. Never build a partial review-task object
     from scratch. Note: `evidence_requirements` entries use the key `requirement_id`
     (not `criterion_id`); using the wrong key causes `research_review_prepare` to return BLOCKED.
   - The artifact descriptor passed to any review-task builder must be **extracted directly from
     `envelope.produced[]`**: find the entry whose `schema_version` matches the producer output
     contract, then pass `{"type": <value>, "ref": <entry.path>, "schema_version": <value>,
     "artifact_version": <value>}`. Never hand-build a descriptor or use `artifact_ref` in place
     of `ref`. For `research_plan_review_task` the descriptor `type` must be the exact string
     `"research_plan"` — any other value causes the builder to reject the descriptor.
6. In the default fast profile, invoke G02-A10 for A01 Planner, A05 Candidate Source Index, A06
   Paper Retrieval and A09 Synthesizer. A07 review is conditional on degraded output, missing
   evidence locations, conflicts, prompt-injection flags or a central-document marker. For A02,
   A03, A04 and A11, a clean deterministic finalizer result receives a
   fast-track deterministic approval record and continues to A05. If the finalizer returns
   `degraded`, dependency problems, coverage gaps or provider issues, build the matching review
   task and run G02-A10.
7. Handle reviewer verdicts:
   - `APPROVED`: continue with the artifact ref; non-blocking advisories do not rerun the producer;
   - `REVISE`: return only the named findings to the same producer, allow one corrected artifact,
     run deterministic finalization, persist `revision_completion@1`, and continue without another
     reviewer invocation;
   - `BLOCKED`: stop the process and explain the blocking decision to the user.
   Never invoke A10 more than once for one producer run.
   A05 is fully derived from reviewed upstreams and profile settings. A05 `REVISE` therefore stops
   for an upstream, search-extension or profile change instead of rerunning the same deterministic
   index and recording a false correction.
8. After G02-A05 Candidate Source Index, run the Human Source Selection Gate. Present or link
   `candidate_source_review.md`, explain coverage and the actions DOWNLOAD, LIBRARY, CITATION,
   RESERVE, EXCLUDE and SEARCH_MORE through `research_source_selection_prepare`.
9. Map the template or natural-language answer to `human_source_selection@1`, validate it through
   `research_source_selection_validate`, accepting stable IDs or the displayed source numbers.
   Show the returned summary including the exact DOWNLOAD
   count and its scholarly/market-case split, and ask for a separate final confirmation. The human
   is the decision maker; A05 recommendations are advisory. Only after confirmation call
   `research_source_selection_finalize`. Route
   SEARCH_MORE to the relevant discovery agent, rebuild and re-review the index. Retrieval receives
   only the produced `human_approved_source_set@1` ref.
10. Run A06 through `research_retrieval_prepare`. For scholarly DOWNLOAD sources call
   `research_doi_verify` when an exact non-conflicting binding cannot be reused, then call
   `research_oa_resolve`, `research_document_retrieve` and `research_document_validate`. A critical
   DOI identity conflict makes that source unavailable for automated download. For market
   cases call `research_web_case_extract` with the final selection ref, reviewed A11 ref and exact
   approved source ID. Finalize both kinds through `research_retrieval_finalize`. Confirm that each
   accepted market case produced a readable Markdown document and a separate JSON audit artifact,
   then review the corpus through `research_retrieval_review_task` before A07.
11. Fan out G02-A07 evidence review per validated scholarly document and per human-approved market
   case file. Use `research_paper_review_prepare`, `research_document_text_index`,
   `research_document_text_window`, `research_paper_review_finalize` and
   `research_paper_review_task`. In `fast`, skip G02-A08 by profile policy and pass reviewed paper
   evidence directly to A09 with `synthesis_mode: evidence_without_claim_assessment`. Pass each A07
   artifact together with its exact review decision and optional revision-completion ref. Keep A08
   intact for later profiles. Run A10 conditionally for A07 according to step 6. If A06 has no
   accepted document because all selected downloads are unavailable or failed, continue to A09
   with explicit retrieval gaps and an empty reviewed A07 set.
12. Run A09 through `research_synthesis_prepare`, `research_synthesis_finalize` and
   `research_synthesis_review_task` as the terminal producer in `fast`, require its A10 review and
   emit no Graph03 handoff before approval. Then run the Human Research Gate with evidence-linked
   updates, limitations, unresolved questions, confidence and accepted coverage exceptions in
   `output_language`. Require explicit decisions for required updates, optional improvements and
   unresolved-item handling; reflect all three choices in the approved summary and bundle.
13. Apply requested corrections through the proper producer. Each new user-requested stage run has
    its own single review, while an A10-triggered correction is never reviewed a second time. After approval,
    validate, freeze and emit `user_approved_research_bundle@1` through
    `research_bundle_finalize`.

## Output requirements

- Keep a task, node, attempt and artifact-version audit trail.
- Persist the original A10 decision and a revision-completion receipt when `REVISE` is corrected.
- Give the user plain-language instructions at both gates, even when the underlying response is JSON.
- Require the boundary contract to provide `output_language` and preserve it in human-readable
  output.
- Never place full PDFs, extracted full text or verbose PaperReviews in the downstream handoff.

## Boundaries

- Do not perform literature search, source classification, paper review, claim assessment or synthesis.
- Do not let a producer self-approve or substitute multiple physical reviewers for the locked universal one.
- Do not bypass human confirmation before retrieval or final handoff.
- Do not expose secrets, private reasoning or unrelated state to an agent.
- Do not change graph order or boundary contracts in prompt logic.

## Failure handling

Relay `needs_input` with enough context and an exact response request. Continue from `degraded` only
when the producer and reviewer make omissions explicit and the manifest permits continuation. Stop on
`failed`, unresolved `BLOCKED` or invalid human authorization. Distinguish provider failure from a
valid empty search and preserve partial artifacts.

## Resume

Resume from the latest accepted artifact per node. Re-run a producer only when input, revision items,
human decisions or an upstream artifact version affecting it changed. Frozen human-approved bundles
are immutable; a later change creates a new task or version.
