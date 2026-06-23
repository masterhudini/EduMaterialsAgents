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
   For G02-A01 call `research_planner_prepare`, pass only `research_planner_input@1`, finalize with
   `research_planner_finalize` and build its review through `research_plan_review_task`.
3. Before G02-A02, call `research_provider_status`. For each approved topic call
   `research_domain_prepare`, pass only `domain_research_input@1`, and let the producer create one
   provider-neutral `query_plan@1`. Execute each authorized route through
   `research_metadata_search`; the agent never sends HTTP itself. Verify every returned valid DOI
   through `research_doi_verify` or `research_doi_verify_batch`, preserving conflicts and registry
   failures without overwriting provider metadata. Finalize only through
   `research_domain_finalize` and build review through `research_domain_review_task`.
4. From the reviewed A02 ref, run A03 through `research_canonical_prepare`, A04 through
   `research_recent_prepare`, and A11 through `research_market_cases_prepare`, with their matching
   finalize and review-task operations. A03 and A04 reuse exact upstream Crossref bindings and
   verify new DOI-bearing candidates. A11 executes only `research_web_case_search` in Tavily mode.
   SearXNG remains disabled and has no trusted endpoint catalog. The three discovery streams are logically independent but the current
   scheduler remains serial. Preserve all three reviewed refs for A05; never browse when the A11
   operation reports an unavailable provider.
5. After every producer artifact, construct exactly one `review_task@1` with the artifact, node profile,
   producer input, output contract, acceptance criteria and revision history. Prepare it through
   `research_review_prepare`, invoke `g02-a10-output-reviewer`, then submit the decision through
   `research_review_finalize`.
6. Handle reviewer verdicts:
   - `APPROVED`: continue with the artifact ref; non-blocking advisories do not rerun the producer;
   - `REVISE`: return only the named findings to the same producer, allow one corrected artifact,
     run deterministic finalization, persist `revision_completion@1`, and continue without another
     reviewer invocation;
   - `BLOCKED`: stop the process and explain the blocking decision to the user.
   Never invoke A10 more than once for one producer run.
7. After G02-A05 Candidate Source Index, run the Human Source Selection Gate. Present or link
   `candidate_source_review.md`, explain coverage and the actions DOWNLOAD, LIBRARY, CITATION,
   RESERVE, EXCLUDE and SEARCH_MORE through `research_source_selection_prepare`.
8. Map the template or natural-language answer to `human_source_selection@1`, validate it through
   `research_source_selection_validate`, accepting stable IDs or the displayed source numbers.
   Show the returned summary including the exact DOWNLOAD
   count and its scholarly/market-case split, and ask for a separate final confirmation. The human
   is the decision maker; A05 recommendations are advisory. Only after confirmation call
   `research_source_selection_finalize`. Route
   SEARCH_MORE to the relevant discovery agent, rebuild and re-review the index. Retrieval receives
   only the produced `human_approved_source_set@1` ref.
9. Run A06 through `research_retrieval_prepare`. For scholarly DOWNLOAD sources call
   `research_doi_verify` when an exact non-conflicting binding cannot be reused, then call
   `research_oa_resolve`, `research_document_retrieve` and `research_document_validate`. A critical
   DOI identity conflict makes that source unavailable for automated download. For market
   cases call `research_web_case_extract` with the final selection ref, reviewed A11 ref and exact
   approved source ID. Finalize both kinds through `research_retrieval_finalize`. Confirm that each
   accepted market case produced a readable Markdown document and a separate JSON audit artifact,
   then review the corpus through `research_retrieval_review_task` before A07.
10. Fan out G02-A07 evidence review per validated scholarly document and per human-approved market
   case file. Then run G02-A08
   Claim Verification per independent claim or tight claim group. Preserve artifact isolation and
   join only reviewed results.
11. After reviewed synthesis, run the Human Research Gate. Present verified, mixed, unsupported and
   insufficient claims, required updates, optional improvements, unresolved questions, confidence
   and accepted coverage exceptions in `output_language`.
12. Apply requested corrections through the proper producer. Each new user-requested stage run has
    its own single review, while an A10-triggered correction is never reviewed a second time. After approval,
    validate, freeze and emit `user_approved_research_bundle@1`.

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
