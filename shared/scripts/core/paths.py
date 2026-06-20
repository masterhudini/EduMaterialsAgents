"""Project-local runtime locations (state drafts, logs, hydrated artifacts) for any graph.

State, logs and artifacts live INSIDE the project under ``.emagents/``, not /tmp, so a run is
inspectable where the work happens, survives across shells, and ships with the repo's
.gitignore rather than scattering temp files. Override the base with ``EMAGENTS_HOME``
(tests/CI). Pure stdlib.

  .emagents/
    drafts/      <graph>.state.json files (resumable graph state)
    logs/        run-<graph>-<run_id>.log files (diagnostic trail)
    artifacts/   files addressed by artifact:// refs (lazy hydration)
"""
from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    """Repo root = four levels up (shared/scripts/core/paths.py -> root)."""
    return Path(__file__).resolve().parents[3]


def runtime_home() -> Path:
    """Base dir for runtime artifacts. EMAGENTS_HOME overrides (tests/CI)."""
    env = os.environ.get("EMAGENTS_HOME")
    return Path(env) if env else project_root() / ".emagents"


def _ensure(d: Path) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    return d


def drafts_dir() -> Path:
    return _ensure(runtime_home() / "drafts")


def logs_dir() -> Path:
    return _ensure(runtime_home() / "logs")


def artifacts_dir() -> Path:
    return _ensure(runtime_home() / "artifacts")
