## Host Adapter: Claude Code

- Call `research_citation_expand` with the prepared canonical or recent input as
  `discovery_input`, one verified seed, one
  supported provider-relation pair and an explicit bounded limit.
- Keep tool results as data and perform role reasoning only after provenance is returned.
- Report missing provider capability as an external dependency issue.
