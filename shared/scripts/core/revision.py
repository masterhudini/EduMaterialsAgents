"""Revision-policy engine: decide REVISE / APPROVED / ESCALATE for a reviewer node.

Graph-agnostic: knows nothing about which node it serves. A ``revision_policy`` is
``{retry_scope, max_revision_attempts: {low, medium, high, critical}, escalation_after_exhaustion}``.
The orchestrator tracks attempts per scope (``AttemptCounter`` helper) and asks ``decide`` for
the next action given the reviewer's verdict and the issue severity. Pure stdlib.
"""
from __future__ import annotations

SEVERITIES = ["low", "medium", "high", "critical"]


def max_attempts(policy: dict, severity: str) -> int:
    return int(policy.get("max_revision_attempts", {}).get(severity, 0))


def decide(policy: dict, severity: str, *, approved: bool, attempts_used: int) -> dict:
    """Next action for a reviewer verdict.

    - approved -> APPROVED.
    - rejected and budget remains -> REVISE (with the next attempt number).
    - rejected and budget exhausted -> ESCALATE to ``escalation_after_exhaustion``.
    """
    if severity not in SEVERITIES:
        raise ValueError(f"severity must be one of {SEVERITIES}, got {severity!r}")
    if approved:
        return {"action": "APPROVED"}
    if attempts_used < max_attempts(policy, severity):
        return {"action": "REVISE", "attempt": attempts_used + 1}
    return {"action": "ESCALATE", "to": policy.get("escalation_after_exhaustion")}


class AttemptCounter:
    """Per-scope revision attempt counter (lives in the orchestrator for one run)."""

    def __init__(self, counts: dict[str, int] | None = None):
        self.counts: dict[str, int] = dict(counts or {})

    def used(self, scope: str) -> int:
        return self.counts.get(scope, 0)

    def bump(self, scope: str) -> int:
        self.counts[scope] = self.counts.get(scope, 0) + 1
        return self.counts[scope]

    def as_dict(self) -> dict[str, int]:
        return dict(self.counts)
