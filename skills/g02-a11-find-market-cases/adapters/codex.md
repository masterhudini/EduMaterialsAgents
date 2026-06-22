## Host Adapter: Codex

- Call MCP `research_market_cases_prepare`, then `research_web_case_search` for each approved route.
- Treat `web_case_tool_result@1` as the provider boundary and preserve its artifact ref, exact scope,
  operation ID, provider runs, cursor, cache status, public budget, observed source tier and issues.
- If MCP is unavailable, return `external_dependency_blocked`; do not browse as a substitute.
- Do not invoke extraction during discovery; it requires final human approval and stored refs.
