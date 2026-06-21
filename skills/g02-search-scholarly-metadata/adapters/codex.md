## Host Adapter: Codex

- Call MCP `research_provider_status`, then `research_metadata_search` for each approved route.
- Treat `literature_tool_result@1` as the provider boundary and preserve its artifact ref, operation
  ID, cursor, cache status and issues.
- If MCP is unavailable, return `external_dependency_blocked`; do not browse as a substitute.
