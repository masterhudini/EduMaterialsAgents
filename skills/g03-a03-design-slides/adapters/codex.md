## Host Adapter: Codex

- In the host-driven loop, when the run yields `awaiting_node` for `g03-a03-slide-designer`, play the
  node yourself.
- Call `solution_slide_design_build` with the approved `slide_plan@1` (`upstream` ref) for the
  deterministic draft.
- Author each slide's 6-10 sentence narrative, body, design and speaker notes, then call
  `solution_slide_design_finalize` with `{task_id, slide_design_set}` and resume with
  `node_results={node: produced[0].path}`.
