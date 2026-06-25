## Host Adapter: Codex

- In the host-driven loop, when the run yields `awaiting_node` for `g03-a02-slide-architect`, play the
  node yourself.
- Call `solution_slide_plan_build` with the node `input` for the deterministic draft; hydrate
  `upstream` refs with `solution_get_artifact` as needed.
- Refine statuses and new-slide proposals, then call `solution_slide_plan_finalize` with
  `{task_id, slide_plan}` and resume with `node_results={node: produced[0].path}`.
