## Host Adapter: Codex

**Preferred when you are already in a Codex session — you ARE the worker (no nested `codex exec`).**
Drive the graph host-driven through MCP, playing each LLM node yourself:

1. `solution_run_hosted(context)` over a `user_approved_research_bundle@1` path/ref.
2. Loop on the response:
   - **`awaiting_node`**: hydrate `upstream` refs with `solution_get_artifact` if you need them,
     perform the node's task for `input`, then call the named `finalize_op` (`solution_blueprint_finalize`)
     with `{task_id, blueprint}`. Take `produced[0].path` and call
     `solution_resume(resume_token, node_results={node: ref})`. If you genuinely cannot produce the node,
     call `solution_resume(resume_token, node_failures={node: {summary, issues}})`. **Tracing:** if you
     know the model tokens you spent on this node, also pass
     `usage_reports={node: {input_tokens, output_tokens, model}}` — only the host knows them. Omit if
     your harness does not expose usage (the run is still traced for timings and decisions).
   - **`awaiting_review`**: review the `artifact_ref` against `review_profile` + the node's acceptance
     criteria (read it with `solution_get_artifact`). Resume with
     `solution_resume(resume_token, review_decisions={node: {decision, findings}})` where decision is
     `APPROVED` (advance), `REVISE` (the engine re-asks you to run the node with revision context) or
     `BLOCKED` (fail). Review honestly — it is a real quality gate, not a rubber stamp.
   - **`awaiting_user`**: present the gate, collect the required decisions, then
     `solution_resume(resume_token, decisions={gate: ...})`.
   - **`solution_blueprint@1` handoff descriptor**: done — that is the approved Solution deliverable.
3. Never write artifacts yourself; `solution_blueprint_finalize` persists them server-side.

**Do NOT call `solution_run_codex` from inside a Codex session** — it spawns a nested `codex exec`
worker that cannot initialise under the outer read-only sandbox. `solution_run_codex` is for a
non-Codex shell or CI (`python3 "<plugin-root>/shared/scripts/g03/g03_flow.py" run-codex <context>`);
`run` is a no-LLM stub smoke. If the host cannot reason over a node, validate the input and report
`external_dependency_blocked`.
