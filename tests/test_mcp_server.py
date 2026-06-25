"""The stdlib MCP server speaks enough JSON-RPC to hand-shake and expose research seams."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from mcp import research_server as srv  # noqa: E402
from g02 import a07_bridge  # noqa: E402
from tests.test_g02_scout_a07_bridge import ScoutA07BridgeTests  # noqa: E402

SEED = str(ROOT / "mocks" / "g02" / "research_graph_input.json")


class MCPServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)
        os.environ["EMAGENTS_HOME"] = str(self.tmp_path / ".emagents")

    def test_initialize_and_tools_list(self):
        init = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                           "params": {"protocolVersion": "2024-11-05"}})
        self.assertEqual(init["result"]["serverInfo"]["name"], "edu-materials-research")
        self.assertEqual(init["result"]["serverInfo"]["version"], "0.17.0")
        self.assertEqual(init["result"]["protocolVersion"], "2024-11-05")
        self.assertIn("prompts", init["result"]["capabilities"])

        tools = srv.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {t["name"] for t in tools["result"]["tools"]}
        self.assertEqual(len(names), 20)
        self.assertEqual(names, {"research_front_door", "research_node_input",
                                 "research_planner_prepare", "research_planner_finalize",
                                 "research_human_gate_prepare",
                                 "research_bundle_finalize",
                                 "research_finalize", "research_scout_fanout",
                                 "research_a07_prepare",
                                 "research_a07_tasks_prepare",
                                 "research_a07_partial_finalize",
                                 "research_a07_aggregate",
                                 "research_a09_task_prepare",
                                 "research_a09_synthesis_finalize",
                                 "research_a09_research_state_finalize",
                                 "research_provider_setup",
                                 "research_run_hosted",
                                 "research_run_codex",
                                 "research_resume",
                                 "research_trace"})
        a09_task = next(
            t for t in tools["result"]["tools"]
            if t["name"] == "research_a09_task_prepare"
        )
        self.assertIn("research_run_codex", names)
        self.assertIn("research_run_hosted", names)
        self.assertIn("research_resume", names)
        self.assertNotIn("research_review_prepare", names)
        self.assertNotIn("research_plan_review_task", names)
        self.assertNotIn("research_domain_prepare", names)
        self.assertNotIn("research_source_selection_prepare", names)
        self.assertEqual(set(a09_task["inputSchema"]["properties"]), {
            "reviews_json", "intake", "max_deep_dive_sources",
            "deep_dive_windows", "deep_dive_chars",
        })

    def test_planner_input_schema_and_loader_accept_object_ref_path_and_json(self):
        tools = {item["name"]: item for item in srv.TOOLS}
        for name in ("research_planner_prepare", "research_planner_finalize"):
            self.assertEqual(
                tools[name]["inputSchema"]["properties"]["input"]["type"],
                ["object", "string"],
            )
            self.assertEqual(
                tools[name]["inputSchema"]["properties"]["execution_profile"]["enum"],
                ["scout_e2e"],
            )

        payload = json.loads(Path(SEED).read_text(encoding="utf-8"))
        self.assertEqual(srv._planner_payload(payload), payload)
        self.assertEqual(srv._planner_payload(json.dumps(payload)), payload)
        path = self.tmp_path / "input.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        self.assertEqual(srv._planner_payload(str(path)), payload)

        ref = srv._front_door({"context": SEED})["ref"]
        self.assertEqual(srv._planner_payload(ref), payload)
        with self.assertRaisesRegex(ValueError, "neither inline JSON nor a safe path"):
            srv._planner_payload("x" * 5000)

        prepared = srv._planner_prepare({"input": payload, "execution_profile": "scout_e2e"})
        self.assertEqual(prepared["plan_output_template"]["global_constraints"]["max_topics"], 6)

    def test_provider_setup_ignores_ambient_credentials_until_user_supplies_them(self):
        with mock.patch.dict(os.environ, {
            "EMAGENTS_HOME": str(self.tmp_path / ".emagents"),
            "EMAGENTS_RESEARCH_CONTACT_EMAIL": "ambient@example.org",
            "OPENALEX_API_KEY": "ambient-openalex-key",
        }, clear=True):
            status = srv._provider_setup({})
            self.assertEqual(status["tier"], "minimal")
            self.assertFalse(status["contact_email_configured"])
            self.assertFalse(status["openalex_token_configured"])
            self.assertFalse(status["openalex_ready"])
            self.assertNotIn("openalex", status["active_providers"])

            configured = srv._provider_setup({
                "email": "user@example.org",
                "openalex_key": "user-openalex-key",
            })
            self.assertEqual(configured["tier"], "email")
            self.assertTrue(configured["contact_email_configured"])
            self.assertTrue(configured["openalex_token_configured"])
            self.assertTrue(configured["openalex_ready"])
            self.assertIn("openalex", configured["active_providers"])

    def test_mcp_audit_logs_keys_only(self):
        entries = []

        class Audit:
            def append(self, *args, **kwargs):
                entries.append((args, kwargs))

        with mock.patch.dict(os.environ, {
            "EMAGENTS_RUN_ID": "RUN_AUDIT",
            "EMAGENTS_NODE_ID": "NODE_AUDIT",
        }, clear=False), mock.patch.object(srv.event_log, "open_log", lambda name: Audit()):
            response = srv.handle({
                "jsonrpc": "2.0", "id": 20, "method": "tools/call",
                "params": {"name": "research_front_door", "arguments": {"context": SEED}},
            })
        self.assertIn("result", response)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0][0][:2], ("NODE_AUDIT", "research_front_door"))
        self.assertEqual(entries[0][1]["detail"], {
            "argument_keys": ["context"],
            "deprecated": False,
        })
        self.assertNotIn(SEED, json.dumps(entries))

    def test_prompts_list_and_get_research(self):
        prompts = srv.handle({"jsonrpc": "2.0", "id": 2, "method": "prompts/list"})
        self.assertEqual(prompts["result"]["prompts"][0]["name"], "research")
        self.assertGreaterEqual(
            {item["name"] for item in prompts["result"]["prompts"]},
            {"research", "research-scout", "research-scout-e2e"},
        )

        prompt = srv.handle({"jsonrpc": "2.0", "id": 3, "method": "prompts/get",
                             "params": {"name": "research", "arguments": {"context": SEED}}})
        text = prompt["result"]["messages"][0]["content"]["text"]
        self.assertIn("research_graph_input", text)
        self.assertIn(SEED, text)

        scout = srv.handle({"jsonrpc": "2.0", "id": 4, "method": "prompts/get",
                            "params": {"name": "research-scout",
                                       "arguments": {"context": SEED}}})
        scout_text = scout["result"]["messages"][0]["content"]["text"]
        for expected in (
            "execution_profile='scout_e2e'",
            "shared/graphs/g02.graph.json",
            "research_provider_setup",
            "research_scout_fanout",
            "path=<artifact:// ref>",
            "Do not call",
            "A10 review",
            "Stop before A07 and A09",
        ):
            self.assertIn(expected, scout_text)

        scout_e2e = srv.handle({"jsonrpc": "2.0", "id": 5, "method": "prompts/get",
                                "params": {"name": "research-scout-e2e",
                                           "arguments": {"context": SEED}}})
        e2e_text = scout_e2e["result"]["messages"][0]["content"]["text"]
        for expected in (
            "research_run_hosted",
            "research_resume",
            "awaiting_node",
            "node_key",
            "finalize_op",
            "awaiting_user",
            "user_approved_research_bundle@1",
            "Graph03 must not",
        ):
            self.assertIn(expected, e2e_text)

    def test_notifications_get_no_reply(self):
        self.assertIsNone(srv.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_tool_call_front_door_then_node_input(self):
        fd = srv.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                         "params": {"name": "research_front_door",
                                    "arguments": {"context": SEED}}})
        payload = json.loads(fd["result"]["content"][0]["text"])
        self.assertEqual(payload["task_id"], "RESEARCH_MOCK_001")
        ref = payload["ref"]

        ni = srv.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                         "params": {"name": "research_node_input",
                                    "arguments": {"ref": ref, "node": "g02-a01-planner"}}})
        seen = json.loads(ni["result"]["content"][0]["text"])
        self.assertEqual(seen["g02-a01-planner"]["task_id"], "RESEARCH_MOCK_001")

    def test_research_run_hosted_starts_at_planner_node(self):
        res = srv.handle({"jsonrpc": "2.0", "id": 30, "method": "tools/call",
                          "params": {"name": "research_run_hosted",
                                     "arguments": {"context": SEED}}})
        payload = json.loads(res["result"]["content"][0]["text"])

        self.assertEqual(payload["status"], "awaiting_node")
        self.assertEqual(payload["node"], "g02-a01-planner")
        self.assertEqual(payload["node_key"], "g02-a01-planner")
        self.assertEqual(payload["finalize_op"], "research_planner_finalize")
        self.assertEqual(payload["output_contract"], "research_plan@1")
        self.assertEqual(payload["input"]["planner_input"]["task_id"], "RESEARCH_MOCK_001")

    def test_tool_error_is_isError_not_protocol_error(self):
        res = srv.handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                          "params": {"name": "research_front_door",
                                     "arguments": {"context": "/no/such/file.json"}}})
        self.assertTrue(res["result"]["isError"])

    def test_deprecated_tool_names_are_not_executed(self):
        entries = []

        class Audit:
            def append(self, *args, **kwargs):
                entries.append((args, kwargs))

        with mock.patch.dict(os.environ, {
            "EMAGENTS_RUN_ID": "RUN_DEPRECATED",
            "EMAGENTS_NODE_ID": "NODE_DEPRECATED",
        }, clear=False), mock.patch.object(srv.event_log, "open_log", lambda name: Audit()):
            res = srv.handle({"jsonrpc": "2.0", "id": 50, "method": "tools/call",
                              "params": {"name": "research_domain_prepare",
                                         "arguments": {"research_plan_ref": "artifact://missing",
                                                       "topic_id": "T1"}}})
        payload = json.loads(res["result"]["content"][0]["text"])
        self.assertEqual(payload["status"], "deprecated_tool")
        self.assertEqual(payload["tool"], "research_domain_prepare")
        self.assertEqual(entries[0][0][:2], ("NODE_DEPRECATED", "research_domain_prepare"))
        self.assertEqual(entries[0][1]["detail"], {
            "argument_keys": ["research_plan_ref", "topic_id"],
            "deprecated": True,
        })
        self.assertEqual(entries[1][1]["status"], "deprecated")
        self.assertEqual(entries[1][1]["detail"], {"is_error": False, "deprecated": True})

    def test_a07_aggregate_returns_envelope(self):
        fixture = ScoutA07BridgeTests()
        run = fixture._make_run(self.tmp_path)
        out = self.tmp_path / "outputs" / "g02" / "T_SCOUT_A07" / "a07"
        reviews = a07_bridge.build_a07_reviews(run, output_dir=out, max_scan_pages=2)
        good = next(item for item in reviews["source_reviews"] if item["source_id"] == "SCOUT_GOOD")
        a07_bridge.finalize_a07_partial(out / good["work_input_ref"], {
            "review_status": "useful_for_update",
            "confidence": "medium",
            "presentation_update_candidates": [{
                "finding": "FRA settlement uses a notional principal.",
                "rationale_vs_existing_presentation": "Supports the settlement explanation.",
                "suggested_slide_action": "add_bullet",
                "draft_insert": "Only the interest differential is settled.",
                "evidence_refs": [{
                    "source_id": "SCOUT_GOOD",
                    "location": "selected window W01",
                    "quote": "notional principal",
                }],
            }],
        })

        envelope = srv._a07_aggregate({"a07_dir": str(out)})

        self.assertEqual(envelope["schema_version"], "envelope@1")
        self.assertEqual(envelope["status"], "ok")
        self.assertEqual(envelope["produced"][0]["type"], "a07_reviews")
        self.assertEqual(envelope["produced"][0]["schema_version"], "a07_reviews@1")
        self.assertTrue(Path(envelope["produced"][0]["path"]).is_file())

    def test_unknown_method_is_protocol_error(self):
        res = srv.handle({"jsonrpc": "2.0", "id": 6, "method": "bogus/method"})
        self.assertEqual(res["error"]["code"], -32601)

    def test_stdio_loop_end_to_end(self):
        msgs = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2024-11-05"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "research_front_door", "arguments": {"context": SEED}}},
        ]
        stdin = "".join(json.dumps(m) + "\n" for m in msgs)
        proc = subprocess.run([sys.executable, str(SCRIPTS / "mcp" / "research_server.py")],
                              input=stdin, capture_output=True, text=True, timeout=30)
        lines = [json.loads(x) for x in proc.stdout.splitlines() if x.strip()]
        self.assertEqual(len(lines), 2)
        payload = json.loads(lines[1]["result"]["content"][0]["text"])
        self.assertEqual(payload["task_id"], "RESEARCH_MOCK_001")


if __name__ == "__main__":
    unittest.main()
