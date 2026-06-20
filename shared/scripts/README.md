# shared/scripts — deterministic mechanics (pure stdlib)

Two layers:

- `core/` — reusable, domain-agnostic engine (contracts, state, gate, event log, graph check,
  revision/parallel/user-gate/artifact mechanics). Every graph reuses it.
- `<graph>/` — per-graph helpers (flow + shape checks). Currently: `research/`.

Agents call these inline via:
`python3 -c "import sys; sys.path.insert(0,'$CLAUDE_PLUGIN_ROOT/shared/scripts'); from <pkg>.<mod> import ..."`.

**Hard rule:** stdlib only. No third-party imports anywhere under `shared/scripts/**` — that
is what lets the installed plugin run with the system python3 and no virtualenv.
