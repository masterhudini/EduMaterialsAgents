## Host Adapter: Claude Code

Drive G02 through the hosted loop:

1. `research_run_hosted({context, through: "user-research-gate"})`.
2. `awaiting_node`: run the named agent with the supplied `input` and `upstream`; call the returned
   `finalize_op` with `finalize_args` completed by the raw model JSON. Resume with
   `research_resume({resume_token, node_results: {node_key: <finalize envelope>}})`.
3. After A01 finalizes and before resuming, call `research_provider_setup` if the user wants to
   provide email or an OpenAlex key for Scout.
4. A07 `node_key`s are independent topic/source units. Use only the task JSON, selected windows and
   compact intake context.
5. A09 is one verifier/refiner pass over the supplied task. If unavailable, use finalizer fallback.
6. `awaiting_user`: present the Human Research Gate and resume with explicit user decisions.

In a host session you are the worker, so drive G02 through `research_run_hosted` rather than
`research_run_codex` (the nested-`codex exec` entrypoint reserved for a non-Codex shell or CI, like
`intake_run_codex` / `solution_run_codex`). Do not use `research_run_stub`, A10 review tools, retired
source filtering gates, A02-A06 tools, A08 or A11 for current G02 runs.
