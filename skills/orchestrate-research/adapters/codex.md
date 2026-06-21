## Host Adapter: Codex

- The Codex bundle exposes the shared skill/runtime and the `edu-materials-research` MCP tools.
- Treat MCP tools as the deterministic boundary for validation, scoped node input, stub runs, and
  final handoff emission.
- Current Codex bundles do not install the Claude node-agent `.md` files. If a run requires real
  node agents and no Codex multi-agent adapter is available in the session, stop after validation
  and report that the Codex node-agent adapter is not installed yet.
- For wiring smoke tests, call `research_run_stub` with `{context}` instead of trying to simulate
  node agents in prompt text.
