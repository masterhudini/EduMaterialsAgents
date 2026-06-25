---
name: g03-orchestrate-solution
description: Run the Solution Graph from a dual-input solution_graph_input@1 request joining g01 lecture_baseline@1 with g02 solution_input_candidate@1, while still accepting legacy user_approved_research_bundle@1, through the isolated solution-architect producer, one universal reviewer and the user solution gate, emitting the approved solution_blueprint@1 deliverable.
---

# Orchestrate Solution

Drive the Solution Graph without performing producer work. Read `shared/graphs/g03.graph.json` as
the node and contract source of truth. Agents never address the user; relay their questions and
explain every required human action.

## Contract

- Consume a `solution_graph_input@1` request or a front-door request that can be normalized into it:
  `lecture_baseline_ref` or inline `lecture_baseline`, plus `research_bundle_ref` or inline
  `research_bundle`.
- Prefer `research_bundle_kind: "solution_input_candidate"` for the official G02 hand-off
  (`solution_input_candidate@1`). Continue to accept `user_approved_research_bundle` as the legacy
  reviewed path when explicitly provided or inferred.
- Produce only a validated `solution_blueprint@1` deliverable after the user solution gate: the
  approved lecture outline, the applied update plan, deferred items and source attribution.
- Also render the approved blueprint as a human-readable Markdown plan and a short inline summary.
  The render is a view only; it never replaces `solution_blueprint@1`.
- Persist intermediate artifacts and carry refs instead of full documents in orchestration context.
- Use `envelope@1` for execution status and `review_decision@1` for reviewer verdicts.

## Workflow

1. Validate and register the input through the deterministic front door; stop on contract failure.
2. Run `g03-a01-solution-architect` as the hosted agent node the engine traverses (entry node in
   `g03.graph.json`). The producer hydrates `lecture_baseline@1` and the research bundle selected by
   `research_bundle_kind`, then performs the join from research update keys to real slide keys. The
   official run is always this agent node through the graph; `solution_blueprint_build` and the CLI
   are the agent's deterministic drafting helper plus a test/fallback path, never a way to bypass the
   agent, the reviewer or the user solution gate.
3. After the producer artifact, invoke `g03-a10-output-reviewer` with exactly one artifact, the
   node's review profile, the output contract, acceptance criteria and revision history. Handle
   `APPROVED` / `REVISE` / `BLOCKED` per the manifest revision policy.
4. Run the User Solution Gate: present the outline, the applied updates and the deferred items, each
   traced to upstream candidate updates or legacy approved findings, and collect: approve outline,
   approve applied updates, confirm deferrals.
5. Validate, freeze and emit the `solution_blueprint@1` deliverable.
6. Render the approved blueprint to Markdown plus inline summary, then present that view to the
   user alongside the final artifact ref.

## Output requirements

- The only thing crossing the boundary is the `solution_blueprint@1` deliverable plus
  `artifact://` refs inside it. Never emit full research or intake states.
- The final user-facing view is Markdown generated from the approved blueprint. It must include the
  outline, applied updates, deferrals and source attribution.
- Default human-readable output to English when `output_language` is absent.

## Boundaries

- Do not add evidence, verify claims, search literature or rewrite slide prose.
- Do not call back into G01 or G02 after the front-door input has been hydrated.
- Do not reintroduce a finding rejected by the legacy human research gate.
- Do not let the producer self-approve or bypass the user solution gate.
- Do not change graph order or boundary contracts in prompt logic.

## Failure handling

Relay `needs_input` with an exact response request. Continue from `degraded` only when omissions are
explicit and the manifest permits. Stop on `failed`, unresolved `BLOCKED` or invalid human
authorization.

## Resume

Resume from the latest approved artifact per node. A frozen solution blueprint is immutable; a later
change creates a new task or version.

{{HOST_ADAPTER}}
