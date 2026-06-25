## Host Adapter: Codex

Inside a Codex session you are the host worker. Drive G02 through `research_run_hosted` and
`research_resume`; do not start nested `codex exec` workers.

1. Call `research_run_hosted({context, through: "user-research-gate"})`.
2. On `awaiting_node`, run the named agent using only the payload input. Call the payload
   `finalize_op` with `finalize_args` filled with the raw model JSON, then resume with
   `research_resume({resume_token, node_results: {node_key: <finalize envelope>}})`.
3. After A01 finalizes and before resuming, call `research_provider_setup` if the user wants to
   provide email or an OpenAlex key for Scout.
4. For A07, treat every `node_key` as a separate topic/source unit. Read only the supplied task,
   selected windows and compact intake context; never read full PDFs or browse.
5. For A09, verify/refine the supplied task once. If no reliable model pass is possible, call the
   finalizer without model output so deterministic fallback is recorded.
6. On `awaiting_user`, collect explicit Human Research Gate decisions and resume. The final
   `output_ref` is the `user_approved_research_bundle@1`.

**Do NOT call `research_run_codex` from inside a Codex session** — it spawns a nested `codex exec`
worker that cannot initialise under the outer read-only sandbox. `research_run_codex` is for a
non-Codex shell or CI (`python3 "<plugin-root>/shared/scripts/g02/g02_flow.py" run-codex <context>`),
mirroring `intake_run_codex` / `solution_run_codex`; `run` is a no-LLM stub smoke.

Do not call `research_run_stub`, A10 review tools, source-selection, A02-A06, A08 or A11 in the
active workflow.
