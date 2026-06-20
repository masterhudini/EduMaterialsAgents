"""artifact:// reference resolver + lazy hydration.

Graphs pass cards and REFERENCES between nodes, not whole states — a node hydrates only the
slice it needs. A ref is ``artifact://<relpath>[#<json-pointer>]`` where ``<relpath>`` resolves
under the runtime artifacts dir and the optional RFC-6901 JSON pointer selects a sub-slice.

  artifact://states/claim_state.approved.json
  artifact://states/claim_state.approved.json#/claims/CLM_001

Pure stdlib.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import paths

SCHEME = "artifact://"


def parse_ref(ref: str) -> tuple[str, str | None]:
    """Split a ref into ``(relpath, json_pointer_or_None)``."""
    if not ref.startswith(SCHEME):
        raise ValueError(f"not an artifact ref: {ref!r}")
    body = ref[len(SCHEME):]
    if "#" in body:
        relpath, pointer = body.split("#", 1)
        return relpath, pointer or None
    return body, None


def resolve_path(ref: str, base: str | Path | None = None) -> Path:
    """Absolute filesystem path for a ref's file part (ignores the pointer)."""
    relpath, _ = parse_ref(ref)
    root = Path(base) if base is not None else paths.artifacts_dir()
    return (root / relpath).resolve()


def _unescape(token: str) -> str:
    # RFC 6901: ~1 -> '/', ~0 -> '~' (order matters).
    return token.replace("~1", "/").replace("~0", "~")


def _pointer_get(doc, pointer: str):
    if pointer in ("", "/"):
        return doc
    cur = doc
    for raw in pointer.lstrip("/").split("/"):
        token = _unescape(raw)
        if isinstance(cur, list):
            cur = cur[int(token)]
        elif isinstance(cur, dict):
            cur = cur[token]
        else:
            raise KeyError(f"pointer {pointer!r} does not resolve in document")
    return cur


def hydrate(ref: str, base: str | Path | None = None):
    """Load the referenced JSON file and apply the pointer (full document if no pointer)."""
    relpath, pointer = parse_ref(ref)
    path = resolve_path(ref, base)
    doc = json.loads(path.read_text(encoding="utf-8"))
    return _pointer_get(doc, pointer) if pointer else doc


# ---- write side (the store) ---------------------------------------------

def ref_for(relpath: str) -> str:
    """The artifact:// ref that addresses ``relpath`` in the store."""
    return f"{SCHEME}{relpath}"


def store(relpath: str, obj, *, base: str | Path | None = None) -> str:
    """Write ``obj`` as pretty JSON under ``relpath`` in the artifact store; return its ref.

    Parent dirs are created. ``base`` overrides the store root (default: the runtime artifacts
    dir), so a subgraph can persist a state/bundle and hand the returned ref downstream.
    """
    root = Path(base) if base is not None else paths.artifacts_dir()
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    return ref_for(relpath)
