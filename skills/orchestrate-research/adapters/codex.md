## Host Adapter: Codex

- Use the installed Research Graph MCP or equivalent node-agent adapter for validation, scoped input,
  agent execution, artifact persistence and final handoff.
- Do not simulate physical node agents by copying their work into the orchestrator context.
- While `[KH-TODO: CODEX-RESEARCH-RUNTIME-ADAPTER]` remains unresolved, validate the boundary input,
  then return `external_dependency_blocked` with the missing capability named explicitly.
