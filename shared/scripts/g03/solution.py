"""g03 producer write path — persist the Solution Graph deliverable server-side.

The Solution Architect runs as a hosted (possibly sandboxed) worker, so it never writes the
artifact itself: it calls this finalize op, which validates the ``solution_blueprint@1`` and stores
it through the shared ``core.finalize`` write path, returning only the ref in an ``envelope@1``.
Pure stdlib.
"""
from __future__ import annotations

import sys as _sys
import pathlib as _pl

_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))  # -> shared/scripts

from core import finalize  # noqa: E402


def finalize_blueprint(task_id: str, blueprint: dict, *, base=None) -> dict:
    """G03-A01 write path: persist a validated solution_blueprint@1; return envelope@1."""
    return finalize.artifact_envelope(task_id, blueprint, contract="solution_blueprint@1",
                                      type_name="solution_blueprint", subdir="blueprint",
                                      namespace="g03", base=base, unknown_task="SOLUTION_UNKNOWN")
