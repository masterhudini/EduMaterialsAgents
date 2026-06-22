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
    { "name": "...", "kind": "agent", "input_contract": "...@1",
      "output_contract": "...@1", "review_profile": "...",
      "produces": ["..."] },
    { "name": "...", "kind": "user-gate" }
  ],
  "edges": [ { "from": "...", "to": "...", "condition": "APPROVED|REVISE|always|..." } ],
  "sequence": ["..."]
}
```

## Research Graph status

`g02.graph.json` istnieje. Zawiera dziesięciu producentów, dwa human gates, jednego
fizycznego `g02-a10-output-reviewer` oraz profile logicznych etapów review. Obowiązująca
kolejność to planner, domain, canonical, recent, market cases, candidate index, source-selection
gate, retrieval, evidence review, claim verification, synthesis i final research gate. Canonical,
recent i market cases są logicznym fan-outem projektu, ale bieżący `g02_flow.py` wykonuje manifest
sekwencyjnie. A11 jest pełnym pionowym wycinkiem: scoped input, Tavily, kontrolowany SearXNG,
review `market_cases` i ekstrakcja po bramce są gotowe. Następnym producerem do implementacji jest
agregujący A05.

Węzły G02-A01 do G02-A04 mają zamrożone kontrakty wejścia i wyjścia. G02-A01 używa
`research_planner_input@1` oraz `research_plan@1`, a G02-A02 używa
`domain_research_input@1` oraz `domain_candidate_sources@1`. G02-A03 i G02-A04 używają odpowiednio
`canonical_research_input@1` i `recent_research_input@1`, po czym zwracają rozłączne strumienie
`candidate_sources@1`. G02-A11 używa `market_case_research_input@1` i zwraca wariant
`market_cases` tego samego `candidate_sources@1`. Kontrakty kolejnych producer nodes są dodawane z
ich zestawami.

Reviewer nie jest kopiowany jako osobny fizyczny node dla każdego producenta. Orkiestrator
tworzy `review_task@1` na podstawie `review_profile`, uruchamia wspólnego reviewera i konsumuje
`review_decision@1`. Polityki rewizji są zamrożone w `retry_matrix`; jawne zależności, edges oraz
scheduler fan-out/fan-in pozostają do dodania przy rozszerzeniu orkiestratora.

`core/graph_check.py` kontroluje kontrakty graniczne grafu, oba kontrakty reviewera, zadeklarowane
kontrakty wejścia i wyjścia producentów oraz obecność `review_profile` na każdym producer node.
Source oraz bundle Claude i Codex wymagają fizycznego pliku reviewera i wszystkich agentów,
zgodnie z bieżącą polityką `includeAgents: true` obu hostów.

Przyszłe grafy wskazane przez projekt: `g01.graph.json` dla Intake Graph i `g03.graph.json` dla
Solution Graph.
