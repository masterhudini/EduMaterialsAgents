## Host Adapter: Claude Code

Drive the Intake Graph host-driven through the MCP server — the SAME loop as Codex, so there is one
interface and complete tracing for both hosts. Use the Task/Agent tool for node ISOLATION inside the
loop, and report the subagent's token usage back so token tracing works for Claude too (the runtime
cannot see inside your harness — only you know what the subagent spent).

1. `intake_upload` (PDF) -> boundary bundle; then `intake_run_hosted(context)`.
2. Loop on the response:
   - **`awaiting_node`**: spawn the isolated producer with the Task/Agent tool, `subagent_type` = the
     manifest node name (e.g. `g01-a02-understanding`), passing only `input` + `upstream` refs. The
     subagent hydrates refs with `intake_get_artifact`, does its task and calls the named `finalize_op`
     (`intake_understanding_finalize` / `intake_synthesis_finalize` / `intake_lecture_baseline_finalize`).
     Take `produced[0].path` and resume: `intake_resume(resume_token, node_results={node: ref},
     usage_reports={node: {input_tokens, output_tokens, model}})` — fill `usage_reports` from the Task's
     reported token usage; omit it only if your harness does not expose usage (timings + decisions are
     still traced). If the node cannot be produced, resume with `node_failures={node: {summary, issues}}`.
     The deterministic PDF intake (`g01-a01-pdf-intake`) is executed in-process by the engine — you only
     play the LLM nodes and the reviewer.
   - **`awaiting_review`**: review `artifact_ref` against `review_profile` + the node's acceptance
     criteria (read it with `intake_get_artifact`); resume `review_decisions={node: {decision,
     findings}}` (APPROVED / REVISE / BLOCKED). Review honestly — it is a real quality gate.
   - **`awaiting_user`**: present the user intake gate (it runs BEFORE a03/a04), collect the required
     decisions and resume `decisions={gate: <intake_gate_decisions@1 object>}` (a `task_id`, plus
     `confirm_audience` / `confirm_domains` / `approve_research_scope` / `locked_sections`). The engine
     persists them and threads the ref into a03/a04 via `upstream["user-intake-gate"]` — you do not
     re-pass them by hand.
   - **`g01-a04-lecture-baseline` `awaiting_node`**: when you play this node, the ref you submit
     (`node_results["g01-a04-lecture-baseline"]`) IS the `lecture_baseline@1` for g03 — capture it.
   - **`research_graph_input@1` handoff descriptor**: done — that is the approved handoff to g02. The
     run also carries `secondary_exits["lecture_baseline@1"]`; surface BOTH refs (g02 input + g03 input).
3. Never write artifacts yourself; the finalize ops persist them server-side. Call
   `intake_trace(run_id=resume_token)` any time for the per-agent / per-tool durations and the
   input/output token roll-up of the run.
