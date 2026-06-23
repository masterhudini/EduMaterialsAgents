"""Contract tests for the isolated Codex worker adapter."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from core import contracts  # noqa: E402
from g02.runners import codex  # noqa: E402


class Log:
    def __init__(self):
        self.entries = []

    def append(self, *args, **kwargs):
        self.entries.append((args, kwargs))


def _process_with(payload):
    def run(cmd, **kwargs):
        last = Path(cmd[cmd.index("--output-last-message") + 1])
        last.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    return run


def test_prompt_loads_only_declared_agent_skills_and_protocol():
    prompt = codex._build_prompt("g02-a01-planner", {
        "input": {"task_id": "T"},
        "protocol": {"allowed_operations": ["research_planner_prepare"]},
    }, "research_plan@1")
    assert "REQUIRED SKILL: g02-a01-plan-research-scope" in prompt
    assert "research_planner_prepare" in prompt
    assert "Do not wrap it" in prompt
    assert "extra `artifact` key" not in prompt


def test_runner_uses_output_schema_and_accepts_only_whole_json():
    valid = {"status": "ok", "produced": [], "summary": "done", "issues": []}
    seen = {}

    def process(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["prompt"] = kwargs["input"]
        return _process_with(valid)(cmd, **kwargs)

    result = codex.codex_node_runner(
        {"name": "g02-a01-planner", "output_contract": "research_plan@1"},
        {"input": {"task_id": "T"}}, Log(), process_runner=process,
    )
    assert result == valid
    assert "--output-schema" in seen["cmd"]
    assert seen["cmd"][seen["cmd"].index("--output-schema") + 1].endswith("envelope.schema.json")

    rejected = codex.codex_node_runner(
        {"name": "g02-a01-planner", "output_contract": "research_plan@1"},
        {"input": {"task_id": "T"}}, Log(),
        process_runner=_process_with("prefix " + json.dumps(valid)),
    )
    assert rejected["status"] == "failed"
    assert contracts.validate_envelope(rejected)["ok"]
    assert rejected["issues"][0]["type"] == "codex_worker"


def test_invalid_worker_envelope_becomes_valid_failed_envelope():
    invalid = {
        "status": "failed", "produced": [], "summary": "bad",
        "issues": [{"severity": "blocking", "message": "missing type"}],
    }
    result = codex.codex_node_runner(
        {"name": "g02-a01-planner", "output_contract": "research_plan@1"},
        {"input": {"task_id": "T"}}, Log(), process_runner=_process_with(invalid),
    )
    assert result["status"] == "failed"
    assert contracts.validate_envelope(result)["ok"]

    extra = {"status": "ok", "produced": [], "summary": "bad", "issues": [], "artifact": {}}
    result = codex.codex_node_runner(
        {"name": "g02-a01-planner", "output_contract": "research_plan@1"},
        {"input": {"task_id": "T"}}, Log(), process_runner=_process_with(extra),
    )
    assert result["status"] == "failed"
    assert "unsupported fields" in result["issues"][0]["message"]


def test_nonzero_codex_exit_is_failed_even_if_last_message_exists():
    valid = {"status": "ok", "produced": [], "summary": "done", "issues": []}

    def process(cmd, **kwargs):
        last = Path(cmd[cmd.index("--output-last-message") + 1])
        last.write_text(json.dumps(valid), encoding="utf-8")
        return SimpleNamespace(returncode=7, stdout="", stderr="worker crashed")

    result = codex.codex_node_runner(
        {"name": "g02-a01-planner", "output_contract": "research_plan@1"},
        {"input": {"task_id": "T"}}, Log(), process_runner=process,
    )
    assert result["status"] == "failed"
    assert "rc=7" in result["issues"][0]["message"]
