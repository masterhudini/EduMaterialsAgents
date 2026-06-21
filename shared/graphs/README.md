# shared/graphs — graph manifests (SINGLE SOURCE OF TRUTH)

One `*.graph.json` per graph. The manifest is the authority for the node sequence; the flow
code (`shared/scripts/<graph>/*_flow.py`), the orchestrator skill prompt, and `plugin.json`
registration must all agree with it. `core/graph_check.py` enforces no drift.

## Manifest shape

```jsonc
{
  "graph_id": "g02",
  "orchestrator": "<skill name that hosts the run>",
  "reviewer": "g02-a10-output-reviewer",
  "review_task_contract": "review_task@1",
  "review_decision_contract": "review_decision@1",
  "entry_node": "g02-a01-planner",
  "exit_artifact": "user_approved_research_bundle@1",
  "nodes": [
    { "name": "...", "kind": "agent", "review_profile": "...",
      "produces": ["..."] },
    { "name": "...", "kind": "user-gate" }
  ],
  "edges": [ { "from": "...", "to": "...", "condition": "APPROVED|REVISE|always|..." } ],
  "sequence": ["..."]
}
```

## Research Graph status

`g02.graph.json` istnieje. Zawiera dziewięciu producentów, dwa human gates, jednego
fizycznego `g02-a10-output-reviewer` oraz profile logicznych etapów review. Obowiązująca
kolejność to planner, domain, równoległe canonical i recent, candidate index, source-selection
gate, retrieval, paper review, claim verification, synthesis i final research gate.

Reviewer nie jest kopiowany jako osobny fizyczny node dla każdego producenta. Orkiestrator
tworzy `review_task@1` na podstawie `review_profile`, uruchamia wspólnego reviewera i konsumuje
`review_decision@1`. Pełne edges, fan-out i fan-in oraz revision policies zostaną zamrożone przy
finalizacji orkiestratora.

`core/graph_check.py` kontroluje oba kontrakty oraz obecność `review_profile` na każdym producer
node. W source i bundlu Claude wymaga także fizycznego pliku reviewera i wszystkich agentów.
W bundlu Codex pomija wyłącznie obecność plików agentów, ponieważ `includeAgents: false` jest
zamierzoną polityką hosta; pozostałe kontrole pozostają aktywne.

Przyszłe grafy wskazane przez projekt: `g01.graph.json` dla Intake Graph i `g03.graph.json` dla
Solution Graph.
