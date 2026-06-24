# Scout Phase A Status

This package contains the vendored Scout/Radar core used for the planned G02
deterministic Scout mode.

Current status:

- The core files are copied from `LLMWiki scout source code/llmwiki_radar`.
- `runtime.py` adapts Scout paths to the EduMaterials runtime under
  `.emagents/g02/scout` or `EMAGENTS_HOME/g02/scout`.
- `_smoke.py` runs Scout standalone; `../scout_fanout.py` is the persistent multi-topic runner
  exposed through MCP as `research_scout_fanout`.
- Phase A disables LLM verification and query expansion. It passes no OpenRouter
  key and does not read LLMWiki env files.

Run from the repository root:

```powershell
python shared/scripts/g02/scout/_smoke.py "value at risk garch" -n 5 --email you@example.edu
```

Optional provider keys are read from process environment variables:

- `OPENALEX_API_KEY`
- `SEMANTIC_SCHOLAR_API_KEY` or `S2_API_KEY`
- `CORE_API_KEY`
- `EMAGENTS_RESEARCH_CONTACT_EMAIL` or `POLITE_POOL_EMAIL`

The production pre-A07 runner accepts one finalized `research_plan@1`, requires 4–6 topics and
`OPENALEX_API_KEY`, then starts one child process per topic. Its stable output is
`<workspace>/runs/<task_id>/` with `plan.json`, per-topic requests/PDFs/manifests/corpora and one
cross-topic `index.json`. Deduplication happens only after every topic finishes, so retrieval never
suppresses a paper relevant to another topic.

A07, A09, `reviews.json`, `SolutionInputCandidate`, Graph03 and host-model verification inside
Scout remain outside this milestone.
