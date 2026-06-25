## Host Adapter: Claude Code

Drive the Solution Graph host-driven through the MCP server. Use the Task/Agent tool for node
isolation inside the loop, and report the subagent's token usage back so tracing works for Claude
too. The runtime cannot see inside your harness; only you know what the subagent spent.

1. `solution_run_hosted(context)` over a request joining g01's `lecture_baseline@1` and g02's
   research hand-off. For the official path, include `research_bundle_kind:
   "solution_input_candidate"` and provide `solution_input_candidate@1` as the research bundle.
   Legacy `user_approved_research_bundle@1` requests still work.
2. Loop on the response (do not hardcode the sequence — derive it from `shared/graphs/g03.graph.json`):
   - **`awaiting_node`**: spawn the isolated producer with the Task/Agent tool, `subagent_type` = the
     manifest node name (`g03-a01-solution-architect`, `g03-a02-slide-architect`,
     `g03-a03-slide-designer` or `g03-a04-prompt-builder`), passing only `input` plus `upstream` refs.
     The subagent hydrates refs with `solution_get_artifact`, does its task and calls the node's named
     `finalize_op` (`solution_blueprint_finalize` / `solution_slide_plan_finalize` /
     `solution_slide_design_finalize` / `solution_prompt_finalize`). Take `produced[0].path` and resume:
     `solution_resume(resume_token, node_results={node: ref}, usage_reports={node: {input_tokens,
     output_tokens, model}})`. Fill `usage_reports` from the Task's reported token usage; omit it only
     if unavailable. If the node cannot be produced, resume with
     `node_failures={node: {summary, issues}}`.
   - **`awaiting_review`**: review `artifact_ref` against `review_profile` (`solution_blueprint` /
     `slide_plan` / `slide_design` / `presentation_prompt`) plus the node's acceptance criteria. Read it
     with `solution_get_artifact`; resume `review_decisions={node: {decision, findings}}` (`APPROVED` /
     `REVISE` / `BLOCKED`).
   - **`awaiting_user`**: present the gate and collect the `required_decisions`. For
     `user-change-plan-gate`, this includes `select_target_tool` (`notebooklm` / `gamma` / `gpt_pro`) —
     ask the user which generator to target; the engine records the choice and routes it to
     `g03-a04-prompt-builder`. For `user-final-review-gate`, confirm the final prompt. Resume
     `decisions={gate: ...}`.
   - **`presentation_prompt@1` handoff descriptor**: call `solution_prompt_render(presentation_prompt=
     <descriptor>, persist=true)` and show the returned Markdown prompt to the user as the deliverable,
     alongside the secondary `solution_blueprint@1` ref. That descriptor remains the approved exit.
3. Never write artifacts yourself; the finalize ops persist the typed artifacts server-side, and the
   render operations only create human-readable views. Call `solution_trace(run_id=resume_token)` any
   time for the per-agent / per-tool durations and the input/output token roll-up of the run.
