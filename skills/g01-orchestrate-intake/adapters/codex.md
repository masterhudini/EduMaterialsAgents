## Host Adapter: Codex

**Preferred when you are already in a Codex session — you ARE the worker (no nested `codex exec`).**
Drive the graph host-driven through MCP, playing each LLM node yourself:

1. `intake_upload` (PDF) → boundary bundle; then `intake_run_hosted(context)`.
2. Loop on the response:
   - **`awaiting_node`**: hydrate `upstream` refs with `intake_get_artifact` if you need them (e.g. the
     producer's `slide_views`), perform the node's task for `input`, then call the named `finalize_op`
     (e.g. `intake_understanding_finalize` / `intake_synthesis_finalize`) with `{task_id, <artifact>}`.
     Take `produced[0].path` and call `intake_resume(resume_token, node_results={node: ref})`. If you
     genuinely cannot produce the node, call `intake_resume(resume_token, node_failures={node: {summary,
     issues}})`. **Tracing:** if your harness exposes the model tokens you spent on this node, also pass
     `usage_reports={node: {input_tokens, output_tokens, model}}` — only the host knows them; omit if
     unavailable (timings and decisions are still traced).
   - **`awaiting_review`**: review the `artifact_ref` against `review_profile` + the node's acceptance
     criteria (read it with `intake_get_artifact`). Resume with
     `intake_resume(resume_token, review_decisions={node: {decision, findings}})` where decision is
     `APPROVED` (advance), `REVISE` (the engine re-asks you to run the node with revision context) or
     `BLOCKED` (fail). Review honestly — it is a real quality gate, not a rubber stamp.
   - **`awaiting_user`**: present the gate, collect the required decisions, then
     `intake_resume(resume_token, decisions={gate: ...})`.
   - **`research_graph_input@1` handoff descriptor**: done — that is the approved handoff to g02.
3. Never write artifacts yourself; the `*_finalize` ops persist them server-side. Deterministic nodes
   (PDF intake) are already executed in-process by the engine — you only play the LLM nodes and the
   reviewer.

**Do NOT call `intake_run_codex` from inside a Codex session** — it spawns a nested `codex exec` worker
that cannot initialise under the outer read-only sandbox. `intake_run_codex` is for a non-Codex shell or
CI (`python3 "<plugin-root>/shared/scripts/g01/g01_flow.py" run-codex <context>`); `run` is a no-LLM stub
smoke. If the host cannot reason over a node, validate the input and report `external_dependency_blocked`.
