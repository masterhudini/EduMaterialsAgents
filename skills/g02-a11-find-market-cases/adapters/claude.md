## Host Adapter: Claude Code

- Call `research_provider_status` during startup and `research_web_case_search` per approved web route.
- Pass only structured QueryPlan route data, including include and exclude domains and the tier floor.
- Never parse ad hoc web results, browse directly or put credentials in the agent context.
- Do not call the extraction operation here; full-page extraction is deferred to G02-A07 on
  human-approved cases.
- Preserve unavailable and zero-result operations in the market-case query log.
