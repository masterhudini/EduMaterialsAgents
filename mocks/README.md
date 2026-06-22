# mocks — hand-authored boundary contexts for testing graphs in isolation

These are mocked **input bundles** that satisfy a graph's boundary contract, so a subgraph can
be run/tested without its upstream producer. Dev-only — not shipped with the plugin (excluded
from `install.sh`).

Namespaced per graph:

- `g02/research_graph_input.json` — a `research_graph_input@1` context (Bayesian Statistics
  lecture refresh). Feed it to the Research Graph:
  - deterministic harness: `python3 shared/scripts/g02/g02_flow.py run mocks/g02/research_graph_input.json`
  - real orchestration: `/research mocks/g02/research_graph_input.json` (plugin installed)
- `g02/research_plan.json` — a complete `research_plan@1` example for G02-A01 finalization and
  universal-reviewer checks. It is paired with the boundary input above.

- `g02/query_plan.json` contains a provider-neutral `query_plan@1` example for the first
  approved topic in `research_plan.json`, including semantic bases for all generated terms.
- `g02/provider_responses/` contains fixed OpenAlex, Semantic Scholar and arXiv responses for
  offline normalization, pagination and provenance tests of G02-A02. It also contains A03
  citation fixtures for OpenAlex `cited_by` and Semantic Scholar `references`, `cited_by` and
  `recommendations`.
- `g02/domain_candidate_sources.json` is the reviewed A02 handoff used to test A03 scoped input,
  unchanged provider records, citation expansion, finalization, review and revision paths.
- `g02/recent_query_plan.json` and the recent OpenAlex/Semantic Scholar responses exercise A04
  date scoping, metadata discovery, preprint handling, maturity, review and revision paths.

Later: `g01/…` and `g03/…` mocks as those graphs come online. Each mock is validated by
the owning graph's front door on load, so a stale mock fails fast against its contract.
