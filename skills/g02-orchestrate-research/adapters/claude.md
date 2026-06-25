## Host Adapter: Claude Code

Drive G02 through the hosted loop:

1. `research_run_hosted({context, through: "user-research-gate"})`.
2. `awaiting_node`: run the named agent with the supplied `input` and `upstream`; call the returned
   `finalize_op` with `finalize_args` completed by the raw model JSON. Resume with
   `research_resume({resume_token, node_results: {node_key: <finalize envelope>}})`.
3. After A01 finalizes and before resuming, call `research_provider_setup` with no arguments,
   present provider readiness, and ask the user for a provider decision. Do not continue to Scout
   until the user either supplies `email` / `openalex_key` values or explicitly chooses to continue
   without additional provider credentials. If values are supplied, call `research_provider_setup`
   again with exactly those user-provided values.
4. A07 `node_key`s are independent topic/source units. Use only the task JSON, selected windows and
   compact intake context.
5. A09 is one verifier/refiner pass over the supplied task. If unavailable, use finalizer fallback.
6. `awaiting_user`: present the User Research Gate and resume with explicit user decisions.

In a host session you are the worker, so drive G02 through `research_run_hosted` rather than
`research_run_codex` (the nested-`codex exec` entrypoint reserved for a non-Codex shell or CI, like
`intake_run_codex` / `solution_run_codex`). A11 (real-world cases via host web search, early) and A08
(claim recommender, last) are active nodes — drive them through `research_a11_*` / `research_a08_*`.
Do not use `research_run_stub`, A10 review tools, retired source filtering gates or A02-A06 tools.
