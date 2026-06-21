#!/usr/bin/env python3
"""Build and install edu-materials-agents for Claude Code and/or Codex."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "plugin.manifest.json"
BUILD_SCRIPT = ROOT / "scripts" / "build-plugin.py"
DEFAULT_DIST = ROOT / "dist"


class InstallError(RuntimeError):
    """Raised when an install cannot be completed safely."""


def load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def run_checked(command: list[str], *, quiet: bool = False) -> None:
    kwargs: dict[str, Any] = {"check": True}
    if quiet:
        kwargs.update(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(command, **kwargs)


def require_cli(name: str) -> str:
    resolved = shutil.which(name)
    if not resolved:
        raise InstallError(f"required CLI {name!r} was not found in PATH")
    return resolved


def build_bundle(host: str, dist: Path) -> None:
    command = [
        sys.executable,
        str(BUILD_SCRIPT),
        "--host",
        host,
        "--dist-dir",
        str(dist),
        "--python-command",
        sys.executable,
    ]
    run_checked(command)


def validate_bundle(dist: Path, manifest: dict[str, Any], hosts: set[str]) -> None:
    expected_skills = len(manifest["components"]["skills"])
    expected_agents = len(manifest["components"]["agents"])
    expected_commands = len(manifest["components"]["commands"])
    for host in hosts:
        root = dist / host / "plugins" / manifest["name"]
        skills = list((root / "skills").glob("*/SKILL.md"))
        if len(skills) != expected_skills:
            raise InstallError(
                f"{host} bundle contains {len(skills)} skills; expected {expected_skills}"
            )
        if any((p.parent / "adapters").exists() for p in skills):
            raise InstallError(f"{host} bundle still contains source adapter directories")
        if manifest["hosts"][host].get("includeAgents", False):
            agents = list((root / "agents").glob("*.md"))
            if len(agents) != expected_agents:
                raise InstallError(
                    f"{host} bundle contains {len(agents)} agents; expected {expected_agents}"
                )
        if manifest["hosts"][host].get("includeCommands", False):
            commands = list((root / "commands").glob("*.md"))
            if len(commands) != expected_commands:
                raise InstallError(
                    f"{host} bundle contains {len(commands)} commands; expected {expected_commands}"
                )
        mcp = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))
        for cfg in mcp["mcpServers"].values():
            if cfg["command"] != sys.executable:
                raise InstallError(f"{host} MCP interpreter does not match the build interpreter")


def preview_actions(target: str, dist: Path, manifest: dict[str, Any]) -> None:
    name = manifest["name"]
    marketplace = manifest["marketplace"]["name"]
    if target in {"all", "claude"}:
        root = DEFAULT_DIST / "claude"
        print(f"DRY: validated Claude bundle in temporary directory {dist / 'claude'}")
        print(f"DRY: claude plugin uninstall {name}  (force fresh cache)")
        print(f"DRY: claude plugin marketplace remove {marketplace}")
        print(f"DRY: claude plugin marketplace add {root}")
        print(f"DRY: claude plugin install {name}@{marketplace}")
    if target in {"all", "codex"}:
        print(f"DRY: validated Codex bundle in temporary directory {dist / 'codex'}")
        codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
        destination = codex_home / "plugins" / name
        local_marketplace = Path.home() / ".agents" / "plugins" / "marketplace.json"
        print(f"DRY: atomically install {name} at {destination}")
        print(f"DRY: register {name} in {local_marketplace}")
        print(f"DRY: codex plugin add {name}@local-plugins")


def install_claude(dist: Path, manifest: dict[str, Any]) -> None:
    claude = require_cli("claude")
    name = manifest["name"]
    marketplace = manifest["marketplace"]["name"]
    root = dist / "claude"
    # Force a fresh cache: Claude does not re-copy an already-installed same-version plugin, so
    # uninstall first (ignored if absent) before re-adding the rebuilt marketplace. Without this,
    # source edits at the same version leave stale agents and a stale MCP config in the cache.
    subprocess.run(
        [claude, "plugin", "uninstall", name],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    subprocess.run(
        [claude, "plugin", "marketplace", "remove", marketplace],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    run_checked([claude, "plugin", "marketplace", "add", str(root)])
    run_checked([claude, "plugin", "install", f"{name}@{marketplace}"])
    print(f"Claude: installed {name}@{marketplace} from {root}.")
    print("Run /reload-plugins or restart Claude Code.")


def marketplace_payload(current: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    name = manifest["name"]
    current.setdefault("name", "local-plugins")
    current.setdefault("interface", {"displayName": "Local Plugins"})
    plugins = [p for p in current.get("plugins", []) if p.get("name") != name]
    plugins.append({
        "name": name,
        "source": {"source": "local", "path": f"./.codex/plugins/{name}"},
        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        "category": manifest["category"]["codex"],
    })
    current["plugins"] = plugins
    return current


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temp, path)


def restore_file(path: Path, original: bytes | None) -> None:
    if original is None:
        path.unlink(missing_ok=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(original)


def absolutize_mcp_paths(mcp_path: Path, plugin_dir: Path) -> None:
    """Pin relative MCP entrypoints to the absolute install path and drop ``cwd``.

    Codex has no ``${CLAUDE_PLUGIN_ROOT}`` and we cannot assume it launches the server with the
    plugin dir as cwd, so the installer rewrites ``./entrypoint`` (+ ``cwd``) to an absolute path.
    """
    data = json.loads(mcp_path.read_text(encoding="utf-8"))
    for cfg in data.get("mcpServers", {}).values():
        cfg["args"] = [
            str(plugin_dir / arg[2:]) if isinstance(arg, str) and arg.startswith("./") else arg
            for arg in cfg.get("args", [])
        ]
        cfg.pop("cwd", None)
    mcp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def absolutize_codex_command_paths(plugin_dir: Path, installed_plugin_dir: Path) -> None:
    commands_dir = plugin_dir / "commands"
    if not commands_dir.exists():
        return
    for command in commands_dir.glob("*.md"):
        text = command.read_text(encoding="utf-8")
        command.write_text(
            text.replace("{{CODEX_PLUGIN_ROOT}}", str(installed_plugin_dir)),
            encoding="utf-8",
        )


def install_codex(dist: Path, manifest: dict[str, Any]) -> None:
    codex = require_cli("codex")
    name = manifest["name"]
    legacy_marketplace = manifest["marketplace"]["name"]
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    source = dist / "codex" / "plugins" / name
    destination = codex_home / "plugins" / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = destination.parent / f".{name}.staging-{uuid.uuid4().hex}"
    backup = destination.parent / f"{name}.bak.{int(time.time())}.{uuid.uuid4().hex[:8]}"
    marketplace = Path.home() / ".agents" / "plugins" / "marketplace.json"
    original_marketplace = marketplace.read_bytes() if marketplace.exists() else None
    moved_old = False

    shutil.copytree(source, stage)
    absolutize_mcp_paths(stage / ".mcp.json", destination)
    absolutize_codex_command_paths(stage, destination)
    try:
        if destination.exists():
            os.replace(destination, backup)
            moved_old = True
        os.replace(stage, destination)

        try:
            current = json.loads(original_marketplace.decode("utf-8")) if original_marketplace else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            current = {}
        atomic_write_json(marketplace, marketplace_payload(current, manifest))
        run_checked([codex, "plugin", "add", f"{name}@local-plugins"])
    except Exception:
        if destination.exists():
            shutil.rmtree(destination)
        if moved_old and backup.exists():
            os.replace(backup, destination)
        restore_file(marketplace, original_marketplace)
        raise
    finally:
        if stage.exists():
            shutil.rmtree(stage)

    subprocess.run(
        [codex, "plugin", "remove", f"{name}@{legacy_marketplace}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    subprocess.run(
        [codex, "plugin", "marketplace", "remove", legacy_marketplace],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    print(f"Codex: installed {name}@local-plugins at {destination}.")
    if moved_old:
        print(f"Previous installation backup: {backup}")
    print("Start a new Codex thread to load plugin skills and MCP tools.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--all", action="store_const", const="all", dest="target")
    target.add_argument("--claude", action="store_const", const="claude", dest="target")
    target.add_argument("--codex", action="store_const", const="codex", dest="target")
    parser.set_defaults(target="all")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate a temporary build and print install actions without changing dist or host state",
    )
    return parser.parse_args()


def selected_hosts(target: str) -> set[str]:
    return {"claude", "codex"} if target == "all" else {target}


def main() -> int:
    args = parse_args()
    manifest = load_manifest()
    hosts = selected_hosts(args.target)

    try:
        if args.dry_run:
            with tempfile.TemporaryDirectory(prefix="edu-materials-build-") as temp:
                dist = Path(temp)
                build_bundle(args.target, dist)
                validate_bundle(dist, manifest, hosts)
                print(
                    f"Validated {len(manifest['components']['skills'])} skills and "
                    f"{len(manifest['components']['agents'])} agents."
                )
                preview_actions(args.target, dist, manifest)
            return 0

        build_bundle(args.target, DEFAULT_DIST)
        validate_bundle(DEFAULT_DIST, manifest, hosts)
        if args.target in {"all", "claude"}:
            install_claude(DEFAULT_DIST, manifest)
        if args.target in {"all", "codex"}:
            install_codex(DEFAULT_DIST, manifest)
        return 0
    except (InstallError, OSError, subprocess.CalledProcessError, ValueError) as exc:
        print(f"install failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
