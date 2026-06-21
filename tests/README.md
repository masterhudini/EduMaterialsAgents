# tests — pytest suite (dev-only, not shipped)

One `test_*.py` per deterministic module. Local unit and contract tests exercise the **stdlib**
engine and shape checks. Forward tests of agents and skills, host checks and opt-in live provider
smoke tests belong to the separate TEST environment and follow the authoritative checklist in
`docs/07_Rejestr_DEV_TEST_1b1.md`.

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
