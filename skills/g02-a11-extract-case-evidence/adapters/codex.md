## Host Adapter: Codex

- Call MCP `research_web_case_extract` only for human-approved cases; preserve the page artifact ref.
- Treat the persisted page as the boundary; emit only the compact evidence card downstream.
- If MCP is unavailable, return `external_dependency_blocked`; do not browse as a substitute.
