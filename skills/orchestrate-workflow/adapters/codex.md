## Host Adapter: Codex

**Preferred inside a Codex session — you ARE the worker (no nested `codex exec`).** Drive the whole
pipeline host-driven through the three MCP servers in sequence:

1. **Intake** — `intake_upload` (PDF) → `intake_run_hosted`. Run the g01 host-driven loop (see
   `g01-orchestrate-intake`). While looping, when you play `g01-a04-lecture-baseline` and call
   `intake_lecture_baseline_finalize`, **keep its `produced[0].path`** = `LECTURE_BASELINE_REF`. On
   completion the `research_graph_input@1` handoff's `ref` = `RESEARCH_INPUT_REF`.
2. **Research** — get and follow the `research-scout-e2e` MCP prompt with
   `context: RESEARCH_INPUT_REF` (see `g02-orchestrate-research`). After the Human Research Gate,
   `research_bundle_finalize` returns `RESEARCH_BUNDLE_REF`.
3. **Solution** — `solution_run_hosted({context: {lecture_baseline_ref: LECTURE_BASELINE_REF,
   research_bundle_ref: RESEARCH_BUNDLE_REF}})`. Run the g03 host-driven loop (see
   `g03-orchestrate-solution`). On completion you have the approved `solution_blueprint@1`.
4. Report the final blueprint ref and each stage's boundary ref. Optional token/timing roll-up is
   still available for G01/G03 hosted loops through their trace tools.

Each graph's human gates fire inside their loops — present them, collect decisions, never
auto-approve. Do NOT use `research_run_hosted`, `research_run_codex` or nested `*_run_codex` tools
inside a Codex session.

For a no-LLM wiring smoke of the whole chain (non-Codex shell / CI):
`python3 "<plugin-root>/shared/scripts/workflow.py" run-stub <intake_context>`.
