## Host Adapter: Codex

**Preferred when you are already in a Codex session: you are the worker.** Drive the graph
host-driven through MCP, playing each LLM node yourself.

1. `solution_run_hosted(context)` over a front-door request containing
   `lecture_baseline_ref|lecture_baseline`, `research_bundle_ref|research_bundle` and, for the
   official path, `research_bundle_kind: "solution_input_candidate"`. Legacy
   `user_approved_research_bundle` requests still work.
2. Loop on the response (derive the sequence from `shared/graphs/g03.graph.json`, do not hardcode it):
   - **`awaiting_node`**: hydrate `upstream` refs with `solution_get_artifact` if needed, perform the
     node's task for `input`, then call the node's named `finalize_op` —
     `solution_blueprint_finalize` (a01), `solution_slide_plan_finalize` (a02),
     `solution_slide_design_finalize` (a03) or `solution_prompt_finalize` (a04). Take
     `produced[0].path` and call `solution_resume(resume_token, node_results={node: ref})`. If you
     genuinely cannot produce the node, call
     `solution_resume(resume_token, node_failures={node: {summary, issues}})`. If you know the model
     tokens spent, also pass `usage_reports={node: {input_tokens, output_tokens, model}}`.
   - **`awaiting_review`**: review the `artifact_ref` against `review_profile` (`solution_blueprint` /
     `slide_plan` / `slide_design` / `presentation_prompt`) plus the node's acceptance criteria. Read
     it with `solution_get_artifact`. Resume with
     `solution_resume(resume_token, review_decisions={node: {decision, findings}})`.
   - **`awaiting_user`**: present the gate, collect the required decisions, then
     `solution_resume(resume_token, decisions={gate: ...})`. For `user-change-plan-gate` this includes
     `select_target_tool` (`notebooklm` / `gamma` / `gpt_pro`), which routes to `g03-a04-prompt-builder`.
   - **`presentation_prompt@1` handoff descriptor**: call
     `solution_prompt_render(presentation_prompt=<descriptor>, persist=true)` and show the returned
     Markdown prompt to the user, alongside the secondary `solution_blueprint@1` ref. That descriptor
     remains the approved exit.
3. Never write artifacts yourself; the finalize ops persist the typed artifacts server-side, and the
   render operations only create human-readable views.

**Do not call `solution_run_codex` from inside a Codex session.** It spawns a nested `codex exec`
worker that cannot initialise under the outer read-only sandbox. `solution_run_codex` is for a
non-Codex shell or CI (`python3 "<plugin-root>/shared/scripts/g03/g03_flow.py" run-codex <context>`);
`run` is a no-LLM stub smoke. If the host cannot reason over a node, validate the input and report
`external_dependency_blocked`.
