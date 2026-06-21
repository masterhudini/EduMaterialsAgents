## Host Adapter: Claude Code

- The Claude bundle includes the research node agents from `agents/*.md`.
- Invoke each node via the Task/Agent tool with `subagent_type` equal to the graph node name
  (for example `research-planner`), passing only that node's scoped input bundle.
- The `/research` command is the normal user entrypoint; it should route to this skill with the
  approved `research_graph_input@1` path or artifact ref.
- The host launches the MCP server from the generated plugin bundle. Do not resolve
  `CLAUDE_PLUGIN_ROOT` manually inside the skill.
