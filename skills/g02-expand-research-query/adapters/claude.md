## Host Adapter: Claude Code

- Run inside the authorized discovery node after `research_domain_prepare`.
- Produce only `query_plan@1`, including one approved `generated_term_bases` entry for every
  generated term; do not expose WebSearch, WebFetch or provider tools during planning.
- Preserve origin terms, exclusions, filters, coverage and provider capabilities exactly.
- Hand the plan to `research_metadata_search` through the calling agent.
