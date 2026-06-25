"""Offline checks for the vendored Scout Phase A wrapper."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from g02.scout import _smoke, runtime  # noqa: E402
from g02 import credentials  # noqa: E402
from g02.scout.engine import RunResult  # noqa: E402


def test_runtime_paths_live_under_emagents_home(tmp_path, monkeypatch):
    home = tmp_path / ".emagents"
    monkeypatch.setenv("EMAGENTS_HOME", str(home))

    workspace = runtime.workspace_dir()
    run_dir = runtime.run_dir("RUN 1")
    pdf_dir = runtime.pdf_dir("RUN 1")

    assert workspace == home.resolve() / "artifacts" / "g02" / "scout"
    assert run_dir == workspace / "runs" / "RUN_1"
    assert pdf_dir == run_dir / "pdf"
    assert workspace.is_dir()
    assert pdf_dir.is_dir()


def test_runtime_ignores_ambient_provider_values(monkeypatch):
    monkeypatch.setenv("EMAGENTS_RESEARCH_CONTACT_EMAIL", "research@example.edu")
    monkeypatch.setenv("OPENALEX_API_KEY", "oa-key")
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "s2-key")
    monkeypatch.setenv("CORE_API_KEY", "core-key")
    monkeypatch.delenv(credentials.MARKER_ENV, raising=False)

    assert runtime.contact_email() == ""
    assert runtime.provider_keys() == {
        "openalex_api_key": "",
        "s2_api_key": "",
        "core_api_key": "",
    }


def test_runtime_reads_agent_collected_provider_values(monkeypatch):
    monkeypatch.setenv(credentials.MARKER_ENV, credentials.MARKER_VALUE)
    monkeypatch.setenv("EMAGENTS_RESEARCH_CONTACT_EMAIL", "research@example.edu")
    monkeypatch.setenv("OPENALEX_API_KEY", "oa-key")
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "s2-key")
    monkeypatch.setenv("CORE_API_KEY", "core-key")

    assert runtime.contact_email() == "research@example.edu"
    assert runtime.provider_keys() == {
        "openalex_api_key": "oa-key",
        "s2_api_key": "s2-key",
        "core_api_key": "",
    }


def test_smoke_uses_emagents_workspace_and_disables_llm(tmp_path, monkeypatch):
    home = tmp_path / ".emagents"
    monkeypatch.setenv("EMAGENTS_HOME", str(home))
    captured: dict[str, object] = {}

    def fake_run_student(topic, n, email, pdf_dir, **kwargs):
        captured["topic"] = topic
        captured["n"] = n
        captured["email"] = email
        captured["pdf_dir"] = Path(pdf_dir)
        captured["kwargs"] = kwargs
        Path(pdf_dir).mkdir(parents=True, exist_ok=True)
        (Path(pdf_dir) / "paper.pdf").write_bytes(b"%PDF-1.4\n")
        result = RunResult(target_n=n)
        result.openalex_total = 1
        result.total_found = 1
        result.oa_count = 1
        result.downloaded = ["paper.pdf"]
        result.items = [{"filename": "paper.pdf", "score_R": 1.0}]
        result.manifest_ok = True
        return result

    monkeypatch.setattr(_smoke, "run_student", fake_run_student)

    status = _smoke.main([
        "asset pricing",
        "-n",
        "1",
        "--email",
        "research@example.edu",
        "--openalex-api-key",
        "oa-test-key",
        "--run-id",
        "RUN 1",
        "--verify-llm",
    ])

    assert status == 0
    assert captured["topic"] == "asset pricing"
    assert captured["n"] == 1
    assert captured["email"] == "research@example.edu"
    assert captured["pdf_dir"] == home.resolve() / "artifacts" / "g02" / "scout" / "runs" / "RUN_1" / "pdf"
    kwargs = captured["kwargs"]
    assert kwargs["verify_llm"] is False
    assert kwargs["openrouter_key"] == ""
    assert kwargs["query_expansion"] is False
    assert kwargs["openalex_api_key"] == "oa-test-key"
    assert kwargs["dedup_cross_run"] is False
    assert kwargs["store"] is None  # lean refactor: Scout runs store-less


def test_smoke_respects_explicit_workspace_out_and_no_store(tmp_path, monkeypatch):
    captured: dict[str, object] = {}
    workspace = tmp_path / "workspace"
    out = tmp_path / "pdf"

    def fake_run_student(topic, n, email, pdf_dir, **kwargs):
        captured["pdf_dir"] = Path(pdf_dir)
        captured["kwargs"] = kwargs
        Path(pdf_dir).mkdir(parents=True, exist_ok=True)
        result = RunResult(target_n=n)
        result.manifest_ok = True
        return result

    monkeypatch.setattr(_smoke, "run_student", fake_run_student)

    status = _smoke.main([
        "monetary policy",
        "-n",
        "2",
        "--workspace",
        str(workspace),
        "--out",
        str(out),
        "--openalex-api-key",
        "oa-test-key",
        "--no-store",
        "--dedup-cross-run",
    ])

    assert status == 0
    assert captured["pdf_dir"] == out.resolve()
    assert captured["kwargs"]["store"] is None
    assert captured["kwargs"]["openalex_api_key"] == "oa-test-key"
    assert captured["kwargs"]["dedup_cross_run"] is True


def test_smoke_runs_without_openalex_api_key(monkeypatch):
    # Option B: the OpenAlex token is no longer a hard requirement — Scout runs without it
    # (OpenAlex degrades / is excluded by the credential tier), it must NOT hard-exit.
    called = False

    def fake_run_student(*args, **kwargs):
        nonlocal called
        called = True
        return RunResult(target_n=1)

    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    monkeypatch.setattr(_smoke, "run_student", fake_run_student)

    status = _smoke.main(["asset pricing", "-n", "1"])

    assert status != 2
    assert called is True
