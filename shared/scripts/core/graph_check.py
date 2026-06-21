"""Graph coherence checker — each graph manifest is the SINGLE SOURCE OF TRUTH.

For every ``shared/graphs/*.graph.json`` it verifies that nodes mapping to a shipped component
actually EXIST on disk (an agent file / a skill dir), and that ``kind: "subgraph"`` nodes
reference an existing manifest. A graph declaring a universal reviewer must reference one
physical agent when the host ships agents, valid review contracts and a review profile on every
producer agent node. Codex bundles intentionally omit Claude agent files, so their graph check
keeps the semantic and contract checks while skipping agent-file presence checks.
Components are discovered from the filesystem
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

from . import contracts

ROOT = Path(__file__).resolve().parents[3]
GRAPHS_DIR = ROOT / "shared" / "graphs"

# Node kinds that are NOT separately shipped components:
#   script / gate / user-gate are control steps inside the orchestrator;
#   subgraph delegates to another manifest (checked for existence, not for a component file).
_NON_REGISTERED_KINDS = {"script", "gate", "user-gate", "subgraph"}
_SUPPORTED_HOSTS = {"source", "claude", "codex"}


def resolve_host(plugin_root: Path | None = None, host: str | None = None) -> str:
    """Resolve source/Claude/Codex validation policy from an explicit value or host marker."""
    root = Path(plugin_root or ROOT)
    if host is not None:
        resolved = host.strip().lower()
        if resolved not in _SUPPORTED_HOSTS:
            allowed = ", ".join(sorted(_SUPPORTED_HOSTS))
            raise ValueError(f"unsupported graph-check host {host!r}; expected one of: {allowed}")
        return resolved

    markers = {
        "claude": root / ".claude-plugin" / "plugin.json",
        "codex": root / ".codex-plugin" / "plugin.json",
    }
    detected = [name for name, marker in markers.items() if marker.is_file()]
    if len(detected) > 1:
        raise ValueError(f"ambiguous plugin host markers under {root}: {', '.join(detected)}")
    return detected[0] if detected else "source"


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


def _load_contract_from_root(ref: str, root: Path) -> dict:
    name, major = contracts.parse_ref(ref)
    path = root / "shared" / "contracts" / f"{name}.schema.json"
    if not path.is_file():
        raise KeyError(f"unknown contract type {name!r} (no {path.name})")
    schema = json.loads(path.read_text(encoding="utf-8"))
    registered = int(schema.get("x-major", 1))
    if major is not None and major != registered:
        raise ValueError(f"contract {name!r} is major {registered}, requested @{major}")
    return schema


def check_manifest(manifest_path, plugin_root: Path | None = None,
                   graphs_dir: Path | None = None, host: str | None = None) -> dict:
    """Validate one manifest against the components present on disk + sibling manifests."""
    manifest_path = Path(manifest_path)
    gdir = graphs_dir or manifest_path.parent or GRAPHS_DIR
    manifest = json.loads(manifest_path.read_text())
    root = plugin_root or ROOT
    resolved_host = resolve_host(root, host)
    require_agent_files = resolved_host != "codex"
    registered = registered_component_names(root)
    errors: list[str] = []
    for field in ("input_contract", "exit_artifact"):
        if field not in manifest:
            continue
        ref = manifest.get(field)
        if not isinstance(ref, str) or not ref:
            errors.append(f"{manifest_path.name}: graph has invalid {field!r}")
            continue
        try:
            _load_contract_from_root(ref, root)
        except (KeyError, ValueError) as exc:
            errors.append(f"{manifest_path.name}: invalid {field} {ref!r}: {exc}")
    reviewer = manifest.get("reviewer")
    if reviewer:
        reviewer_path = root / "agents" / f"{reviewer}.md"
        if require_agent_files and not reviewer_path.is_file():
            errors.append(
                f"{manifest_path.name}: reviewer {reviewer!r} has no physical agent file"
            )
        for field in ("review_task_contract", "review_decision_contract"):
            ref = manifest.get(field)
            if not isinstance(ref, str) or not ref:
                errors.append(f"{manifest_path.name}: reviewer graph is missing {field!r}")
                continue
            try:
                _load_contract_from_root(ref, root)
            except (KeyError, ValueError) as exc:
                errors.append(f"{manifest_path.name}: invalid {field} {ref!r}: {exc}")
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
        require_component = kind == "skill" or (kind == "agent" and require_agent_files)
        if require_component and name not in registered:
            errors.append(f"{manifest_path.name}: node {name!r} (kind={kind}) has no component "
                          f"file on disk")
        if reviewer and kind == "agent":
            profile = node.get("review_profile")
            if not isinstance(profile, str) or not profile.strip():
                errors.append(
                    f"{manifest_path.name}: agent node {name!r} has no review_profile"
                )
        for field in ("input_contract", "output_contract"):
            if field not in node:
                continue
            ref = node.get(field)
            if not isinstance(ref, str) or not ref:
                errors.append(
                    f"{manifest_path.name}: node {name!r} has invalid {field} {ref!r}"
                )
                continue
            try:
                _load_contract_from_root(ref, root)
            except (KeyError, ValueError) as exc:
                errors.append(
                    f"{manifest_path.name}: node {name!r} has invalid {field} {ref!r}: {exc}"
                )
        for ref in node.get("produces", []):
            if not isinstance(ref, str) or "@" not in ref:
                continue
            try:
                _load_contract_from_root(ref, root)
            except (KeyError, ValueError) as exc:
                errors.append(
                    f"{manifest_path.name}: node {name!r} produces invalid contract {ref!r}: {exc}"
                )
    return {
        "ok": not errors,
        "graph": manifest.get("graph_id", manifest_path.stem),
        "host": resolved_host,
        "errors": errors,
    }


def check_all(graphs_dir: Path | None = None, plugin_root: Path | None = None,
              host: str | None = None) -> dict:
    """Check every manifest. No manifests -> ok (scaffold stage)."""
    gdir = graphs_dir or GRAPHS_DIR
    resolved_host = resolve_host(plugin_root, host)
    manifests = sorted(gdir.glob("*.graph.json")) if gdir.exists() else []
    results = [
        check_manifest(m, plugin_root, graphs_dir=gdir, host=resolved_host)
        for m in manifests
    ]
    return {
        "ok": all(r["ok"] for r in results),
        "host": resolved_host,
        "checked": len(results),
        "results": results,
    }
