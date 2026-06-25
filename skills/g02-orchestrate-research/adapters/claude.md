## Host Adapter: Claude Code

Enter through `/research` and keep this skill as the only conversational surface. Drive the Research
Graph host-driven through the `edu-materials-research` MCP server — the SAME loop as Codex, so there
is one interface and complete tracing for both hosts. Use the Task/Agent tool for node ISOLATION
inside the loop, and report the subagent's token usage back so token tracing works for Claude too
(the runtime cannot see inside your harness — only you know what the subagent spent).

1. `research_run_hosted({context, through?, topic_ids?})` over a `research_graph_input@1` path/ref.
2. Loop on the response:
   - **`awaiting_node`**: spawn the isolated producer with the Task/Agent tool, `subagent_type` = the
     manifest node name (e.g. `g02-a01-planner`), passing only `input` + `upstream` refs. The subagent
     performs its task and calls the node's `finalize_op` named in the payload (e.g.
     `research_planner_finalize` / `research_domain_finalize` / … / `research_synthesis_finalize`).
     Resume with the RETURNED ENVELOPE: `research_resume({resume_token, node_results={node: <finalize
     envelope>}, usage_reports={node: {input_tokens, output_tokens, model}}})` — fill `usage_reports`
     from the Task's reported usage; omit it only if your harness does not expose usage. If the node
     cannot be produced, resume with `node_failures={node: {summary, issues}}`.
   - **`awaiting_review`**: invoke A10 once per producer — spawn `g02-a10-output-reviewer` with the
     `review_task` and `artifact_ref`; it calls `research_review_finalize`. Resume with
     `research_resume({resume_token, review_results={node: <review finalize envelope>}})`. After a
     REVISE the producer runs once more (preserve the deterministic revision-completion receipt
     without another A10 call); BLOCKED fails.
   - **`awaiting_user`**: present the human gate (the two-step source-selection gate, then the Human
     Research Gate — show the `research_summary@1` digest from the payload). Collect the required
     decisions and resume with `research_resume({resume_token, decisions={gate: …}})`. Never
     auto-approve a human gate.
   - **`research_run_report@1`** (status `completed`): done — `output_ref` is the approved
     `user_approved_research_bundle@1` handoff to g03. Call `research_trace({run_id: resume_token})`
     any time for the per-agent / per-tool durations and the input/output token roll-up.
3. Never write artifacts yourself; the `*_finalize` ops persist them. Do not simulate physical node
   agents by copying their work into the orchestrator context.

Deterministic seams are MCP tools from the `edu-materials-research` server (call them as tools, never
shell out or build paths): `research_front_door {context}` → `{ref, task_id}`; `research_node_input
{ref, node}`; `research_doi_verify` / `research_doi_verify_batch` on unchanged records;
`research_finalize {bundle}` to emit the handoff; `research_run_stub {context}` for a no-LLM wiring
smoke.
