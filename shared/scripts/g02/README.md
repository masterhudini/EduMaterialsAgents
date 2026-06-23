# shared/scripts/g02 — Research Graph deterministic operations

Graph-specific, **pure stdlib** helpers for the Research Graph. The reviewed reasoning lives
in `agents/`; this package holds deterministic validation, artifact and flow operations.

Source of truth for the graph: `shared/graphs/g02.graph.json`.
Authoritative design references: `docs/02_Architektura_agentow_i_skilli.md` and
`docs/03_Kontrakty_i_artefakty.md`.

## Implemented and planned modules

| Module | Responsibility |
|---|---|
| `g02_flow.py` | Public CLI and dispatch between the no-op wiring harness and real reviewed execution. |
| `reviewed_flow.py` | Fail-closed A01–A06 frontier: scoped stage protocols, per-topic serial discovery, typed artifact hydration, one exact A10 review, one correction without re-review, two-step source gate, pause/resume and `research_run_report@1`. |
| `planner.py` | Scope and validate G02-A01 input, validate and store `research_plan@1`, constrain revisions, build the frozen `research_plan` review task and standardize planner envelopes. |
| `domain.py` | Scope one approved topic for G02-A02, validate and store `domain_candidate_sources@1`, audit provider-result refs, constrain revisions and build the frozen `domain_candidates` review task. |
| `canonical.py` | Scope reviewed A01/A02 artifacts for G02-A03, validate and store canonical `candidate_sources@1`, constrain revisions and build the frozen `canonical_sources` review task. |
| `recent.py` | Derive the exact intake-approved recent window, scope reviewed A01/A02 artifacts for G02-A04, validate and store recent `candidate_sources@1`, constrain revisions and build the frozen `recent_developments` review task. |
| `market_cases.py` | Project the minimal A11 input from reviewed A01/A02 refs, validate market-case annotations, materiality, tiering, coverage and revisions, persist the `market_cases` stream and build MC-01 to MC-06 review tasks. |
| `web_cases.py` | Execute controlled web discovery; the bundled profile uses Tavily and leaves the existing administrator-pinned SearXNG seam disabled. Enforce budgets, cache, redirect and response controls, normalize `market_case` records, and perform Tavily extraction only after a final stored source selection. |
| `retrieval.py` | Prepare A06 from the finally confirmed source set, finalize scholarly PDFs and render every accepted market case as readable Markdown plus a separate untrusted JSON audit artifact with distinct refs and checksums. |
| `citations.py` | Execute bounded one-hop OpenAlex and Semantic Scholar citation relations with the shared provider transport, normalization, cache and provenance boundary. |
| `provider_config.py` | Load and validate the secret-free provider profile, environment credentials, runtime paths and startup capabilities. |
| `crossref.py` | Verify unchanged DOI-bearing source records through the fixed Crossref Works endpoint, compare bibliographic identity and persist compact bindings plus raw provenance. |
| `query_planning.py` | Validate provider-neutral `query_plan@1` routes, generated-term bases, approved topic scope, coverage and enabled providers. |
| `providers.py` | Execute bounded OpenAlex, Semantic Scholar and arXiv requests with allowlisted endpoints, retry, rate limits, cache, raw artifacts and normalized `source_record@1` results. |
| `review.py` | Validate ReviewTask and ReviewDecision, constrain artifact access, map severity, persist review decisions and standardize reviewer envelopes. |
| `*_shape.py` | Planned structural validators for later producer artifacts. G02-A01 through G02-A04 and G02-A11 validation lives in the owning modules. |

Later producer shape checks follow the same pure-stdlib pattern as the implemented modules
and are added with the producer that first requires them.
