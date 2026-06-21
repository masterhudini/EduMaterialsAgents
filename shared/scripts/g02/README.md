# shared/scripts/g02 — Research Graph deterministic operations

Graph-specific, **pure stdlib** helpers for the Research Graph. The reviewed reasoning lives
in `agents/`; this package holds deterministic validation, artifact and flow operations.

Source of truth for the graph: `shared/graphs/g02.graph.json`.
Authoritative design references: `docs/02_Architektura_agentow_i_skilli.md` and
`docs/03_Kontrakty_i_artefakty.md`.

## Implemented and planned modules

| Module | Responsibility |
|---|---|
| `g02_flow.py` | Deterministic orchestration of the node sequence (planner → parallel work → selection → retrieval → review → synthesis → user gate) + event-log calls. Must agree with the manifest. |
| `planner.py` | Scope and validate G02-A01 input, validate and store `research_plan@1`, constrain revisions, build the frozen `research_plan` review task and standardize planner envelopes. |
| `domain.py` | Scope one approved topic for G02-A02, validate and store `domain_candidate_sources@1`, audit provider-result refs, constrain revisions and build the frozen `domain_candidates` review task. |
| `provider_config.py` | Load and validate the secret-free provider profile, environment credentials, runtime paths and startup capabilities. |
| `query_planning.py` | Validate provider-neutral `query_plan@1` routes, generated-term bases, approved topic scope, coverage and enabled providers. |
| `providers.py` | Execute bounded OpenAlex, Semantic Scholar and arXiv requests with allowlisted endpoints, retry, rate limits, cache, raw artifacts and normalized `source_record@1` results. |
| `review.py` | Validate ReviewTask and ReviewDecision, constrain artifact access, map severity, persist review decisions and standardize reviewer envelopes. |
| `*_shape.py` | Planned structural validators for later producer artifacts. G02-A01 and G02-A02 validation live in their owning modules. |
| `revision.py` (or in core) | Apply `revision_policy` counters and decide REVISE / APPROVED / ESCALATE for a reviewer node. |

Later producer shape checks follow the same pure-stdlib pattern as the implemented modules
and are added with the producer that first requires them.
