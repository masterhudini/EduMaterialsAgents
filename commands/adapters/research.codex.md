## Host Adapter: Codex

Use the installed research MCP server, not `g02_flow.py run-codex`.

1. Call `research_run_hosted({context: <command argument>, through: "user-research-gate"})`.
2. For each `awaiting_node`, run the named agent using only the payload input. Call `finalize_op`
   with the provided `finalize_args` completed by the raw model JSON, then call
   `research_resume({resume_token, node_results: {node_key: <finalize envelope>}})`.
3. After A01 finalizes and before resuming, call `research_provider_setup` if the user wants to
   provide email or an OpenAlex key for Scout.
4. For `awaiting_user`, collect explicit Human Research Gate decisions and resume with
   `decisions: {"user-research-gate": ...}`.
5. Return the completed `output_ref`.

Do not call `research_run_codex`, `research_run_stub`, A10 review tools or retired A02-A06/source
selection tools.
