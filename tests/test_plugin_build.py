"""Packaging tests for manifest completeness, host adapters and dry-run safety."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "plugin.manifest.json"
BUILDER = ROOT / "scripts" / "build-plugin.py"
INSTALLER = ROOT / "scripts" / "install_plugin.py"


def digest_tree(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def source_skills() -> list[Path]:
    return sorted(path.parent for path in (ROOT / "skills").glob("*/SKILL.md"))


def test_manifest_declares_every_source_component():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    components = manifest["components"]
    skills = {path.relative_to(ROOT).as_posix() for path in source_skills()}
    agents = {path.relative_to(ROOT).as_posix() for path in (ROOT / "agents").glob("*.md")}
    commands = {path.relative_to(ROOT).as_posix() for path in (ROOT / "commands").glob("*.md")}

    assert set(components["skills"]) == skills
    assert set(components["agents"]) == agents
    assert set(components["commands"]) == commands
    assert len(skills) == 20
    assert len(agents) == 11


def test_every_skill_has_required_host_adapters():
    for skill in source_skills():
        adapters = skill / "adapters"
        for name in ("claude.md", "codex.md", "claude.frontmatter.yaml"):
            path = adapters / name
            assert path.is_file(), f"{skill.name}: missing {name}"
            assert path.read_text(encoding="utf-8").strip(), f"{skill.name}: empty {name}"


def test_every_agent_required_skill_exists():
    available = {skill.name for skill in source_skills()}
    for agent in (ROOT / "agents").glob("*.md"):
        text = agent.read_text(encoding="utf-8")
        section = re.search(r"^## Required Skills\s*$\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
        assert section, f"{agent.name}: missing Required Skills section"
        required = set(re.findall(r"`([a-z0-9-]+)`", section.group(1)))
        assert required, f"{agent.name}: no skill references"
        assert required <= available, f"{agent.name}: unknown skills {sorted(required - available)}"


def test_build_renders_all_skills_without_mutating_sources(tmp_path):
    source_before = digest_tree(ROOT / "skills")
    subprocess.run(
        [
            sys.executable,
            str(BUILDER),
            "--host",
            "all",
            "--dist-dir",
            str(tmp_path),
            "--python-command",
            sys.executable,
        ],
        check=True,
    )

    for host in ("claude", "codex"):
        plugin = tmp_path / host / "plugins" / "edu-materials-agents"
        rendered = sorted((plugin / "skills").glob("*/SKILL.md"))
        assert len(rendered) == 20
        assert not list((plugin / "skills").glob("*/adapters"))
        mcp = json.loads((plugin / ".mcp.json").read_text(encoding="utf-8"))
        assert mcp["mcpServers"]["edu-materials-research"]["command"] == sys.executable

        for skill_md in rendered:
            text = skill_md.read_text(encoding="utf-8")
            assert f"<!-- BEGIN HOST ADAPTER: {host.upper()} -->" in text
            other = "CODEX" if host == "claude" else "CLAUDE"
            assert f"<!-- BEGIN HOST ADAPTER: {other} -->" not in text
            assert not (skill_md.parent / "adapters").exists()
            if host == "claude":
                assert "\nmodel:" in text
            else:
                assert "\nmodel:" not in text

    claude_plugin = tmp_path / "claude" / "plugins" / "edu-materials-agents"
    codex_plugin = tmp_path / "codex" / "plugins" / "edu-materials-agents"
    assert len(list((claude_plugin / "agents").glob("*.md"))) == 11
    assert len(list((claude_plugin / "commands").glob("*.md"))) == 1
<<<<<<< Updated upstream
    assert not (codex_plugin / "agents").exists()
=======
    assert len(list((codex_plugin / "agents").glob("*.md"))) == 11
>>>>>>> Stashed changes
    assert not (codex_plugin / "commands").exists()
    assert source_before == digest_tree(ROOT / "skills")


def test_dry_run_validates_in_temporary_directory_without_touching_dist():
    before = digest_tree(ROOT / "dist")
    completed = subprocess.run(
        [sys.executable, str(INSTALLER), "--all", "--dry-run"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Validated 20 skills and 11 agents." in completed.stdout
    assert before == digest_tree(ROOT / "dist")
