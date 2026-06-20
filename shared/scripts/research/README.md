# shared/scripts/research — Research Graph deterministic shapes (TO IMPLEMENT)

Graph-specific, **pure stdlib** helpers for the Research Graph. The reviewed reasoning lives
in the agents (`agents/research/`); this package holds only the deterministic shape checks and
flow wiring that agents call inline and tests exercise without an LLM.

Source of truth for the graph: `shared/graphs/research.graph.json`.
Design reference: `docs/research graph project.md` (§8 Research Graph, §9 User Research Gate).

## Likely modules

| Module | Responsibility |
|---|---|
| `research_flow.py` | Deterministic orchestration of the node sequence (planner → parallel work → selection → retrieval → review → synthesis → user gate) + event-log calls. Must agree with the manifest. |
| `*_shape.py` | Structural validators per produced artifact (e.g. `research_plan_shape`, `candidate_sources_shape`, `claim_verification_shape`, `selected_sources_shape`, `paper_review_shape`). Called by the owning agent before it returns. |
| `revision.py` (or in core) | Apply `revision_policy` counters and decide REVISE / APPROVED / ESCALATE for a reviewer node. |

Each agent's prompt calls its shape check inline, e.g.:

```bash
python3 -c "import sys; sys.path.insert(0,'$CLAUDE_PLUGIN_ROOT/shared/scripts'); \
  from research.research_plan_shape import check_plan; import json,sys; \
  print(check_plan(json.load(sys.stdin)))" <<< '<plan-json>'
```
