"""Graph coherence checker — each graph manifest is the SINGLE SOURCE OF TRUTH.

For every ``shared/graphs/*.graph.json`` it verifies that the functional nodes (kinds that map
to a shipped component) are registered in ``plugin.json``, so the manifest and the registry
can never silently drift apart. Graph-agnostic and tolerant of the scaffold stage: with no
manifests yet it simply reports ok. Pure stdlib, offline, deterministic.

Run whenever the node set changes:
    python3 -c "import sys; sys.path.insert(0,'shared/scripts'); \
      from core.graph_check import check_all; import json; print(json.dumps(check_all(), indent=2))"
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GRAPHS_DIR = ROOT / "shared" / "graphs"
PLUGIN = ROOT / "plugin.json"

# Node kinds that are NOT separately registered components in plugin.json:
#   script / gate / user-gate are control steps inside the orchestrator;
#   subgraph delegates to another manifest (checked for existence, not registration).
_NON_REGISTERED_KINDS = {"script", "gate", "user-gate", "subgraph"}


def registered_component_names(plugin_path: Path | None = None) -> set[str]:
    pj = json.loads((plugin_path or PLUGIN).read_text())
    names: set[str] = set()
    for entry in pj.get("skills", []):
        names.add(Path(entry).name)          # skill dir name
    for entry in pj.get("agents", []):
        names.add(Path(entry).stem)          # agent file stem
    return names


def check_manifest(manifest_path: Path, plugin_path: Path | None = None,
                   graphs_dir: Path | None = None) -> dict:
    """Validate one manifest:

    - every ``agent``/``skill`` node is registered in plugin.json;
    - every ``subgraph`` node references an existing ``<graph>.graph.json`` manifest.
    """
    manifest_path = Path(manifest_path)
    gdir = graphs_dir or manifest_path.parent or GRAPHS_DIR
    manifest = json.loads(manifest_path.read_text())
    registered = registered_component_names(plugin_path)
    errors: list[str] = []
    for node in manifest.get("nodes", []):
        kind = node.get("kind")
        name = node.get("name", "<unnamed>")
        if kind == "subgraph":
            sub = node.get("graph") or name
            if not (gdir / f"{sub}.graph.json").exists():
                errors.append(f"{manifest_path.name}: subgraph node {name!r} references "
                              f"missing manifest {sub}.graph.json")
            continue
        if kind in _NON_REGISTERED_KINDS:
            continue
        if kind in ("agent", "skill") and name not in registered:
            errors.append(f"{manifest_path.name}: node {name!r} (kind={kind}) not registered in plugin.json")
    return {"ok": not errors, "graph": manifest.get("graph_id", manifest_path.stem), "errors": errors}


def check_all(graphs_dir: Path | None = None, plugin_path: Path | None = None) -> dict:
    """Check every manifest. No manifests yet -> ok (scaffold stage)."""
    gdir = graphs_dir or GRAPHS_DIR
    manifests = sorted(gdir.glob("*.graph.json")) if gdir.exists() else []
    results = [check_manifest(m, plugin_path, graphs_dir=gdir) for m in manifests]
    return {"ok": all(r["ok"] for r in results), "checked": len(results), "results": results}
