## Host Adapter: Codex

- Call `research_oa_resolve` with the prepared retrieval input and approved source ID.
- Preserve route attempts and treat unavailable as a valid structured result.
- If the MCP operation is absent, return `external_dependency_blocked`; do not use general browsing as retrieval authority.
