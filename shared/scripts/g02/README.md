# shared/scripts/g02 — Research Graph deterministic operations

Graph-specific, **pure stdlib** helpers for the Research Graph. Agent reasoning lives in
`agents/`; this package holds deterministic validation, artifact and flow operations.

Source of truth for the graph: `shared/graphs/g02.graph.json`.
Authoritative design references: `docs/02_Architektura_agentow_i_skilli.md` and
`docs/03_Kontrakty_i_artefakty.md`.

## Active and legacy modules

| Module | Responsibility |
|---|---|
| `g02_flow.py` | Legacy CLI harness for boundary inspection and retired reviewed execution. New G02 runs use MCP prompt `research-scout-e2e`. |
| `reviewed_flow.py` | Retired A02-A06/A08/A11 host-driven runner kept for legacy tests until removed fully. Do not use for new runs. |
| `planner.py` | Scope and validate G02-A01 input, validate and store `research_plan@1`, constrain revisions and standardize planner envelopes. Legacy review-task support remains internal. |
| `scout_request.py` | Convert A01 topics into one `scout_search_request@1` each and allocate the profile-level PDF budget. |
| `scout_fanout.py` | Run Scout in parallel child processes per topic, persist machine artifacts under `.emagents`, and copy human-readable PDFs to `knowledge/g02/<task_id>/<topic-name>/`. |
| `a07_bridge.py` | Prepare the native Scout run directory for A07 light review: validate plan/index/corpora, apply a cheap topic prefilter, select bounded PDF text windows and persist parallel-safe per-source work items plus `reviews.json`. |
| `a07_runner.py` | Turn pending Scout A07 work items into compact host-model tasks with linked intake context, run them through an injected or external executor, persist per-source partial reviews and aggregate `reviews.json`. |
| `a09_synthesis.py` | Bounded A09 path: deduplicate, group and rank aggregated A07 updates; select at most five auditable deep-dive sources; gather bounded windows; resolve every pointer into a recommendation or explicit gap; emit `solution_input_candidate@1` and materialize `research_state@1` for the Human Research Gate. |
| `a09_runner.py` | Obligatory Bounded A09 verifier/refiner: prepare a deterministic baseline and compact `a09_synthesis_task@1`, use the 5-source/8-window/1200-character Opus/medium budget, then finalize the model output or an auditable deterministic fallback. |
| `domain.py`, `canonical.py`, `recent.py`, `market_cases.py`, `web_cases.py`, `retrieval.py`, `paper_review.py`, `synthesis.py` | Legacy fast-frontier modules from the retired A02-A06/A08/A11 path. Their MCP names return `deprecated_tool` in the current runtime. |
| `citations.py` | Execute bounded one-hop OpenAlex and Semantic Scholar citation relations with the shared provider transport, normalization, cache and provenance boundary. |
| `provider_config.py` | Load and validate the secret-free provider profile, environment credentials, runtime paths and startup capabilities; cap scholarly, web and retrieval fan-out from the active execution profile. |
| `crossref.py` | Verify unchanged DOI-bearing source records through the fixed Crossref Works endpoint, compare bibliographic identity and persist compact bindings plus raw provenance. |
| `query_planning.py` | Generate the common bounded fast scholarly plan and validate provider-neutral `query_plan@1` routes, generated-term bases, approved topic scope, coverage and enabled providers. |
| `providers.py` | Execute bounded OpenAlex, Semantic Scholar and arXiv requests with allowlisted endpoints, retry, rate limits, cache, raw artifacts and normalized `source_record@1` results. |
| `review.py` | Deprecated A10 review helper kept for migration and legacy tests. Not active in `scout_e2e`. |
| `*_shape.py` | Planned structural validators for later producer artifacts. |

Later producer shape checks follow the same pure-stdlib pattern as the implemented modules
and are added with the producer that first requires them.
