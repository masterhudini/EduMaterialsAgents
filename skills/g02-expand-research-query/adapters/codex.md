## Host Adapter: Codex

- Execute inside the isolated discovery node after MCP `research_domain_prepare`.
- Produce only `query_plan@1`, including one approved `generated_term_bases` entry for every
  generated term, without direct browser or network access.
- Pass the plan to MCP `research_metadata_search`; deterministic validation occurs there.
- Return the supplied failure envelope when preparation or provider startup is blocked.
