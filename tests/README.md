# tests — pytest suite (dev-only, not shipped)

One `test_*.py` per deterministic module. Tests exercise the **stdlib** engine and shape
checks without invoking any LLM node — the agents/skills are prompts, the scripts are what we
unit-test. Mirrors `inspiration/tests/`.

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
