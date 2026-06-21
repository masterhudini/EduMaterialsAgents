## Host Adapter: Codex

- Call the configured Research Graph MCP metadata-search operation with the QueryPlan JSON.
- Treat MCP output as the provider boundary and preserve operation IDs, cursors and issues.
- If the MCP surface is not installed, return `external_dependency_blocked`; do not browse as a substitute.
