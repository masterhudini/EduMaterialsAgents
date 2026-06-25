## Host Adapter: Codex

**Preferred when you are already in a Codex session: you are the worker.** Drive the graph
host-driven through MCP, playing each LLM node yourself.

1. `solution_run_hosted(context)` over a front-door request containing
   `lecture_baseline_ref|lecture_baseline`, `research_bundle_ref|research_bundle` and, for the
   official path, `research_bundle_kind: "solution_input_candidate"`. Legacy
   `user_approved_research_bundle` requests still work.
2. Loop on the response:
   - **`awaiting_node`**: hydrate `upstream` refs with `solution_get_artifact` if needed, perform the
     node's task for `input`, then call the named `finalize_op` (`solution_blueprint_finalize`) with
     `{task_id, blueprint}`. Take `produced[0].path` and call
     `solution_resume(resume_token, node_results={node: ref})`. If you genuinely cannot produce the
     node, call `solution_resume(resume_token, node_failures={node: {summary, issues}})`. Tracing: if
     you know the model tokens spent on this node, also pass
     `usage_reports={node: {input_tokens, output_tokens, model}}`; omit it when unavailable.
   - **`awaiting_review`**: review the `artifact_ref` against `review_profile` plus the node's
     acceptance criteria. Read it with `solution_get_artifact`. Resume with
     `solution_resume(resume_token, review_decisions={node: {decision, findings}})` where decision is
     `APPROVED`, `REVISE` or `BLOCKED`.
   - **`awaiting_user`**: present the gate, collect the required decisions, then
     `solution_resume(resume_token, decisions={gate: ...})`.
   - **`solution_blueprint@1` handoff descriptor**: call `solution_blueprint_render(blueprint=<descriptor>)`
     and show the returned Markdown plan plus `inline_summary` to the user. That descriptor remains
     the approved Solution deliverable.
3. Never write artifacts yourself; `solution_blueprint_finalize` persists the typed blueprint
   server-side, and `solution_blueprint_render` only creates the human-readable view.

**Do not call `solution_run_codex` from inside a Codex session.** It spawns a nested `codex exec`
worker that cannot initialise under the outer read-only sandbox. `solution_run_codex` is for a
non-Codex shell or CI (`python3 "<plugin-root>/shared/scripts/g03/g03_flow.py" run-codex <context>`);
`run` is a no-LLM stub smoke. If the host cannot reason over a node, validate the input and report
`external_dependency_blocked`.
