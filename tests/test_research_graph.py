"""Research Graph manifest coherence for the active Scout E2E path."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from core import contracts, graph_check, graphs  # noqa: E402

SEED = ROOT / "tests" / "fixtures" / "research_graph_input.example.json"


class ResearchGraphTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        os.environ["EMAGENTS_HOME"] = str(Path(self._tmp.name) / ".emagents")

    def test_seed_satisfies_input_contract(self):
        seed = json.loads(SEED.read_text())
        self.assertTrue(contracts.validate(seed, "research_graph_input@1")["ok"])

    def test_active_g02_graph_is_scout_e2e_without_review(self):
        manifest = graphs.load("g02")
        self.assertEqual(manifest["default_execution_profile"], "scout_e2e")
        self.assertIsNone(manifest["reviewer"])
        profile = manifest["execution_profiles"]["scout_e2e"]
        self.assertEqual(profile["implemented_terminal_stage"], "user-research-gate")
        self.assertEqual(profile["review_mode"], "none")
        self.assertEqual(profile["scout"]["total_target"], 50)
        self.assertEqual(manifest["sequence"], [
            "g02-a01-planner",
            "g02-a11-market-cases",
            "research-scout-fanout",
            "g02-a07-paper-review",
            "g02-a09-synthesizer",
            "g02-a08-claim-verification",
            "user-research-gate",
        ])

    def test_active_g02_nodes_reference_current_mcp_operations(self):
        nodes = {node["name"]: node for node in graphs.load("g02")["nodes"]}
        self.assertEqual(nodes["g02-a01-planner"]["operations"], {
            "prepare": "research_planner_prepare",
            "finalize": "research_planner_finalize",
        })
        self.assertEqual(nodes["research-scout-fanout"]["operations"], {
            "provider_setup": "research_provider_setup",
            "run": "research_scout_fanout",
        })
        self.assertEqual(
            nodes["g02-a07-paper-review"]["operations"]["prepare_tasks"],
            "research_a07_tasks_prepare",
        )
        self.assertEqual(
            nodes["g02-a09-synthesizer"]["operations"]["finalize_research_state"],
            "research_a09_research_state_finalize",
        )
        self.assertEqual(
            nodes["user-research-gate"]["operations"]["finalize"],
            "research_bundle_finalize",
        )
        self.assertEqual(
            nodes["user-research-gate"]["operations"]["trace"],
            "research_trace",
        )

    def test_manifest_matches_registration(self):
        res = graph_check.check_all()
        self.assertTrue(res["ok"], res)

        manifest = graphs.load("g02")
        registered = graph_check.registered_component_names()
        for node in graphs.nodes(manifest):
            if node["kind"] == "agent":
                self.assertIn(node["name"], registered)
            if node["kind"] == "user-gate":
                self.assertNotIn(node["name"], registered)

    def test_graph_check_validates_script_and_user_gate_contracts(self):
        with tempfile.TemporaryDirectory() as temp:
            graph_path = Path(temp) / "bad.graph.json"
            graph_path.write_text(json.dumps({
                "graph_id": "bad",
                "nodes": [
                    {
                        "name": "bad-script",
                        "kind": "script",
                        "output_contract": "definitely_missing@1",
                    },
                    {
                        "name": "bad-gate",
                        "kind": "user-gate",
                        "produces": ["also_missing@1"],
                    },
                ],
                "sequence": ["bad-script", "bad-gate"],
            }), encoding="utf-8")
            res = graph_check.check_manifest(graph_path, plugin_root=ROOT)
        self.assertFalse(res["ok"], res)
        self.assertIn("bad-script", "\n".join(res["errors"]))
        self.assertIn("bad-gate", "\n".join(res["errors"]))

    def test_graph_check_validates_g02_operations_against_research_mcp(self):
        manifest = graphs.load("g02")
        mutated = json.loads(json.dumps(manifest))
        mutated["nodes"][0]["operations"]["prepare"] = "research_missing_operation"
        with tempfile.TemporaryDirectory() as temp:
            graph_path = Path(temp) / "g02.graph.json"
            graph_path.write_text(json.dumps(mutated), encoding="utf-8")
            res = graph_check.check_manifest(graph_path, plugin_root=ROOT)
        self.assertFalse(res["ok"], res)
        self.assertIn("research_missing_operation", "\n".join(res["errors"]))

    def test_graph_check_rejects_hardcoded_g02_adapter_flow_terms(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "shared" / "contracts").mkdir(parents=True)
            for schema in (ROOT / "shared" / "contracts").glob("*.schema.json"):
                (root / "shared" / "contracts" / schema.name).write_text(
                    schema.read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
            (root / "agents").mkdir()
            for name in ("g02-a01-planner", "g02-a07-paper-review", "g02-a09-synthesizer"):
                (root / "agents" / f"{name}.md").write_text("---\nname: x\n---\n", encoding="utf-8")
            skill = root / "skills" / "g02-orchestrate-research"
            (skill / "adapters").mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "Read shared/graphs/g02.graph.json as source of truth.",
                encoding="utf-8",
            )
            (skill / "adapters" / "codex.md").write_text(
                "Follow this copied sequence: A01 prepare/finalize, Scout fanout.",
                encoding="utf-8",
            )
            graph_path = root / "g02.graph.json"
            graph_path.write_text(json.dumps(graphs.load("g02")), encoding="utf-8")
            res = graph_check.check_manifest(graph_path, plugin_root=root)
        self.assertFalse(res["ok"], res)
        self.assertIn("hardcoded/retired G02 flow term", "\n".join(res["errors"]))

    def test_graph_check_rejects_hardcoded_g02_a01_topic_count_policy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "shared" / "contracts").mkdir(parents=True)
            for schema in (ROOT / "shared" / "contracts").glob("*.schema.json"):
                (root / "shared" / "contracts" / schema.name).write_text(
                    schema.read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
            (root / "agents").mkdir()
            for name in ("g02-a07-paper-review", "g02-a09-synthesizer"):
                (root / "agents" / f"{name}.md").write_text("---\nname: x\n---\n", encoding="utf-8")
            (root / "agents" / "g02-a01-planner.md").write_text(
                "When the scoped limit is six, choose 4-6 groups.",
                encoding="utf-8",
            )
            skill = root / "skills" / "g02-orchestrate-research"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "Read shared/graphs/g02.graph.json as source of truth.",
                encoding="utf-8",
            )
            graph_path = root / "g02.graph.json"
            graph_path.write_text(json.dumps(graphs.load("g02")), encoding="utf-8")
            res = graph_check.check_manifest(graph_path, plugin_root=root)
        self.assertFalse(res["ok"], res)
        self.assertIn("hardcoded G02 planner topic-count policy", "\n".join(res["errors"]))

if __name__ == "__main__":
    unittest.main()
