---
name: g02-orchestrate-research
description: Run the current Research Graph from an approved research_graph_input@1 through A01 planning, Scout discovery, A07 light source review, A09 synthesis and the Human Research Gate. Use as the graph's only conversational surface and final handoff coordinator.
---

# Orchestrate Research

Drive G02 without doing hidden producer work in the orchestrator. The active runtime is
prompt-assisted host-driven: use `research_run_hosted` / `research_resume`, and let the runner read
`shared/graphs/g02.graph.json` as the node, operation and contract source of truth.

Do not use the retired A02-A06/A08/A11/source-selection workflow for new runs.

## Semantic Entry

- Treat "zrob research", "zrób research", "run research" and "run the research graph" as requests
  to run this workflow when the user provides, references or can supply a `research_graph_input@1`
  bundle.
- Prefer `research_run_hosted`; the MCP prompt `research-scout-e2e` is only a hosted-loop wrapper.
- If the input bundle path or `artifact://` ref is missing, ask for exactly that value before
  starting the graph.

## Contract

- Consume a path or artifact reference satisfying `research_graph_input@1`.
- Produce only a validated `user_approved_research_bundle@1` descriptor after final human approval.
- Persist intermediate artifacts and carry refs instead of full documents in orchestration context.
- Use deterministic finalizers for persistence through the hosted runner. The active `scout_e2e`
  profile does not run A10 review.

## Workflow

1. Call `research_run_hosted({context, through: "user-research-gate"})`.
2. Loop on the returned status.
3. `awaiting_node`: run only the named node using the payload `input`, `upstream`, `node_key`,
   `finalize_op` and `finalize_args`. Fill the raw model JSON into the finalizer call, then resume
   with `research_resume({resume_token, node_results: {node_key: <finalize envelope>}})`.
4. After the A01 planner finalizer succeeds and before resuming, call `research_provider_setup` if
   the user wants to provide email or an OpenAlex key for Scout.
5. For `g02-a07-paper-review`, each `node_key` is one topic/source work unit. The worker may read
   only the supplied `a07_review_task@1`, selected windows and compact intake context.
6. `awaiting_user`: present the Human Research Gate summary, limitations, optional improvements and
   unresolved handling to the user. Never auto-approve. Resume with
   `decisions: {"user-research-gate": <explicit decision>}`.
7. `completed`: the `output_ref` is the only `user_approved_research_bundle@1` handoff to G03.

## Output Requirements

- Preserve `output_language` from the boundary input in user-facing summaries.
- Keep refs to plan, Scout run, A07 reviews, research state and final bundle.
- Keep full PDFs, full extracted text and verbose per-source review details out of the downstream
  handoff.
- Surface A08 omission as an explicit fast/scout-mode limitation.

## Boundaries

- Do not call retired A02-A06/A08/A11 tools or retired human source filtering gates.
- `research_run_codex` is a valid entrypoint for a non-Codex shell or CI (it spawns nested
  `codex exec` workers, exactly like `intake_run_codex` / `solution_run_codex`); inside a Codex or
  host session prefer `research_run_hosted` because you are already the worker.
- Do not call A10 review tools in the active `scout_e2e` profile.
- Do not let a producer self-approve.
- Do not browse or search from an agent; discovery is only through `research_scout_fanout`.
- Do not expose secrets, private reasoning or unrelated state to an agent.
- Do not ask G03 to do research or to call back into G02.

## Failure Handling

Stop on contract failure, failed Scout run, failed A07 aggregate operation, failed A09 finalization or
rejected Human Research Gate. Continue with deterministic A09 fallback only when the model attempt
is unavailable or fails and the finalizer records that fact.
