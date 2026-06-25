"""G03 boundary tests for joining G01 lecture_baseline with G02 research hand-offs."""
from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from core import artifacts, contracts  # noqa: E402
from g03 import blueprint  # noqa: E402
from g03 import g03_flow  # noqa: E402
from g03 import render as solution_render  # noqa: E402
from g03 import solution  # noqa: E402
from mcp import solution_server as solution_srv  # noqa: E402


def _load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def _candidate_join_targets(lecture_baseline: dict, research_bundle: dict) -> dict[str, list[str]]:
    claim_to_slides: dict[str, list[str]] = {}
    concept_to_slides: dict[str, list[str]] = {}
    for slide in lecture_baseline["slides"]:
        slide_id = slide["slide_id"]
        for claim_id in slide.get("claim_ids", []):
            claim_to_slides.setdefault(claim_id, []).append(slide_id)
        for concept_id in slide.get("concept_ids", []):
            concept_to_slides.setdefault(concept_id, []).append(slide_id)

    resolved: dict[str, list[str]] = {}
    for update in research_bundle.get("suggested_updates", []):
        linked = update.get("linked_intake_ids", {})
        slide_ids: list[str] = []
        for claim_id in linked.get("claim_ids", []):
            slide_ids.extend(claim_to_slides.get(claim_id, []))
        if not slide_ids:
            for concept_id in linked.get("concept_ids", []):
                slide_ids.extend(concept_to_slides.get(concept_id, []))
        resolved[update["update_id"]] = sorted(set(slide_ids))
    return resolved


class G03SolutionInputTests(unittest.TestCase):
    def test_real_g02_solution_input_candidate_validates(self) -> None:
        candidate = _load("mocks/g02/EXAMPLE g02-a09-solution_input_candidate.artifact.json")

        checked = contracts.validate(candidate, "solution_input_candidate@1")

        self.assertTrue(checked["ok"], checked["errors"])

    def test_front_door_accepts_real_candidate_with_explicit_kind(self) -> None:
        request = _load("mocks/g03/solution_request.json")
        request["task_id"] = "T_SYNTHESIS"
        request["research_bundle_kind"] = "solution_input_candidate"
        request["research_bundle"] = _load(
            "mocks/g02/EXAMPLE g02-a09-solution_input_candidate.artifact.json"
        )
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)

            ref = solution.build_solution_input(request, base=base)
            composite = artifacts.hydrate(ref, base=base)
            research_bundle = artifacts.hydrate(composite["research_bundle_ref"], base=base)

        self.assertEqual(composite["schema_version"], "solution_graph_input@1")
        self.assertEqual(composite["research_bundle_kind"], "solution_input_candidate")
        self.assertEqual(research_bundle["schema_version"], "solution_input_candidate@1")

    def test_front_door_auto_detects_inline_candidate_schema(self) -> None:
        request = _load("mocks/g03/solution_request.candidate.json")
        request.pop("research_bundle_kind")
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)

            ref = solution.build_solution_input(request, base=base)
            composite = artifacts.hydrate(ref, base=base)

        self.assertEqual(composite["research_bundle_kind"], "solution_input_candidate")

    def test_front_door_keeps_legacy_default_when_kind_is_absent(self) -> None:
        request = _load("mocks/g03/solution_request.json")
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)

            ref = solution.build_solution_input(request, base=base)
            composite = artifacts.hydrate(ref, base=base)
            research_bundle = artifacts.hydrate(composite["research_bundle_ref"], base=base)

        self.assertEqual(composite["research_bundle_kind"], "user_approved_research_bundle")
        self.assertEqual(research_bundle["schema_version"], "user_approved_research_bundle@1")

    def test_candidate_mock_has_real_join_keys_for_g03(self) -> None:
        request = _load("mocks/g03/solution_request.candidate.json")
        checked = contracts.validate(request["lecture_baseline"], "lecture_baseline@1")
        self.assertTrue(checked["ok"], checked["errors"])
        checked = contracts.validate(request["research_bundle"], "solution_input_candidate@1")
        self.assertTrue(checked["ok"], checked["errors"])

        resolved = _candidate_join_targets(request["lecture_baseline"], request["research_bundle"])

        self.assertEqual(resolved["UPD_FRA_PRICING"], ["p012"])
        self.assertEqual(resolved["UPD_FRA_SETTLE"], ["p013"])

    def test_candidate_request_path_resolves_through_front_door(self) -> None:
        path = ROOT / "mocks" / "g03" / "solution_request.candidate.json"
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)

            ref = solution.resolve_context(path, base=base)
            composite = artifacts.hydrate(ref, base=base)

        self.assertEqual(composite["task_id"], "SOLUTION_CANDIDATE_MOCK_001")
        self.assertEqual(composite["research_bundle_kind"], "solution_input_candidate")

    def test_front_door_preserves_explicit_candidate_kind(self) -> None:
        request = copy.deepcopy(_load("mocks/g03/solution_request.candidate.json"))
        request["research_bundle_kind"] = "solution_input_candidate"
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)

            ref = solution.build_solution_input(request, base=base)
            composite = artifacts.hydrate(ref, base=base)

        self.assertEqual(composite["research_bundle_kind"], "solution_input_candidate")

    def test_solution_mcp_front_door_describes_dual_input_candidate(self) -> None:
        response = solution_srv.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        tools = {item["name"]: item for item in response["result"]["tools"]}

        front_door = tools["solution_front_door"]
        blueprint_build = tools["solution_blueprint_build"]
        blueprint_render = tools["solution_blueprint_render"]
        context_description = front_door["inputSchema"]["properties"]["context"]["description"]

        self.assertIn("dual-input G03 request", front_door["description"])
        self.assertIn("solution_blueprint@1", blueprint_build["description"])
        self.assertIn("Markdown plan", blueprint_render["description"])
        self.assertIn("solution_input_candidate@1", context_description)
        self.assertIn("research_bundle_kind", context_description)

    def test_solution_mcp_prompt_points_to_candidate_request(self) -> None:
        response = solution_srv.handle({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "prompts/get",
            "params": {
                "name": "solution",
                "arguments": {"context": "mocks/g03/solution_request.candidate.json"},
            },
        })
        text = response["result"]["messages"][0]["content"]["text"]

        self.assertIn("solution_input_candidate@1", text)
        self.assertIn("research_bundle_kind='solution_input_candidate'", text)
        self.assertIn("solution_blueprint_render", text)
        self.assertIn("mocks/g03/solution_request.candidate.json", text)

    def test_builds_solution_blueprint_from_candidate_request(self) -> None:
        path = ROOT / "mocks" / "g03" / "solution_request.candidate.json"

        with tempfile.TemporaryDirectory() as tmp:
            result = blueprint.build_blueprint(path, base=Path(tmp))
        checked = contracts.validate(result, "solution_blueprint@1")
        updates = {item["update_id"]: item for item in result["applied_updates"]}
        deferred = result["deferred_items"]

        self.assertTrue(checked["ok"], checked["errors"])
        self.assertEqual(result["task_id"], "SOLUTION_CANDIDATE_MOCK_001")
        self.assertEqual(result["output_language"], "Polish")
        self.assertEqual(result["lecture_outline"][0]["slide_ids"], ["p012", "p013", "p014"])
        self.assertEqual(updates["UPD_FRA_PRICING"]["target_slide_ids"], ["p012"])
        self.assertEqual(updates["UPD_FRA_SETTLE"]["target_slide_ids"], ["p013"])
        self.assertEqual(updates["UPD_FRA_PRICING"]["target_section_id"], "S1")
        self.assertIn("p012", updates["UPD_FRA_PRICING"]["change_summary"])
        self.assertEqual(
            {item["source_ref"] for item in result["source_attribution"]},
            {"SRC_FRA_PRICING", "SRC_FRA_SETTLE"},
        )
        self.assertTrue(any(item.get("related_claim_ref") == "CL03" for item in deferred))

    def test_renders_candidate_blueprint_to_markdown_and_inline_summary(self) -> None:
        path = ROOT / "mocks" / "g03" / "solution_request.candidate.json"

        with tempfile.TemporaryDirectory() as tmp:
            result = blueprint.build_blueprint(path, base=Path(tmp))
            rendered = solution_render.render_blueprint(result)

        self.assertIn("# Nowy plan prezentacji z poprawkami", rendered["markdown"])
        self.assertIn("UPD_FRA_PRICING", rendered["markdown"])
        self.assertIn("UPD_FRA_SETTLE", rendered["markdown"])
        self.assertIn("`p012`", rendered["markdown"])
        self.assertIn("`p013`", rendered["markdown"])
        self.assertIn("SRC_FRA_PRICING", rendered["markdown"])
        self.assertIn("CL03", rendered["markdown"])
        self.assertEqual(rendered["metrics"]["applied_updates"], 2)
        self.assertIn("2 zastosowane poprawki", rendered["inline_summary"])

    def test_renders_legacy_blueprint_to_markdown(self) -> None:
        path = ROOT / "mocks" / "g03" / "solution_request.json"

        with tempfile.TemporaryDirectory() as tmp:
            result = blueprint.build_blueprint(path, base=Path(tmp))
            rendered = solution_render.render_blueprint(result)

        self.assertIn("F1", rendered["markdown"])
        self.assertIn("SRC_001", rendered["markdown"])
        self.assertIn("solution_blueprint@1 SOLUTION_MOCK_001", rendered["inline_summary"])

    def test_solution_mcp_renders_candidate_blueprint(self) -> None:
        path = ROOT / "mocks" / "g03" / "solution_request.candidate.json"
        with tempfile.TemporaryDirectory() as tmp:
            result = blueprint.build_blueprint(path, base=Path(tmp))

        response = solution_srv.handle({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "solution_blueprint_render",
                "arguments": {"blueprint": result},
            },
        })
        content = response["result"]["content"][0]["text"]
        rendered = json.loads(content)

        self.assertIn("Nowy plan prezentacji z poprawkami", rendered["markdown"])
        self.assertIn("UPD_FRA_PRICING", rendered["markdown"])
        self.assertIn("2 zastosowane poprawki", rendered["inline_summary"])

    def test_persists_markdown_render_as_text_artifact(self) -> None:
        path = ROOT / "mocks" / "g03" / "solution_request.candidate.json"

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            result = blueprint.build_blueprint(path, base=base)
            rendered = solution_render.render_blueprint(result, base=base, persist=True)
            markdown = artifacts.resolve_path(rendered["ref"], base=base).read_text(encoding="utf-8")

        self.assertTrue(rendered["ref"].endswith(".solution-plan.md"))
        self.assertIn("Nowy plan prezentacji z poprawkami", markdown)
        self.assertIn("UPD_FRA_SETTLE", markdown)

    def test_hosted_g03_candidate_run_reaches_user_gate_and_renders_final_blueprint(self) -> None:
        path = ROOT / "mocks" / "g03" / "solution_request.candidate.json"

        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"EMAGENTS_HOME": tmp}):
            base = Path(tmp) / "artifacts"
            front = g03_flow.front_door(path, base=base)

            step = g03_flow.run(front["ref"], base=base, pause_on_node=True, pause_on_gate=True)
            self.assertEqual(step["status"], "awaiting_node")
            self.assertEqual(step["node"], "g03-a01-solution-architect")

            built = blueprint.build_blueprint(step["input"], base=base)
            finalized = solution.finalize_blueprint(built["task_id"], built, base=base)
            produced_ref = finalized["produced"][0]["path"]

            step = g03_flow.run(
                None,
                base=base,
                pause_on_node=True,
                pause_on_gate=True,
                resume_token=step["resume_token"],
                node_results={"g03-a01-solution-architect": produced_ref},
            )
            self.assertEqual(step["status"], "awaiting_review")

            step = g03_flow.run(
                None,
                base=base,
                pause_on_node=True,
                pause_on_gate=True,
                resume_token=step["resume_token"],
                review_decisions={"g03-a01-solution-architect": {"decision": "APPROVED", "findings": []}},
            )
            self.assertEqual(step["status"], "awaiting_user")
            self.assertEqual(step["gate"], "user-solution-gate")

            final = g03_flow.run(
                None,
                base=base,
                pause_on_node=True,
                pause_on_gate=True,
                resume_token=step["resume_token"],
                decisions={
                    "user-solution-gate": {
                        "approve_outline": True,
                        "approve_applied_updates": True,
                        "confirm_deferrals": True,
                    }
                },
            )
            final_blueprint = artifacts.hydrate(final["ref"], base=base)
            rendered = solution_render.render_blueprint(final_blueprint, base=base)

        self.assertEqual(final["schema_version"], "solution_blueprint@1")
        self.assertTrue(contracts.validate(final_blueprint, "solution_blueprint@1")["ok"])
        self.assertIn("UPD_FRA_PRICING", rendered["markdown"])
        self.assertIn("2 zastosowane poprawki", rendered["inline_summary"])

    def test_builds_solution_blueprint_from_legacy_request(self) -> None:
        path = ROOT / "mocks" / "g03" / "solution_request.json"

        with tempfile.TemporaryDirectory() as tmp:
            result = blueprint.build_blueprint(path, base=Path(tmp))
        checked = contracts.validate(result, "solution_blueprint@1")
        updates = {item["update_id"]: item for item in result["applied_updates"]}

        self.assertTrue(checked["ok"], checked["errors"])
        self.assertEqual(result["task_id"], "SOLUTION_MOCK_001")
        self.assertEqual(updates["F1"]["target_slide_ids"], ["p012"])
        self.assertEqual(updates["F1"]["source_refs"], ["SRC_001"])
        self.assertTrue(any(item["item_id"] == "CLM_009" for item in result["deferred_items"]))

    def test_locked_candidate_slide_is_deferred_not_applied(self) -> None:
        request = copy.deepcopy(_load("mocks/g03/solution_request.candidate.json"))
        request["lecture_baseline"]["slides"][0]["locked"] = True

        with tempfile.TemporaryDirectory() as tmp:
            result = blueprint.build_blueprint(request, base=Path(tmp))
        update_ids = {item["update_id"] for item in result["applied_updates"]}
        deferred = {item["item_id"]: item for item in result["deferred_items"]}

        self.assertNotIn("UPD_FRA_PRICING", update_ids)
        self.assertIn("UPD_FRA_SETTLE", update_ids)
        self.assertIn("UPD_FRA_PRICING", deferred)
        self.assertIn("locked", deferred["UPD_FRA_PRICING"]["reason"])

    def test_candidate_join_does_not_trust_target_slide_hint(self) -> None:
        request = copy.deepcopy(_load("mocks/g03/solution_request.candidate.json"))
        request["research_bundle"]["suggested_updates"][0]["linked_intake_ids"]["claim_ids"] = ["UNKNOWN"]
        request["research_bundle"]["suggested_updates"][0]["linked_intake_ids"]["concept_ids"] = []

        with tempfile.TemporaryDirectory() as tmp:
            result = blueprint.build_blueprint(request, base=Path(tmp))
        update_ids = {item["update_id"] for item in result["applied_updates"]}
        deferred = {item["item_id"]: item for item in result["deferred_items"]}

        self.assertNotIn("UPD_FRA_PRICING", update_ids)
        self.assertIn("UPD_FRA_PRICING", deferred)
        self.assertIn("No matching unlocked lecture slide", deferred["UPD_FRA_PRICING"]["reason"])


if __name__ == "__main__":
    unittest.main()
