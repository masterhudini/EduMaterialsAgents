"""Graph coherence checker — each graph manifest is the SINGLE SOURCE OF TRUTH.

For every ``shared/graphs/*.graph.json`` it verifies that nodes mapping to a shipped component
actually EXIST on disk (an agent file / a skill dir), and that ``kind: "subgraph"`` nodes
reference an existing manifest. A graph declaring a universal reviewer must reference one
physical agent, valid review contracts and a review profile on every producer agent node. Both
current host bundles ship the shared agent definitions, so source, Claude and Codex checks require
the same physical agent inventory.
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
_G02_RETIRED_OR_FLOW_COPY_TERMS = (
    "A01 prepare/finalize",
    "Scout fanout",
    "A07 task preparation",
    "A07 aggregation",
    "A09 task/finalize",
    "A09 research state materialization",
    "Human Research Gate and `research_bundle_finalize`",
    "domain/canonical/recent",
    "market-case discovery",
    "source-selection gate",
)


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


def _g02_research_mcp_tools(root: Path) -> tuple[set[str], str | None]:
    scripts = root / "shared" / "scripts"
    import sys
    inserted = False
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
        inserted = True
    try:
        from mcp import research_server  # noqa: WPS433
        dispatch = set(getattr(research_server, "DISPATCH", {}))
        listed = {tool.get("name") for tool in getattr(research_server, "TOOLS", [])
                  if isinstance(tool, dict)}
        active = set(getattr(research_server, "ACTIVE_TOOL_NAMES", set()))
        return {name for name in dispatch | listed | active if isinstance(name, str)}, None
    except Exception as exc:  # pragma: no cover - defensive diagnostic path
        return set(), f"could not import research MCP server: {type(exc).__name__}: {exc}"
    finally:
        if inserted:
            try:
                sys.path.remove(str(scripts))
            except ValueError:
                pass


def _check_g02_orchestrator_text(root: Path, orchestrator: str, manifest_path: Path,
                                 errors: list[str]) -> None:
    skill_dir = root / "skills" / orchestrator
    files = [skill_dir / "SKILL.md"]
    adapters = skill_dir / "adapters"
    if adapters.exists():
        files.extend(sorted(adapters.glob("*.md")))
    for path in files:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if "g02.graph.json" not in text and path.name == "SKILL.md":
            errors.append(
                f"{manifest_path.name}: orchestrator skill {orchestrator!r} must "
                "reference g02.graph.json (manifest is the single source of truth)"
            )
        for term in _G02_RETIRED_OR_FLOW_COPY_TERMS:
            if term in text:
                rel = path.relative_to(root)
                errors.append(
                    f"{manifest_path.name}: {rel} contains hardcoded/retired G02 flow term "
                    f"{term!r}; derive active sequence from g02.graph.json or the MCP prompt"
                )


def check_manifest(
    manifest_path,
    plugin_root: Path | None = None,
    graphs_dir: Path | None = None,
    host: str | None = None,
) -> dict:
    """Validate one manifest against the components present on disk + sibling manifests."""
    manifest_path = Path(manifest_path)
    gdir = graphs_dir or manifest_path.parent or GRAPHS_DIR
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = plugin_root or ROOT
    resolved_host = resolve_host(root, host)
    require_agent_files = True
    registered = registered_component_names(root)
    errors: list[str] = []
    graph_id = manifest.get("graph_id", manifest_path.stem)
    mcp_tool_names: set[str] = set()
    mcp_import_error: str | None = None
    if graph_id == "g02":
        mcp_tool_names, mcp_import_error = _g02_research_mcp_tools(root)
        if mcp_import_error:
            errors.append(f"{manifest_path.name}: {mcp_import_error}")
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
                errors.append(
                    f"{manifest_path.name}: subgraph node {name!r} references "
                    f"missing manifest {sub}.graph.json"
                )
            continue

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
        operations = node.get("operations")
        if graph_id == "g02" and operations is not None:
            if not isinstance(operations, dict):
                errors.append(f"{manifest_path.name}: node {name!r} has non-object operations")
            else:
                for op_name, tool_name in operations.items():
                    if not isinstance(tool_name, str) or not tool_name.strip():
                        errors.append(
                            f"{manifest_path.name}: node {name!r} operation {op_name!r} "
                            f"has invalid tool name {tool_name!r}"
                        )
                    elif mcp_tool_names and tool_name not in mcp_tool_names:
                        errors.append(
                            f"{manifest_path.name}: node {name!r} operation {op_name!r} "
                            f"references unknown research MCP tool {tool_name!r}"
                        )

        if kind in _NON_REGISTERED_KINDS:
            continue

        require_component = kind == "skill" or (kind == "agent" and require_agent_files)
        if require_component and name not in registered:
            errors.append(
                f"{manifest_path.name}: node {name!r} (kind={kind}) has no component "
                f"file on disk"
            )

        if reviewer and kind == "agent":
            profile = node.get("review_profile")
            if not isinstance(profile, str) or not profile.strip():
                errors.append(
                    f"{manifest_path.name}: agent node {name!r} has no review_profile"
                )

        # Host-driven (pause_on_node) graphs: a node played by the host must declare the finalize
        # MCP op it uses to persist its artifact; deterministic nodes run in-process instead.
        if kind == "agent" and node.get("execution") == "hosted":
            finalize_op = node.get("finalize_op")
            if not isinstance(finalize_op, str) or not finalize_op.strip():
                errors.append(
                    f"{manifest_path.name}: hosted agent node {name!r} has no finalize_op"
                )

    # Parity guard: the host orchestrator skill must stay manifest-driven (single source of
    # truth) rather than hardcoding a divergent sequence/policy. We require it to reference the
    # manifest file so a refactor that copies the flow into the prompt is caught here.
    orchestrator = manifest.get("orchestrator")
    if orchestrator:
        skill_md = root / "skills" / orchestrator / "SKILL.md"
        gid_file = f"{manifest.get('graph_id', manifest_path.stem)}.graph.json"
        if not skill_md.exists():
            errors.append(f"{manifest_path.name}: orchestrator skill {orchestrator!r} not found")
        elif gid_file not in skill_md.read_text(encoding="utf-8"):
            errors.append(
                f"{manifest_path.name}: orchestrator skill {orchestrator!r} must "
                f"reference {gid_file} (manifest is the single source of truth)"
            )
        if graph_id == "g02":
            _check_g02_orchestrator_text(root, orchestrator, manifest_path, errors)

    return {
        "ok": not errors,
        "graph": manifest.get("graph_id", manifest_path.stem),
        "host": resolved_host,
        "errors": errors,
    }


def check_all(
    graphs_dir: Path | None = None,
    plugin_root: Path | None = None,
    host: str | None = None,
) -> dict:
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
