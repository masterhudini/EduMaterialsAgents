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
    assert init["result"]["serverInfo"]["version"] == "0.17.0"
    assert init["result"]["protocolVersion"] == "2024-11-05"
    assert "prompts" in init["result"]["capabilities"]

    tools = srv.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in tools["result"]["tools"]}
    assert len(names) == 60
    assert names == {"research_front_door", "research_node_input",
                     "research_planner_prepare", "research_planner_finalize",
                     "research_plan_review_task",
                     "research_provider_status", "research_domain_prepare",
                     "research_query_plan_generate_fast",
                     "research_metadata_search", "research_doi_verify",
                     "research_doi_verify_batch", "research_domain_finalize",
                     "research_domain_review_task",
                     "research_canonical_prepare", "research_citation_expand",
                     "research_canonical_finalize", "research_canonical_review_task",
                     "research_recent_prepare", "research_recent_finalize",
                     "research_recent_review_task",
                     "research_market_cases_prepare", "research_web_case_search",
                     "research_market_cases_finalize", "research_market_cases_review_task",
                     "research_candidate_index_prepare", "research_candidate_index_finalize",
                     "research_candidate_index_review_task",
                     "research_source_selection_prepare", "research_source_selection_validate",
                     "research_source_selection_finalize", "research_retrieval_prepare",
                     "research_oa_resolve", "research_document_retrieve",
                     "research_document_validate", "research_retrieval_finalize",
                     "research_retrieval_review_task",
                     "research_web_case_extract",
                     "research_paper_review_prepare", "research_document_text_index",
                     "research_document_text_window", "research_paper_review_finalize",
                     "research_paper_review_task",
                     "research_synthesis_prepare", "research_synthesis_finalize",
                     "research_synthesis_review_task", "research_bundle_finalize",
                     "research_review_prepare", "research_review_finalize",
                     "research_finalize", "research_scout_fanout",
                     "research_scout_a07_prepare",
                     "research_scout_a07_tasks_prepare",
                     "research_scout_a07_partial_finalize",
                     "research_scout_a07_aggregate",
                     "research_scout_synthesis_prepare",
                     "research_scout_deep_dive_windows",
                     "research_scout_a09_task_prepare",
                     "research_scout_synthesis_finalize",
                     "research_run_stub", "research_run_codex"}
    run_codex = next(t for t in tools["result"]["tools"] if t["name"] == "research_run_codex")
    a09_task = next(
        t for t in tools["result"]["tools"]
        if t["name"] == "research_scout_a09_task_prepare"
    )
    a11_tools = [t for t in tools["result"]["tools"] if t["name"] in {
        "research_market_cases_prepare", "research_web_case_search",
        "research_market_cases_finalize", "research_market_cases_review_task",
        "research_web_case_extract",
    }]
    assert len(a11_tools) == 5
    assert all("config" not in t["inputSchema"]["properties"] for t in a11_tools)
    assert set(run_codex["inputSchema"]["properties"]) == {
        "context", "gates", "resume_token", "decisions", "through", "topic_ids"
    }
    assert set(a09_task["inputSchema"]["properties"]) == {
        "reviews_json", "intake", "max_deep_dive_sources",
        "deep_dive_windows", "deep_dive_chars",
    }


def test_planner_input_schema_and_loader_accept_object_ref_path_and_json(tmp_path):
    tools = {item["name"]: item for item in srv.TOOLS}
    for name in ("research_planner_prepare", "research_planner_finalize",
                 "research_plan_review_task"):
        assert tools[name]["inputSchema"]["properties"]["input"]["type"] == ["object", "string"]
        assert tools[name]["inputSchema"]["properties"]["execution_profile"]["enum"] == [
            "fast", "scout"
        ]

    payload = json.loads(Path(SEED).read_text(encoding="utf-8"))
    assert srv._planner_payload(payload) == payload
    assert srv._planner_payload(json.dumps(payload)) == payload
    path = tmp_path / "input.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert srv._planner_payload(str(path)) == payload

    ref = srv._front_door({"context": SEED})["ref"]
    assert srv._planner_payload(ref) == payload
    with pytest.raises(ValueError, match="neither inline JSON nor a safe path"):
        srv._planner_payload("x" * 5000)

    prepared = srv._planner_prepare({"input": payload, "execution_profile": "scout"})
    assert prepared["plan_output_template"]["global_constraints"]["max_topics"] == 6


def test_reviewed_run_disallows_auto_gate_and_mcp_audit_logs_keys_only(monkeypatch):
    with pytest.raises(ValueError, match="require gates='pause'"):
        srv._run_codex({"context": SEED, "gates": "auto"})

    entries = []

    class Audit:
        def append(self, *args, **kwargs):
            entries.append((args, kwargs))

    monkeypatch.setenv("EMAGENTS_RUN_ID", "RUN_AUDIT")
    monkeypatch.setenv("EMAGENTS_NODE_ID", "NODE_AUDIT")
    monkeypatch.setattr(srv.event_log, "open_log", lambda name: Audit())
    response = srv.handle({
        "jsonrpc": "2.0", "id": 20, "method": "tools/call",
        "params": {"name": "research_front_door", "arguments": {"context": SEED}},
    })
    assert "result" in response
    assert len(entries) == 2
    assert entries[0][0][:2] == ("NODE_AUDIT", "research_front_door")
    assert entries[0][1]["detail"] == {"argument_keys": ["context"]}
    assert SEED not in json.dumps(entries)


def test_prompts_list_and_get_research():
    prompts = srv.handle({"jsonrpc": "2.0", "id": 2, "method": "prompts/list"})
    assert prompts["result"]["prompts"][0]["name"] == "research"
    assert {item["name"] for item in prompts["result"]["prompts"]} >= {
        "research", "research-scout", "research-scout-e2e"
    }

    prompt = srv.handle({"jsonrpc": "2.0", "id": 3, "method": "prompts/get",
                         "params": {"name": "research", "arguments": {"context": SEED}}})
    text = prompt["result"]["messages"][0]["content"]["text"]
    assert "research_graph_input bundle" in text
    assert SEED in text

    scout = srv.handle({"jsonrpc": "2.0", "id": 4, "method": "prompts/get",
                        "params": {"name": "research-scout",
                                   "arguments": {"context": SEED}}})
    scout_text = scout["result"]["messages"][0]["content"]["text"]
    assert "execution_profile='scout'" in scout_text
    assert "research_scout_fanout" in scout_text
    assert "research_review_prepare" in scout_text
    assert "schema_version='review_decision@1'" in scout_text
    assert "reviewer_agent='g02-a10-output-reviewer'" in scout_text
    assert "confidence ('low', 'medium' or 'high')" in scout_text
    assert "descriptor.path" in scout_text
    assert "advance artifact_version" in scout_text
    assert "maximum is exactly one review" in scout_text
    assert "Stop before A07 and A09" in scout_text

    scout_e2e = srv.handle({"jsonrpc": "2.0", "id": 5, "method": "prompts/get",
                            "params": {"name": "research-scout-e2e",
                                       "arguments": {"context": SEED}}})
    e2e_text = scout_e2e["result"]["messages"][0]["content"]["text"]
    assert "research_scout_a07_prepare" in e2e_text
    assert "research_scout_a07_tasks_prepare" in e2e_text
    assert "research_scout_a07_partial_finalize" in e2e_text
    assert "research_scout_a09_task_prepare" in e2e_text
    assert "g02-a09-scout-synthesis" in e2e_text
    assert "Opus with medium effort" in e2e_text
    assert "deep_dive_windows=8" in e2e_text
    assert "a09_model_pass=false" in e2e_text
    assert "research_scout_synthesis_finalize" in e2e_text
    assert "solution_input_candidate@1" in e2e_text
    assert "Graph03 must not" in e2e_text


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
