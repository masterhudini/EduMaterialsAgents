"""GATE + FREEZE — the single bottleneck before a state becomes a frozen product spec.

Graph-agnostic: the GATE takes a ``validator`` (typically built on ``validate_state.validate_state``
with the graph's required-field set) and lets nothing incomplete, unconfirmed or flagged
through. It is deterministic — the judgement already happened upstream (sense checks in
collectors, coherence checks globally); here we only verify those verdicts and produce the
frozen spec. Pure stdlib.
"""
from __future__ import annotations

from typing import Callable

from . import state as st


def gate_status(state: dict, validator: Callable[[dict], dict]) -> dict:
    """Can this state freeze? Returns ``{ok, reasons[], state_validation}``."""
    sv = validator(state)
    reasons: list[str] = []
    if not sv.get("ok", False):
        for issue in sv.get("issues", []):
            reasons.append(
                f"{issue['field']}: {issue['problem']} (fix at {issue.get('route_back_to', 'USER')})")
    return {"ok": not reasons, "reasons": reasons, "state_validation": sv}


def pass_gate_and_freeze(state: dict, validator: Callable[[dict], dict],
                         *, drop: set[str] | tuple[str, ...] = ()) -> dict:
    """Run the GATE; on pass, advance phase and return the frozen spec.

    Raises ``ValueError`` with the blocking reasons if the GATE does not pass — the caller
    routes those back to the owning nodes, never forces a freeze.
    """
    status = gate_status(state, validator)
    if not status["ok"]:
        raise ValueError("GATE failed: " + "; ".join(status["reasons"]))
    st.set_phase(state, "checked")
    st.set_phase(state, "gated")
    spec = st.freeze(state, drop=drop)
    st.set_phase(state, "frozen")
    return spec
