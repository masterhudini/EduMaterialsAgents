# shared/graphs — graph manifests (SINGLE SOURCE OF TRUTH)

One `*.graph.json` per graph. The manifest is the authority for the node sequence; the flow
code (`shared/scripts/<graph>/*_flow.py`), the orchestrator skill prompt, and `plugin.json`
registration must all agree with it. `core/graph_check.py` enforces no drift.

## Manifest shape (see inspiration/shared/graphs/intake.graph.json)

```jsonc
{
  "graph_id": "research",
  "orchestrator": "<skill name that hosts the run>",
  "entry_node": "research-planner",
  "exit_artifact": "user_approved_research_bundle@1",
  "nodes": [
    { "name": "...", "kind": "agent|skill|reviewer|gate|script",
      "produces": ["..."], "condition": "...", "revision_policy": { } }
  ],
  "edges": [ { "from": "...", "to": "...", "condition": "APPROVED|REVISE|always|..." } ],
  "sequence": ["..."]
}
```

## To create

- `research.graph.json` — the Research Graph from `docs/research graph project.md` §8.4:
  planner + plan reviewer → parallel research (domain / claim-verification / recent /
  canonical) each with its reviewer → source selection → retrieval → paper review →
  synthesis → **User Research Gate** → `UserApprovedResearchBundle`. Encode reviewer loops
  via `revision_policy` and APPROVED/REVISE/BLOCKED edges, and the parallel block via
  fan-out/fan-in edges.

Future graphs (referenced by the design): `intake.graph.json`, `solution.graph.json`.
