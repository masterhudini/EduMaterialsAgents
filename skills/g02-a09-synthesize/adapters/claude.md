## Host Adapter: Claude Code

- Call `research_a09_task_prepare`, then use the `g02-a09-synthesize` skill exactly once
  for the returned `a09_synthesis_task@1`, with model opus / effort medium.
- Verify and refine the supplied `deterministic_baseline`; do not regenerate it from scratch.
- Return only the JSON object described by the skill.
- Call MCP `research_a09_synthesis_finalize` with the same `reviews_json`, `intake`, the
  `deep_dive` package returned beside the A09 task, and `output` set to your JSON.
- Never read a full PDF or any path outside the supplied task.
