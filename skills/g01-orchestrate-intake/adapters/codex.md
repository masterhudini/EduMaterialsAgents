## Host Adapter: Codex

- Drive the deterministic engine with Codex workers: `python3 "<plugin-root>/shared/scripts/g01/g01_flow.py" run-codex <context>`
  loads + validates the boundary input, runs each node as an isolated `codex exec` worker and hosts the
  user intake gate on the terminal. (Use `run` instead for a no-LLM stub smoke.)
- Each node is a separate isolated worker reading its own agent prompt (shipped under `agents/`); do not
  copy a producer's work into the orchestrator context.
- If the `codex` CLI is unavailable or the user is not logged in, validate the boundary input and report
  `external_dependency_blocked`, naming the missing capability.
