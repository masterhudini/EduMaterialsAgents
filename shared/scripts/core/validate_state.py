"""Deterministic state validation primitives — graph-agnostic.

Three validation duties exist in the system; two are deterministic scripts (here), the third
is an agent:

  - validate_field_type   : LOCAL — is one value the right Python shape? (zero judgement)
  - validate_state        : GLOBAL — completeness (required facts present + confirmed) and any
                            graph-supplied structural checks. Emits ``state_validation@1``.
  - validate_field_sense  : "does the value answer the question?" — an AGENT, not here.

The graph passes its OWN field requirements in: ``required`` field names, an optional
``route_back`` map (field -> owning node, for repair routing), and optional ``extra_checks``
(callables returning issue dicts). This module hardcodes no field set. Pure stdlib.
"""
from __future__ import annotations

from typing import Callable

from . import state as st


def validate_field_type(field: str, value, expected) -> dict:
    """LOCAL: is ``value`` an instance of ``expected`` (a type or tuple of types)?"""
    if not isinstance(value, expected):
        exp = getattr(expected, "__name__", str(expected))
        return {"ok": False, "errors": [f"{field}: expected {exp}, got {type(value).__name__}"]}
    return {"ok": True, "errors": []}


def _issue(field, problem, detail, route_back):
    owner = (route_back or {}).get(field.split(".")[0], "USER")
    return {"field": field, "problem": problem, "detail": detail, "route_back_to": owner}


def validate_state(
    state: dict,
    required: list[str],
    *,
    route_back: dict[str, str] | None = None,
    extra_checks: list[Callable[[dict], list[dict]]] | None = None,
) -> dict:
    """GLOBAL: required facts present + confirmed, plus any graph-supplied checks.

    Returns a ``state_validation@1`` dict ``{ok, issues[]}`` where each issue carries
    ``route_back_to`` so the orchestrator can route a repair to the owning node.
    """
    issues: list[dict] = []

    for field in required:
        status = st.get_status(state, field)
        value = st.get_value(state, field)
        if value is None and status == "empty":
            issues.append(_issue(field, "missing", "required field not filled", route_back))
        elif status != "confirmed":
            issues.append(_issue(field, "not_confirmed",
                                 f"status is {status!r}, must be confirmed", route_back))

    for check in extra_checks or []:
        issues.extend(check(state) or [])

    return {"ok": not issues, "issues": issues}
