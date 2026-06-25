"""Offline tests for the Scout -> A07 light-review bridge."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from core import contracts  # noqa: E402
from g02 import scout_a07_bridge, scout_a07_runner, scout_fanout, scout_synthesis  # noqa: E402


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _pdf(path: Path, text: str) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = f"%PDF-1.4\n({text})\n%%EOF\n".encode("latin-1", errors="ignore")
    path.write_bytes(raw)
    return {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "byte_count": len(raw),
    }


def _plan() -> dict:
    return {
        "schema_version": "research_plan@1",
        "artifact_version": "1.0.0",
        "task_id": "T_SCOUT_A07",
        "approved_research_scope": {
            "include_canonical_sources": True,
            "include_recent_developments": True,
            "recency_window_years": 5,
            "verify_claims": {"priority": ["high"], "claim_ids": ["CL01"]},
        },
        "topics": [{
            "topic_id": "TOPIC_FRA_SETTLEMENT",
            "name": "FRA cash settlement mechanics",
            "purpose": "Find sources explaining forward rate agreement cash settlement and notional principal.",
            "priority": "high",
            "linked_driver_ids": ["DRV01"],
            "related_claims": ["CL01"],
            "related_concepts": ["C01"],
            "related_flow_issues": [],
            "related_update_needs": [],
            "approved_domains": ["D01"],
            "source_roles_required": {
                "canonical": True,
                "current": False,
                "survey": False,
                "didactic": False,
                "qualifying_or_critical": False,
            },
            "search_strategy": {
                "core_terms": [
                    "forward rate agreement cash settlement",
                    "FRA notional principal",
                ],
                "allowed_expansion_areas": ["OTC interest rate derivative"],
                "excluded_terms": ["day care", "astronomy"],
                "year_from": None,
                "year_to": None,
                "languages": ["en"],
                "work_types": ["article"],
                "seed_sources": [],
            },
            "coverage_requirements": [{
                "coverage_id": "COV_FRA_SETTLEMENT",
                "description": "Source explicitly states that an FRA settles the interest differential in cash.",
                "source_roles": ["canonical"],
                "minimum_sources": 1,
                "mandatory": True,
            }],
            "stop_rule": {
                "candidate_limit": 12,
                "no_new_coverage_passes": 2,
                "complementary_search_route_required": True,
            },
        }],
        "uncovered_driver_ids": [],
        "input_issues": [],
        "global_constraints": {
            "allowed_languages": ["en"],
            "allowed_work_types": ["article"],
            "candidate_limit_per_topic": 12,
            "max_topics": 6,
            "no_new_coverage_passes": 2,
            "year_from": None,
            "year_to": None,
        },
        "output_language": "pl",
        "review_profile_ref": "research_plan",
    }


class ScoutA07BridgeTests(unittest.TestCase):
    def _make_run(self, tmp: Path) -> Path:
        run = tmp / "outputs" / "g02" / "T_SCOUT_A07" / "scout"
        plan = _plan()
        request = {
            "schema_version": "scout_search_request@1",
            "artifact_version": "1.0.0",
            "task_id": "T_SCOUT_A07",
            "topic_id": "TOPIC_FRA_SETTLEMENT",
            "query": "forward rate agreement cash settlement FRA notional principal",
            "keywords": [
                "forward rate agreement cash settlement",
                "FRA notional principal",
                "OTC interest rate derivative",
            ],
            "intent": plan["topics"][0]["purpose"],
            "target_n": 10,
            "year_from": None,
            "recency_year_from": 2021,
            "year_to": None,
            "lang": "en",
            "work_type": "",
            "output_language": "pl",
            "excluded_terms": ["day care", "astronomy"],
            "quota_canonical": 0.4,
            "snowball": True,
            "created_from": {
                "task_id": "T_SCOUT_A07",
                "topic_id": "TOPIC_FRA_SETTLEMENT",
            },
        }
        good = _pdf(
            run / "topics" / "TOPIC_FRA_SETTLEMENT" / "pdf" / "fra_settlement.pdf",
            "Forward rate agreement cash settlement uses a notional principal to settle the interest differential.",
        )
        bad = _pdf(
            run / "topics" / "TOPIC_FRA_SETTLEMENT" / "pdf" / "day_care.pdf",
            "Systematic reviews of day care for mental disorders and outpatient treatment.",
        )
        corpus = {
            "schema_version": "scout_retrieved_corpus@1",
            "artifact_version": "1.0.0",
            "task_id": "T_SCOUT_A07",
            "topic_id": "TOPIC_FRA_SETTLEMENT",
            "run_id": "T_SCOUT_A07__TOPIC_FRA_SETTLEMENT",
            "research_plan_ref": "plan.json",
            "request_ref": "requests/TOPIC_FRA_SETTLEMENT.json",
            "documents": [
                {
                    "source_id": "SCOUT_GOOD",
                    "local_ref": "topics/TOPIC_FRA_SETTLEMENT/pdf/fra_settlement.pdf",
                    "sha256": good["sha256"],
                    "byte_count": good["byte_count"],
                    "doi": "10.1000/fra",
                    "title": "Forward rate agreement cash settlement and notional principal",
                    "year": 2018,
                    "fwci": None,
                    "venue": "Journal of Interest Rate Derivatives",
                    "work_type": "article",
                    "source_type": "canonical",
                    "source_type_basis": "pre-window year 2018 < 2021",
                    "topic_ids": ["TOPIC_FRA_SETTLEMENT"],
                },
                {
                    "source_id": "SCOUT_BAD",
                    "local_ref": "topics/TOPIC_FRA_SETTLEMENT/pdf/day_care.pdf",
                    "sha256": bad["sha256"],
                    "byte_count": bad["byte_count"],
                    "doi": "10.1000/day-care",
                    "title": "Systematic reviews of the effectiveness of day care for people with severe mental disorders",
                    "year": 2001,
                    "fwci": None,
                    "venue": "Health Technology Assessment",
                    "work_type": "article",
                    "source_type": "canonical",
                    "source_type_basis": "pre-window year 2001 < 2021",
                    "topic_ids": ["TOPIC_FRA_SETTLEMENT"],
                },
            ],
            "retrieval_summary": {
                "target_count": 10,
                "downloaded_count": 2,
                "stub_count": 0,
                "rejected_count": 0,
            },
        }
        index = {
            "schema_version": "scout_run_index@1",
            "artifact_version": "1.0.0",
            "task_id": "T_SCOUT_A07",
            "status": "completed",
            "execution_profile": "scout",
            "total_target": 10,
            "allocated_target": 10,
            "plan_ref": "plan.json",
            "topics": [{
                "topic_id": "TOPIC_FRA_SETTLEMENT",
                "run_id": "T_SCOUT_A07__TOPIC_FRA_SETTLEMENT",
                "status": "completed",
                "target_n": 10,
                "request_ref": "requests/TOPIC_FRA_SETTLEMENT.json",
                "pdf_dir": "topics/TOPIC_FRA_SETTLEMENT/pdf",
                "manifest_ref": "topics/TOPIC_FRA_SETTLEMENT/MANIFEST.md",
                "retrieved_corpus_ref": "topics/TOPIC_FRA_SETTLEMENT/retrieved_corpus.json",
                "counts": {"downloaded": 2, "stubs": 0, "rejected": 0},
                "error": None,
            }],
            "deduplicated_works": [],
            "summary": {
                "topic_count": 1,
                "completed_topic_count": 1,
                "failed_topic_count": 0,
                "downloaded_pdf_count": 2,
                "unique_work_count": 2,
            },
        }
        _write_json(run / "plan.json", plan)
        _write_json(run / "index.json", index)
        _write_json(run / "requests" / "TOPIC_FRA_SETTLEMENT.json", request)
        _write_json(run / "topics" / "TOPIC_FRA_SETTLEMENT" / "retrieved_corpus.json", corpus)
        (run / "topics" / "TOPIC_FRA_SETTLEMENT" / "MANIFEST.md").write_text("# MANIFEST\n", encoding="utf-8")
        return run

    def test_prefilter_generalizes_to_non_fra_domain(self) -> None:
        # Regression for the hardcoded-FRA prefilter: anchors must be derived
        # dynamically from the plan, so a completely different domain still
        # produces review_candidate / context_only / irrelevant correctly.
        plan = {
            "schema_version": "research_plan@1",
            "artifact_version": "1.0.0",
            "task_id": "T_BAYES",
            "topics": [{
                "topic_id": "TOPIC_SCALABLE_BAYES",
                "name": "Scalable Bayesian inference and variational methods",
                "purpose": "Find sources on scalable posterior approximation for Bayesian models.",
                "linked_driver_ids": ["DRV01"],
                "related_claims": ["CL01"],
                "related_concepts": [],
                "related_flow_issues": [],
                "related_update_needs": [],
                "search_strategy": {
                    "core_terms": [
                        "scalable Bayesian inference",
                        "variational inference",
                        "stochastic gradient MCMC",
                    ],
                    "allowed_expansion_areas": ["posterior approximation"],
                    "excluded_terms": ["day care", "astronomy"],
                    "languages": ["en"],
                    "work_types": ["article"],
                },
                "coverage_requirements": [],
            }],
        }
        lens = scout_a07_bridge._topic_lenses(plan, {})["TOPIC_SCALABLE_BAYES"]
        # No FRA vocabulary should leak into a Bayesian topic lens.
        self.assertNotIn("fra", lens["anchor_tokens"])
        self.assertIn("variational", lens["anchor_tokens"])

        on_topic = scout_a07_bridge.prefilter_source(
            {"title": "Scalable variational inference for Bayesian neural networks",
             "venue": "Journal of Machine Learning Research", "work_type": "article"},
            lens,
        )
        background = scout_a07_bridge.prefilter_source(
            {"title": "Posterior predictive checks in applied statistics",
             "venue": "Statistical Science", "work_type": "article"},
            lens,
        )
        off_domain = scout_a07_bridge.prefilter_source(
            {"title": "Systematic reviews of day care for people with mental disorders",
             "venue": "Health Technology Assessment", "work_type": "article"},
            lens,
        )
        self.assertEqual(on_topic["status"], "review_candidate")
        self.assertEqual(background["status"], "context_only")
        self.assertEqual(off_domain["status"], "irrelevant_for_topic")

    def test_bridge_prepares_parallel_safe_work_items_and_filters_noise(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            tmp = Path(temp)
            run = self._make_run(tmp)
            out = tmp / "outputs" / "g02" / "T_SCOUT_A07" / "a07"

            reviews = scout_a07_bridge.build_scout_a07_reviews(
                run,
                output_dir=out,
                intake_ref="mocks/g02/KP_intake_bundle.json",
                max_scan_pages=2,
            )

            checked = contracts.validate(reviews, "scout_a07_reviews@1")
            self.assertTrue(checked["ok"], checked["errors"])
            self.assertTrue((out / "reviews.json").is_file())
            self.assertEqual(reviews["status"], "prepared")
            self.assertEqual(len(reviews["source_reviews"]), 2)
            by_source = {item["source_id"]: item for item in reviews["source_reviews"]}
            self.assertEqual(by_source["SCOUT_GOOD"]["prefilter_status"], "review_candidate")
            self.assertGreaterEqual(by_source["SCOUT_GOOD"]["selected_window_count"], 1)
            self.assertEqual(by_source["SCOUT_BAD"]["prefilter_status"], "irrelevant_for_topic")
            self.assertEqual(by_source["SCOUT_BAD"]["selected_window_count"], 0)
            self.assertEqual(len(reviews["irrelevant_sources"]), 1)
            self.assertEqual(reviews["parallel_write_policy"]["unit"], "topic_source")
            good_work = out / by_source["SCOUT_GOOD"]["work_input_ref"]
            bad_work = out / by_source["SCOUT_BAD"]["work_input_ref"]
            self.assertTrue(good_work.is_file())
            self.assertTrue(bad_work.is_file())
            work_payload = json.loads(good_work.read_text(encoding="utf-8"))
            self.assertTrue(work_payload["review_budget"]["full_pdf_forbidden"])
            self.assertIn("selected_windows", work_payload)
            self.assertFalse((out / by_source["SCOUT_GOOD"]["worker_output_ref"]).exists())

    def test_partial_reviews_aggregate_and_feed_scout_fast_a09(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            tmp = Path(temp)
            run = self._make_run(tmp)
            out = tmp / "outputs" / "g02" / "T_SCOUT_A07" / "a07"
            reviews = scout_a07_bridge.build_scout_a07_reviews(
                run,
                output_dir=out,
                intake_ref=str(ROOT / "mocks" / "g02" / "KP_intake_bundle.json"),
                max_scan_pages=2,
            )
            good = next(item for item in reviews["source_reviews"]
                        if item["source_id"] == "SCOUT_GOOD")
            work_path = out / good["work_input_ref"]

            partial = scout_a07_bridge.finalize_scout_a07_partial(work_path, {
                "review_status": "useful_for_update",
                "confidence": "medium",
                "presentation_update_candidates": [{
                    "finding": "FRA settlement should be described as a cash settlement of the interest differential on a notional principal.",
                    "rationale_vs_existing_presentation": "This directly supports the claim that notional is a settlement base rather than exchanged principal.",
                    "suggested_slide_action": "add_bullet",
                    "draft_insert": "FRA settlement is cash based: only the interest differential is paid, calculated on a notional principal.",
                    "evidence_refs": [{
                        "source_id": "SCOUT_GOOD",
                        "location": "selected window W01",
                        "quote": "cash settlement uses a notional principal",
                    }],
                }],
                "limitations": ["Fixture A07 review."],
            })

            self.assertTrue(contracts.validate(partial, "scout_a07_partial_review@1")["ok"])
            aggregated = scout_a07_bridge.aggregate_scout_a07_reviews(out)
            self.assertEqual(aggregated["status"], "completed")
            self.assertEqual(len(aggregated["presentation_update_candidates"]), 1)
            self.assertTrue(contracts.validate(aggregated, "scout_a07_reviews@1")["ok"])

            prepared = scout_synthesis.prepare_scout_fast_synthesis(
                out / "reviews.json",
                intake=ROOT / "mocks" / "g02" / "KP_intake_bundle.json",
            )
            self.assertTrue(prepared["ready"])
            self.assertLessEqual(
                len(prepared["synthesis_input"]["deep_dive_requests"]), 5
            )
            solution = scout_synthesis.finalize_scout_fast_solution(
                prepared["synthesis_input"],
            )
            checked = contracts.validate(solution, "solution_input_candidate@1")
            self.assertTrue(checked["ok"], checked["errors"])
            self.assertEqual(solution["synthesis_mode"], "scout_fast")
            self.assertEqual(solution["a08_status"], "skipped_scout_fast")
            self.assertEqual(len(solution["slide_update_plan"]), 1)
            self.assertTrue(solution["graph03_handoff_constraints"]["graph03_must_not_call_g02"])

    def test_runner_builds_model_tasks_and_executes_parallel_partials(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            tmp = Path(temp)
            run = self._make_run(tmp)
            out = tmp / "outputs" / "g02" / "T_SCOUT_A07" / "a07"
            reviews = scout_a07_bridge.build_scout_a07_reviews(
                run,
                output_dir=out,
                intake_ref=str(ROOT / "mocks" / "g02" / "KP_intake_bundle.json"),
                max_scan_pages=2,
            )
            good = next(item for item in reviews["source_reviews"]
                        if item["source_id"] == "SCOUT_GOOD")
            work_path = out / good["work_input_ref"]

            task = scout_a07_runner.build_scout_a07_model_task(
                work_path,
                intake=ROOT / "mocks" / "g02" / "KP_intake_bundle.json",
            )

            checked = contracts.validate(task, "scout_a07_model_task@1")
            self.assertTrue(checked["ok"], checked["errors"])
            self.assertEqual(task["model_policy"]["recommended_model"], "sonnet")
            self.assertEqual(task["model_policy"]["reasoning_effort"], "high")
            self.assertTrue(task["selected_windows"])
            self.assertTrue(task["intake_context"]["available"])
            self.assertTrue(task["intake_context"]["claim_cards"])
            self.assertTrue(task["intake_context"]["research_drivers"])
            self.assertTrue(task["topic_lens"]["linked_intake_ids"]["driver_ids"])

            prepared_tasks = scout_a07_runner.write_scout_a07_model_tasks(
                out,
                intake=ROOT / "mocks" / "g02" / "KP_intake_bundle.json",
            )
            self.assertEqual(prepared_tasks["task_count"], 1)
            self.assertTrue((out / prepared_tasks["tasks"][0]["task_ref"]).is_file())

            def fake_executor(model_task: dict) -> dict:
                self.assertEqual(model_task["schema_version"], "scout_a07_model_task@1")
                self.assertTrue(model_task["model_policy"]["full_pdf_forbidden"])
                return {
                    "review_status": "useful_for_update",
                    "confidence": "medium",
                    "presentation_update_candidates": [{
                        "finding": "FRA settlement is a cash settlement of an interest-rate differential calculated on a notional principal.",
                        "rationale_vs_existing_presentation": "This can clarify that notional is a calculation base, not exchanged principal.",
                        "extension_relation": "confirms",
                        "draft_insert": {
                            "slide_bullet": "FRA settlement is cash based: the interest differential is calculated on a notional principal.",
                            "speaker_note": "Use this to separate settlement cash flow from exchange of principal.",
                            "optional_detail": "The notional amount is the reference base for the differential."
                        },
                        "evidence_refs": [{
                            "source_id": model_task["source_id"],
                            "location": model_task["selected_windows"][0]["window_id"],
                            "quote": "cash settlement uses a notional principal",
                        }],
                    }],
                    "lookup_pointers": [],
                    "coverage_gaps": [],
                    "limitations": ["Offline executor fixture."],
                }

            run_result = scout_a07_runner.run_scout_a07_light(
                out,
                fake_executor,
                intake=ROOT / "mocks" / "g02" / "KP_intake_bundle.json",
                max_workers=2,
            )
            self.assertEqual(run_result["processed_count"], 1)
            self.assertEqual(run_result["failed_count"], 0)
            aggregated = run_result["aggregate"]
            self.assertEqual(aggregated["status"], "completed")
            self.assertEqual(len(aggregated["presentation_update_candidates"]), 1)
            self.assertTrue(contracts.validate(aggregated, "scout_a07_reviews@1")["ok"])

            prepared = scout_synthesis.prepare_scout_fast_synthesis(
                out / "reviews.json",
                intake=ROOT / "mocks" / "g02" / "KP_intake_bundle.json",
            )
            solution = scout_synthesis.finalize_scout_fast_solution(
                prepared["synthesis_input"],
            )
            self.assertTrue(contracts.validate(solution, "solution_input_candidate@1")["ok"])
            self.assertEqual(len(solution["slide_update_plan"]), 1)

    def test_normalize_tolerates_loose_model_output(self) -> None:
        # Real A07 model responses omit optional fields and send null where the
        # contract expects arrays. Normalization must stay crash-free and still
        # produce a valid scout_a07_partial_review@1 without manual fixes.
        with tempfile.TemporaryDirectory() as temp:
            tmp = Path(temp)
            run = self._make_run(tmp)
            out = tmp / "outputs" / "g02" / "T_SCOUT_A07" / "a07"
            reviews = scout_a07_bridge.build_scout_a07_reviews(
                run, output_dir=out, max_scan_pages=2
            )
            good = next(i for i in reviews["source_reviews"]
                        if i["source_id"] == "SCOUT_GOOD")
            work_item = json.loads(
                (out / good["work_input_ref"]).read_text(encoding="utf-8")
            )

            # Candidate with only a finding; null collections; no review_status/confidence.
            loose = {
                "presentation_update_candidates": [
                    {"finding": "FRA settlement is a cash payment on a notional principal."}
                ],
                "lookup_pointers": None,
                "coverage_gaps": None,
                "limitations": None,
            }
            partial = scout_a07_bridge.normalize_scout_a07_partial(
                work_item, loose, work_input_ref=good["work_input_ref"]
            )
            checked = contracts.validate(partial, "scout_a07_partial_review@1")
            self.assertTrue(checked["ok"], checked["errors"])
            self.assertEqual(partial["review_status"], "useful_for_update")
            self.assertEqual(len(partial["presentation_update_candidates"]), 1)
            self.assertTrue(partial["presentation_update_candidates"][0]["confidence"])

            # Fully empty object: status inferred from prefilter, still valid.
            empty_partial = scout_a07_bridge.normalize_scout_a07_partial(
                work_item, {}, work_input_ref=good["work_input_ref"]
            )
            self.assertTrue(
                contracts.validate(empty_partial, "scout_a07_partial_review@1")["ok"]
            )

            # A chat model wraps JSON in a fenced block plus prose; recover it.
            fenced = ("Here is the review:\n```json\n"
                      "{\"review_status\": \"context_only\", \"confidence\": \"low\"}\n```\n")
            recovered = scout_a07_runner.parse_model_json(fenced)
            self.assertEqual(recovered["review_status"], "context_only")

    def test_default_scout_run_root_uses_outputs_without_workspace(self) -> None:
        root = scout_fanout.default_scout_run_root("Task 01")

        self.assertEqual(root, Path.cwd().resolve() / "outputs" / "g02" / "Task_01" / "scout")


if __name__ == "__main__":
    unittest.main()
