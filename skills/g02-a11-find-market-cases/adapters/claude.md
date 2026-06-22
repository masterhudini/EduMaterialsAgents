## Host Adapter: Claude Code

- Call `research_market_cases_prepare`, then `research_web_case_search` per approved web route.
- Pass only structured QueryPlan route data, including include and exclude domains and the tier floor.
- Never parse ad hoc web results, browse directly or put credentials in the agent context.
- Pass `market_case_input`, the exact route ID and its prepared provider mode. Do not select a
  SearXNG instance or handle Tavily credentials.
- Do not call extraction here; it requires a final persisted Human Source Selection artifact.
- Preserve unavailable and zero-result operations in the market-case query log.
