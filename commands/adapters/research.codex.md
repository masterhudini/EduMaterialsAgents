## Host Adapter: Codex

Run the Codex worker runtime from the installed plugin bundle:

```bash
python3 "{{CODEX_PLUGIN_ROOT}}/shared/scripts/g02/g02_flow.py" run-codex <path-or-artifact-ref-to-research_graph_input> --gates pause
```

Use the command argument as `<path-or-artifact-ref-to-research_graph_input>`. Prefer an absolute
path for local JSON files so the MCP/runtime process does not depend on a particular working
directory.

The default execution profile is `fast`: A01 plans at most two priority-selected topics, discovery
uses bounded provider calls, A07 reviews each accepted source, A08 is skipped with an explicit
limitation, and A09 is the default reviewed terminal producer. A10 is mandatory for A01, A05, A06
and A09; A07 is reviewed conditionally.

Use `--gates prompt` for both terminal gates. The source gate accepts displayed numbers or stable
source IDs and requires a separate confirmation; the final gate collects required-update,
optional-improvement and unresolved-item decisions. Use `--gates pause` when the host must
return a resume token and collect the decision in the conversation. Resume the CLI with
`--resume-token <token> --decisions <json-file>` and omit the context argument; the JSON object is
keyed by `user-source-selection-gate` or `user-research-gate`. The real runner never
auto-approves a gate; use `research_run_stub` only for a synthetic no-op wiring smoke.
After reviewed A09, `run-codex` returns `awaiting_user` at the Human Research Gate. Resume with the
returned token and a `user-research-gate` decision to create the compact Graph03 bundle.
