# tests — pytest suite (dev-only, not shipped)

One `test_*.py` per deterministic module. Tests exercise the **stdlib** engine and shape
checks without invoking any LLM node — the agents/skills are prompts, the scripts are what we
unit-test. Mirrors `inspiration/tests/`.

## Run

```bash
bash scripts/dev-setup.sh   # one-time: creates .venv with pytest
.venv/bin/pytest
```

`tests/` is excluded from the installed plugin (see `install.sh` PLUGIN_ITEMS).

## To add

- `test_contracts.py` — envelope + schema validation, version ref parsing.
- `test_state.py`, `test_validate_state.py`, `test_gate.py` — state/gate mechanics.
- `test_graph_manifest.py` / `test_graph_check.py` — manifest ≡ plugin.json ≡ flow.
- `test_revision.py` — revision-policy counters and REVISE/APPROVED/ESCALATE routing.
- one `test_<artifact>_shape.py` per Research Graph shape check.
