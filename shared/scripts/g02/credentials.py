"""Ephemeral session credentials for g02 providers (contact email + optional premium key).

The MCP server reads provider env at startup, so when the host supplies the email mid-session we
bridge it through a tiny file — ``<home>/g02/credentials.json`` — overlay it onto ``os.environ`` in
the running process, and DELETE the file as soon as a real provider query succeeds. After that the
credentials live only in the process's memory (and any Scout child it forks), never lingering on
disk. Treated like a password: local/dev only, gitignored. Pure stdlib.

Scope: the contact email unlocks arXiv, Crossref and Unpaywall. OpenAlex is enabled only when the
user supplies both contact email and the free OpenAlex API token collected through
``research_provider_setup``; without that pair OpenAlex is skipped.
"""
from __future__ import annotations

import json
import os
import sys
import pathlib as _pl

sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))  # -> shared/scripts

from core import paths  # noqa: E402

# accepted credential field -> environment variable it maps to
FIELDS = {
    "email": "EMAGENTS_RESEARCH_CONTACT_EMAIL",
    "openalex_key": "OPENALEX_API_KEY",
}
MARKER_ENV = "EMAGENTS_G02_PROVIDER_CREDENTIALS"
MARKER_VALUE = "provider_setup"
MANAGED_ENV_NAMES = {
    *FIELDS.values(),
    "POLITE_POOL_EMAIL",
    "SEMANTIC_SCHOLAR_API_KEY",
    "S2_API_KEY",
}

_purged = False


def _path() -> _pl.Path:
    return paths.runtime_home() / "g02" / "credentials.json"


def save(creds: dict) -> dict:
    """Persist the provided credentials (email and/or openalex_key) and overlay them now.

    Empty/whitespace values are ignored. Returns the field names that were stored."""
    env_map = {FIELDS[k]: str(v).strip() for k, v in (creds or {}).items()
               if k in FIELDS and str(v).strip()}
    global _purged
    if env_map:
        _purged = False                     # new creds -> arm purge again
        p = _path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(env_map, ensure_ascii=False) + "\n", encoding="utf-8")
        os.environ.update(env_map)          # take effect immediately in this process
        os.environ[MARKER_ENV] = MARKER_VALUE
    return {"stored": sorted(k for k in (creds or {}) if k in FIELDS and str(creds.get(k)).strip())}


def overlay() -> list[str]:
    """Overlay the on-disk credential file (if any) onto ``os.environ``; return the keys set.

    Called at provider_config load so a freshly started process still picks up creds the host left
    on disk before the first successful query purged them."""
    p = _path()
    if not p.exists():
        return []
    try:
        env_map = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    keys = []
    for env_name, value in (env_map or {}).items():
        if isinstance(value, str) and value.strip():
            os.environ[env_name] = value
            keys.append(env_name)
    if keys:
        os.environ[MARKER_ENV] = MARKER_VALUE
    return keys


def is_managed(env: dict | None = None) -> bool:
    """True when provider creds came through ``research_provider_setup``."""
    active = os.environ if env is None else env
    return active.get(MARKER_ENV) == MARKER_VALUE


def managed_environment(env: dict | None = None) -> dict:
    """Copy env and strip provider creds unless the setup marker is present.

    Raw shell credentials must not silently influence the active G02 run. The agent first asks the
    user and calls ``research_provider_setup``; after that the marker is inherited by Scout child
    processes as process transport only.
    """
    active = dict(os.environ if env is None else env)
    if is_managed(active):
        return active
    for name in MANAGED_ENV_NAMES:
        active.pop(name, None)
    return active


def managed_value(name: str, default: str = "", env: dict | None = None) -> str:
    active = os.environ if env is None else env
    if not is_managed(active):
        return default
    return str(active.get(name, "") or default).strip()


def purge() -> bool:
    """Delete the on-disk credential file. Creds already in os.environ stay for the session."""
    p = _path()
    existed = p.exists()
    p.unlink(missing_ok=True)
    return existed


def purge_once() -> bool:
    """Purge exactly once per armed credential set — call after the first successful DB query."""
    global _purged
    if _purged:
        return False
    _purged = True
    return purge()
