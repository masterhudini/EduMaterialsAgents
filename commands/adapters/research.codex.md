## Host Adapter: Codex

Run the Codex worker runtime from the installed plugin bundle:

```bash
python3 "{{CODEX_PLUGIN_ROOT}}/shared/scripts/g02/g02_flow.py" run-codex <path-or-artifact-ref-to-research_graph_input> --gates auto
```

Use the command argument as `<path-or-artifact-ref-to-research_graph_input>`. Prefer an absolute
path for local JSON files so the MCP/runtime process does not depend on a particular working
directory.

If the user asks to handle gates interactively, use `--gates prompt` instead of `--gates auto`.
