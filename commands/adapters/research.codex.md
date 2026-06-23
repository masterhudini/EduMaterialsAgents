## Host Adapter: Codex

Run the Codex worker runtime from the installed plugin bundle:

```bash
python3 "{{CODEX_PLUGIN_ROOT}}/shared/scripts/g02/g02_flow.py" run-codex <path-or-artifact-ref-to-research_graph_input> --gates pause
```

Use the command argument as `<path-or-artifact-ref-to-research_graph_input>`. Prefer an absolute
path for local JSON files so the MCP/runtime process does not depend on a particular working
directory.

Use `--gates prompt` for the numbered, two-step terminal source gate; it accepts displayed numbers
or stable source IDs and requires a separate confirmation. Use `--gates pause` when the host must
return a resume token and collect the decision in the conversation. The real runner never
auto-approves a gate; use `research_run_stub` only for a synthetic no-op wiring smoke.
