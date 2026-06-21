#!/usr/bin/env python3
"""Build host-specific plugin bundles from plugin.manifest.json.

The repo is the source of truth. This script composes installable Claude Code and Codex
bundles under dist/ without making either host treat the repo root as the production plugin.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "plugin.manifest.json"
DIST = ROOT / "dist"


def load_manifest() -> dict[str, Any]:
    with MANIFEST_PATH.open() as handle:
        return json.load(handle)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def ignore_generated(_dir: str, names: list[str]) -> set[str]:
    ignored = {"__pycache__", ".pytest_cache"}
    ignored.update(name for name in names if name.endswith(".pyc"))
    return ignored


def copy_path(src_rel: str, dst_root: Path) -> None:
    src = ROOT / src_rel
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
    payload.update({
        "skills": "./skills/",
        "mcpServers": "./.mcp.json",
        "interface": interface,
    })
    return payload


def build_claude_mcp(manifest: dict[str, Any]) -> dict[str, Any]:
    servers = {}
    for name, cfg in manifest["mcpServers"].items():
        servers[name] = {
            "command": cfg["command"],
            "args": [f"${{CLAUDE_PLUGIN_ROOT}}/{cfg['entrypoint']}"],
        }
    return {"mcpServers": servers}


def build_codex_mcp(manifest: dict[str, Any]) -> dict[str, Any]:
    servers = {}
    for name, cfg in manifest["mcpServers"].items():
        servers[name] = {
            "command": cfg["command"],
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
        "plugins": [
            {
                "name": name,
                "description": manifest["description"],
                "author": {"name": manifest["author"]["name"]},
                "category": manifest["category"]["claude"],
                "source": f"./plugins/{name}",
            }
        ],
    }


def build_codex_marketplace(manifest: dict[str, Any]) -> dict[str, Any]:
    name = manifest["name"]
    mp = manifest["marketplace"]
    return {
        "name": mp["name"],
        "interface": {
            "displayName": mp["displayName"],
        },
        "plugins": [
            {
                "name": name,
                "source": {
                    "source": "local",
                    "path": f"./plugins/{name}",
                },
                "policy": {
                    "installation": "AVAILABLE",
                    "authentication": "ON_INSTALL",
                },
                "category": manifest["category"]["codex"],
            }
        ],
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
        adapters_dir = skill_root / "adapters"
        adapter_md = adapters_dir / f"{host}.md"
        adapter_frontmatter = adapters_dir / f"{host}.frontmatter.yaml"

        if not skill_md.exists():
            raise FileNotFoundError(f"skill is missing SKILL.md after copy: {rel}")

        body = skill_md.read_text()
        if adapter_frontmatter.exists():
            extra_frontmatter = adapter_frontmatter.read_text().strip()
            if extra_frontmatter:
                if not body.startswith("---\n"):
                    raise ValueError(f"skill frontmatter is required for host metadata injection: {rel}")
                frontmatter_end = body.find("\n---\n", 4)
                if frontmatter_end == -1:
                    raise ValueError(f"skill frontmatter is not closed: {rel}")
                body = (
                    body[:frontmatter_end].rstrip()
                    + "\n"
                    + extra_frontmatter
                    + body[frontmatter_end:]
                )

        adapter = adapter_md.read_text().strip() if adapter_md.exists() else ""
        if "{{HOST_ADAPTER}}" in body:
            body = body.replace("{{HOST_ADAPTER}}", adapter)
        elif adapter:
            body = f"{body.rstrip()}\n\n{adapter}\n"
        skill_md.write_text(body.rstrip() + "\n")

        if adapters_dir.exists():
            shutil.rmtree(adapters_dir)


def build_claude(manifest: dict[str, Any]) -> Path:
    root = DIST / "claude"
    plugin_root = root / "plugins" / manifest["name"]
    reset_dir(root)
    copy_common(manifest, plugin_root, "claude")
    render_skill_adapters(manifest, plugin_root, "claude")
    write_json(plugin_root / ".claude-plugin" / "plugin.json", build_claude_manifest(manifest))
    write_json(plugin_root / ".mcp.json", build_claude_mcp(manifest))
    write_json(root / ".claude-plugin" / "marketplace.json", build_claude_marketplace(manifest))
    return root


def build_codex(manifest: dict[str, Any]) -> Path:
    root = DIST / "codex"
    plugin_root = root / "plugins" / manifest["name"]
    reset_dir(root)
    copy_common(manifest, plugin_root, "codex")
    render_skill_adapters(manifest, plugin_root, "codex")
    write_json(plugin_root / ".codex-plugin" / "plugin.json", build_codex_manifest(manifest))
    write_json(plugin_root / ".mcp.json", build_codex_mcp(manifest))
    write_json(root / ".agents" / "plugins" / "marketplace.json", build_codex_marketplace(manifest))
    return root


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=["all", "claude", "codex"], default="all")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = load_manifest()
    built: list[Path] = []
    if args.host in {"all", "claude"}:
        built.append(build_claude(manifest))
    if args.host in {"all", "codex"}:
        built.append(build_codex(manifest))
    for path in built:
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
