---
name: orchestrate-research
description: Run the complete Research Graph from an approved input bundle through isolated producer agents, one universal reviewer, the human source-selection gate and the human research gate. Use when the user asks to "zrob research", "zrób research", "run research", "run the research graph", or otherwise requests the research pass over a research_graph_input bundle. Use as the graph's only conversational surface and final handoff coordinator.
---

# Orchestrate Research

Drive the Research Graph without performing producer work. Read
`shared/graphs/research.graph.json` as the node and contract source of truth. Agents never address
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
- Use `envelope@1` for execution status and `ReviewDecision` for reviewer verdicts.

The installed `research_graph_input@1` schema is approved and authoritative. Do not rename or
extend its fields inside the orchestrator.

## Workflow

1. Validate and register the input through the deterministic research front door. Stop on contract
   failure and explain the missing fields without inventing them.
2. Load the manifest and create the smallest authorized input bundle for each node. Do not pass the
   complete graph input when the agent needs only a topic, source set, document or claim group.
3. Invoke each producer and persist its artifacts. Conceptually independent Canonical Sources and
   Recent Developments runs may execute concurrently when runtime support and manifest semantics
   allow it; both consume the approved Domain result and join before Candidate Source Index.
4. After every producer artifact, invoke `research-output-reviewer` with exactly one artifact, the
   node's profile, producer input, output contract, acceptance criteria and revision history.
5. Handle reviewer verdicts:
   - `APPROVED`: continue with the approved artifact ref;
   - `REVISE`: return minimal findings to the same producer and review the new artifact version;
   - `BLOCKED`: route by root cause or explain the blocking decision to the user;
   - exhausted revision budget: escalate through the conversation without silently approving.
6. After Candidate Source Index, run the Human Source Selection Gate. Present or link
   `candidate_source_review.md`, explain coverage and the actions DOWNLOAD, LIBRARY, CITATION,
   RESERVE, EXCLUDE and SEARCH_MORE, then provide a copyable response format.
7. Parse the answer into `HumanSourceSelection`, show the interpretation and require final
   confirmation. Route SEARCH_MORE to the relevant discovery agent, rebuild and re-review the index.
   Retrieval receives only confirmed `HumanApprovedSourceSet`.
8. Fan out Paper Review per validated document when supported, then Claim Verification per independent
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
