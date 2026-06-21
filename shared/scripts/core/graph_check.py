"""Graph coherence checker — each graph manifest is the SINGLE SOURCE OF TRUTH.

For every ``shared/graphs/*.graph.json`` it verifies that nodes mapping to a shipped component
actually EXIST on disk (an agent file / a skill dir), and that ``kind: "subgraph"`` nodes
reference an existing manifest. Components are discovered from the filesystem
(``agents/**/<name>.md``, ``skills/**/SKILL.md``) — the same auto-discovery Claude Code uses —
so the check does NOT depend on the plugin manifest listing them (manifests use auto-discovery
and carry no component arrays). Graph-agnostic, offline, deterministic, pure stdlib.

Run whenever the node set changes:
    python3 -c "import sys; sys.path.insert(0,'shared/scripts'); \
      from core.graph_check import check_all; import json; print(json.dumps(check_all(), indent=2))"
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GRAPHS_DIR = ROOT / "shared" / "graphs"

# Node kinds that are NOT separately shipped components:
#   script / gate / user-gate are control steps inside the orchestrator;
#   subgraph delegates to another manifest (checked for existence, not for a component file).
_NON_REGISTERED_KINDS = {"script", "gate", "user-gate", "subgraph"}


def registered_component_names(plugin_root: Path | None = None) -> set[str]:
    """Component names discovered on disk: agent file stems + skill dir names."""
    root = plugin_root or ROOT
    names: set[str] = set()
    agents = root / "agents"
    if agents.exists():
        for p in agents.rglob("*.md"):
            if p.name != "README.md":
                names.add(p.stem)
    skills = root / "skills"
    if skills.exists():
        for p in skills.rglob("SKILL.md"):
            names.add(p.parent.name)
    return names


def check_manifest(manifest_path, plugin_root: Path | None = None,
                   graphs_dir: Path | None = None) -> dict:
    """Validate one manifest against the components present on disk + sibling manifests."""
    manifest_path = Path(manifest_path)
    gdir = graphs_dir or manifest_path.parent or GRAPHS_DIR
    manifest = json.loads(manifest_path.read_text())
    registered = registered_component_names(plugin_root)
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
            errors.append(f"{manifest_path.name}: node {name!r} (kind={kind}) has no component "
                          f"file on disk")

    # Parity guard: the host orchestrator skill must stay manifest-driven (single source of
    # truth) rather than hardcoding a divergent sequence/policy. We require it to reference the
    # manifest file so a refactor that copies the flow into the prompt is caught here.
    orchestrator = manifest.get("orchestrator")
    if orchestrator:
        root = plugin_root or ROOT
        skill_md = root / "skills" / orchestrator / "SKILL.md"
        gid_file = f"{manifest.get('graph_id', manifest_path.stem)}.graph.json"
        if not skill_md.exists():
            errors.append(f"{manifest_path.name}: orchestrator skill {orchestrator!r} not found")
        elif gid_file not in skill_md.read_text(encoding="utf-8"):
            errors.append(f"{manifest_path.name}: orchestrator skill {orchestrator!r} must "
                          f"reference {gid_file} (manifest is the single source of truth)")

    return {"ok": not errors, "graph": manifest.get("graph_id", manifest_path.stem), "errors": errors}


def check_all(graphs_dir: Path | None = None, plugin_root: Path | None = None) -> dict:
    """Check every manifest. No manifests -> ok (scaffold stage)."""
    gdir = graphs_dir or GRAPHS_DIR
    manifests = sorted(gdir.glob("*.graph.json")) if gdir.exists() else []
    results = [check_manifest(m, plugin_root, graphs_dir=gdir) for m in manifests]
    return {"ok": all(r["ok"] for r in results), "checked": len(results), "results": results}
