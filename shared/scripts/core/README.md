# shared/scripts/core — reusable runtime engine

Domain-agnostic, **pure stdlib**, offline, deterministic. No graph here knows about lectures,
claims or research — this is the machinery every graph reuses. Mirrors the meta-factory
reference (`inspiration/shared/scripts/`). **Implemented** (no nodes/edges/agents yet — those
are graph config the engine consumes).

## Modules

| Module | Responsibility |
|---|---|
| `contracts.py` | Contract registry + minimal JSON-Schema validator (subset: type/required/properties/items/enum). Versioned refs `type@major`. `validate(payload, ref)`, `validate_envelope(payload)`. |
| `paths.py` | Project-local runtime dirs under `.emagents/` (`drafts/`, `logs/`, `artifacts/`). Override with `EMAGENTS_HOME`. |
| `state.py` | Persisted graph state. Facts wrapped `{value, status}` (empty/inferred/confirmed); meta keys separate. Phases with guarded transitions, `resume_token`, clarify counters, `freeze()`. No hardcoded field set — facts are detected structurally. |
| `validate_state.py` | `validate_field_type` (local), `validate_state(required, route_back, extra_checks)` (global) → `state_validation@1`. The graph supplies its own required-field set. |
| `gate.py` | GATE + FREEZE — the single bottleneck. Takes a `validator`, verifies upstream verdicts, freezes the clean spec. |
| `revision.py` | Revision-policy engine: `decide()` → APPROVED / REVISE / ESCALATE, `AttemptCounter` per scope. |
| `artifacts.py` | Constrained `artifact://path#/pointer` resolver + lazy hydration, **and** atomic write side (`store()`, `ref_for()`) — the central artifact store. |
| `handoff.py` | The **subgraph seam**: `emit_handoff` (freeze → validate against contract → store → typed descriptor) / `load_handoff` (hydrate + re-validate). Only this crosses a subgraph boundary. |
| `graphs.py` | Manifest loader + pipeline helpers (load by id, list graphs, read `subgraph` nodes / entry / exit). |
| `event_log.py` | Append-only per-run diagnostic trail (`{ts, run_id, node, action, status, detail}`). Never feeds the product. |
| `graph_check.py` | Asserts each manifest's shipped agent/skill nodes have a component file on disk (filesystem auto-discovery, not `plugin.json` arrays), and that `kind: "subgraph"` nodes reference existing manifests. Host policy is detected from plugin metadata: source/Claude require agent files, while Codex skips only agent-file presence because its bundle intentionally excludes Claude agents. |
| `locators.py` | Address skills/agents by name, not path. |

### Multi-graph composition (3 subgraphs + parent)

The build is `g01` (intake) → `g02` (research) → `g03` (solution) subgraphs, sequenced by a thin `system` parent
graph with user gates between them. The engine supports this without per-graph special-casing:

- each subgraph has its own manifest, state file, contracts and scripts package, and is
  independently runnable/testable;
- a subgraph ends with `gate.pass_gate_and_freeze` → `handoff.emit_handoff` → typed bundle in
  the store; the next subgraph's input contract is that bundle (re-validated on load);
- the `system` parent is modelled with the same `state`/`gate` primitives — facts are the three
  bundle refs, the final freeze is the `FinalLecturePackage`;
- **never pass full upstream state across a boundary** — only the bundle + `artifact://` refs.

Tested in `tests/test_core_runtime.py` (stdlib-only; redirects `EMAGENTS_HOME` to a tmp dir).

## Still graph-specific (NOT in core — live in `shared/scripts/<graph>/` when built)

- the **node sequence / flow** and reviewer wiring (from each graph manifest),
- per-artifact **shape checks**,
- the **required-field set + route_back map** each graph feeds to `validate_state`/`gate`,
- **complexity_class → model/budget** mapping (a per-graph table),
- parallel fan-out/fan-in and user-gate orchestration (sequencing lives in the orchestrator
  skill; the engine provides the primitives above).

## Constraint

`import` only the standard library. Anything needing a third-party package (network retrieval,
PDF parsing, embeddings) belongs in an **isolated agent with its own tool**, never in this
deterministic core. This is what keeps the plugin installable without a venv.
