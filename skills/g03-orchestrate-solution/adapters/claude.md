## Host Adapter: Claude Code

Drive the Solution Graph host-driven through the MCP server — the SAME loop as Codex, so there is one
interface and complete tracing for both hosts. Use the Task/Agent tool for node ISOLATION inside the
loop, and report the subagent's token usage back so token tracing works for Claude too (the runtime
cannot see inside your harness — only you know what the subagent spent).

1. `solution_run_hosted(context)` over a request joining g01's `lecture_baseline@1` and g02's
   `user_approved_research_bundle@1`.
2. Loop on the response:
   - **`awaiting_node`**: spawn the isolated producer with the Task/Agent tool, `subagent_type` = the
     manifest node name (e.g. `g03-a01-solution-architect`), passing only `input` + `upstream` refs.
     The subagent hydrates refs with `solution_get_artifact`, does its task and calls the named
     `finalize_op` (`solution_blueprint_finalize`). Take `produced[0].path` and resume:
     `solution_resume(resume_token, node_results={node: ref}, usage_reports={node: {input_tokens,
     output_tokens, model}})` — fill `usage_reports` from the Task's reported token usage; omit it
     only if your harness does not expose usage (timings + decisions are still traced). If the node
     cannot be produced, resume with `node_failures={node: {summary, issues}}`.
   - **`awaiting_review`**: review `artifact_ref` against `review_profile` + the node's acceptance
     criteria (read it with `solution_get_artifact`); resume `review_decisions={node: {decision,
     findings}}` (APPROVED / REVISE / BLOCKED). Review honestly — it is a real quality gate.
   - **`awaiting_user`**: present the gate, collect the required decisions, resume `decisions={gate: ...}`.
   - **`solution_blueprint@1` handoff descriptor**: done — that is the approved Solution deliverable.
3. Never write artifacts yourself; the finalize op persists them server-side. Call
   `solution_trace(run_id=resume_token)` any time for the per-agent / per-tool durations and the
   input/output token roll-up of the run.
