---
name: g01-orchestrate-intake
description: Run the Intake / Understanding Graph from an uploaded lecture PDF through isolated producer agents, one universal reviewer and the user intake gate, emitting the approved research_graph_input@1 handoff for the Research Graph. Use as the graph's only conversational surface and final handoff coordinator.
---

# Orchestrate Intake

Drive the Intake Graph without performing producer work. Read `shared/graphs/g01.graph.json` as the
node, contract, review and execution source of truth. Derive node order from `sequence`; derive
producer contracts, review profiles, hosted/deterministic execution and finalize operations from
each node entry. Agents never address the user; relay their questions and explain every required
human action.

## Contract

- Consume a path or artifact reference satisfying `intake_graph_input@1` (the uploaded PDF + ingestion
  profile).
- Produce only a validated `research_graph_input@1` descriptor after the user intake gate — this is
  the approved handoff the Research Graph (g01 -> g02) consumes.
- Persist intermediate artifacts and carry refs instead of full documents in orchestration context.
- Use `envelope@1` for execution status and `review_decision@1` for reviewer verdicts.

## Workflow

1. Validate and register the input through the deterministic front door; stop on contract failure.
2. Load `shared/graphs/g01.graph.json` and iterate through `sequence`.
3. For each `agent` node:
   - if `execution` is `deterministic`, let the runtime run the node in-process and keep any
     dependency-missing state explicit;
   - if `execution` is `hosted`, run the isolated agent named by the node, pass only the scoped
     node input plus upstream refs, and persist output only through the node's `finalize_op`;
   - validate and carry only the produced descriptor matching the node's `output_contract`.
4. After each producer artifact, invoke the graph reviewer named by `reviewer` with exactly one
   artifact, that node's `review_profile`, `output_contract`, acceptance criteria and revision
   history. Handle `APPROVED` / `REVISE` / `BLOCKED` per the manifest revision policy.
5. For each `user-gate` node, present decisions declared in `required_decisions`; collect explicit
   user authorization and resume with those decisions. Never infer or auto-approve gate decisions.
6. Emit the graph `exit_artifact` only after the final gate and contract validation succeed.

## Output requirements

- The only thing crossing the boundary is the `research_graph_input@1` descriptor (plus `artifact://`
  refs inside it). Never emit raw PDF text or full intake states.
- Default human-readable output to English when `output_language` is absent.

## Boundaries

- Do not verify claims, search literature, design a change plan or rewrite slides — that is later graphs.
- Do not let a producer self-approve or bypass the user intake gate.
- Do not change graph order, review policy, execution mode or boundary contracts in prompt logic.

## Failure handling

Relay `needs_input` with an exact response request. Continue from `degraded` only when omissions are
explicit and the manifest permits. Stop on `failed`, unresolved `BLOCKED` or invalid human authorization.

## Resume

Resume from the latest approved artifact per node. A frozen intake handoff is immutable; a later change
creates a new task or version.

{{HOST_ADAPTER}}
