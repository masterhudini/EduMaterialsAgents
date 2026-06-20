"""Runtime locations (state drafts, logs, hydrated artifacts) for any graph.

These live in the USER'S PROJECT — the current working directory where the plugin is invoked —
under ``.emagents/``, so drafts/logs/artifacts (the lecture, states, bundles) sit with the
user's work and survive across shells. They deliberately do NOT live next to the plugin code:
once installed, the code is read-only under ``$CLAUDE_PLUGIN_ROOT`` (e.g. the plugin cache),
which is the wrong place for per-project data. ``$CLAUDE_PLUGIN_ROOT`` is for finding code;
the cwd is for the project's data. Override the base with ``EMAGENTS_HOME`` (tests/CI).
Pure stdlib.

  <project>/.emagents/
    drafts/      <graph>.state.json files (resumable graph state)
    logs/        run-<graph>-<run_id>.log files (diagnostic trail)
    artifacts/   files addressed by artifact:// refs (lazy hydration)
"""
from __future__ import annotations

import os
from pathlib import Path


def runtime_home() -> Path:
    """Base dir for runtime artifacts, anchored to the current project (cwd) — never the
    plugin's install location. ``EMAGENTS_HOME`` overrides (tests/CI)."""
    env = os.environ.get("EMAGENTS_HOME")
    return Path(env) if env else Path.cwd() / ".emagents"


def _ensure(d: Path) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    return d


def drafts_dir() -> Path:
    return _ensure(runtime_home() / "drafts")


def logs_dir() -> Path:
    return _ensure(runtime_home() / "logs")


def artifacts_dir() -> Path:
    return _ensure(runtime_home() / "artifacts")
