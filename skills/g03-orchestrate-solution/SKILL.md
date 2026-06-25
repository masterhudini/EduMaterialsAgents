---
name: g03-orchestrate-solution
description: Run the Solution Graph from a dual-input solution_graph_input@1 request joining g01 lecture_baseline@1 with g02 solution_input_candidate@1, while still accepting legacy user_approved_research_bundle@1, through the isolated solution-architect producer, one universal reviewer and the user solution gate, emitting the approved solution_blueprint@1 deliverable.
---

# Orchestrate Solution

Drive the Solution Graph without performing producer work. Read `shared/graphs/g03.graph.json` as the
node, contract, review and execution source of truth. Derive node order from `sequence`; derive
producer contracts, review profiles, hosted execution and finalize operations from each node entry.
Agents never address the user; relay their questions and explain every required user action.

## Contract

- Consume a `solution_graph_input@1` request or a front-door request that can be normalized into it:
  `lecture_baseline_ref` or inline `lecture_baseline`, plus `research_bundle_ref` or inline
  `research_bundle`.
- Prefer `research_bundle_kind: "solution_input_candidate"` for the official G02 hand-off
  (`solution_input_candidate@1`). Continue to accept `user_approved_research_bundle` as the legacy
  reviewed path when explicitly provided or inferred.
- Produce only a validated `solution_blueprint@1` deliverable after the user solution gate: the
  approved lecture outline, the applied update plan, deferred items and source attribution.
- Also render the approved blueprint as a user-readable Markdown plan and a short inline summary.
  The render is a view only; it never replaces `solution_blueprint@1`.
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
6. In the current graph this means: run `g03-a01-solution-architect` through the graph, let it
   hydrate `lecture_baseline@1` plus the research bundle selected by `research_bundle_kind`, review
   the produced `solution_blueprint@1`, then run the User Solution Gate.
7. Emit the graph `exit_artifact` only after the final gate and contract validation succeed.
8. Render the approved blueprint to Markdown plus inline summary, then present that view to the
   user alongside the final artifact ref.

## Output requirements

- The only thing crossing the boundary is the `solution_blueprint@1` deliverable plus
  `artifact://` refs inside it. Never emit full research or intake states.
- The final user-facing view is Markdown generated from the approved blueprint. It must include the
  outline, applied updates, deferrals and source attribution.
- Default user-readable output to English when `output_language` is absent.

## Boundaries

- Do not add evidence, verify claims, search literature or rewrite slide prose.
- Do not call back into G01 or G02 after the front-door input has been hydrated.
- Do not reintroduce a finding rejected by the legacy user research gate.
- Do not let the producer self-approve or bypass the user solution gate.
- Do not change graph order, review policy, execution mode or boundary contracts in prompt logic.

## Failure handling

Relay `needs_input` with an exact response request. Continue from `degraded` only when omissions are
explicit and the manifest permits. Stop on `failed`, unresolved `BLOCKED` or invalid user
authorization.

## Resume

Resume from the latest approved artifact per node. A frozen solution blueprint is immutable; a later
change creates a new task or version.

{{HOST_ADAPTER}}
