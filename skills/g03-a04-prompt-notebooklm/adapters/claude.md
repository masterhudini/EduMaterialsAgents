## Host Adapter: Claude Code

- Used by the `g03-a04-prompt-builder` node when the change-plan gate chose `target_tool=notebooklm`.
- Call `solution_prompt_build` with the approved `slide_design_set@1` (upstream ref) and
  `target_tool="notebooklm"` for the draft; refine the wording to NotebookLM's idiom.
- Call `solution_prompt_finalize` with `{task_id, presentation_prompt}`; optionally
  `solution_prompt_render` for the `.md` copy. Return only the finalize `envelope@1`.
