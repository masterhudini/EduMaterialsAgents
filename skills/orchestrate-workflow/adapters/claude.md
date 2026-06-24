## Host Adapter: Claude Code

Drive the whole pipeline host-driven through the three MCP servers in sequence, using the Task/Agent
tool for node isolation inside each graph's loop (same pattern as the per-graph adapters).

1. **Intake** — `intake_upload` (PDF) → `intake_run_hosted`. Run the g01 host-driven loop (see
   `g01-orchestrate-intake`). While looping, when you play `g01-a04-lecture-baseline` and call
   `intake_lecture_baseline_finalize`, **keep its `produced[0].path`** = `LECTURE_BASELINE_REF`. On
   completion the `research_graph_input@1` handoff descriptor's `ref` = `RESEARCH_INPUT_REF`.
2. **Research** — `research_run_hosted({context: RESEARCH_INPUT_REF})`. Run the g02 host-driven loop
   (see `g02-orchestrate-research`). On `completed`, the report's `output_ref` = `RESEARCH_BUNDLE_REF`
   (the approved `user_approved_research_bundle@1`).
3. **Solution** — `solution_run_hosted({context: {lecture_baseline_ref: LECTURE_BASELINE_REF,
   research_bundle_ref: RESEARCH_BUNDLE_REF}})`. Run the g03 host-driven loop (see
   `g03-orchestrate-solution`). On completion you have the approved `solution_blueprint@1`.
4. Report the final blueprint ref and each stage's boundary ref.

Each graph's human gates (user intake gate; two-step source-selection gate + Human Research Gate;
user solution gate) fire inside their loops — present them and collect decisions; never auto-approve.
For a no-LLM wiring smoke of the whole chain, run
`python3 "<plugin-root>/shared/scripts/workflow.py" run-stub <intake_context>`.
