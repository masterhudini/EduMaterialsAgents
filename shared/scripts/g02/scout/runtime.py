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
from g02 import credentials

SCOUT_RUNTIME_SUBDIR = Path("g02") / "scout"


class ConfigError(RuntimeError):
    """Raised when Scout is missing required EduMaterials runtime config."""


def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def runtime_root(base: str | Path | None = None) -> Path:
    """Return the Scout runtime root INSIDE the artifact store, so everything Scout writes (plan,
    per-topic PDFs, corpora, cross-topic index) lives in one place and is addressable as
    ``artifact://g02/scout/...``.

    When ``base`` is provided it is treated as the exact Scout workspace. Without it, the default is
    ``<artifact store>/g02/scout`` = ``<EMAGENTS_HOME or cwd/.emagents>/artifacts/g02/scout``.
    """
    if base is not None:
        return _ensure(Path(base).expanduser().resolve())
    return _ensure(paths.artifacts_dir().expanduser().resolve() / SCOUT_RUNTIME_SUBDIR)


def as_artifact_ref(path: str | Path, base: str | Path | None = None) -> str:
    """``artifact://`` ref for a Scout file (it now lives inside the artifact store). Used by the
    Scout->candidate_sources adapter and A06 to reference downloaded PDFs/corpora without copying."""
    from core import artifacts
    root = (Path(base) if base is not None else paths.artifacts_dir()).expanduser().resolve()
    rel = Path(path).expanduser().resolve().relative_to(root)
    return artifacts.ref_for(rel.as_posix())


def workspace_dir(base: str | Path | None = None) -> Path:
    """Workspace root passed to ScoutStore.

    ScoutStore still uses Radar's internal table names, but the physical files live inside the
    artifact store under ``<artifact store>/g02/scout`` (``artifact://g02/scout/...``).
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
    return (
        credentials.managed_value("EMAGENTS_RESEARCH_CONTACT_EMAIL")
        or credentials.managed_value("POLITE_POOL_EMAIL", default)
    )


def provider_keys() -> dict[str, str]:
    return {
        "openalex_api_key": credentials.managed_value("OPENALEX_API_KEY"),
        "s2_api_key": credentials.managed_value("SEMANTIC_SCHOLAR_API_KEY")
        or credentials.managed_value("S2_API_KEY"),
        "core_api_key": "",
    }


def openalex_api_key(explicit: str = "") -> str:
    """OpenAlex API token. Empty is allowed — we never hard-fail Scout on it; instead OpenAlex is
    simply left out of the source set (we query OpenAlex through its API with email + token, never
    keyless). The credential tier at the seam decides whether OpenAlex is used."""
    return (explicit or "").strip() or provider_keys()["openalex_api_key"]


# Backwards-compatible alias; no longer raises (absence is handled at the seam, see openalex_api_key).
require_openalex_api_key = openalex_api_key
