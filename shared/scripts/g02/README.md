# shared/scripts/g02 — Research Graph deterministic operations

Graph-specific, **pure stdlib** helpers for the Research Graph. The reviewed reasoning lives
in `agents/`; this package holds deterministic validation, artifact and flow operations.

Source of truth for the graph: `shared/graphs/g02.graph.json`.
Authoritative design references: `docs/02_Architektura_agentow_i_skilli.md` and
`docs/03_Kontrakty_i_artefakty.md`.

## Implemented and planned modules

| Module | Responsibility |
|---|---|
| `g02_flow.py` | Deterministic orchestration of the node sequence (planner → parallel work → selection → retrieval → review → synthesis → user gate) + event-log calls. Must agree with the manifest. |
| `review.py` | Validate ReviewTask and ReviewDecision, constrain artifact access, map severity, persist review decisions and standardize reviewer envelopes. |
| `*_shape.py` | Planned structural validators per produced artifact. Called by the owning agent before it returns. |
| `revision.py` (or in core) | Apply `revision_policy` counters and decide REVISE / APPROVED / ESCALATE for a reviewer node. |

Planned producer shape checks follow the same pure-stdlib pattern as `review.py` and are added
with the producer that first requires them.
