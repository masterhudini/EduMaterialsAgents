## Host Adapter: Claude Code

- Used by the `g03-a02-slide-architect` node, spawned through the Task/Agent tool by the orchestrator.
- Call `solution_slide_plan_build` with the node's boundary input for the deterministic draft; hydrate
  the blueprint / lecture / candidate refs with `solution_get_artifact` as needed.
- Refine statuses and new-slide proposals by your own judgment, then call
  `solution_slide_plan_finalize` with `{task_id, slide_plan}`.
- Return only the `envelope@1` from the finalize op. Never write the artifact yourself.
