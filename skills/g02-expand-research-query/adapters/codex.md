## Host Adapter: Codex

- Execute inside the isolated discovery node after MCP `research_domain_prepare`,
  `research_recent_prepare` or `research_market_cases_prepare`.
- For scholarly fast inputs, call `research_query_plan_generate_fast` first and use its validated
  plan unchanged. Construct a plan manually only for the structured gap it reports.
- Produce only `query_plan@1`, including one approved `generated_term_bases` entry for every
  generated term, without direct browser or network access.
- Pass the validated plan to MCP `research_metadata_search`.
- For A04, copy the prepared calendar window exactly into every route.
- For A11, pass the validated web routes only to `research_web_case_search`.
- Return the supplied failure envelope when preparation or provider startup is blocked.
