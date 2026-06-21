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
import os
import tempfile
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
    """Absolute path for a ref, constrained to the configured artifact root.

    Reject absolute paths, ``..`` traversal and symlink resolution that would leave the
    artifact store. Artifact references may come from scoped input bundles and are never
    trusted as filesystem paths.
    """
    relpath, _ = parse_ref(ref)
    root = (Path(base) if base is not None else paths.artifacts_dir()).resolve()
    resolved = (root / relpath).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"artifact ref escapes artifact root: {ref!r}") from exc
    return resolved


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
    """Atomically write ``obj`` under a constrained artifact-store path; return its ref.

    Parent dirs are created. ``base`` overrides the store root (default: the runtime artifacts
    dir), so a subgraph can persist a state/bundle and hand the returned ref downstream.
    """
    root = (Path(base) if base is not None else paths.artifacts_dir()).resolve()
    path = (root / relpath).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"artifact write escapes artifact root: {relpath!r}") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(obj, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return ref_for(relpath)
