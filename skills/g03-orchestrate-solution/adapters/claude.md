## Host Adapter: Claude Code

Drive the Solution Graph host-driven through the MCP server. Use the Task/Agent tool for node
isolation inside the loop, and report the subagent's token usage back so tracing works for Claude
too. The runtime cannot see inside your harness; only you know what the subagent spent.

1. `solution_run_hosted(context)` over a request joining g01's `lecture_baseline@1` and g02's
   research hand-off. For the official path, include `research_bundle_kind:
   "solution_input_candidate"` and provide `solution_input_candidate@1` as the research bundle.
   Legacy `user_approved_research_bundle@1` requests still work.
2. Loop on the response:
   - **`awaiting_node`**: spawn the isolated producer with the Task/Agent tool, `subagent_type` = the
     manifest node name, passing only `input` plus `upstream` refs. The subagent hydrates refs with
     `solution_get_artifact`, does its task and calls the named `finalize_op`
     (`solution_blueprint_finalize`). Take `produced[0].path` and resume:
     `solution_resume(resume_token, node_results={node: ref}, usage_reports={node: {input_tokens,
     output_tokens, model}})`. Fill `usage_reports` from the Task's reported token usage; omit it
     only if unavailable. If the node cannot be produced, resume with
     `node_failures={node: {summary, issues}}`.
   - **`awaiting_review`**: review `artifact_ref` against `review_profile` plus the node's acceptance
     criteria. Read it with `solution_get_artifact`; resume
     `review_decisions={node: {decision, findings}}` (`APPROVED` / `REVISE` / `BLOCKED`).
   - **`awaiting_user`**: present the gate, collect the required decisions, resume
     `decisions={gate: ...}`.
   - **`solution_blueprint@1` handoff descriptor**: call `solution_blueprint_render(blueprint=<descriptor>)`
     and show the returned Markdown plan plus `inline_summary` to the user. That descriptor remains
     the approved Solution deliverable.
3. Never write artifacts yourself; the finalize op persists the typed blueprint server-side, and the
   render operation only creates the human-readable view. Call
   `solution_trace(run_id=resume_token)` any time for the per-agent / per-tool durations and the
   input/output token roll-up of the run.
