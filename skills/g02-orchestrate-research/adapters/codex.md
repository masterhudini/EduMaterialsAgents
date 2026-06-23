## Host Adapter: Codex

- Use the installed Research Graph MCP or equivalent node-agent adapter for validation, scoped input,
  agent execution, artifact persistence and final handoff.
- Do not simulate physical node agents by copying their work into the orchestrator context.
- For semantic requests such as "zrob research", "zrób research" or "run the research graph", use
  the MCP tool `research_run_codex` when available:

  ```json
  {"context": "<path-or-artifact-ref>", "gates": "pause"}
  ```

  `gates: "pause"` is the default and preserves human gates by returning `awaiting_user` with a
  `resume_token`; resume with the same tool using `resume_token` and `decisions`. The reviewed
  runner never auto-approves a human gate.
- The Codex runtime adapter drives the deterministic engine with **Codex workers**: each node runs
  as an isolated `codex exec` call. Entry point (headless/local, subscription login, no API key):

  ```bash
  python3 "<plugin-root>/shared/scripts/g02/g02_flow.py" run-codex <context> [--gates prompt|pause]
  ```

  This loads and validates the boundary input, runs the implemented A01–A06 frontier via isolated
  `codex exec`, applies one fail-closed review per producer with at most one unreviewed correction,
  and hosts the numbered two-step source gate on the
  terminal (`--gates prompt`). It returns `research_run_report@1`; later A07–A09 execution remains
  outside this bounded runner until those producers are implemented.
- The Codex plugin manifest does not register plugin-local `commands/` as slash commands. Do not
  tell the user to use `/research` in Codex; `/research` is Claude-only for now.
- Do not simulate physical node agents by copying their work into the orchestrator context — each
  node is a separate `codex exec` worker reading its own agent prompt (shipped under `agents/`).
- If the `codex` CLI is unavailable or the user is not logged in, validate the boundary input and
  report `external_dependency_blocked`, naming the missing capability (codex CLI / login).
