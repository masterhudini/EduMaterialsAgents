## Host Adapter: Claude Code

Use the `g02-orchestrate-research` skill and the hosted MCP loop:

1. `research_run_hosted({context: <command argument>, through: "user-research-gate"})`.
2. On `awaiting_node`, run the requested producer, call its returned `finalize_op`, then resume with
   `node_results` keyed by `node_key`.
3. After A01 finalizes and before resuming, call `research_provider_setup` if the user wants to
   provide email or an OpenAlex key for Scout.
4. On `awaiting_user`, present the Human Research Gate and resume only after explicit approval.
5. On `completed`, `output_ref` is the approved `user_approved_research_bundle@1`.

Do not use `research_run_codex`, `research_run_stub`, A10 review tools or the retired source
selection / A02-A06 path.
