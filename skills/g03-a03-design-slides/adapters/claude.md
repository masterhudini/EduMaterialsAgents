## Host Adapter: Claude Code

- Used by the `g03-a03-slide-designer` node, spawned through the Task/Agent tool by the orchestrator.
- Call `solution_slide_design_build` with the approved `slide_plan@1` (upstream ref) for the
  deterministic draft; hydrate refs with `solution_get_artifact` as needed.
- Author each slide's 6-10 sentence narrative, body, design and speaker notes, then call
  `solution_slide_design_finalize` with `{task_id, slide_design_set}`.
- Return only the `envelope@1` from the finalize op. Never write the artifact yourself.
