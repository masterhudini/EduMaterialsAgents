"""Offline Crossref DOI verification, provenance and binding tests."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from core import artifacts, contracts  # noqa: E402
from g02 import crossref, provider_config  # noqa: E402

MOCKS = ROOT / "mocks" / "g02"
CONFIG = MOCKS / "retrieval_provider_config.json"


@pytest.fixture(autouse=True)
def _runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("EMAGENTS_HOME", str(tmp_path / ".emagents"))
    monkeypatch.setenv("EMAGENTS_RESEARCH_CONTACT_EMAIL", "tests@example.com")
    monkeypatch.setenv("OPENALEX_API_KEY", "openalex-test-key")
    # Model a session that completed research_provider_setup so managed_environment keeps the creds.
    monkeypatch.setenv("EMAGENTS_G02_PROVIDER_CREDENTIALS", "provider_setup")


def _record() -> dict:
    pool = json.loads((MOCKS / "domain_candidate_sources.json").read_text(encoding="utf-8"))
    return copy.deepcopy(pool["candidates"][0])


def _transport_for(message: dict, *, status_code: int = 200):
    def transport(url, headers, timeout, max_bytes):
        assert url.startswith("https://api.crossref.org/works/")
        assert headers["Accept"] == "application/json"
        assert "mailto:tests@example.com" in headers["User-Agent"]
        assert timeout == 2
        assert max_bytes == 1048576
        payload = {"status": "ok", "message": message}
        return {
            "status_code": status_code,
            "headers": {"content-type": "application/json"},
            "body": json.dumps(payload).encode("utf-8"),
            "final_url": url,
        }
    return transport


def _message(**overrides) -> dict:
    value = {
        "DOI": "10.1214/17-STS668",
        "title": ["A Conceptual Introduction to Hamiltonian Monte Carlo"],
        "author": [{"given": "Michael", "family": "Betancourt"}],
        "issued": {"date-parts": [[2017]]},
        "container-title": ["arXiv"],
        "publisher": "Cornell University",
        "type": "journal-article",
    }
    value.update(overrides)
    return value


def test_crossref_confirms_exact_identity_and_persists_raw_provenance():
    result = crossref.verify_source_record(
        _record(), config_path=CONFIG, transport=_transport_for(_message())
    )
    assert result["status"] == "ok"
    assert result["registry_status"] == "confirmed_crossref"
    assert result["match_status"] == "exact"
    assert result["normalized_doi"] == "10.1214/17-sts668"
    assert result["suggested_bibliographic_overlay"] == {}
    assert artifacts.hydrate(result["artifact_ref"])["operation_id"] == result["operation_id"]
    assert artifacts.hydrate(result["provenance"]["raw_response_ref"])["message"]["DOI"] \
        == "10.1214/17-STS668"
    assert contracts.validate(result, "doi_verification_result@1")["ok"]


def test_crossref_conflict_is_visible_and_never_overwrites_provider_metadata():
    record = _record()
    original = copy.deepcopy(record)
    result = crossref.verify_source_record(
        record,
        config_path=CONFIG,
        transport=_transport_for(_message(
            title=["A Different Work"],
            author=[{"given": "Other", "family": "Author"}],
            issued={"date-parts": [[1999]]},
        )),
    )
    assert record == original
    assert result["status"] == "partial"
    assert result["match_status"] == "conflict"
    assert result["suggested_bibliographic_overlay"] == {}
    assert result["issues"][0]["code"] == "bibliographic_identity_conflict"


def test_missing_and_malformed_doi_are_deterministic_without_network():
    calls = []

    def forbidden(*args):
        calls.append(args)
        raise AssertionError("transport must not be called")

    missing = _record()
    missing["identifiers"]["doi"] = None
    result = crossref.verify_source_record(missing, config_path=CONFIG, transport=forbidden)
    assert result["status"] == "ok"
    assert result["registry_status"] == "not_applicable"

    malformed = _record()
    malformed["identifiers"]["doi"] = "not-a-doi"
    result = crossref.verify_source_record(malformed, config_path=CONFIG, transport=forbidden)
    assert result["status"] == "failed"
    assert result["issues"][0]["code"] == "invalid_doi"
    assert crossref.validate_bindings([malformed], [crossref.descriptor(result)]) == []
    assert calls == []


def test_compact_binding_must_match_exact_source_and_stored_result():
    record = _record()
    result = crossref.verify_source_record(
        record, config_path=CONFIG, transport=_transport_for(_message())
    )
    binding = crossref.descriptor(result)
    assert crossref.validate_bindings([record], [binding]) == []

    modified = copy.deepcopy(binding)
    modified["match_status"] = "conflict"
    errors = crossref.validate_bindings([record], [modified])
    assert any("differs from its stored result" in item for item in errors)
    assert crossref.validate_bindings([record], []) == [
        "DOI-bearing candidates lack Crossref verification: ['SRC_OPENALEX_4FBB7A48C33F038E']"
    ]


def test_crossref_not_found_and_http_unavailable_remain_distinct():
    not_found = crossref.verify_source_record(
        _record(), config_path=CONFIG,
        transport=_transport_for({"DOI": "10.1214/17-STS668"}, status_code=404),
    )
    assert not_found["status"] == "not_found"
    assert not_found["registry_status"] == "not_found_crossref"

    unavailable = crossref.verify_source_record(
        _record(), config_path=CONFIG,
        transport=_transport_for({"DOI": "10.1214/17-STS668"}, status_code=503),
    )
    assert unavailable["status"] == "unavailable"
    assert unavailable["registry_status"] == "unavailable"
    assert unavailable["issues"][0]["retryable"] is True


def test_crossref_plain_text_404_is_not_misclassified_as_json_failure():
    def plain_404(url, headers, timeout, max_bytes):
        return {
            "status_code": 404, "headers": {"content-type": "text/plain"},
            "body": b"Resource not found.", "final_url": url,
        }

    result = crossref.verify_source_record(
        _record(), config_path=CONFIG, transport=plain_404,
    )
    assert result["status"] == "not_found"
    assert result["registry_status"] == "not_found_crossref"
    assert result["issues"][0]["code"] == "doi_not_found_crossref"


def test_batch_limit_is_enforced_before_any_request():
    with pytest.raises(ValueError, match="more than 60"):
        crossref.verify_source_records([_record()] * 61, config_path=CONFIG)


def test_pre_crossref_provider_config_migrates_disabled_in_memory(tmp_path):
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    del payload["providers"]["crossref"]
    del payload["rate_limits"]["crossref_min_interval_seconds"]
    legacy = tmp_path / "legacy-provider-config.json"
    legacy.write_text(json.dumps(payload), encoding="utf-8")

    config = provider_config.load_config(legacy)
    assert config.enabled("crossref") is False
    assert config.data["rate_limits"]["crossref_min_interval_seconds"] == 0.2
    crossref_status = next(
        item for item in config.public_status()["capabilities"]
        if item["provider"] == "crossref"
    )
    assert crossref_status == {
        "provider": "crossref", "enabled": False, "ready": False,
        "authentication": "disabled",
    }

    result = crossref.verify_source_record(
        _record(), config_path=legacy,
        transport=lambda *args: (_ for _ in ()).throw(
            AssertionError("disabled Crossref must not perform a request")
        ),
    )
    assert result["status"] == "unavailable"
    assert result["issues"][0]["code"] == "crossref_disabled"
