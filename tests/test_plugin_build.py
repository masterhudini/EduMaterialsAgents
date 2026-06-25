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


EXPECTED_AGENT_SETTINGS = {
    "g02-a01-planner": ("opus", "medium"),
    "g02-a02-domain": ("sonnet", "medium"),
    "g02-a03-canonical-sources": ("sonnet", "medium"),
    "g02-a04-recent-developments": ("sonnet", "medium"),
    "g02-a05-candidate-source-index": ("opus", "medium"),
    "g02-a06-paper-retrieval": ("sonnet", "medium"),
    "g02-a07-paper-review": ("opus", "medium"),
    "g02-a08-claim-verification": ("opus", "medium"),
    "g02-a09-synthesizer": ("opus", "medium"),
    "g02-a10-output-reviewer": ("sonnet", "medium"),
    "g02-a11-market-cases": ("sonnet", "medium"),
}


EXPECTED_GLOBAL_SETTINGS = {
    "cross_artifact_reconciliation": ("sonnet", "medium"),
    "deterministic_technical": ("sonnet", "medium"),
    "evidence_high_impact": ("opus", "medium"),
    "research_planning": ("sonnet", "xhigh"),
    "research_search": ("sonnet", "medium"),
    "synthesis_decision": ("opus", "medium"),
}


EXPECTED_SKILL_SETTINGS = {
    "g01-orchestrate-intake": ("opus", "medium"),
    "g02-a01-plan-research-scope": ("opus", "medium"),
    "g02-a05-annotate-source-candidates": ("opus", "medium"),
    "g02-a05-deduplicate-source-records": ("opus", "medium"),
    "g02-a05-rank-source-candidates": ("opus", "medium"),
    "g02-a06-resolve-open-access": ("sonnet", "medium"),
    "g02-a06-retrieve-open-access-document": ("sonnet", "medium"),
    "g02-a06-validate-retrieved-document": ("sonnet", "medium"),
    "g02-a07-extract-paper-evidence": ("opus", "medium"),
    "g02-a07-scout-light-review": ("sonnet", "high"),
    "g02-a08-assess-claim-evidence": ("opus", "medium"),
    "g02-a09-scout-synthesis": ("opus", "medium"),
    "g02-a09-synthesize-research-findings": ("opus", "medium"),
    "g02-a11-extract-case-evidence": ("opus", "medium"),
    "g02-a11-find-market-cases": ("sonnet", "medium"),
    "g02-assess-source-coverage": ("opus", "medium"),
    "g02-classify-source-role": ("sonnet", "medium"),
    "g02-expand-citation-graph": ("sonnet", "medium"),
    "g02-expand-research-query": ("sonnet", "medium"),
    "g02-normalize-source-metadata": ("sonnet", "medium"),
    "g02-orchestrate-research": ("opus", "low"),
    "g02-review-research-output": ("sonnet", "medium"),
    "g02-search-scholarly-metadata": ("sonnet", "medium"),
    "g02-verify-doi-metadata": ("sonnet", "medium"),
}


def test_manifest_declares_every_source_component():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    components = manifest["components"]
    skills = {path.relative_to(ROOT).as_posix() for path in source_skills()}
    agents = {path.relative_to(ROOT).as_posix() for path in (ROOT / "agents").glob("*.md")}
    commands = {path.relative_to(ROOT).as_posix() for path in (ROOT / "commands").glob("*.md")}

    assert set(components["skills"]) == skills
    assert set(components["agents"]) == agents
    assert set(components["commands"]) == commands
    assert len(skills) == len(components["skills"])
    assert len(agents) == len(components["agents"])


def test_every_skill_has_required_host_adapters():
    for skill in (item for item in source_skills() if item.name.startswith("g02-")):
        adapters = skill / "adapters"
        for name in ("claude.md", "codex.md", "claude.frontmatter.yaml"):
            path = adapters / name
            assert path.is_file(), f"{skill.name}: missing {name}"
            assert path.read_text(encoding="utf-8").strip(), f"{skill.name}: empty {name}"


def test_claude_agent_and_skill_model_effort_matrix_is_exact():
    graph = json.loads((ROOT / "shared" / "graphs" / "g02.graph.json").read_text(encoding="utf-8"))
    actual_agents = {
        name: (value["claude"]["model"], value["claude"]["effort"])
        for name, value in graph["agent_host_bindings"].items()
    }
    assert actual_agents == EXPECTED_AGENT_SETTINGS

    actual_globals = {
        name: (value["claude"]["model"], value["claude"]["effort"])
        for name, value in graph["model_bindings"].items()
    }
    assert actual_globals == EXPECTED_GLOBAL_SETTINGS

    actual_skills = {}
    for skill in (item for item in source_skills() if item.name.startswith(("g01-", "g02-"))):
        text = (skill / "adapters" / "claude.frontmatter.yaml").read_text(encoding="utf-8")
        model = re.search(r"^model:\s*(\S+)\s*$", text, re.MULTILINE)
        effort = re.search(r"^effort:\s*(\S+)\s*$", text, re.MULTILINE)
        assert model and effort, f"{skill.name}: incomplete Claude settings"
        actual_skills[skill.name] = (model.group(1), effort.group(1))
    assert actual_skills == EXPECTED_SKILL_SETTINGS


def test_every_command_has_required_host_adapters():
    adapters = ROOT / "commands" / "adapters"
    for command in (ROOT / "commands").glob("*.md"):
        text = command.read_text(encoding="utf-8")
        assert "{{HOST_ADAPTER}}" in text, f"{command.name}: missing host adapter placeholder"
        for host in ("claude", "codex"):
            path = adapters / f"{command.stem}.{host}.md"
            assert path.is_file(), f"{command.name}: missing {path.name}"
            assert path.read_text(encoding="utf-8").strip(), f"{command.name}: empty {path.name}"


def test_every_agent_required_skill_exists():
    available = {skill.name for skill in source_skills()}
    for agent in (ROOT / "agents").glob("g02-*.md"):
        text = agent.read_text(encoding="utf-8")
        section = re.search(r"^## Required Skills\s*$\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
        assert section, f"{agent.name}: missing Required Skills section"
        section_text = re.sub(r"\s+", " ", section.group(1)).casefold()
        if "no separate skill is loaded" in section_text:
            continue
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
        assert len(rendered) == len(source_skills())
        assert not list((plugin / "skills").glob("*/adapters"))
        for relative in (
            "agents/g02-a03-canonical-sources.md",
            "agents/g02-a04-recent-developments.md",
            "skills/g02-expand-citation-graph/SKILL.md",
            "skills/g02-search-scholarly-metadata/SKILL.md",
            "skills/g02-classify-source-role/SKILL.md",
            "shared/contracts/canonical_research_input.schema.json",
            "shared/contracts/recent_research_input.schema.json",
            "shared/contracts/market_case_research_input.schema.json",
            "shared/contracts/web_case_tool_result.schema.json",
            "shared/contracts/web_case_extract_result.schema.json",
            "shared/contracts/human_source_selection.schema.json",
            "shared/contracts/human_approved_source_set.schema.json",
            "shared/contracts/doi_verification_result.schema.json",
            "shared/contracts/retrieval_input.schema.json",
            "shared/contracts/open_access_resolution.schema.json",
            "shared/contracts/retrieved_file_candidate.schema.json",
            "shared/contracts/validated_document.schema.json",
            "shared/contracts/retrieved_corpus.schema.json",
            "shared/contracts/retrieval_directory.schema.json",
            "shared/contracts/paper_review.schema.json",
            "shared/contracts/scout_a07_deep_dive.schema.json",
            "shared/contracts/scout_a09_model_task.schema.json",
            "shared/contracts/research_state.schema.json",
            "shared/contracts/evidence_map.schema.json",
            "shared/contracts/user_research_validation_packet.schema.json",
            "shared/contracts/solution_input_candidate.schema.json",
            "shared/contracts/research_summary.schema.json",
            "shared/contracts/user_approved_research_bundle.schema.json",
            "shared/contracts/candidate_sources.schema.json",
            "shared/scripts/g02/canonical.py",
            "shared/scripts/g02/citations.py",
            "shared/scripts/g02/recent.py",
            "shared/scripts/g02/market_cases.py",
            "shared/scripts/g02/web_cases.py",
            "shared/scripts/g02/source_selection.py",
            "shared/scripts/g02/crossref.py",
            "shared/scripts/g02/oa_retrieval.py",
            "shared/scripts/g02/retrieval.py",
            "shared/scripts/g02/paper_review.py",
            "shared/scripts/g02/scout_a09_runner.py",
            "shared/scripts/g02/scout_synthesis.py",
            "shared/scripts/g02/synthesis.py",
        ):
            assert (plugin / relative).is_file(), f"{host}: missing A03 file {relative}"
        assert not (plugin / "mocks").exists()
        assert not (plugin / "tests").exists()
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
                assert "\neffort:" in text
            else:
                assert "\nmodel:" not in text

    claude_plugin = tmp_path / "claude" / "plugins" / "edu-materials-agents"
    codex_plugin = tmp_path / "codex" / "plugins" / "edu-materials-agents"
    expected_agent_count = len(json.loads(MANIFEST.read_text(encoding="utf-8"))["components"]["agents"])
    assert len(list((claude_plugin / "agents").glob("*.md"))) == expected_agent_count
    assert len(list((claude_plugin / "commands").glob("*.md"))) == 1
    assert len(list((codex_plugin / "agents").glob("*.md"))) == expected_agent_count
    assert not (codex_plugin / "commands").exists()
    for agent, (model, effort) in EXPECTED_AGENT_SETTINGS.items():
        rendered_agent = (claude_plugin / "agents" / f"{agent}.md").read_text(encoding="utf-8")
        assert re.search(rf"^model:\s*{model}\s*$", rendered_agent, re.MULTILINE)
        assert re.search(rf"^effort:\s*{effort}\s*$", rendered_agent, re.MULTILINE)
    codex_manifest = json.loads((codex_plugin / ".codex-plugin" / "plugin.json").read_text())
    assert "agents" not in codex_manifest
    assert "commands" not in codex_manifest
    assert codex_manifest["mcpServers"] == "./.mcp.json"
    assert source_before == digest_tree(ROOT / "skills")


def test_dry_run_validates_in_temporary_directory_without_touching_dist():
    before = digest_tree(ROOT / "dist")
    completed = subprocess.run(
        [sys.executable, str(INSTALLER), "--all", "--dry-run"],
        check=True,
        capture_output=True,
        text=True,
    )
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert (
        f"Validated {len(manifest['components']['skills'])} skills and "
        f"{len(manifest['components']['agents'])} agents."
    ) in completed.stdout
    assert before == digest_tree(ROOT / "dist")
