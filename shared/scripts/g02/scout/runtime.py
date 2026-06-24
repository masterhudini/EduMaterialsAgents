"""EduMaterials runtime helpers for the vendored Scout engine.

The Scout source files are intentionally kept close to the upstream Radar code.
This module is the local adapter for project runtime paths, environment values
and smoke-run defaults. It never reads legacy LLMWiki env files and never writes
secrets to the repository.
"""
from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

from core import paths

SCOUT_RUNTIME_SUBDIR = Path("g02") / "scout"


class ConfigError(RuntimeError):
    """Raised when Scout is missing required EduMaterials runtime config."""


def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def runtime_root(base: str | Path | None = None) -> Path:
    """Return the Scout runtime root under the EduMaterials project runtime.

    When ``base`` is provided it is treated as the exact Scout workspace. Without
    it, the default is ``<EMAGENTS_HOME or cwd/.emagents>/g02/scout``.
    """
    if base is not None:
        return _ensure(Path(base).expanduser().resolve())
    return _ensure(paths.runtime_home().expanduser().resolve() / SCOUT_RUNTIME_SUBDIR)


def workspace_dir(base: str | Path | None = None) -> Path:
    """Workspace root passed to ScoutStore.

    ScoutStore still uses Radar's internal table names, but the physical files
    live under ``.emagents/g02/scout`` or ``EMAGENTS_HOME/g02/scout``.
    """
    return runtime_root(base)


def runs_dir(base: str | Path | None = None) -> Path:
    return _ensure(runtime_root(base) / "runs")


def safe_segment(value: str) -> str:
    segment = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip())
    return segment.strip("._-") or "run"


def make_run_id(prefix: str = "SCOUT") -> str:
    prefix = safe_segment(prefix).upper()
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def run_dir(run_id: str, base: str | Path | None = None) -> Path:
    return _ensure(runs_dir(base) / safe_segment(run_id))


def pdf_dir(run_id: str, base: str | Path | None = None) -> Path:
    return _ensure(run_dir(run_id, base) / "pdf")


def env_str(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default or "").strip()


def env_float(name: str, default: float) -> float:
    raw = env_str(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def env_int(name: str, default: int) -> int:
    raw = env_str(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def env_bool(name: str, default: bool = False) -> bool:
    raw = env_str(name)
    if not raw:
        return default
    return raw.casefold() in {"1", "true", "yes", "on"}


def contact_email(default: str = "") -> str:
    return env_str("EMAGENTS_RESEARCH_CONTACT_EMAIL") or env_str("POLITE_POOL_EMAIL", default)


def provider_keys() -> dict[str, str]:
    return {
        "openalex_api_key": env_str("OPENALEX_API_KEY"),
        "s2_api_key": env_str("SEMANTIC_SCHOLAR_API_KEY") or env_str("S2_API_KEY"),
        "core_api_key": env_str("CORE_API_KEY"),
    }


def require_openalex_api_key(explicit: str = "") -> str:
    key = (explicit or "").strip() or provider_keys()["openalex_api_key"]
    if not key:
        raise ConfigError(
            "OPENALEX_API_KEY is required for Scout in EduMaterials; "
            "email is only used as polite-pool mailto."
        )
    return key
