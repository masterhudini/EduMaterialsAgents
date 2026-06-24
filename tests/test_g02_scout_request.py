"""Offline checks for the G02 A01 -> Scout request seam."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from core import contracts  # noqa: E402
from g02 import scout_request  # noqa: E402
from g02.scout import _smoke  # noqa: E402
from g02.scout.engine import (  # noqa: E402
    Candidate,
    RunResult,
    _apply_joint_quotas,
    _apply_recency_quota,
    _source_type_details,
)


FIXTURE = ROOT / "mocks" / "g02" / "EXAMPLE g02-a01-planner.artifact.json"


def _load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class ScoutRequestTests(unittest.TestCase):
    def test_total_budget_is_allocated_across_all_topics(self) -> None:
        plan = _load_fixture()
        plan["topics"] = [
            {**plan["topics"][index % 2],
             "topic_id": f"TOPIC_{index + 1}",
             "name": f"Searchable topic {index + 1}"}
            for index in range(4)
        ]

        requests = scout_request.build_scout_search_requests(plan, total_target=50)

        self.assertEqual([item["target_n"] for item in requests], [12, 12, 12, 12])
        self.assertEqual(sum(item["target_n"] for item in requests), 48)

    def test_scout_profile_has_one_total_budget_knob(self) -> None:
        settings = scout_request.scout_profile_settings()
        self.assertEqual(settings["total_target"], 50)
        self.assertEqual(settings["max_parallel_topics"], 6)

    def test_example_a01_artifact_builds_two_valid_requests(self) -> None:
        plan = _load_fixture()

        requests = scout_request.build_scout_search_requests(plan, current_year=2026)

        self.assertEqual(len(requests), 2)
        topic_ids = [item["topic_id"] for item in requests]
        self.assertEqual(topic_ids, ["TOPIC_BAYESIAN_COMPUTATION", "TOPIC_VARIATIONAL_INFERENCE"])
        for request in requests:
            checked = contracts.validate(request, "scout_search_request@1")
            self.assertTrue(checked["ok"], checked["errors"])
            self.assertEqual(request["task_id"], "RESEARCH_MOCK_001")
            self.assertEqual(request["target_n"], 15)
            self.assertIsNone(request["year_from"])
            self.assertEqual(request["recency_year_from"], 2021)
            self.assertIsNone(request["year_to"])
            self.assertEqual(request["lang"], "en")
            self.assertEqual(request["work_type"], "")
            self.assertEqual(request["quota_canonical"], 0.4)
            self.assertTrue(request["snowball"])
            self.assertEqual(request["created_from"], {
                "task_id": request["task_id"],
                "topic_id": request["topic_id"],
            })

        first = requests[0]
        self.assertEqual(first["query"], "Bayesian computation MCMC scalability posterior sampling")
        self.assertIn("Bayesian computation", first["keywords"])
        self.assertIn("Hamiltonian Monte Carlo", first["keywords"])
        self.assertEqual(first["excluded_terms"], ["frequentist inference", "classical statistics"])

    def test_minimal_plan_and_missing_keywords_still_build_request(self) -> None:
        plan = {
            "task_id": "T_MIN",
            "topics": [
                {
                    "topic_id": "TOPIC_1",
                    "name": "Minimal topic",
                    "purpose": "",
                    "search_strategy": {},
                }
            ],
            "output_language": "English",
        }

        requests = scout_request.build_scout_search_requests(plan, current_year=2026, target_n_default=3)

        self.assertEqual(len(requests), 1)
        request = requests[0]
        self.assertTrue(contracts.validate(request, "scout_search_request@1")["ok"])
        self.assertEqual(request["keywords"], [])
        self.assertEqual(request["target_n"], 5)
        self.assertIsNone(request["year_from"])
        self.assertIsNone(request["recency_year_from"])
        self.assertIsNone(request["quota_canonical"])
        self.assertFalse(request["snowball"])
        self.assertEqual(request["lang"], "both")

    def test_year_language_and_single_work_type_mapping(self) -> None:
        plan = {
            "task_id": "T_MAP",
            "output_language": "Polish",
            "approved_research_scope": {
                "include_recent_developments": True,
                "recency_window_years": 7,
            },
            "global_constraints": {
                "year_from": 2018,
                "year_to": 2024,
                "allowed_languages": ["en", "pl"],
                "allowed_work_types": ["article"],
            },
            "topics": [
                {
                    "topic_id": "TOPIC_MAP",
                    "name": "Mapping topic",
                    "purpose": "Map fields",
                    "search_strategy": {
                        "core_terms": ["alpha", "Alpha"],
                        "allowed_expansion_areas": ["beta"],
                        "excluded_terms": ["gamma"],
                        "languages": ["pl"],
                        "work_types": ["review"],
                    },
                }
            ],
        }

        request = scout_request.build_scout_search_requests(plan, current_year=2026)[0]

        self.assertEqual(request["year_from"], 2018)
        self.assertEqual(request["recency_year_from"], 2018)
        self.assertEqual(request["year_to"], 2024)
        self.assertEqual(request["lang"], "pl")
        self.assertEqual(request["work_type"], "review")
        self.assertEqual(request["keywords"], ["alpha", "beta"])

    def test_select_request_requires_topic_id_for_multi_topic_plan(self) -> None:
        requests = scout_request.build_scout_search_requests(_load_fixture(), current_year=2026)

        with self.assertRaisesRegex(ValueError, "--topic-id is required"):
            scout_request.select_request(requests)

        selected = scout_request.select_request(requests, "TOPIC_VARIATIONAL_INFERENCE")
        self.assertEqual(selected["topic_id"], "TOPIC_VARIATIONAL_INFERENCE")

    def test_smoke_can_run_from_a01_plan_for_one_topic_without_network(self) -> None:
        captured: dict[str, object] = {}

        def fake_run_student(topic, n, email, pdf_dir, **kwargs):
            captured["topic"] = topic
            captured["n"] = n
            captured["email"] = email
            captured["pdf_dir"] = Path(pdf_dir)
            captured["kwargs"] = kwargs
            result = RunResult(target_n=n)
            result.manifest_ok = True
            return result

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with patch.object(_smoke, "run_student", fake_run_student):
                status = _smoke.main([
                    "--plan-json",
                    str(FIXTURE),
                    "--topic-id",
                    "TOPIC_BAYESIAN_COMPUTATION",
                    "--openalex-api-key",
                    "oa-test-key",
                    "--email",
                    "research@example.edu",
                    "--workspace",
                    str(tmp_path / "workspace"),
                    "--out",
                    str(tmp_path / "pdf"),
                    "--no-store",
                ])

        self.assertEqual(status, 0)
        self.assertEqual(captured["topic"], "Bayesian computation MCMC scalability posterior sampling")
        self.assertEqual(captured["n"], 15)
        self.assertEqual(captured["email"], "research@example.edu")
        kwargs = captured["kwargs"]
        self.assertEqual(kwargs["openalex_api_key"], "oa-test-key")
        self.assertEqual(kwargs["search_lang"], "en")
        self.assertIsNone(kwargs["year_from"])
        self.assertEqual(kwargs["recency_year_from"], 2021)
        self.assertIsNone(kwargs["year_to"])
        self.assertEqual(kwargs["work_type"], "")
        self.assertEqual(kwargs["facets_required"], ["Bayesian computation MCMC scalability posterior sampling"])
        self.assertIn("Bayesian computation", kwargs["facets"])
        self.assertEqual(kwargs["quota_canonical"], 0.4)
        self.assertTrue(kwargs["snowball"])
        self.assertFalse(kwargs["verify_llm"])
        self.assertFalse(kwargs["query_expansion"])

    def test_source_type_uses_all_approved_metadata_signals(self) -> None:
        def candidate(doi: str, *, year=2025, fwci=None, source="openalex",
                      work_type="article") -> Candidate:
            return Candidate(doi, doi, year, "Author", True, "https://example/pdf", source,
                             fwci=fwci, work_type=work_type)

        cases = [
            candidate("10.1/year", year=2019),
            candidate("10.1/fwci", fwci=2.1),
            candidate("10.1/snowball", source="snowball"),
            candidate("10.1/book", work_type="book"),
        ]
        for item in cases:
            source_type, basis = _source_type_details(item, 2021)
            self.assertEqual(source_type, "canonical")
            self.assertTrue(basis)
        self.assertEqual(_source_type_details(candidate("10.1/recent"), 2021)[0], "recent")

    def test_recency_quota_handles_edges_and_uses_ceiling(self) -> None:
        recent = [Candidate(f"10.1/r{i}", f"r{i}", 2025, "A", True, "u", "openalex")
                  for i in range(6)]
        canonical = [Candidate(f"10.1/c{i}", f"c{i}", 2010, "A", True, "u", "openalex")
                     for i in range(4)]
        ranked = recent + canonical

        selected = _apply_recency_quota(ranked, 2021, 0.4, 9)[:9]
        self.assertEqual(sum(item.year < 2021 for item in selected), 4)
        self.assertTrue(all(item.year >= 2021 for item in
                            _apply_recency_quota(ranked, 2021, 0.0, 6)[:6]))
        self.assertTrue(all(item.year < 2021 for item in
                            _apply_recency_quota(ranked, 2021, 1.0, 4)[:4]))

    def test_joint_quota_preserves_language_and_recency_margins(self) -> None:
        ranked = []
        lang_map = {}
        for source_type, year in (("c", 2010), ("r", 2025)):
            for lang in ("pl", "en"):
                for index in range(3):
                    doi = f"10.1/{source_type}-{lang}-{index}"
                    ranked.append(Candidate(doi, doi, year, "A", True, "u", "openalex"))
                    lang_map[doi] = {lang}

        selected = _apply_joint_quotas(ranked, lang_map, 0.25, 2021, 0.5, 8)[:8]
        self.assertEqual(sum(item.year < 2021 for item in selected), 4)
        self.assertEqual(sum("pl" in lang_map[item.doi] for item in selected), 2)


if __name__ == "__main__":
    unittest.main()
