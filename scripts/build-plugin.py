#!/usr/bin/env python3
"""Build validated, host-specific plugin bundles from plugin.manifest.json."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "plugin.manifest.json"
DEFAULT_DIST = ROOT / "dist"
FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", re.DOTALL)
VALID_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


class BuildError(ValueError):
    """Raised when source components cannot produce a safe plugin bundle."""


def load_manifest() -> dict[str, Any]:
    with MANIFEST_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(value)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    write_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def ignore_generated(_dir: str, names: list[str]) -> set[str]:
    ignored = {"__pycache__", ".pytest_cache"}
    ignored.update(name for name in names if name.endswith(".pyc"))
    return ignored


def copy_path(src_rel: str, dst_root: Path) -> None:
    src = (ROOT / src_rel).resolve()
    try:
        src.relative_to(ROOT)
    except ValueError as exc:
        raise BuildError(f"manifest path escapes repository root: {src_rel}") from exc
    if not src.exists():
        raise FileNotFoundError(f"manifest path does not exist: {src_rel}")
    dst = dst_root / src_rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst, ignore=ignore_generated)
    else:
        shutil.copy2(src, dst)


def parse_scalar_map(text: str, source: Path) -> OrderedDict[str, str]:
    """Parse the intentionally small key: scalar frontmatter subset used by skills."""
    values: OrderedDict[str, str] = OrderedDict()
    for number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise BuildError(f"{source}:{number}: expected 'key: value'")
        key, raw_value = line.split(":", 1)
        key = key.strip()
        value = raw_value.strip()
        if not VALID_KEY_RE.fullmatch(key) or not value:
            raise BuildError(f"{source}:{number}: invalid scalar frontmatter entry")
        if key in values:
            raise BuildError(f"{source}:{number}: duplicate frontmatter key {key!r}")
        if value.startswith('"'):
            try:
                value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise BuildError(f"{source}:{number}: invalid quoted scalar") from exc
        elif value.startswith("'"):
            if len(value) < 2 or not value.endswith("'"):
                raise BuildError(f"{source}:{number}: invalid quoted scalar")
            value = value[1:-1]
        values[key] = value
    return values


def load_skill(path: Path) -> tuple[OrderedDict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise BuildError(f"{path}: missing YAML frontmatter")
    metadata = parse_scalar_map(match.group(1), path)
    if set(metadata) != {"name", "description"}:
        raise BuildError(f"{path}: neutral frontmatter must contain only name and description")
    if path.parent.name != metadata["name"]:
        raise BuildError(f"{path}: folder name must match skill name")
    return metadata, text[match.end():].lstrip("\r\n")


def load_overlay(path: Path) -> OrderedDict[str, str]:
    if not path.exists():
        return OrderedDict()
    return parse_scalar_map(path.read_text(encoding="utf-8"), path)


def dump_frontmatter(metadata: OrderedDict[str, str]) -> str:
    lines = ["---"]
    for key, value in metadata.items():
        if key == "name" and re.fullmatch(r"[a-z0-9-]+", value):
            rendered = value
        else:
            rendered = json.dumps(value, ensure_ascii=False)
        lines.append(f"{key}: {rendered}")
    lines.append("---")
    return "\n".join(lines)


def source_component_paths(kind: str) -> set[str]:
    if kind == "skills":
        return {p.parent.relative_to(ROOT).as_posix() for p in (ROOT / "skills").glob("*/SKILL.md")}
    return {p.relative_to(ROOT).as_posix() for p in (ROOT / kind).glob("*.md")}


def validate_manifest(manifest: dict[str, Any]) -> None:
    components = manifest.get("components") or {}
    for kind in ("skills", "agents", "commands"):
        declared = components.get(kind)
        if not isinstance(declared, list) or not declared:
            raise BuildError(f"manifest components.{kind} must be a non-empty list")
        if len(declared) != len(set(declared)):
            raise BuildError(f"manifest components.{kind} contains duplicates")
        actual = source_component_paths(kind)
        expected = set(declared)
        if actual != expected:
            missing = sorted(actual - expected)
            stale = sorted(expected - actual)
            raise BuildError(
                f"manifest components.{kind} differs from source; missing={missing}, stale={stale}"
            )

    for rel in components["skills"]:
        skill_root = ROOT / rel
        load_skill(skill_root / "SKILL.md")
        adapters = skill_root / "adapters"
        required = ("claude.md", "codex.md", "claude.frontmatter.yaml")
        absent = [name for name in required if not (adapters / name).is_file()]
        if absent:
            raise BuildError(f"{rel}: missing required adapter files: {', '.join(absent)}")
        for host in ("claude", "codex"):
            adapter_path = adapters / f"{host}.md"
            if not adapter_path.read_text(encoding="utf-8").strip():
                raise BuildError(f"{adapter_path}: adapter body cannot be empty")
            overlay = load_overlay(adapters / f"{host}.frontmatter.yaml")
            if "name" in overlay and overlay["name"] != skill_root.name:
                raise BuildError(f"{rel}: host overlay cannot rename a skill")


def base_metadata(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": manifest["name"],
        "version": manifest["version"],
        "description": manifest["description"],
        "author": manifest["author"],
        "license": manifest["license"],
        "keywords": manifest["keywords"],
    }


def build_claude_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    payload = base_metadata(manifest)
    payload["description"] = f"{manifest['description']} Targets Claude Code and Codex."
    payload["claude-code-version"] = ">=0.4.0"
    return payload


def build_codex_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    interface = dict(manifest["interface"])
    interface["category"] = manifest["category"]["codex"]
    payload = base_metadata(manifest)
    payload.update({"skills": "./skills/", "mcpServers": "./.mcp.json", "interface": interface})
    return payload


def server_command(cfg: dict[str, Any], python_command: str) -> str:
    return python_command if cfg["command"] == "{python}" else cfg["command"]


def build_claude_mcp(manifest: dict[str, Any], python_command: str) -> dict[str, Any]:
    servers = {}
    for name, cfg in manifest["mcpServers"].items():
        servers[name] = {
            "command": server_command(cfg, python_command),
            "args": [f"${{CLAUDE_PLUGIN_ROOT}}/{cfg['entrypoint']}"],
        }
    return {"mcpServers": servers}


def build_codex_mcp(manifest: dict[str, Any], python_command: str) -> dict[str, Any]:
    servers = {}
    for name, cfg in manifest["mcpServers"].items():
        servers[name] = {
            "command": server_command(cfg, python_command),
            "args": [f"./{cfg['entrypoint']}"],
            "cwd": ".",
        }
    return {"mcpServers": servers}


def build_claude_marketplace(manifest: dict[str, Any]) -> dict[str, Any]:
    mp = manifest["marketplace"]
    name = manifest["name"]
    return {
        "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
        "name": mp["name"],
        "description": mp["description"],
        "owner": manifest["author"],
        "plugins": [{
            "name": name,
            "description": manifest["description"],
            "author": {"name": manifest["author"]["name"]},
            "category": manifest["category"]["claude"],
            "source": f"./plugins/{name}",
        }],
    }


def build_codex_marketplace(manifest: dict[str, Any]) -> dict[str, Any]:
    name = manifest["name"]
    mp = manifest["marketplace"]
    return {
        "name": mp["name"],
        "interface": {"displayName": mp["displayName"]},
        "plugins": [{
            "name": name,
            "source": {"source": "local", "path": f"./plugins/{name}"},
            "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
            "category": manifest["category"]["codex"],
        }],
    }


def copy_common(manifest: dict[str, Any], plugin_root: Path, host: str) -> None:
    components = manifest["components"]
    for rel in components["skills"]:
        copy_path(rel, plugin_root)
    for rel in components["shared"]:
        copy_path(rel, plugin_root)
    if manifest["hosts"][host].get("includeAgents", False):
        for rel in components["agents"]:
            copy_path(rel, plugin_root)
    if manifest["hosts"][host].get("includeCommands", False):
        for rel in components["commands"]:
            copy_path(rel, plugin_root)


def render_skill_adapters(manifest: dict[str, Any], plugin_root: Path, host: str) -> None:
    for rel in manifest["components"]["skills"]:
        skill_root = plugin_root / rel
        skill_md = skill_root / "SKILL.md"
        adapters = skill_root / "adapters"
        metadata, body = load_skill(skill_md)
        overlay = load_overlay(adapters / f"{host}.frontmatter.yaml")
        if "name" in overlay and overlay["name"] != metadata["name"]:
            raise BuildError(f"{rel}: host overlay cannot rename a skill")
        metadata.update(overlay)

        adapter = (adapters / f"{host}.md").read_text(encoding="utf-8").strip()
        adapter_section = (
            f"<!-- BEGIN HOST ADAPTER: {host.upper()} -->\n"
            f"{adapter}\n"
            f"<!-- END HOST ADAPTER: {host.upper()} -->"
        )
        if "{{HOST_ADAPTER}}" in body:
            body = body.replace("{{HOST_ADAPTER}}", adapter_section)
        else:
            body = f"{body.rstrip()}\n\n{adapter_section}"
        write_text(skill_md, f"{dump_frontmatter(metadata)}\n\n{body.rstrip()}\n")
        shutil.rmtree(adapters)


def build_claude(manifest: dict[str, Any], dist: Path, python_command: str) -> Path:
    root = dist / "claude"
    plugin_root = root / "plugins" / manifest["name"]
    reset_dir(root)
    copy_common(manifest, plugin_root, "claude")
    render_skill_adapters(manifest, plugin_root, "claude")
    write_json(plugin_root / ".claude-plugin" / "plugin.json", build_claude_manifest(manifest))
    write_json(plugin_root / ".mcp.json", build_claude_mcp(manifest, python_command))
    write_json(root / ".claude-plugin" / "marketplace.json", build_claude_marketplace(manifest))
    return root


def build_codex(manifest: dict[str, Any], dist: Path, python_command: str) -> Path:
    root = dist / "codex"
    plugin_root = root / "plugins" / manifest["name"]
    reset_dir(root)
    copy_common(manifest, plugin_root, "codex")
    render_skill_adapters(manifest, plugin_root, "codex")
    write_json(plugin_root / ".codex-plugin" / "plugin.json", build_codex_manifest(manifest))
    write_json(plugin_root / ".mcp.json", build_codex_mcp(manifest, python_command))
    write_json(root / ".agents" / "plugins" / "marketplace.json", build_codex_marketplace(manifest))
    return root


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=["all", "claude", "codex"], default="all")
    parser.add_argument("--dist-dir", type=Path, default=DEFAULT_DIST)
    parser.add_argument("--python-command", default=sys.executable)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = load_manifest()
    validate_manifest(manifest)
    dist = args.dist_dir.resolve()
    if dist == ROOT or dist.parent == dist:
        raise BuildError(f"unsafe dist directory: {dist}")

    built: list[Path] = []
    if args.host in {"all", "claude"}:
        built.append(build_claude(manifest, dist, args.python_command))
    if args.host in {"all", "codex"}:
        built.append(build_codex(manifest, dist, args.python_command))
    for path in built:
        print(path)


if __name__ == "__main__":
    main()
