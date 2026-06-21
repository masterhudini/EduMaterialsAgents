## Host Adapter: Claude Code

- Enter through `/research` and keep this skill as the only conversational surface.
- Invoke graph nodes through the Task/Agent tool with `subagent_type` equal to the manifest node name.
- Pass only the scoped bundle returned for that node; persist produced artifact refs between calls.
- Use the plugin-provided runtime surface. Do not construct installation paths in prompt logic.

The deterministic seams are **MCP tools** from the `edu-materials-research` server — call them as
tools (never shell out or build paths):

- workflow step 1 (validate + register input) → `research_front_door` `{context}` → `{ref, task_id}`;
- workflow step 2 (per-node scoped input) → `research_node_input` `{ref, node}`;
- workflow step 10 (freeze + emit handoff) → `research_finalize` `{bundle}` → descriptor;
- wiring smoke without driving agents → `research_run_stub` `{context}`.
