"""Offline persistence and dedup tests for the parallel Scout fan-out."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from core import contracts  # noqa: E402
from g02 import scout_fanout  # noqa: E402
from g02.scout.engine import RunResult  # noqa: E402

FIXTURE = ROOT / "mocks" / "g02" / "EXAMPLE g02-a01-planner.artifact.json"


def _four_topic_plan() -> dict:
    source = json.loads(FIXTURE.read_text(encoding="utf-8"))
    topics = []
    for index in range(4):
        topic = copy.deepcopy(source["topics"][index % len(source["topics"])])
        topic["topic_id"] = f"TOPIC_SCOUT_{index + 1}"
        topic["name"] = f"Technical search field {index + 1}"
        topics.append(topic)
    source["topics"] = topics
    source["global_constraints"]["max_topics"] = 6
    return source


def _fake_topic_runner(job: dict) -> dict:
    topic_id = job["request"]["topic_id"]
    number = int(topic_id.rsplit("_", 1)[-1])
    pdf_dir = Path(job["pdf_dir"])
    pdf_dir.mkdir(parents=True, exist_ok=True)
    filename = f"paper_{number}.pdf"
    (pdf_dir / filename).write_bytes(f"%PDF-1.4\n{topic_id}\n".encode())
    (pdf_dir / "MANIFEST.md").write_text(
        f"# MANIFEST\n\n- {filename}\n", encoding="utf-8"
    )
    # Topics one and two intentionally describe the same DOI. The parent must
    # retain both local files and both topic memberships after post-run dedup.
    doi = "10.1000/shared" if number <= 2 else f"10.1000/unique-{number}"
    title = "Shared methods paper" if number <= 2 else f"Unique paper {number}"
    return {
        "target_n": job["request"]["target_n"],
        "openalex_total": 8,
        "total_found": 6,
        "oa_count": 5,
        "downloaded": [filename],
        "stubs": [],
        "rejected": [],
        "items": [{
            "filename": filename,
            "doi": doi,
            "title": title,
            "year": 2025,
            "fwci": 0.8,
            "venue": "Journal of Offline Tests",
            "work_type": "article",
            "source": "openalex",
            "source_type": "recent",
            "source_type_basis": "year 2025 >= 2021; no canonical signal",
        }],
        "manifest_ok": True,
    }


def test_fanout_persists_complete_layout_and_cross_topic_membership(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", "offline-test-key")
    workspace = tmp_path / "scout"

    output = scout_fanout.run_scout_fanout(
        _four_topic_plan(), workspace=workspace, topic_runner=_fake_topic_runner
    )

    run_root = Path(output["run_directory"])
    assert run_root == workspace / "runs" / "RESEARCH_MOCK_001"
    assert (run_root / "plan.json").is_file()
    index = json.loads((run_root / "index.json").read_text(encoding="utf-8"))
    assert "offline-test-key" not in json.dumps(index)
    assert contracts.validate(index, "scout_run_index@1")["ok"]
    assert index["status"] == "completed"
    assert index["total_target"] == 50
    assert index["allocated_target"] == 48
    assert index["summary"]["downloaded_pdf_count"] == 4
    assert index["summary"]["unique_work_count"] == 3

    for topic in index["topics"]:
        topic_id = topic["topic_id"]
        assert (run_root / topic["request_ref"]).is_file()
        assert (run_root / topic["manifest_ref"]).is_file()
        assert not (run_root / topic["pdf_dir"] / "MANIFEST.md").exists()
        corpus_path = run_root / topic["retrieved_corpus_ref"]
        corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
        assert contracts.validate(corpus, "scout_retrieved_corpus@1")["ok"]
        document = corpus["documents"][0]
        assert (run_root / document["local_ref"]).is_file()
        assert len(document["sha256"]) == 64
        assert document["source_type"] == "recent"
        assert document["source_type_basis"]
        assert document["fwci"] == 0.8

    shared = next(item for item in index["deduplicated_works"]
                  if item["doi"] == "10.1000/shared")
    assert shared["topic_ids"] == ["TOPIC_SCOUT_1", "TOPIC_SCOUT_2"]
    assert len(shared["local_refs"]) == 2
    for topic_id in shared["topic_ids"]:
        corpus = json.loads((run_root / "topics" / topic_id / "retrieved_corpus.json")
                            .read_text(encoding="utf-8"))
        assert corpus["documents"][0]["topic_ids"] == shared["topic_ids"]
        assert corpus["documents"][0]["source_id"] == shared["dedup_id"]


def test_fanout_requires_openalex_key_before_creating_output(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)

    with pytest.raises(Exception, match="OPENALEX_API_KEY"):
        scout_fanout.run_scout_fanout(
            _four_topic_plan(), workspace=tmp_path / "scout",
            topic_runner=_fake_topic_runner,
        )

    assert not (tmp_path / "scout").exists()


def test_fanout_rejects_non_scout_topic_count(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", "offline-test-key")
    plan = _four_topic_plan()
    plan["topics"] = plan["topics"][:3]

    with pytest.raises(ValueError, match="4 to 6 topics"):
        scout_fanout.run_scout_fanout(
            plan, workspace=tmp_path / "scout", topic_runner=_fake_topic_runner
        )


def test_default_run_root_points_to_outputs_handoff(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    root = scout_fanout.default_scout_run_root("RESEARCH MOCK 001")

    assert root == tmp_path / "outputs" / "g02" / "RESEARCH_MOCK_001" / "scout"


def test_fanout_redacts_provider_key_from_worker_error(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", "super-secret-offline-key")

    def failed_runner(job):
        raise RuntimeError("request failed: ?api_key=super-secret-offline-key")

    output = scout_fanout.run_scout_fanout(
        _four_topic_plan(), workspace=tmp_path / "scout", topic_runner=failed_runner
    )

    serialized = json.dumps(output)
    assert "super-secret-offline-key" not in serialized
    assert "[REDACTED]" in serialized
    assert output["index"]["status"] == "failed"


def test_production_topic_worker_uses_approved_oversample(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", "offline-test-key")
    captured = {}

    def fake_run_student(topic, n, email, pdf_dir, **kwargs):
        captured.update(kwargs)
        return RunResult(target_n=n)

    monkeypatch.setattr(scout_fanout, "run_student", fake_run_student)
    request = {
        "query": "Bayesian computation scalability",
        "target_n": 10,
        "intent": "",
        "year_from": None,
        "recency_year_from": 2021,
        "year_to": None,
        "work_type": "",
        "lang": "en",
        "keywords": ["Bayesian computation"],
        "quota_canonical": 0.4,
        "snowball": True,
    }

    scout_fanout._run_topic_worker({"request": request, "pdf_dir": str(tmp_path / "pdf")})

    assert captured["oversample"] == 1.2
    assert captured["quota_canonical"] == 0.4
    assert captured["recency_year_from"] == 2021
    assert captured["snowball"] is True
