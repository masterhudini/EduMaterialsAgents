---
name: g02-orchestrate-research
description: Run the complete Research Graph from an approved input bundle through isolated producer agents, one universal reviewer, the human source-selection gate and the human research gate. Use as the graph's only conversational surface and final handoff coordinator.
---

# Orchestrate Research

Drive the Research Graph without performing producer work. Read
`shared/graphs/g02.graph.json` as the node and contract source of truth. Agents never address
the user; relay their questions and explain every required human action.

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
3. Invoke each producer and persist its artifacts. Conceptually independent G02-A03 Canonical
   Sources and G02-A04 Recent Developments runs may execute concurrently when runtime support and
   manifest semantics allow it; both consume the approved G02-A02 Domain result and join before
   G02-A05 Candidate Source Index.
4. After every producer artifact, construct one `review_task@1` with the artifact, node profile,
   producer input, output contract, acceptance criteria and revision history. Prepare it through
   `research_review_prepare`, invoke `g02-a10-output-reviewer`, then submit the decision through
   `research_review_finalize`.
5. Handle reviewer verdicts:
   - `APPROVED`: continue with the approved artifact ref;
   - `REVISE`: return minimal findings to the same producer and review the new artifact version;
   - `BLOCKED`: route by root cause or explain the blocking decision to the user;
   - exhausted revision budget: escalate through the conversation without silently approving.
6. After G02-A05 Candidate Source Index, run the Human Source Selection Gate. Present or link
   `candidate_source_review.md`, explain coverage and the actions DOWNLOAD, LIBRARY, CITATION,
   RESERVE, EXCLUDE and SEARCH_MORE, then provide a copyable response format.
7. Parse the answer into `HumanSourceSelection`, show the interpretation and require final
   confirmation. Route SEARCH_MORE to the relevant discovery agent, rebuild and re-review the index.
   Retrieval receives only confirmed `HumanApprovedSourceSet`.
8. Fan out G02-A07 Paper Review per validated document when supported, then G02-A08 Claim Verification per independent
   claim or tight claim group. Preserve artifact isolation and join only reviewed results.
9. After reviewed synthesis, run the Human Research Gate. Present verified, mixed, unsupported and
   insufficient claims, required updates, optional improvements, unresolved questions, confidence
   and accepted coverage exceptions in `output_language`.
10. Apply requested corrections through the proper producer and reviewer loop. After approval,
    validate, freeze and emit `user_approved_research_bundle@1`.

## Output requirements

- Keep a task, node, attempt and artifact-version audit trail.
- Give the user plain-language instructions at both gates, even when the underlying response is JSON.
- Default human-readable output to English when `output_language` is absent.
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

Resume from the latest approved artifact per node. Re-run a producer only when input, revision items,
human decisions or an upstream artifact version affecting it changed. Frozen human-approved bundles
are immutable; a later change creates a new task or version.
