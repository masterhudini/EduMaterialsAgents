## Host Adapter: Claude Code

Use the `orchestrate-research` skill as the conversational runtime. Start by calling the
plugin-provided MCP front door with the command argument, then drive producer agents through the
Task/Agent tool and use MCP seams for deterministic validation, scoped input and final handoff.

For a deterministic wiring check without producer agents, call `research_run_stub` with the same
context argument.
