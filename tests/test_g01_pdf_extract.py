import builtins
import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from core import artifacts, contracts, paths  # noqa: E402
from g01 import g01_flow, intake, pdf_extract  # noqa: E402
from mcp import intake_server  # noqa: E402


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("EMAGENTS_HOME", str(tmp_path / ".emagents"))


def _minimal_pdf(text: str) -> bytes:
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n",
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]
    stream = f"BT /F1 24 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    objects.append(
        b"5 0 obj\n<< /Length " + str(len(stream)).encode("ascii") +
        b" >>\nstream\n" + stream + b"\nendstream\nendobj\n"
    )
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for item in objects:
        offsets.append(len(out))
        out.extend(item)
    xref = len(out)
    out.extend(b"xref\n0 6\n0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    out.extend(
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n" +
        str(xref).encode("ascii") + b"\n%%EOF\n"
    )
    return bytes(out)


def test_pdf_extract_contract_accepts_dependency_missing(tmp_path, monkeypatch):
    pdf = tmp_path / "input.pdf"
    pdf.write_bytes(_minimal_pdf("Dependency missing path"))
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pypdf":
            raise ImportError("blocked in test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    result = pdf_extract.extract(str(pdf), store=False)

    assert result["extraction_status"] == "dependency_missing"
    assert result["degraded"] is True
    assert contracts.validate(result, "pdf_extract_result@1")["ok"]


def test_upload_merges_profile_validates_before_write_and_deduplicates(tmp_path):
    pdf = tmp_path / "lecture.pdf"
    data = _minimal_pdf("Deduplicated upload")
    pdf.write_bytes(data)

    uploaded = intake.upload(str(pdf), ingestion_profile={"output_language": "pl"})
    uploaded_again = intake.upload(str(pdf), ingestion_profile={"extract_text": True})

    assert uploaded["pdf_ref"] == uploaded_again["pdf_ref"]
    assert uploaded["ref"] != uploaded_again["ref"]
    assert uploaded["sha256"] == hashlib.sha256(data).hexdigest()
    stored = list((paths.artifacts_dir() / "uploads").glob("*.pdf"))
    assert len(stored) == 1
    bundle = artifacts.hydrate(uploaded["ref"])
    assert bundle["ingestion_profile"]["extract_text"] is True
    assert bundle["ingestion_profile"]["output_language"] == "pl"

    not_pdf = tmp_path / "not.pdf"
    not_pdf.write_bytes(b"not a pdf")
    with pytest.raises(ValueError):
        intake.upload(str(not_pdf))
    assert len(list((paths.artifacts_dir() / "uploads").glob("*.pdf"))) == 1


def test_intake_pdf_extract_tool_is_advertised():
    tools = intake_server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {tool["name"] for tool in tools["result"]["tools"]}
    assert "intake_pdf_extract" in names
    assert "intake_slide_views" in names
    schema = next(tool for tool in tools["result"]["tools"] if tool["name"] == "intake_pdf_extract")
    assert schema["inputSchema"]["properties"]["input"]["type"] == ["object", "string"]


@pytest.mark.skipif(importlib.util.find_spec("pypdf") is None, reason="pypdf not installed")
def test_pdf_extract_with_local_pypdf_from_uploaded_intake(tmp_path):
    pdf = tmp_path / "lecture.pdf"
    pdf.write_bytes(_minimal_pdf("Hello EduMaterials PDF intake"))
    uploaded = intake.upload(str(pdf), task_id="INTAKE_PDF_TEST")

    result = pdf_extract.extract(uploaded["ref"], store=True)

    assert result["extraction_status"] == "ok"
    assert result["page_count"] == 1
    assert "Hello EduMaterials PDF intake" in result["pages"][0]["text"]
    assert result["result_ref"].startswith("artifact://g01/pdf-extract/")
    stored = artifacts.hydrate(result["result_ref"])
    assert stored["result_ref"] == result["result_ref"]
    assert contracts.validate(result, "pdf_extract_result@1")["ok"]


@pytest.mark.skipif(importlib.util.find_spec("pypdf") is None, reason="pypdf not installed")
def test_slide_views_bridge_from_uploaded_intake(tmp_path):
    pdf = tmp_path / "lecture.pdf"
    pdf.write_bytes(_minimal_pdf("Hello slide views bridge"))
    uploaded = intake.upload(str(pdf), task_id="INTAKE_SLIDES_TEST")

    views = pdf_extract.slide_views(uploaded["ref"], store=True)

    assert views["slide_count"] == 1
    assert views["slides"][0]["slide_id"] == 1
    assert "Hello slide views bridge" in views["slides"][0]["normalized_text"]
    assert views["source_extraction_status"] == "ok"
    assert views["slide_views_ref"].startswith("artifact://g01/slide-views/")
    assert contracts.validate(views, "slide_views@1")["ok"]


@pytest.mark.skipif(importlib.util.find_spec("pypdf") is None, reason="pypdf not installed")
def test_g01_codex_runner_executes_a01_deterministically(tmp_path):
    pdf = tmp_path / "lecture.pdf"
    pdf.write_bytes(_minimal_pdf("Hello deterministic A01"))
    uploaded = intake.upload(str(pdf), task_id="INTAKE_A01_TEST")
    input_bundle = g01_flow._load_any(uploaded["ref"])

    class Log:
        def append(self, *args, **kwargs):
            pass

    envelope = g01_flow.make_g01_codex_runner()(
        {"name": "g01-a01-pdf-intake", "output_contract": "slide_views@1"},
        {"input": input_bundle, "upstream": {}},
        Log(),
    )

    assert envelope["status"] == "ok"
    assert envelope["artifact"]["slide_count"] == 1
    assert "Hello deterministic A01" in envelope["artifact"]["slides"][0]["normalized_text"]
    assert contracts.validate_envelope(envelope)["ok"]
    assert contracts.validate(envelope["artifact"], "slide_views@1")["ok"]
