## Host Adapter: Codex

- Use the configured MCP retrieval operation with structured limits and verified OA resolution.
- Treat the returned temporary descriptor as untrusted until validation succeeds.
- If retrieval MCP is unavailable, return `external_dependency_blocked`; do not issue ad hoc network commands.
