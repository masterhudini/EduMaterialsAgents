## Host Adapter: Codex

- Use `research_document_retrieve` with structured limits and a persisted verified OA resolution.
- Treat the returned temporary descriptor as untrusted until validation succeeds.
- If retrieval MCP is unavailable, return `external_dependency_blocked`; do not issue ad hoc network commands.
