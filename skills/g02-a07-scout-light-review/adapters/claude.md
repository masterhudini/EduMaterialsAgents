## Host Adapter: Claude Code

- Use the `g02-a07-scout-light-review` skill for each `scout_a07_model_task@1`.
- Return only the JSON object described by the skill.
- Call MCP `research_scout_a07_partial_finalize` with the original `work_input_ref` resolved under
  the A07 directory and the JSON output.
- Never read the full PDF or any path outside the supplied task.
