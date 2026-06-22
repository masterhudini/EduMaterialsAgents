# tests — pytest suite (dev-only, not shipped)

One `test_*.py` per deterministic module. Local unit and contract tests exercise the **stdlib**
engine and shape checks. Forward tests of agents and skills, host checks and opt-in live provider
smoke tests belong to the separate TEST environment and follow the authoritative checklist in
`docs/07_Rejestr_DEV_TEST_1b1.md`.

`test_g02_market_cases.py` contains offline A11 contract, scoped-input, Tavily/SearXNG,
materiality, review, safety and gated-extraction scenarios. It is authored for the separate TEST
environment; the A11 DEV session runs only the short static checks allowed by the checklist.

`test_g02_retrieval.py` verifies the two-step human gate, OA resolution and PDF validation, then
checks the complete market-case bundle. The expected run directory contains the PDF, a readable
`.market-case.md`, a separate `.market-case.json` and `retrieved_corpus.json`; the test checks A11
fact/mechanism content, safety warning, refs, SHA-256 values and rejection of a missing A11 annotation.
The default A06 module run should report eight passed tests and one skipped opt-in live test.

## Run

```bash
bash scripts/dev-setup.sh   # one-time: creates .venv with pytest
.venv/bin/python -m pytest
```

Windows:

```powershell
.\scripts\dev-setup.ps1
.\.venv\Scripts\python.exe -m pytest
```

## Opt-in real PDF smoke for G02-A06

The A06 live smoke is skipped by default. It uses a fixed open-access PLOS DOI, resolves the PDF
through Unpaywall, downloads the real bytes with the production transport, validates the file and
stores the PDF plus `retrieved_corpus.json` in one run directory. Use a real contact email and an
isolated runtime home. The test prints `A06_LIVE_RUN_DIRECTORY=...` when run with output capture off.

Linux or WSL:

```bash
export EMAGENTS_RUN_LIVE_A06=1
export EMAGENTS_RESEARCH_CONTACT_EMAIL='your-contact@example.edu'
export EMAGENTS_LIVE_A06_HOME=/tmp/emagents-a06-live
.venv/bin/python -m pytest -q -s tests/test_g02_retrieval.py -k live_unpaywall
```

Windows PowerShell:

```powershell
$env:EMAGENTS_RUN_LIVE_A06 = '1'
$env:EMAGENTS_RESEARCH_CONTACT_EMAIL = 'your-contact@example.edu'
$env:EMAGENTS_LIVE_A06_HOME = Join-Path $env:TEMP 'emagents-a06-live'
.\.venv\Scripts\python.exe -m pytest -q -s tests/test_g02_retrieval.py -k live_unpaywall
```

`EMAGENTS_LIVE_A06_HOME` is optional. Setting it makes the resulting run folder easy to inspect
after pytest exits. No API key is required for this Unpaywall-only smoke.

`tests/` is excluded from generated plugin bundles by `scripts/build-plugin.py`.

## To add

- `test_contracts.py` — envelope + schema validation, version ref parsing.
- `test_state.py`, `test_validate_state.py`, `test_gate.py` — state/gate mechanics.
- extend graph checks beyond current manifest, registration and packaging coverage.
- `test_revision.py` — revision-policy counters and REVISE/APPROVED/ESCALATE routing.
- one `test_<artifact>_shape.py` per Research Graph shape check.
- TEST 2 modules for Planner preparation, semantic validation, finalization, revision and review.
- TEST 3 modules for provider configuration, QueryPlan generated-term bases, offline provider
  fixtures, Domain finalization, MCP parity and secret-redaction scans.
- opt-in live tests for OpenAlex, Semantic Scholar and arXiv; they must remain skipped by default.
- opt-in live tests for Tavily search/extraction and the administrator-configured SearXNG instance;
  they must remain skipped by default.
