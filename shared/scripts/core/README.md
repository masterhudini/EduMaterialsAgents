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
| `artifacts.py` | `artifact://path#/pointer` resolver + lazy hydration (JSON-pointer slice) against the artifacts dir. |
| `event_log.py` | Append-only per-run diagnostic trail (`{ts, run_id, node, action, status, detail}`). Never feeds the product. |
| `graph_check.py` | Asserts each graph manifest ≡ `plugin.json` registration. Tolerant of the no-manifest scaffold stage. |
| `locators.py` | Address skills/agents by name, not path. |

Tested in `tests/test_core_runtime.py` (stdlib-only; redirects `EMAGENTS_HOME` to a tmp dir).

## Still graph-specific (NOT in core — live in `shared/scripts/<graph>/` when built)

- the **node sequence / flow** and reviewer wiring (from each graph manifest),
- per-artifact **shape checks**,
- the **required-field set + route_back map** each graph feeds to `validate_state`/`gate`,
- **complexity_class → model/budget** mapping (a per-graph table),
- parallel fan-out/fan-in and human-gate orchestration (sequencing lives in the orchestrator
  skill; the engine provides the primitives above).

## Constraint

`import` only the standard library. Anything needing a third-party package (network retrieval,
PDF parsing, embeddings) belongs in an **isolated agent with its own tool**, never in this
deterministic core. This is what keeps the plugin installable without a venv.
