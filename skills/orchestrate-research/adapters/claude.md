## Host Adapter: Claude Code

- Enter through `/research` and keep this skill as the only conversational surface.
- Invoke graph nodes through the Task/Agent tool with `subagent_type` equal to the manifest node name.
- Pass only the scoped bundle returned for that node; persist produced artifact refs between calls.
- Use the plugin-provided runtime surface. Do not construct installation paths in prompt logic.
