## Host Adapter: Codex

**Preferred when you are already in a Codex session — you ARE the worker (no nested `codex exec`).**
Drive the Research Graph host-driven through MCP, playing each producer and reviewer yourself:

1. `research_run_hosted({context, through?, topic_ids?})` over a `research_graph_input@1` path/ref.
1a. **Provider credentials (after the A01 planner, before discovery).** Call
   `research_provider_setup({})` to show the catalog, then ask the user for their data: present the
   `note` and `catalog`, collect a contact **email** (free, no account — unlocks OpenAlex polite
   pool, arXiv, Crossref and Unpaywall/OA) and **ENCOURAGE the optional OpenAlex token** using
   `openalex_token_hint` + the `token.signup` link (a FREE key — log in & generate; higher
   limits, worth it for bigger material). The user provides, then CONFIRMS; call `research_provider_setup({email,
   openalex_key?})` with what they gave. They may provide nothing (Semantic Scholar still works). The
   stored file is auto-deleted after the first successful provider query.
2. Loop on the response:
   - **`awaiting_node`**: hydrate `upstream` refs with `research_node_input` if needed, perform the
     producer node's task for `input`, then call the node's `finalize_op` named in the payload (e.g.
     `research_planner_finalize` / `research_domain_finalize` / … / `research_synthesis_finalize`).
     Resume with the RETURNED ENVELOPE: `research_resume({resume_token, node_results={node: <finalize
     envelope>}})` — g02 passes the whole finalize envelope, not just a ref. If you cannot produce the
     node, resume with `node_failures={node: {summary, issues}}`. **Tracing:** if your harness exposes
     the model tokens you spent, also pass `usage_reports={node: {input_tokens, output_tokens, model}}`
     (omit if unavailable — timings and decisions are still traced).
   - **`awaiting_review`**: review the `artifact_ref` against the `review_task` (acceptance criteria,
     prohibited behaviors). Call `research_review_finalize({task, decision})` to persist your
     `review_decision@1`, then resume with `research_resume({resume_token, review_results={node:
     <review finalize envelope>}})`. APPROVED advances; REVISE re-asks the producer (one correction);
     BLOCKED fails. Review honestly — it is a real quality gate, not a rubber stamp.
   - **`awaiting_user`**: present the human gate (the two-step source-selection gate, then the Human
     Research Gate — `research_summary@1` is in the payload, show that digest). Collect the required
     decisions and resume with `research_resume({resume_token, decisions={gate: …}})`. Never
     auto-approve a human gate.
   - **`research_run_report@1`** (status `completed`): done — `output_ref` is the approved
     `user_approved_research_bundle@1` handoff to g03. The report's `trace` carries per-agent/tool
     durations and the token roll-up; `research_trace({run_id: resume_token})` returns it any time.
3. Never write artifacts yourself; the `*_finalize` ops persist them server-side. Do not simulate
   physical node agents by copying their work into the orchestrator context.

**Fallback — nested workers (NOT inside a Codex session):** `research_run_codex({context, gates:
"pause"})` spawns isolated `codex exec` workers and cannot initialise under an outer read-only
sandbox. Use it only from a non-Codex shell or CI:

```bash
python3 "<plugin-root>/shared/scripts/g02/g02_flow.py" run-codex <context> --gates pause
```

`research_run_stub` is a no-LLM wiring smoke (auto-approves synthetic gates). If the `codex` CLI is
unavailable or the user is not logged in, validate the boundary input and report
`external_dependency_blocked`, naming the missing capability (codex CLI / login).

The deterministic seams remain MCP tools from the `edu-materials-research` server (call them as
tools, never shell out): `research_front_door {context}`, `research_node_input {ref, node}`,
`research_doi_verify[_batch]`, `research_finalize {bundle}`. The Codex plugin manifest does not
register plugin-local `commands/`; `/research` is Claude-only for now.
