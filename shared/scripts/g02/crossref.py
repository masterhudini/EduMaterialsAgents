"""Deterministic Crossref DOI verification and conservative metadata enrichment."""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Callable

from core import artifacts, contracts
from g02 import provider_config

RESULT_CONTRACT = "doi_verification_result@1"
SOURCE_CONTRACT = "source_record@1"
ENDPOINT = "https://api.crossref.org/works"
ENDPOINT_LABEL = "https://api.crossref.org/works/{doi}"
RETRYABLE = {408, 425, 429, 500, 502, 503, 504}
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.I)
Transport = Callable[[str, dict[str, str], float, int], dict]

_RATE_LOCK = threading.Lock()
_LAST_REQUEST = 0.0


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def normalize_doi(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if text.casefold().startswith(prefix):
            text = text[len(prefix):]
            break
    text = urllib.parse.unquote(text).strip().rstrip(".,;)").casefold()
    return text if DOI_RE.fullmatch(text) else None


def _issue(code: str, message: str, *, retryable: bool = False) -> dict:
    return {"code": code, "retryable": retryable, "message": message}


def _empty_metadata() -> dict:
    return {"doi": None, "title": None, "authors": [], "year": None,
            "venue": None, "publisher": None, "work_type": None}


def _norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _similarity(left: object, right: object) -> float:
    return difflib.SequenceMatcher(None, _norm(left), _norm(right)).ratio()


def _first_text(value: object) -> str | None:
    if isinstance(value, list):
        value = next((item for item in value if isinstance(item, str) and item.strip()), None)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _crossref_year(message: dict) -> int | None:
    for field in ("published-print", "published-online", "issued", "created"):
        item = message.get(field)
        parts = item.get("date-parts") if isinstance(item, dict) else None
        if isinstance(parts, list) and parts and isinstance(parts[0], list) \
                and parts[0] and isinstance(parts[0][0], int):
            return parts[0][0]
    return None


def _crossref_authors(message: dict) -> list[str]:
    result = []
    for item in message.get("author", []) if isinstance(message.get("author"), list) else []:
        if not isinstance(item, dict):
            continue
        name = " ".join(part for part in (item.get("given"), item.get("family"))
                        if isinstance(part, str) and part.strip()).strip()
        if name:
            result.append(name)
    return result


def _metadata(message: dict) -> dict:
    work_types = {
        "journal-article": "article", "proceedings-article": "article",
        "book": "book", "monograph": "book", "book-chapter": "chapter",
        "book-section": "chapter", "posted-content": "preprint",
        "report": "report", "dissertation": "dissertation",
    }
    return {
        "doi": normalize_doi(message.get("DOI")),
        "title": _first_text(message.get("title")),
        "authors": _crossref_authors(message),
        "year": _crossref_year(message),
        "venue": _first_text(message.get("container-title")),
        "publisher": _first_text(message.get("publisher")),
        "work_type": work_types.get(message.get("type"), message.get("type")
                                    if isinstance(message.get("type"), str) else None),
    }


def _compare_field(field: str, source: object, registry: object) -> dict:
    source_missing = source is None or source == "" or source == []
    registry_missing = registry is None or registry == "" or registry == []
    if source_missing:
        status = "source_missing" if not registry_missing else "registry_missing"
    elif registry_missing:
        status = "registry_missing"
    elif field == "year":
        status = "exact" if source == registry else (
            "compatible" if isinstance(source, int) and isinstance(registry, int)
            and abs(source - registry) <= 1 else "conflict"
        )
    elif field == "authors":
        left = {_norm(item).split()[-1] for item in source if _norm(item)} \
            if isinstance(source, list) else set()
        right = {_norm(item).split()[-1] for item in registry if _norm(item)} \
            if isinstance(registry, list) else set()
        overlap = len(left & right) / max(1, min(len(left), len(right)))
        status = "exact" if left == right else ("compatible" if overlap >= 0.5 else "conflict")
    else:
        ratio = _similarity(source, registry)
        status = "exact" if _norm(source) == _norm(registry) else (
            "compatible" if ratio >= (0.85 if field == "title" else 0.75) else "conflict"
        )
    return {"field": field, "status": status,
            "source_value": deepcopy(source), "crossref_value": deepcopy(registry)}


def _comparison(record: dict, metadata: dict) -> tuple[list[dict], str, dict]:
    bibliographic = record.get("bibliographic") if isinstance(record.get("bibliographic"), dict) else {}
    fields = ("title", "authors", "year", "venue", "publisher", "work_type")
    comparisons = [_compare_field(field, bibliographic.get(field), metadata.get(field))
                   for field in fields]
    critical = {item["field"]: item["status"] for item in comparisons}
    if any(critical.get(field) == "conflict" for field in ("title", "authors", "year")):
        match = "conflict"
    elif all(item["status"] == "exact" for item in comparisons):
        match = "exact"
    else:
        match = "compatible"
    overlay = {
        item["field"]: {"value": deepcopy(item["crossref_value"]), "source": "crossref"}
        for item in comparisons if item["status"] == "source_missing"
    }
    return comparisons, match, overlay


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class _CrossrefRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Allow redirects only inside Crossref's fixed HTTPS API origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlparse(newurl)
        if parsed.scheme != "https" or parsed.hostname != "api.crossref.org":
            raise ValueError("Crossref redirect left the fixed HTTPS origin")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _default_transport(url: str, headers: dict[str, str], timeout: float, max_bytes: int) -> dict:
    request = urllib.request.Request(url, headers=headers, method="GET")
    opener = urllib.request.build_opener(_CrossrefRedirectHandler())
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read(max_bytes + 1)
            return {"status_code": response.status, "headers": dict(response.headers),
                    "body": body, "final_url": response.geturl()}
    except urllib.error.HTTPError as exc:
        return {"status_code": exc.code, "headers": dict(exc.headers),
                "body": exc.read(max_bytes + 1), "final_url": exc.geturl()}


def _wait(config: provider_config.ProviderRuntimeConfig) -> None:
    global _LAST_REQUEST
    rates = config.data.get("rate_limits")
    interval = float(rates.get("crossref_min_interval_seconds", 0.2)) \
        if isinstance(rates, dict) else 0.2
    with _RATE_LOCK:
        remaining = interval - (time.monotonic() - _LAST_REQUEST)
        if remaining > 0:
            time.sleep(remaining)
        _LAST_REQUEST = time.monotonic()


def _cache_path(config: provider_config.ProviderRuntimeConfig, doi: str) -> Path:
    digest = hashlib.sha256(doi.encode("utf-8")).hexdigest()
    return config.cache_dir / "crossref" / f"{digest}.json"


def _cache_read(config: provider_config.ProviderRuntimeConfig, doi: str) -> dict | None:
    cache = config.data.get("cache")
    path = _cache_path(config, doi)
    if not isinstance(cache, dict) or cache.get("enabled") is not True or not path.is_file():
        return None
    ttl = int(cache.get("ttl_seconds", 0))
    if ttl == 0 or time.time() - path.stat().st_mtime > ttl:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if value.get("doi") == doi else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _cache_write(config: provider_config.ProviderRuntimeConfig, doi: str,
                 status_code: int, payload: dict) -> None:
    cache = config.data.get("cache")
    if not isinstance(cache, dict) or cache.get("enabled") is not True:
        return
    _atomic_json(_cache_path(config, doi),
                 {"doi": doi, "status_code": status_code, "payload": payload,
                  "cached_at": _utc_now()})


def _persist(result: dict, *, base=None) -> dict:
    checked = contracts.validate(result, RESULT_CONTRACT)
    if not checked["ok"]:
        raise ValueError("invalid DOI verification result: " + "; ".join(checked["errors"]))
    ref = artifacts.store(f"g02/doi-verifications/{result['operation_id']}.json", result, base=base)
    returned = deepcopy(result)
    returned["artifact_ref"] = ref
    return returned


def verify_source_record(record: dict, *, config_path=None, transport: Transport | None = None,
                         base=None) -> dict:
    """Verify one SourceRecord DOI against Crossref and persist the auditable result."""
    shape = contracts.validate(record, SOURCE_CONTRACT)
    if not shape["ok"]:
        raise ValueError("invalid source_record@1: " + "; ".join(shape["errors"]))
    operation_id = f"DOI_{uuid.uuid4().hex.upper()}"
    source_id = record["source_id"]
    input_doi = record.get("identifiers", {}).get("doi")
    doi = normalize_doi(input_doi)
    empty = _empty_metadata()
    base_result = {
        "schema_version": RESULT_CONTRACT, "operation_id": operation_id,
        "provider": "crossref", "source_id": source_id,
        "input_doi": input_doi if isinstance(input_doi, str) else None,
        "normalized_doi": doi, "crossref_metadata": empty,
        "field_comparisons": [], "suggested_bibliographic_overlay": {},
        "provenance": {"retrieved_at": _utc_now(), "raw_response_ref": None,
                       "cache_hit": False, "endpoint": ENDPOINT_LABEL},
        "issues": [],
    }
    if input_doi in (None, ""):
        return _persist({**base_result, "status": "ok", "registry_status": "not_applicable",
                         "match_status": "not_assessed"}, base=base)
    if doi is None:
        return _persist({**base_result, "status": "failed", "registry_status": "not_applicable",
                         "match_status": "not_assessed",
                         "issues": [_issue("invalid_doi", "DOI syntax is invalid")]}, base=base)

    config = provider_config.load_config(config_path)
    if not config.enabled("crossref"):
        return _persist({**base_result, "status": "unavailable",
                         "registry_status": "unavailable", "match_status": "not_assessed",
                         "issues": [_issue("crossref_disabled",
                                           "Crossref is disabled in provider configuration")]},
                        base=base)
    if not config.contact_email:
        return _persist({**base_result, "status": "unavailable",
                         "registry_status": "unavailable", "match_status": "not_assessed",
                         "issues": [_issue("crossref_contact_missing",
                                           "Crossref requires a configured contact email")]},
                        base=base)
    cached = _cache_read(config, doi)
    cache_hit = cached is not None
    status_code = int(cached["status_code"]) if cached else 0
    payload = cached["payload"] if cached else None
    request_cfg = config.data["request"]
    url = ENDPOINT + "/" + urllib.parse.quote(doi, safe="")
    if payload is None:
        runner = transport or _default_transport
        last_error = None
        for attempt in range(int(request_cfg["max_retries"]) + 1):
            try:
                _wait(config)
                response = runner(
                    url,
                    {"Accept": "application/json",
                     "User-Agent": f"EduMaterialsAgents/0.9 (mailto:{config.contact_email})"},
                    float(request_cfg["timeout_seconds"]),
                    int(request_cfg["max_response_bytes"]),
                )
                status_code = int(response["status_code"])
                final = urllib.parse.urlparse(str(response.get("final_url", url)))
                if final.scheme != "https" or final.hostname != "api.crossref.org":
                    raise ValueError("Crossref redirect left the fixed HTTPS origin")
                body = response.get("body", b"")
                if isinstance(body, bytes) and len(body) > int(request_cfg["max_response_bytes"]):
                    raise ValueError("Crossref response exceeded configured byte limit")
                # Crossref legitimately returns a plain-text 404 for an unregistered DOI.
                # Decode JSON only when a response can carry registry metadata; non-200 bodies
                # are not trusted or persisted as structured provider data.
                if status_code != 200:
                    payload = {}
                elif body:
                    payload = json.loads(
                        body.decode("utf-8") if isinstance(body, bytes) else str(body)
                    )
                else:
                    payload = {}
                if status_code not in RETRYABLE or attempt == int(request_cfg["max_retries"]):
                    break
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt == int(request_cfg["max_retries"]):
                    return _persist({**base_result, "status": "unavailable",
                                     "registry_status": "unavailable",
                                     "match_status": "not_assessed",
                                     "issues": [_issue("crossref_request_failed", str(exc),
                                                       retryable=True)]}, base=base)
            if attempt < int(request_cfg["max_retries"]):
                time.sleep(float(request_cfg["backoff_seconds"]) * (2 ** attempt))
        if payload is None and last_error is not None:
            raise last_error
        if status_code in {200, 404}:
            _cache_write(config, doi, status_code, payload or {})

    raw_ref = artifacts.store(
        f"{config.raw_artifact_subdir}/{operation_id}.crossref.json", payload or {}, base=base
    )
    provenance = {"retrieved_at": _utc_now(), "raw_response_ref": raw_ref,
                  "cache_hit": cache_hit, "endpoint": ENDPOINT_LABEL}
    if status_code == 404:
        return _persist({**base_result, "status": "not_found",
                         "registry_status": "not_found_crossref",
                         "match_status": "not_assessed", "provenance": provenance,
                         "issues": [_issue("doi_not_found_crossref",
                                           "Crossref has no work for this DOI")]}, base=base)
    if status_code != 200:
        return _persist({**base_result, "status": "unavailable",
                         "registry_status": "unavailable", "match_status": "not_assessed",
                         "provenance": provenance,
                         "issues": [_issue("crossref_http_error",
                                           f"Crossref returned HTTP {status_code}",
                                           retryable=status_code in RETRYABLE)]}, base=base)
    message = payload.get("message") if isinstance(payload, dict) else None
    if not isinstance(message, dict) or normalize_doi(message.get("DOI")) != doi:
        return _persist({**base_result, "status": "failed", "registry_status": "unavailable",
                         "match_status": "not_assessed", "provenance": provenance,
                         "issues": [_issue("crossref_identity_mismatch",
                                           "Crossref response did not bind the requested DOI")]},
                        base=base)
    metadata = _metadata(message)
    comparisons, match, overlay = _comparison(record, metadata)
    issues = [_issue("bibliographic_identity_conflict",
                     "Crossref conflicts with a critical provider bibliographic field")] \
        if match == "conflict" else []
    return _persist({**base_result, "status": "partial" if issues else "ok",
                     "registry_status": "confirmed_crossref", "match_status": match,
                     "crossref_metadata": metadata, "field_comparisons": comparisons,
                     "suggested_bibliographic_overlay": overlay,
                     "provenance": provenance, "issues": issues}, base=base)


def verify_source_records(records: list[dict], *, config_path=None,
                          transport: Transport | None = None, base=None) -> dict:
    """Verify unique SourceRecords in order; callers may reuse cache across duplicate DOI values."""
    if not isinstance(records, list):
        raise ValueError("records must be an array")
    if len(records) > 60:
        raise ValueError("records cannot contain more than 60 SourceRecords")
    results = [verify_source_record(item, config_path=config_path, transport=transport, base=base)
               for item in records]
    return {"provider": "crossref", "result_count": len(results), "results": results}


def descriptor(result: dict) -> dict:
    """Project a public verification result to the compact producer-artifact binding."""
    return {
        "source_id": result["source_id"],
        "normalized_doi": result["normalized_doi"],
        "status": result["status"],
        "registry_status": result["registry_status"],
        "match_status": result["match_status"],
        "result_ref": result["artifact_ref"],
    }


def validate_bindings(records: list[dict], bindings: object, *, base=None) -> list[str]:
    """Validate one exact Crossref result binding for every DOI-bearing scholarly record."""
    if not isinstance(bindings, list):
        return ["doi_verifications must be an array"]
    record_map = {item.get("source_id"): item for item in records if isinstance(item, dict)}
    doi_ids = {
        source_id for source_id, item in record_map.items()
        if isinstance(item.get("identifiers", {}).get("doi"), str)
        and item["identifiers"]["doi"].strip()
    }
    errors = []
    seen = set()
    for index, item in enumerate(bindings):
        if not isinstance(item, dict):
            errors.append(f"doi_verifications[{index}] must be an object")
            continue
        source_id = item.get("source_id")
        if source_id in seen:
            errors.append(f"duplicate DOI verification for {source_id!r}")
            continue
        seen.add(source_id)
        if source_id not in doi_ids:
            errors.append(f"DOI verification references non-DOI candidate {source_id!r}")
            continue
        ref = item.get("result_ref")
        if not isinstance(ref, str) or not ref.startswith(artifacts.SCHEME):
            errors.append(f"DOI verification {source_id!r} has no artifact result ref")
            continue
        try:
            result = artifacts.hydrate(ref, base=base)
            checked = contracts.validate(result, RESULT_CONTRACT)
            if not checked["ok"]:
                raise ValueError("; ".join(checked["errors"]))
        except (OSError, ValueError, KeyError, IndexError) as exc:
            errors.append(f"DOI verification {source_id!r} is unreadable: {exc}")
            continue
        expected = descriptor({**result, "artifact_ref": ref})
        if item != expected:
            errors.append(f"DOI verification {source_id!r} differs from its stored result")
        record_doi = normalize_doi(record_map[source_id].get("identifiers", {}).get("doi"))
        if result.get("source_id") != source_id or result.get("normalized_doi") != record_doi:
            errors.append(f"DOI verification {source_id!r} does not bind the candidate DOI")
    missing = doi_ids - seen
    if missing:
        errors.append(f"DOI-bearing candidates lack Crossref verification: {sorted(missing)}")
    return errors
