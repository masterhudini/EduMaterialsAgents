"""Persisted graph state: a resumable JSON file the nodes fill field-by-field.

Stateless host (Claude Code / Codex) -> state lives in a file. Domain-agnostic: this module
imposes NO field set. A FACT is any field written via ``set_field``, stored as
``{"value": ..., "status": ...}`` with status in {empty, inferred, confirmed}. META keys
(schema_version, graph_id, phase, resume_token, clarify_rounds, run_status) carry no status —
they are infrastructure, not facts. The graph decides which facts it needs; this module only
stores, transitions and freezes them. Pure stdlib.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from . import paths

STATE_SCHEMA = "graph_state@1"

PHASES = ["empty", "collecting", "checked", "gated", "frozen"]
_ALLOWED_TRANSITIONS = {
    "empty": {"collecting"},
    "collecting": {"checked", "collecting"},   # self-loop = re-collect after route-back
    "checked": {"gated", "collecting"},         # back to collecting on validation fail
    "gated": {"frozen", "collecting"},
    "frozen": set(),
}

FIELD_STATUSES = ["empty", "inferred", "confirmed"]

_META_KEYS = {"schema_version", "graph_id", "phase", "resume_token",
              "clarify_rounds", "run_status"}


def new_state(graph_id: str, *, phase: str = "collecting") -> dict:
    """Initialise a fresh state for ``graph_id``."""
    if phase not in PHASES:
        raise ValueError(f"unknown phase {phase!r}")
    return {
        "schema_version": STATE_SCHEMA,
        "graph_id": graph_id,
        "phase": phase,
        "resume_token": str(uuid.uuid4()),
        "clarify_rounds": {},
        "run_status": "active",
    }


def is_fact(value) -> bool:
    return isinstance(value, dict) and "value" in value and "status" in value


def fact_fields(state: dict) -> list[str]:
    """Field names the state currently tracks as facts (wrapped {value,status})."""
    return [k for k, v in state.items() if k not in _META_KEYS and is_fact(v)]


def set_field(state: dict, field: str, value, status: str = "confirmed") -> dict:
    """Set a fact field's value and status. Mutates and returns the state."""
    if field in _META_KEYS:
        raise KeyError(f"{field!r} is a meta key, not a fact field")
    if status not in FIELD_STATUSES:
        raise ValueError(f"status must be one of {FIELD_STATUSES}, got {status!r}")
    state[field] = {"value": value, "status": status}
    return state


def get_value(state: dict, field: str):
    return (state.get(field) or {}).get("value") if is_fact(state.get(field)) else None


def get_status(state: dict, field: str) -> str:
    v = state.get(field)
    return v.get("status", "empty") if is_fact(v) else "empty"


def get_phase(state: dict) -> str:
    return state.get("phase", "empty")


def set_phase(state: dict, phase: str) -> dict:
    """Transition phase, asserting the move is allowed."""
    if phase not in PHASES:
        raise ValueError(f"unknown phase {phase!r}")
    current = get_phase(state)
    if phase != current and phase not in _ALLOWED_TRANSITIONS.get(current, set()):
        raise ValueError(f"illegal phase transition {current!r} -> {phase!r}")
    state["phase"] = phase
    return state


def bump_clarify(state: dict, node: str) -> int:
    """Increment and return the clarify-round counter for a node (guard <=3)."""
    state.setdefault("clarify_rounds", {})
    state["clarify_rounds"][node] = state["clarify_rounds"].get(node, 0) + 1
    return state["clarify_rounds"][node]


def is_resumable(state: dict) -> bool:
    return state.get("run_status") == "active" and get_phase(state) != "frozen"


# ---- persistence ----------------------------------------------------------

def state_path(graph_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in graph_id)
    return paths.drafts_dir() / f"{safe}.state.json"


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path: str | Path, state: dict) -> None:
    Path(path).write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def resume(path: str | Path) -> dict:
    """Load a state for resumption. Raises if not resumable."""
    state = load(path)
    if not is_resumable(state):
        raise ValueError(
            f"state not resumable (run_status={state.get('run_status')}, phase={get_phase(state)})")
    return state


def freeze(state: dict, *, drop: set[str] | tuple[str, ...] = ()) -> dict:
    """Unwrap fact values into a clean product spec. Drops META keys and any field in ``drop``.

    The result carries no infrastructure traces ({value,status}, phase, tokens) — it is what
    a downstream graph or the product consumes. ``None`` values are omitted.
    """
    drop = set(drop)
    spec: dict = {}
    for field in fact_fields(state):
        if field in drop:
            continue
        value = get_value(state, field)
        if value is not None:
            spec[field] = value
    return spec
