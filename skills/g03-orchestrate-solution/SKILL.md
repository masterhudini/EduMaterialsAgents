---
name: g03-orchestrate-solution
description: Run the Solution Graph from a dual-input solution_graph_input@1 request joining g01 lecture_baseline@1 with g02 solution_input_candidate@1 (legacy user_approved_research_bundle@1 still accepted) through four isolated producers (solution-architect, slide-architect, slide-designer, prompt-builder), one universal reviewer and two user gates, emitting the approved presentation_prompt@1 deliverable plus the secondary solution_blueprint@1.
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
- Produce a validated `presentation_prompt@1` deliverable (the primary exit) after the final user
  gate: a single ready-to-paste Markdown generator prompt for the chosen tool. The intermediate
  `solution_blueprint@1`, `slide_plan@1` and `slide_design_set@1` are persisted secondary exits.
- Also render the approved prompt as a user-readable Markdown `.md` and surface the secondary
  blueprint. The render is a view only; it never replaces `presentation_prompt@1`.
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
6. In the current graph this means, in `sequence` order: `g03-a01-solution-architect`
   (`solution_blueprint@1`, the evidence layer) -> `g03-a02-slide-architect` (`slide_plan@1`) ->
   **User Change-Plan Gate** (approve the deck and collect `select_target_tool`:
   notebooklm / gamma / gpt_pro) -> `g03-a03-slide-designer` (`slide_design_set@1`) ->
   `g03-a04-prompt-builder` (`presentation_prompt@1`, using the tool chosen at the gate) ->
   **User Final-Review Gate**. Each producer is reviewed by `g03-a10-output-reviewer` with its
   per-node `review_profile` before the next step.
7. Emit the graph `exit_artifact` (`presentation_prompt@1`) only after the final gate and contract
   validation succeed.
8. Render the approved prompt to Markdown with `solution_prompt_render`, then present that view to
   the user alongside the final artifact ref and the secondary `solution_blueprint@1` ref.

## Output requirements

- The primary deliverable crossing the boundary is `presentation_prompt@1` plus `artifact://` refs
  inside it; `solution_blueprint@1`, `slide_plan@1` and `slide_design_set@1` are persisted secondary
  exits. Never emit full research or intake states.
- The final user-facing view is the Markdown generator prompt rendered from the approved
  `presentation_prompt@1`, alongside the secondary blueprint ref.
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
