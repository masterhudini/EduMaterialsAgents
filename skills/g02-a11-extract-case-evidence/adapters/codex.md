## Host Adapter: Codex

- Call MCP `research_web_case_extract` with stored selection/candidate refs and the approved source ID.
- Preserve its safety flags, content boundary, content hash and page artifact ref.
- Treat the persisted page as the boundary; emit only the compact evidence card downstream.
- If MCP is unavailable, return `external_dependency_blocked`; do not browse as a substitute.
