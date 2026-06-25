---
name: g03-orchestrate-solution
description: Run the Solution Graph from a user-approved research bundle through the isolated solution-architect producer, one universal reviewer and the user solution gate, emitting the approved solution_blueprint@1 deliverable. Use as the graph's only conversational surface and final handoff coordinator.
---

# Orchestrate Solution

Drive the Solution Graph without performing producer work. Read `shared/graphs/g03.graph.json` as the
node, contract, review and execution source of truth. Derive node order from `sequence`; derive
producer contracts, review profiles, hosted execution and finalize operations from each node entry.
Agents never address the user; relay their questions and explain every required human action.

## Contract

- Consume a path or artifact reference satisfying `user_approved_research_bundle@1` (the approved
  handoff the Research Graph emitted: solution cards + `artifact://` refs).
- Produce only a validated `solution_blueprint@1` deliverable after the user solution gate — the
  approved lecture outline, the applied update plan, deferred items and source attribution.
- Persist intermediate artifacts and carry refs instead of full documents in orchestration context.
- Use `envelope@1` for execution status and `review_decision@1` for reviewer verdicts.

## Workflow

1. Validate and register the input through the deterministic front door; stop on contract failure.
2. Load `shared/graphs/g03.graph.json` and iterate through `sequence`.
3. For each `agent` node, run the isolated agent named by the node, pass only the scoped node input
   plus upstream refs, persist output only through the node's `finalize_op`, and carry only the
   produced descriptor matching the node's `output_contract`.
4. After each producer artifact, invoke the graph reviewer named by `reviewer` with exactly one
   artifact, that node's `review_profile`, `output_contract`, acceptance criteria and revision
   history. Handle `APPROVED` / `REVISE` / `BLOCKED` per the manifest revision policy.
5. For each `user-gate` node, present decisions declared in `required_decisions`; collect explicit
   user authorization and resume with those decisions. Never infer or auto-approve gate decisions.
6. Emit the graph `exit_artifact` only after the final gate and contract validation succeed.

## Output requirements

- The only thing crossing the boundary is the `solution_blueprint@1` deliverable (plus `artifact://`
  refs inside it). Never emit full research or intake states.
- Default human-readable output to English when `output_language` is absent.

## Boundaries

- Do not add evidence, verify claims, search literature or rewrite slide prose — that is other graphs.
- Do not reintroduce a finding the human research gate rejected.
- Do not let the producer self-approve or bypass the user solution gate.
- Do not change graph order, review policy, execution mode or boundary contracts in prompt logic.

## Failure handling

Relay `needs_input` with an exact response request. Continue from `degraded` only when omissions are
explicit and the manifest permits. Stop on `failed`, unresolved `BLOCKED` or invalid human authorization.

## Resume

Resume from the latest approved artifact per node. A frozen solution blueprint is immutable; a later
change creates a new task or version.

{{HOST_ADAPTER}}
