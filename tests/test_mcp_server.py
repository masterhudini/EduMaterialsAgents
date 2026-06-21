"""The stdlib MCP server speaks enough JSON-RPC to hand-shake and expose the research seams.

Tests `handle()` directly (no subprocess) + one end-to-end pipe through the stdio loop.
Stdlib only; EMAGENTS_HOME redirected to a tmp dir.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from mcp import research_server as srv  # noqa: E402

SEED = str(ROOT / "mocks" / "g02" / "research_graph_input.json")


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("EMAGENTS_HOME", str(tmp_path / ".emagents"))


def test_initialize_and_tools_list():
    init = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                       "params": {"protocolVersion": "2024-11-05"}})
    assert init["result"]["serverInfo"]["name"] == "edu-materials-research"
    assert init["result"]["protocolVersion"] == "2024-11-05"
    assert "prompts" in init["result"]["capabilities"]

    tools = srv.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in tools["result"]["tools"]}
    assert names == {"research_front_door", "research_node_input",
                     "research_planner_prepare", "research_planner_finalize",
                     "research_plan_review_task",
                     "research_provider_status", "research_domain_prepare",
                     "research_metadata_search", "research_domain_finalize",
                     "research_domain_review_task",
                     "research_review_prepare", "research_review_finalize",
                     "research_finalize", "research_run_stub", "research_run_codex"}
    run_codex = next(t for t in tools["result"]["tools"] if t["name"] == "research_run_codex")
    assert set(run_codex["inputSchema"]["properties"]) == {
        "context", "gates", "resume_token", "decisions"
    }


def test_prompts_list_and_get_research():
    prompts = srv.handle({"jsonrpc": "2.0", "id": 2, "method": "prompts/list"})
    assert prompts["result"]["prompts"][0]["name"] == "research"

    prompt = srv.handle({"jsonrpc": "2.0", "id": 3, "method": "prompts/get",
                         "params": {"name": "research", "arguments": {"context": SEED}}})
    text = prompt["result"]["messages"][0]["content"]["text"]
    assert "research_graph_input bundle" in text
    assert SEED in text


def test_notifications_get_no_reply():
    assert srv.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_tool_call_front_door_then_node_input():
    fd = srv.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                     "params": {"name": "research_front_door", "arguments": {"context": SEED}}})
    payload = json.loads(fd["result"]["content"][0]["text"])
    assert payload["task_id"] == "RESEARCH_MOCK_001"
    ref = payload["ref"]

    ni = srv.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                     "params": {"name": "research_node_input",
                                "arguments": {"ref": ref, "node": "g02-a01-planner"}}})
    seen = json.loads(ni["result"]["content"][0]["text"])
    assert seen["g02-a01-planner"]["task_id"] == "RESEARCH_MOCK_001"


def test_tool_error_is_isError_not_protocol_error():
    res = srv.handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                      "params": {"name": "research_front_door",
                                 "arguments": {"context": "/no/such/file.json"}}})
    assert res["result"]["isError"] is True


def test_unknown_method_is_protocol_error():
    res = srv.handle({"jsonrpc": "2.0", "id": 6, "method": "bogus/method"})
    assert res["error"]["code"] == -32601


def test_stdio_loop_end_to_end():
    """Pipe real newline-delimited JSON-RPC through the process and read responses."""
    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "research_run_stub", "arguments": {"context": SEED}}},
    ]
    stdin = "".join(json.dumps(m) + "\n" for m in msgs)
    proc = subprocess.run([sys.executable, str(SCRIPTS / "mcp" / "research_server.py")],
                          input=stdin, capture_output=True, text=True, timeout=30)
    lines = [json.loads(x) for x in proc.stdout.splitlines() if x.strip()]
    assert len(lines) == 2                      # initialize + tools/call (notification: no reply)
    call = lines[1]
    payload = json.loads(call["result"]["content"][0]["text"])
    assert payload["type"] == "user_approved_research_bundle"
