## Host Adapter: Codex

- In the host-driven loop, when `g03-a04-prompt-builder` runs and the change-plan gate chose
  `target_tool=gpt_pro`, play the node yourself.
- Call `solution_prompt_build` with the approved `slide_design_set@1` (`upstream` ref) and
  `target_tool="gpt_pro"`; refine into a self-contained generation prompt.
- Call `solution_prompt_finalize` with `{task_id, presentation_prompt}` and resume with
  `node_results={node: produced[0].path}`.
