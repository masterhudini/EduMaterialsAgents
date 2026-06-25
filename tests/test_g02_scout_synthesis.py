"""Offline tests for the deterministic Bounded A09 decision layer."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from core import contracts  # noqa: E402
from g02 import a07_bridge, a09_runner, a09_synthesis  # noqa: E402
from tests import test_g02_scout_a07_bridge as bridge_fixtures  # noqa: E402


def _reviews(*, candidates=None, pointers=None, gaps=None, source_reviews=None) -> dict:
    return {
        "schema_version": "a07_reviews@1",
        "artifact_version": "1.0.0",
        "task_id": "T_SYNTHESIS",
        "status": "completed",
        "scout_run_ref": "missing-scout-run",
        "plan_ref": "plan.json",
        "intake_ref": None,
        "parallel_write_policy": {
            "unit": "topic_source",
            "work_dir": "work",
            "partial_dir": "partial",
            "aggregate_ref": "reviews.json",
            "atomic_write_required": True,
            "worker_write_rule": "one worker, one partial",
        },
        "topic_reviews": [],
        "source_reviews": source_reviews or [],
        "presentation_update_candidates": candidates or [],
        "lookup_pointers": pointers or [],
        "coverage_gaps": gaps or [],
        "irrelevant_sources": [],
        "limitations": [],
    }


def _candidate(
    candidate_id: str,
    finding: str,
    *,
    source_id: str = "SRC_1",
    confidence: str = "supported_by_reviewed_source",
    relation: str = "adds_new_angle",
    evidence=None,
    slides=None,
) -> dict:
    return {
        "candidate_id": candidate_id,
        "topic_id": "TOPIC_1",
        "source_id": source_id,
        "linked_intake_ids": {
            "claim_ids": ["CLM_1"],
            "concept_ids": [],
            "flow_issue_ids": [],
            "update_need_ids": [],
        },
        "presentation_target": {
            "affected_slides": slides or [],
            "section_hint": "Section 1",
        },
        "extension_relation": relation,
        "finding": finding,
        "rationale_vs_existing_presentation": "Fixture rationale.",
        "suggested_slide_action": "add_bullet",
        "draft_insert": finding,
        "evidence_refs": evidence if evidence is not None else [{
            "source_id": source_id,
            "location": "p. 1",
            "quote": finding,
        }],
        "source_refs": [{"source_id": source_id, "title": f"Source {source_id}"}],
        "confidence": confidence,
        "source_type": "canonical",
    }


def _pointer(index: int, *, source_type: str | None = None) -> dict:
    pointer = {
        "pointer_id": f"PTR_{index}",
        "topic_id": "TOPIC_1",
        "source_id": f"SRC_{index}",
        "why_relevant": f"Follow up signal {index}",
        "where_to_look": {
            "matched_terms": [f"term {index}"],
            "pages": [index],
            "work_input_ref": f"work/SRC_{index}.json",
        },
        "linked_intake_ids": {
            "claim_ids": ["CLM_1"],
            "concept_ids": [],
            "flow_issue_ids": [],
            "update_need_ids": [],
        },
        "confidence": "needs_human_check",
    }
    if source_type:
        pointer["source_type"] = source_type
    return pointer


def _solution(reviews: dict, *, deep_dive=None) -> dict:
    prepared = a09_synthesis.prepare_a09_synthesis(reviews)
    solution = a09_synthesis.finalize_a09_solution(
        prepared["synthesis_input"], deep_dive=deep_dive
    )
    checked = contracts.validate(solution, "solution_input_candidate@1")
    if not checked["ok"]:
        raise AssertionError(checked["errors"])
    return solution


class ScoutSynthesisTests(unittest.TestCase):
    def test_dedup_merges_evidence_sources_and_linked_ids(self) -> None:
        first = _candidate("UPD_1", "  Same   substantive signal ", confidence="context_only")
        first["linked_intake_ids"]["claim_ids"] = ["CLM_1"]
        second = _candidate("UPD_2", "same substantive SIGNAL", confidence="supported_by_reviewed_source")
        second["evidence_refs"] = [{
            "source_id": "SRC_1", "location": "p. 2", "quote": "second evidence"
        }]
        second["linked_intake_ids"]["flow_issue_ids"] = ["FLOW_1"]
        third = _candidate("UPD_3", "A different signal", source_id="SRC_2")

        deduped = a09_synthesis._dedup_candidates([first, second, third])

        self.assertEqual(len(deduped), 2)
        self.assertEqual(deduped[0]["candidate_id"], "UPD_2")
        self.assertEqual(len(deduped[0]["evidence_refs"]), 2)
        self.assertEqual(deduped[0]["linked_intake_ids"]["claim_ids"], ["CLM_1"])
        self.assertEqual(deduped[0]["linked_intake_ids"]["flow_issue_ids"], ["FLOW_1"])
        solution = _solution(_reviews(candidates=[first, second, third]))
        self.assertEqual(len(solution["slide_update_plan"]), 2)

    def test_loose_a07_refs_are_normalized_into_contract_shape(self) -> None:
        # Reproduces the host-repair case: A07 emitted evidence_refs without location/quote and
        # source_refs as bare strings. A09 must coerce them so solution_input_candidate@1 validates
        # without any manual editing.
        candidate = _candidate("UPD_LOOSE", "BSM gives a unique no-arbitrage price.")
        candidate["evidence_refs"] = [{"source_id": "SRC_1"}, "p. 12, eq. 3"]
        candidate["source_refs"] = ["SRC_1", "SRC_2"]

        solution = _solution(_reviews(candidates=[candidate]))

        update = solution["suggested_updates"][0]
        for ref in update["evidence_refs"]:
            self.assertEqual({"source_id", "location", "quote"} & set(ref),
                             {"source_id", "location", "quote"})
            self.assertTrue(ref["source_id"])
        for ref in update["source_refs"]:
            self.assertTrue(ref["source_id"])

    def test_grouping_keeps_same_slide_adjacent_and_stable(self) -> None:
        updates = [
            a09_synthesis._ready_update(_candidate("UPD_A", "A", slides=[12]), 1),
            a09_synthesis._ready_update(_candidate("UPD_B", "B", slides=[13]), 2),
            a09_synthesis._ready_update(_candidate("UPD_C", "C", source_id="SRC_3", slides=[12]), 3),
        ]

        grouped = a09_synthesis._group_updates(updates)

        self.assertEqual([item["update_id"] for item in grouped], ["UPD_A", "UPD_C", "UPD_B"])
        solution = _solution(_reviews(candidates=[
            _candidate("UPD_A", "A", slides=[12]),
            _candidate("UPD_B", "B", slides=[13]),
            _candidate("UPD_C", "C", source_id="SRC_3", slides=[12]),
        ]))
        self.assertEqual(
            [item["update_id"] for item in solution["slide_update_plan"]],
            ["UPD_A", "UPD_C", "UPD_B"],
        )

    def test_ranking_moves_weak_updates_to_optional(self) -> None:
        high = _candidate("UPD_HIGH", "Contradictory evidence", relation="contradicts")
        insufficient = _candidate(
            "UPD_WEAK", "Weak evidence", source_id="SRC_2", confidence="insufficient_evidence"
        )
        empty = _candidate("UPD_EMPTY", "No evidence", source_id="SRC_3", evidence=[])

        solution = _solution(_reviews(candidates=[empty, insufficient, high]))

        self.assertEqual([item["update_id"] for item in solution["slide_update_plan"]], ["UPD_HIGH"])
        self.assertEqual(
            {item["update_id"] for item in solution["optional_improvements"]},
            {"UPD_WEAK", "UPD_EMPTY"},
        )
        self.assertEqual(solution["slide_revision_priorities"][0]["update_id"], "UPD_HIGH")

    def test_handoff_is_self_contained_with_opinions_and_coverage(self) -> None:
        covered = _candidate("UPD_COVERED", "Settled finding", slides=[12])
        covered["linked_intake_ids"]["claim_ids"] = ["CL01"]
        gap = {
            "gap_type": "insufficient_evidence",
            "note": "No reviewed source covers CL02.",
            "topic_id": "TOPIC_1",
            "linked_intake_ids": {"claim_ids": ["CL02"]},
        }
        solution = _solution(_reviews(candidates=[covered], gaps=[gap]))

        # Each suggested update carries the analyzed-article opinion, self-contained.
        update = solution["suggested_updates"][0]
        for field in ("finding", "rationale", "extension_relation", "confidence",
                      "evidence_refs", "source_refs", "ready_to_apply_text", "target"):
            self.assertIn(field, update)
        self.assertNotIn("evidence", update)  # legacy key must be gone
        self.assertTrue(update["evidence_refs"])
        self.assertTrue(all(isinstance(ref, dict) for ref in update["source_refs"]))
        self.assertTrue(all(isinstance(s, str) for s in update["target"]["slide_ids"]))

        # coverage_summary states covered vs uncovered per intake element.
        by_id = {row["element_id"]: row for row in solution["coverage_summary"]}
        self.assertEqual(by_id["CL01"]["status"], "covered")
        self.assertEqual(by_id["CL01"]["source_count"], 1)
        self.assertEqual(by_id["CL02"]["status"], "uncovered")

        constraints = solution["graph03_handoff_constraints"]
        for flag in ("no_full_pdfs", "no_full_extracted_text", "no_verbose_paper_reviews",
                     "graph03_must_not_call_g02", "ready_to_apply_updates_required"):
            self.assertTrue(constraints[flag])

    def test_unconsumed_pointers_become_unresolved_items(self) -> None:
        solution = _solution(_reviews(pointers=[_pointer(1), _pointer(2)]))

        pointer_items = [
            item for item in solution["unresolved_items"]
            if item.get("why_unresolved") == "lookup_pointer_not_resolved"
        ]
        self.assertEqual(len(pointer_items), 2)
        self.assertEqual(solution["slide_update_plan"], [])
        self.assertTrue(all("matched terms" in item["what_would_resolve"] for item in pointer_items))

    def test_deep_dive_selector_is_auditable_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp)
            (run / "plan.json").write_text(json.dumps({
                "topics": [{"topic_id": "TOPIC_1", "priority": "high"}]
            }), encoding="utf-8")
            pointers = [_pointer(index) for index in range(1, 9)]
            pointers[1]["conflict"] = True
            pointers[3]["source_type"] = "canonical"
            pointers[4]["source_type"] = "recent"
            candidate = _candidate(
                "UPD_SIGNAL", "Outdated claim", source_id="SRC_1", relation="updates_outdated"
            )
            reviews = _reviews(candidates=[candidate], pointers=pointers)
            reviews["scout_run_ref"] = str(run)

            first = a09_synthesis._select_deep_dive_requests(reviews, max_sources=5)
            second = a09_synthesis._select_deep_dive_requests(reviews, max_sources=5)

        self.assertEqual(first, second)
        self.assertEqual(len(first), 5)
        self.assertEqual(first[0]["selection_criterion"], "high_slide_change_potential")
        self.assertEqual(first[1]["selection_criterion"], "conflicting_findings")
        self.assertTrue(all(item["reason"] for item in first))
        solution = _solution(reviews)
        self.assertTrue(contracts.validate(solution, "solution_input_candidate@1")["ok"])

    def test_gather_deep_dive_windows_expands_and_fails_open(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            tmp = Path(temp)
            run = bridge_fixtures.ScoutA07BridgeTests()._make_run(tmp)
            out = tmp / "a07"
            reviews = a07_bridge.build_a07_reviews(
                run, output_dir=out, max_scan_pages=2
            )
            prepared = a09_synthesis.prepare_a09_synthesis(reviews)
            requests = prepared["synthesis_input"]["deep_dive_requests"]
            selected_count = next(
                item["selected_window_count"] for item in reviews["source_reviews"]
                if item["source_id"] == requests[0]["source_id"]
            )
            expanded = [{
                "window_id": f"W{index:02d}",
                "source_id": requests[0]["source_id"],
                "topic_id": requests[0]["topic_id"],
                "kind": "term_match",
                "page": index,
                "matched_terms": ["FRA notional principal"],
                "char_count": 20,
                "text": f"Expanded window {index}",
            } for index in range(1, selected_count + 3)]
            with mock.patch.object(
                a07_bridge, "select_pdf_windows", return_value=(expanded, [])
            ):
                package = a09_synthesis.gather_deep_dive_windows(reviews, requests)
            self.assertGreater(len(package["requests"][0]["additional_windows"]), selected_count)
            self.assertLessEqual(len(package["requests"][0]["additional_windows"]), 12)
            self.assertTrue(contracts.validate(package, "a07_deep_dive@1")["ok"])

            pdf_path = run / "topics" / "TOPIC_FRA_SETTLEMENT" / "pdf" / "fra_settlement.pdf"
            pdf_path.unlink()
            missing = a09_synthesis.gather_deep_dive_windows(reviews, requests)
            self.assertEqual(missing["requests"][0]["additional_windows"], [])
            self.assertTrue(missing["requests"][0]["limitation"])

    def test_deep_dive_becomes_recommendation_or_coverage_gap(self) -> None:
        reviews = _reviews(
            pointers=[_pointer(1), _pointer(2)],
            source_reviews=[
                {"source_id": "SRC_1", "title": "Source 1", "source_type": "canonical"},
                {"source_id": "SRC_2", "title": "Source 2", "source_type": "recent"},
            ],
        )
        prepared = a09_synthesis.prepare_a09_synthesis(reviews)
        requests = deepcopy(prepared["synthesis_input"]["deep_dive_requests"])
        by_source = {item["source_id"]: item for item in requests}
        by_source["SRC_1"]["additional_windows"] = [{
            "window_id": "W05",
            "source_id": "SRC_1",
            "topic_id": "TOPIC_1",
            "kind": "term_match",
            "page": 5,
            "matched_terms": ["term 1"],
            "char_count": 30,
            "text": "A matched bounded source passage.",
        }]
        by_source["SRC_1"]["limitations"] = []
        by_source["SRC_1"]["limitation"] = None
        by_source["SRC_2"]["additional_windows"] = [{
            "window_id": "W01",
            "source_id": "SRC_2",
            "topic_id": "TOPIC_1",
            "kind": "overview",
            "page": 1,
            "matched_terms": [],
            "char_count": 20,
            "text": "No targeted match.",
        }]
        by_source["SRC_2"]["limitations"] = []
        by_source["SRC_2"]["limitation"] = None
        deep_dive = {
            "schema_version": "a07_deep_dive@1",
            "artifact_version": "1.0.0",
            "task_id": reviews["task_id"],
            "scout_run_ref": reviews["scout_run_ref"],
            "max_windows_per_source": 12,
            "max_chars_per_window": 1800,
            "requests": list(by_source.values()),
            "limitations": [],
        }

        solution = a09_synthesis.finalize_a09_solution(
            prepared["synthesis_input"], deep_dive=deep_dive
        )

        self.assertEqual(len(solution["slide_update_plan"]), 1)
        self.assertEqual(solution["slide_update_plan"][0]["source_id"], "SRC_1")
        self.assertTrue(any(
            gap.get("gap_type") == "deep_dive_no_matching_signal"
            for gap in solution["coverage_gaps"]
        ))
        self.assertEqual(
            sum(item.get("why_unresolved") == "lookup_pointer_not_resolved"
                for item in solution["unresolved_items"]),
            1,
        )
        self.assertTrue(contracts.validate(solution, "solution_input_candidate@1")["ok"])

    def test_a09_model_task_contract_compact_intake_and_budget(self) -> None:
        candidate = _candidate("UPD_A09", "Verified FRA update")
        candidate["linked_intake_ids"] = {
            "driver_ids": ["DRV01"],
            "claim_ids": ["CL01"],
            "concept_ids": ["C01"],
            "flow_issue_ids": ["FI01"],
            "update_need_ids": [],
        }
        intake = json.loads(
            (ROOT / "mocks" / "g02" / "KP_intake_bundle.json").read_text(
                encoding="utf-8"
            )
        )
        intake["task_id"] = "T_SYNTHESIS"
        built = a09_runner.build_a09_task(
            _reviews(candidates=[candidate]),
            intake=intake,
        )

        task = built["task"]
        checked = contracts.validate(task, "a09_synthesis_task@1")
        self.assertTrue(checked["ok"], checked["errors"])
        self.assertEqual(task["model_policy"]["recommended_model"], "opus")
        self.assertEqual(task["model_policy"]["reasoning_effort"], "medium")
        self.assertEqual(task["model_policy"]["max_deep_dive_sources"], 5)
        self.assertEqual(task["model_policy"]["max_windows_per_source"], 8)
        self.assertEqual(task["model_policy"]["max_chars_per_window"], 1200)
        self.assertEqual(built["deep_dive"]["max_windows_per_source"], 8)
        self.assertEqual(built["deep_dive"]["max_chars_per_window"], 1200)
        self.assertEqual(task["intake_context"]["claim_cards"][0]["claim_id"], "CL01")
        self.assertEqual(
            task["intake_context"]["selected_flow_issue_cards"][0]["issue_id"],
            "FI01",
        )
        with self.assertRaisesRegex(ValueError, "between 1 and 8"):
            a09_runner.build_a09_task(
                _reviews(candidates=[candidate]), deep_dive_windows=9
            )

    def test_a09_runner_model_pass_refines_baseline(self) -> None:
        reviews = _reviews(candidates=[_candidate("UPD_MODEL", "Model-checked update")])

        def executor(task: dict) -> dict:
            baseline = task["deterministic_baseline"]
            return {
                "slide_update_plan": deepcopy(baseline["slide_update_plan"]),
                "slide_revision_priorities": deepcopy(
                    baseline["slide_revision_priorities"]
                ),
                "optional_improvements": deepcopy(baseline["optional_improvements"]),
                "do_not_change": [],
                "unresolved_items": deepcopy(baseline["unresolved_items"]),
                "deep_dive_used": [],
                "confidence": "medium",
            }

        result = a09_runner.run_a09(reviews, executor)

        self.assertTrue(result["a09_model_pass"])
        self.assertEqual(result["synthesis_engine"], "a09_opus_medium")
        self.assertIsNone(result["executor_error"])
        checked = contracts.validate(result["solution"], "solution_input_candidate@1")
        self.assertTrue(checked["ok"], checked["errors"])

    def test_a09_runner_executor_failure_uses_auditable_fallback(self) -> None:
        reviews = _reviews(candidates=[_candidate("UPD_FALLBACK", "Fallback update")])

        def executor(_task: dict) -> dict:
            raise RuntimeError("fixture executor failure")

        result = a09_runner.run_a09(reviews, executor)

        self.assertFalse(result["a09_model_pass"])
        self.assertEqual(result["synthesis_engine"], "deterministic_fallback")
        self.assertIn("fixture executor failure", result["executor_error"])
        checked = contracts.validate(result["solution"], "solution_input_candidate@1")
        self.assertTrue(checked["ok"], checked["errors"])

        prepared = a09_synthesis.prepare_a09_synthesis(reviews)
        empty_output = a09_synthesis.finalize_a09_solution(
            prepared["synthesis_input"], output={}
        )
        self.assertFalse(empty_output["a09_model_pass"])
        self.assertEqual(empty_output["synthesis_engine"], "deterministic_fallback")
        with self.assertRaisesRegex(ValueError, "A09 output missing"):
            a09_synthesis.finalize_a09_solution(
                prepared["synthesis_input"], output={"confidence": "medium"}
            )


if __name__ == "__main__":
    unittest.main()
