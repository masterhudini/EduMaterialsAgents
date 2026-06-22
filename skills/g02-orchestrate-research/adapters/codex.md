## Host Adapter: Codex

- Use the installed Research Graph MCP or equivalent node-agent adapter for validation, scoped input,
  agent execution, artifact persistence and final handoff.
- Do not simulate physical node agents by copying their work into the orchestrator context.
- While `[KH-TODO: CODEX-RESEARCH-RUNTIME-ADAPTER]` remains unresolved, validate the boundary input,
  then return `external_dependency_blocked` with the missing capability named explicitly.
- For semantic requests such as "zrob research", "zrób research" or "run the research graph", use
  the MCP tool `research_run_codex` when available:

  ```json
  {"context": "<path-or-artifact-ref>", "gates": "pause"}
  ```

  `gates: "pause"` is the default and preserves human gates by returning `awaiting_user` with a
  `resume_token`; resume with the same tool using `resume_token` and `decisions`. Use
  `gates: "auto"` only for explicit smoke/dev runs.
- The Codex runtime adapter drives the deterministic engine with **Codex workers**: each node runs
  as an isolated `codex exec` call. Entry point (headless/local, subscription login, no API key):

  ```bash
  python3 "<plugin-root>/shared/scripts/g02/g02_flow.py" run-codex <context> [--gates prompt|auto]
  ```

  This loads + validates the boundary input, runs every node via `codex exec`, applies the reviewer
  loop, and hosts the two user gates on the terminal (`--gates prompt`).
- The Codex plugin manifest does not register plugin-local `commands/` as slash commands. Do not
  tell the user to use `/research` in Codex; `/research` is Claude-only for now.
- Do not simulate physical node agents by copying their work into the orchestrator context — each
  node is a separate `codex exec` worker reading its own agent prompt (shipped under `agents/`).
- If the `codex` CLI is unavailable or the user is not logged in, validate the boundary input and
  report `external_dependency_blocked`, naming the missing capability (codex CLI / login).