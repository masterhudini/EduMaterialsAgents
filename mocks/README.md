# mocks — hand-authored boundary contexts for testing graphs in isolation

These are mocked **input bundles** that satisfy a graph's boundary contract, so a subgraph can
be run/tested without its upstream producer. Dev-only — not shipped with the plugin (excluded
from `install.sh`).

Namespaced per graph:

- `g02/research_graph_input.json` — a `research_graph_input@1` context (Bayesian Statistics
  lecture refresh). Feed it to the Research Graph:
  - deterministic harness: `python3 shared/scripts/g02/g02_flow.py run mocks/g02/research_graph_input.json`
  - real orchestration: `/research mocks/g02/research_graph_input.json` (plugin installed)

Later: `g01/…` and `g03/…` mocks as those graphs come online. Each mock is validated by
the owning graph's front door on load, so a stale mock fails fast against its contract.
