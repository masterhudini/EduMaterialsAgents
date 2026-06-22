## Host Adapter: Claude Code

- Run inside the authorized discovery node after `research_domain_prepare`,
  `research_recent_prepare` or `research_market_cases_prepare`.
- Produce only `query_plan@1`, including one approved `generated_term_bases` entry for every
  generated term; do not expose WebSearch, WebFetch or provider tools during planning.
- Preserve origin terms, exclusions, filters, coverage and provider capabilities exactly.
- For A04, preserve the prepared calendar window in every route and keep a preprint route when
  approved.
- For A11, preserve the provider mode, source-tier domain policy and market-case needs exactly.
- Hand the plan to `research_metadata_search` through the calling agent.
