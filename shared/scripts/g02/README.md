# shared/scripts/g02 — Research Graph deterministic operations

Graph-specific, **pure stdlib** helpers for the Research Graph. The reviewed reasoning lives
in `agents/`; this package holds deterministic validation, artifact and flow operations.

Source of truth for the graph: `shared/graphs/g02.graph.json`.
Authoritative design references: `docs/02_Architektura_agentow_i_skilli.md` and
`docs/03_Kontrakty_i_artefakty.md`.

## Implemented and planned modules

| Module | Responsibility |
|---|---|
| `g02_flow.py` | Deterministic orchestration of the manifest node sequence (planner → discovery → selection → retrieval → review → synthesis → user gate), injectable node runners, revision loops and event-log calls. The current scheduler is serial. |
| `planner.py` | Scope and validate G02-A01 input, validate and store `research_plan@1`, constrain revisions, build the frozen `research_plan` review task and standardize planner envelopes. |
| `domain.py` | Scope one approved topic for G02-A02, validate and store `domain_candidate_sources@1`, audit provider-result refs, constrain revisions and build the frozen `domain_candidates` review task. |
| `canonical.py` | Scope reviewed A01/A02 artifacts for G02-A03, validate and store canonical `candidate_sources@1`, constrain revisions and build the frozen `canonical_sources` review task. |
| `recent.py` | Derive the exact intake-approved recent window, scope reviewed A01/A02 artifacts for G02-A04, validate and store recent `candidate_sources@1`, constrain revisions and build the frozen `recent_developments` review task. |
| `citations.py` | Execute bounded one-hop OpenAlex and Semantic Scholar citation relations with the shared provider transport, normalization, cache and provenance boundary. |
| `provider_config.py` | Load and validate the secret-free provider profile, environment credentials, runtime paths and startup capabilities. |
| `query_planning.py` | Validate provider-neutral `query_plan@1` routes, generated-term bases, approved topic scope, coverage and enabled providers. |
| `providers.py` | Execute bounded OpenAlex, Semantic Scholar and arXiv requests with allowlisted endpoints, retry, rate limits, cache, raw artifacts and normalized `source_record@1` results. |
| `review.py` | Validate ReviewTask and ReviewDecision, constrain artifact access, map severity, persist review decisions and standardize reviewer envelopes. |
| `*_shape.py` | Planned structural validators for later producer artifacts. G02-A01 through G02-A04 validation lives in the owning modules. |
| `revision.py` (or in core) | Apply `revision_policy` counters and decide REVISE / APPROVED / ESCALATE for a reviewer node. |

Later producer shape checks follow the same pure-stdlib pattern as the implemented modules
and are added with the producer that first requires them.
