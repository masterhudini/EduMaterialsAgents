"""Legal OA resolution, bounded download and document validation for G02-A06."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import shutil
import socket
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
try:
    from datetime import UTC, datetime
except ImportError:  # Python < 3.11
    from datetime import datetime, timezone
    UTC = timezone.utc
from pathlib import Path
from typing import Callable

from core import artifacts, contracts
from g02 import provider_config

RETRIEVAL_INPUT_CONTRACT = "retrieval_input@1"
RESOLUTION_CONTRACT = "open_access_resolution@1"
FILE_CONTRACT = "retrieved_file_candidate@1"
DOCUMENT_CONTRACT = "validated_document@1"
CORPUS_SCHEME = "corpus://"
METADATA_ORIGINS = {
    "unpaywall": "https://api.unpaywall.org",
    "core": "https://api.core.ac.uk",
    "doab": "https://directory.doabooks.org",
    "oapen": "https://library.oapen.org",
}
METADATA_USER_AGENT = "EduMaterialsAgents/0.9"
RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}
MetadataTransport = Callable[[str, dict[str, str], float, int], dict]
DownloadTransport = Callable[[str, dict[str, str], float, int, Path, int], dict]
_LAST_REQUEST: dict[str, float] = {}
_RATE_LOCKS = {name: threading.Lock() for name in provider_config.RETRIEVAL_PROVIDERS}


class RetrievalError(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool = False,
                 http_status: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.http_status = http_status


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()) or "unknown"


def _issue(code: str, message: str, *, retryable=False, provider=None) -> dict:
    result = {"code": code, "message": message, "retryable": retryable}
    if provider:
        result["provider"] = provider
    return result


def _shape(payload: object, contract_ref: str) -> list[str]:
    try:
        return contracts.validate(payload, contract_ref)["errors"]
    except (KeyError, ValueError) as exc:
        return [str(exc)]


def _source(retrieval_input: dict, source_id: str, record_type: str | None = None) -> dict:
    matches = [item for item in retrieval_input.get("approved_sources", [])
               if isinstance(item, dict) and item.get("source_id") == source_id]
    if len(matches) != 1:
        raise ValueError("source_id must resolve exactly once in approved retrieval input")
    if record_type is not None and matches[0].get("record_type") != record_type:
        raise ValueError(f"approved source must be {record_type}")
    return matches[0]


def _doi(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if text.casefold().startswith(prefix):
            text = text[len(prefix):]
            break
    return text.casefold() or None


def _isbn(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    result = re.sub(r"[^0-9Xx]", "", value)
    return result.upper() if len(result) in {10, 13} else None


def _norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _validate_https_url(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RetrievalError("invalid_retrieval_url", "retrieval URL is empty")
    url = value.strip()
    parsed = urllib.parse.urlparse(url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise RetrievalError("invalid_retrieval_url", "retrieval URL has invalid port") from exc
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password \
            or parsed.fragment or port not in (None, 443):
        raise RetrievalError(
            "unsafe_retrieval_url", "retrieval URL must be credential-free HTTPS on port 443"
        )
    host = parsed.hostname.casefold()
    if host == "localhost":
        raise RetrievalError("unsafe_retrieval_host", "loopback retrieval host is prohibited")
    try:
        address = ipaddress.ip_address(host)
        if address.is_private or address.is_loopback or address.is_link_local \
                or address.is_reserved or address.is_multicast:
            raise RetrievalError("unsafe_retrieval_host", "private or reserved host is prohibited")
    except ValueError:
        pass
    return url


def _validate_metadata_url(provider: str, url: str) -> str:
    checked = _validate_https_url(url)
    parsed = urllib.parse.urlparse(checked)
    allowed = urllib.parse.urlparse(METADATA_ORIGINS[provider])
    if parsed.hostname != allowed.hostname:
        raise RetrievalError("unsafe_metadata_origin", f"{provider} metadata origin is invalid")
    return checked


def corpus_ref(path: Path, config: provider_config.ProviderRuntimeConfig) -> str:
    root = config.corpus_dir.resolve()
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("corpus path escapes configured corpus root") from exc
    return CORPUS_SCHEME + relative.as_posix()


def resolve_corpus_ref(ref: str, config: provider_config.ProviderRuntimeConfig) -> Path:
    if not isinstance(ref, str) or not ref.startswith(CORPUS_SCHEME):
        raise ValueError("not a corpus:// ref")
    relative = ref[len(CORPUS_SCHEME):]
    if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("unsafe corpus ref")
    root = config.corpus_dir.resolve()
    resolved = (root / Path(relative)).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("corpus ref escapes configured corpus root") from exc
    return resolved


def _rate_limit(config: provider_config.ProviderRuntimeConfig, provider: str) -> None:
    section = config.data.get("retrieval", {})
    rates = section.get("rate_limits", {}) if isinstance(section, dict) else {}
    interval = float(rates.get(f"{provider}_min_interval_seconds", 0.0))
    with _RATE_LOCKS[provider]:
        remaining = interval - (time.monotonic() - _LAST_REQUEST.get(provider, 0.0))
        if remaining > 0:
            time.sleep(remaining)
        _LAST_REQUEST[provider] = time.monotonic()


def _default_metadata_transport(url: str, headers: dict[str, str], timeout: float,
                                max_bytes: int) -> dict:
    request = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise RetrievalError("metadata_response_too_large", "metadata response exceeds limit")
        return {"status_code": response.status, "headers": dict(response.headers.items()),
                "body": body, "final_url": response.geturl()}


def _metadata_json(config: provider_config.ProviderRuntimeConfig, provider: str, url: str,
                   headers: dict[str, str], transport: MetadataTransport | None) -> dict:
    _validate_metadata_url(provider, url)
    section = config.data["retrieval"]
    request_cfg = section["request"]
    timeout = float(request_cfg["timeout_seconds"])
    max_retries = int(request_cfg["max_retries"])
    backoff = float(request_cfg["backoff_seconds"])
    max_bytes = int(request_cfg["max_metadata_response_bytes"])
    runner = transport or _default_metadata_transport
    request_headers = dict(headers)
    request_headers.setdefault("Accept", "application/json")
    request_headers.setdefault("User-Agent", METADATA_USER_AGENT)
    last: RetrievalError | None = None
    for attempt in range(max_retries + 1):
        _rate_limit(config, provider)
        try:
            raw = runner(url, request_headers, timeout, max_bytes)
            status = int(raw["status_code"])
            final_url = str(raw.get("final_url", url))
            _validate_metadata_url(provider, final_url)
            response_headers = {str(k).casefold(): str(v) for k, v in raw.get("headers", {}).items()}
            if status != 200:
                last = RetrievalError("metadata_http_error", f"{provider} returned HTTP {status}",
                                      status in RETRYABLE_STATUS, status)
            else:
                content_type = response_headers.get("content-type", "").casefold()
                if content_type and "json" not in content_type:
                    raise RetrievalError("metadata_content_type_error",
                                         f"{provider} returned non-JSON metadata")
                body = raw.get("body", b"")
                if isinstance(body, bytes):
                    body = body.decode("utf-8")
                return json.loads(body)
        except RetrievalError as exc:
            last = exc
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            last = RetrievalError(
                "metadata_http_error", f"{provider} returned HTTP {status}",
                status in RETRYABLE_STATUS, status,
            )
        except (urllib.error.URLError, TimeoutError, OSError, ValueError,
                UnicodeDecodeError, json.JSONDecodeError, KeyError) as exc:
            last = RetrievalError("metadata_transport_error", str(exc), True)
        if last is not None and (not last.retryable or attempt >= max_retries):
            break
        time.sleep(backoff * (2 ** attempt))
    assert last is not None
    raise last


def _candidate(provider: str, *, landing_url=None, file_url=None, version_type="unknown",
               license_value=None, identity_basis=None, access_basis="metadata", priority=100) -> dict:
    landing = _validate_https_url(landing_url) if landing_url else None
    file_value = _validate_https_url(file_url) if file_url else None
    return {
        "provider": provider, "landing_url": landing, "file_url": file_value,
        "version_type": version_type, "license": license_value,
        "identity_basis": list(identity_basis or []), "access_basis": access_basis,
        "priority": priority,
    }


def _official_https(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme == "http" and parsed.hostname in {
        "directory.doabooks.org", "library.oapen.org"
    }:
        return urllib.parse.urlunparse(parsed._replace(scheme="https", netloc=parsed.hostname))
    return value


def _record_candidates(record: dict) -> list[dict]:
    access = record.get("access", {})
    identifiers = record.get("identifiers", {})
    identity = []
    doi = _doi(identifiers.get("doi"))
    isbn = _isbn(identifiers.get("isbn"))
    if doi:
        identity.append(f"doi_exact:{doi}")
    if isbn:
        identity.append(f"isbn_exact:{isbn}")
    if identifiers.get("arxiv_id"):
        identity.append("provider_record_arxiv_id")
    identity = identity or ["approved_provider_record"]
    result = []
    for url in access.get("candidate_pdf_urls", []):
        try:
            result.append(_candidate(
                "record", landing_url=access.get("publisher_url"), file_url=url,
                version_type="preprint" if "arxiv" in str(url).casefold() else "unknown",
                license_value=None, identity_basis=identity,
                access_basis="approved source_record candidate_pdf_urls", priority=10,
            ))
        except RetrievalError:
            continue
    return result


def _unpaywall_candidates(record: dict, config: provider_config.ProviderRuntimeConfig,
                          transport: MetadataTransport | None) -> list[dict]:
    doi = _doi(record.get("identifiers", {}).get("doi"))
    if not doi or not config.contact_email:
        return []
    url = ("https://api.unpaywall.org/v2/" + urllib.parse.quote(doi, safe="/")
           + "?email=" + urllib.parse.quote(config.contact_email, safe="@"))
    payload = _metadata_json(config, "unpaywall", url, {"Accept": "application/json"}, transport)
    locations = []
    if isinstance(payload.get("best_oa_location"), dict):
        locations.append(payload["best_oa_location"])
    locations.extend(item for item in payload.get("oa_locations", []) if isinstance(item, dict))
    result = []
    for item in locations:
        file_url = item.get("url_for_pdf")
        if not file_url:
            continue
        version = {
            "publishedVersion": "version_of_record",
            "acceptedVersion": "accepted_manuscript",
            "submittedVersion": "submitted_manuscript",
        }.get(item.get("version"), "unknown")
        try:
            result.append(_candidate(
                "unpaywall", landing_url=item.get("url_for_landing_page") or item.get("url"),
                file_url=file_url, version_type=version, license_value=item.get("license"),
                identity_basis=[f"doi_exact:{doi}"], access_basis="Unpaywall OA location",
                priority=20,
            ))
        except RetrievalError:
            continue
    return result


def _core_candidates(record: dict, config: provider_config.ProviderRuntimeConfig,
                     transport: MetadataTransport | None) -> list[dict]:
    doi = _doi(record.get("identifiers", {}).get("doi"))
    key = config.retrieval_api_key("core")
    if not doi or not key:
        return []
    query = urllib.parse.urlencode({"q": f'doi:"{doi}"', "limit": 5})
    url = "https://api.core.ac.uk/v3/search/works?" + query
    payload = _metadata_json(
        config, "core", url, {"Accept": "application/json", "Authorization": f"Bearer {key}"},
        transport,
    )
    result = []
    for item in payload.get("results", []):
        if not isinstance(item, dict) or _doi(item.get("doi")) != doi:
            continue
        file_url = item.get("downloadUrl") or item.get("download_url")
        if not file_url and item.get("id") is not None:
            file_url = f"https://api.core.ac.uk/v3/works/{item['id']}/download"
        try:
            result.append(_candidate(
                "core", landing_url=item.get("sourceFulltextUrls", [None])[0]
                if isinstance(item.get("sourceFulltextUrls"), list) else None,
                file_url=file_url, version_type="unknown", license_value=item.get("license"),
                identity_basis=[f"doi_exact:{doi}"], access_basis="CORE exact DOI work",
                priority=30,
            ))
        except (RetrievalError, IndexError):
            continue
    return result


def _metadata_values(metadata: object, field: str) -> list[str]:
    if isinstance(metadata, list):
        return [entry["value"] for entry in metadata if isinstance(entry, dict)
                and entry.get("key") == field and isinstance(entry.get("value"), str)]
    if isinstance(metadata, dict):
        values = metadata.get(field, [])
        return [entry.get("value") for entry in values if isinstance(entry, dict)
                and isinstance(entry.get("value"), str)]
    return []


def _dspace_candidates(provider: str, record: dict,
                       config: provider_config.ProviderRuntimeConfig,
                       transport: MetadataTransport | None) -> list[dict]:
    identifiers = record.get("identifiers", {})
    doi = _doi(identifiers.get("doi"))
    isbn = _isbn(identifiers.get("isbn"))
    title = record.get("bibliographic", {}).get("title")
    query_value = isbn or doi or str(title or "").strip()
    if not query_value:
        return []
    base = METADATA_ORIGINS[provider]
    query = urllib.parse.urlencode({"query": query_value, "limit": 5})
    url = base + "/rest/search?" + query
    payload = _metadata_json(config, provider, url, {"Accept": "application/json"}, transport)
    objects = payload if isinstance(payload, list) else []
    result = []
    for item in objects:
        if not isinstance(item, dict) or not isinstance(item.get("uuid"), str):
            continue
        metadata_url = base + f"/rest/items/{item['uuid']}/metadata"
        metadata = _metadata_json(
            config, provider, metadata_url, {"Accept": "application/json"}, transport
        )
        item_dois = [_doi(value) for value in _metadata_values(metadata, "dc.identifier.doi")]
        item_isbns = [_isbn(value) for value in (
            _metadata_values(metadata, "dc.identifier.isbn")
            + _metadata_values(metadata, "dc.identifier.other"))]
        item_titles = _metadata_values(metadata, "dc.title")
        identity = []
        if doi and doi in item_dois:
            identity.append(f"doi_exact:{doi}")
        if isbn and isbn in item_isbns:
            identity.append(f"isbn_exact:{isbn}")
        if title and any(_norm(value) == _norm(title) for value in item_titles):
            identity.append("title_exact")
        if not identity:
            continue
        landing = _official_https(next(iter(_metadata_values(metadata, "dc.identifier.uri")), None))
        file_urls = []
        if provider == "oapen":
            bitstreams_url = base + f"/rest/items/{item['uuid']}/bitstreams"
            bitstreams = _metadata_json(
                config, provider, bitstreams_url, {"Accept": "application/json"}, transport
            )
            for bitstream in bitstreams if isinstance(bitstreams, list) else []:
                if not isinstance(bitstream, dict) \
                        or bitstream.get("bundleName") != "ORIGINAL" \
                        or bitstream.get("mimeType") != "application/pdf":
                    continue
                retrieve_link = bitstream.get("retrieveLink")
                if isinstance(retrieve_link, str):
                    file_urls.append(base + retrieve_link if retrieve_link.startswith("/")
                                     else retrieve_link)
        if file_urls:
            for file_url in file_urls:
                try:
                    result.append(_candidate(
                        provider, landing_url=landing, file_url=file_url,
                        version_type="published_book", license_value=next(iter(
                            _metadata_values(metadata, "dc.rights.license")), None),
                        identity_basis=identity, access_basis=f"{provider.upper()} repository record",
                        priority=40 if provider == "oapen" else 60,
                    ))
                except RetrievalError:
                    continue
        elif landing:
            try:
                result.append(_candidate(
                    provider, landing_url=landing, file_url=None, version_type="published_book",
                    identity_basis=identity, access_basis=f"{provider.upper()} catalog record",
                    priority=80,
                ))
            except RetrievalError:
                continue
    return result


def resolve_open_access(retrieval_input: dict, source_id: str, *, config_path=None,
                        runtime_home=None, artifact_base=None,
                        metadata_transport: MetadataTransport | None = None) -> dict:
    errors = _shape(retrieval_input, RETRIEVAL_INPUT_CONTRACT)
    if errors:
        raise ValueError("invalid retrieval input: " + "; ".join(errors))
    approved = _source(retrieval_input, source_id)
    operation_id = f"OP_{uuid.uuid4().hex.upper()}"
    record_type = approved["record_type"]
    if record_type == "market_case":
        resolution = {
            "schema_version": RESOLUTION_CONTRACT, "operation_id": operation_id,
            "task_id": retrieval_input["task_id"], "source_id": source_id,
            "record_type": record_type, "status": "market_extract",
            "checked_providers": [{"provider": "tavily", "status": "gated_by_A11", "candidate_count": 1}],
            "candidates": [_candidate(
                "tavily", landing_url=approved["source_record"].get("access", {}).get("publisher_url"),
                file_url=None, version_type="unknown", identity_basis=["approved_market_source_id"],
                access_basis="reviewed A11 market case", priority=1,
            )],
            "selected_candidate": None, "issues": [], "resolved_at": _utc_now(),
        }
        ref = artifacts.store(
            f"g02/oa-resolutions/{operation_id}.json", resolution, base=artifact_base
        )
        return {**resolution, "artifact_ref": ref}
    verification = approved.get("doi_verification")
    if isinstance(verification, dict) and verification.get("match_status") == "conflict":
        resolution = {
            "schema_version": RESOLUTION_CONTRACT, "operation_id": operation_id,
            "task_id": retrieval_input["task_id"], "source_id": source_id,
            "record_type": record_type, "status": "unavailable",
            "checked_providers": [{"provider": "crossref", "status": "identity_conflict",
                                   "candidate_count": 0}],
            "candidates": [], "selected_candidate": None,
            "issues": [_issue(
                "crossref_identity_conflict",
                "Crossref conflicts with the approved bibliographic identity; automated retrieval is blocked",
                provider="crossref",
            )],
            "resolved_at": _utc_now(),
        }
        errors = _shape(resolution, RESOLUTION_CONTRACT)
        if errors:
            raise ValueError("invalid OA resolution: " + "; ".join(errors))
        ref = artifacts.store(
            f"g02/oa-resolutions/{operation_id}.json", resolution, base=artifact_base
        )
        return {**resolution, "artifact_ref": ref}
    config = provider_config.load_config(
        config_path, runtime_home=runtime_home, create_dirs=True
    )
    if not config.retrieval_enabled():
        raise ValueError("retrieval provider profile is disabled")
    record = approved["source_record"]
    checked, candidates, issues = [], [], []
    resolvers = {
        "record": lambda: _record_candidates(record),
        "unpaywall": lambda: _unpaywall_candidates(record, config, metadata_transport),
        "core": lambda: _core_candidates(record, config, metadata_transport),
        "doab": lambda: _dspace_candidates("doab", record, config, metadata_transport),
        "oapen": lambda: _dspace_candidates("oapen", record, config, metadata_transport),
    }
    for provider in provider_config.RETRIEVAL_PROVIDERS:
        if not config.retrieval_provider_enabled(provider):
            checked.append({"provider": provider, "status": "disabled", "candidate_count": 0})
            continue
        ready = next((item["ready"] for item in config.public_retrieval_status()["capabilities"]
                      if item["provider"] == provider), False)
        if not ready:
            checked.append({"provider": provider, "status": "unavailable", "candidate_count": 0})
            issues.append(_issue("retrieval_provider_not_ready",
                                 f"{provider} is enabled but not ready", provider=provider))
            continue
        try:
            found = resolvers[provider]()
            candidates.extend(found)
            checked.append({"provider": provider, "status": "ok", "candidate_count": len(found)})
        except RetrievalError as exc:
            checked.append({"provider": provider, "status": "failed", "candidate_count": 0})
            issues.append(_issue(exc.code, exc.message, retryable=exc.retryable, provider=provider))
    downloadable = [item for item in candidates if item.get("file_url")]
    downloadable.sort(key=lambda item: (item["priority"], item["provider"], item["file_url"]))
    selected = downloadable[0] if downloadable else None
    library = record.get("access", {}).get("library_access_required") is True
    status = "resolved" if selected else ("library_required" if library else "unavailable")
    resolution = {
        "schema_version": RESOLUTION_CONTRACT, "operation_id": operation_id,
        "task_id": retrieval_input["task_id"], "source_id": source_id,
        "record_type": record_type, "status": status, "checked_providers": checked,
        "candidates": candidates, "selected_candidate": selected, "issues": issues,
        "resolved_at": _utc_now(),
    }
    errors = _shape(resolution, RESOLUTION_CONTRACT)
    if errors:
        raise ValueError("invalid OA resolution: " + "; ".join(errors))
    ref = artifacts.store(f"g02/oa-resolutions/{operation_id}.json", resolution, base=artifact_base)
    return {**resolution, "artifact_ref": ref}


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, max_redirects: int):
        self.max_redirects = max_redirects
        self.chain: list[str] = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_https_url(newurl)
        _reject_private_dns(newurl)
        if len(self.chain) >= self.max_redirects:
            raise RetrievalError("redirect_limit_exceeded", "document redirect limit exceeded")
        self.chain.append(newurl)
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None:
            redirected.remove_header("Authorization")
        return redirected


def _reject_private_dns(url: str) -> None:
    host = urllib.parse.urlparse(url).hostname
    if not host:
        raise RetrievalError("unsafe_retrieval_host", "retrieval host is missing")
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise RetrievalError("retrieval_dns_error", str(exc), True) from exc
    for item in addresses:
        address = ipaddress.ip_address(item[4][0])
        if address.is_private or address.is_loopback or address.is_link_local \
                or address.is_reserved or address.is_multicast:
            raise RetrievalError("unsafe_retrieval_host",
                                 "retrieval DNS resolved to a private or reserved address")


def _default_download_transport(url: str, headers: dict[str, str], timeout: float,
                                max_bytes: int, target: Path, max_redirects: int) -> dict:
    _reject_private_dns(url)
    handler = _SafeRedirectHandler(max_redirects)
    opener = urllib.request.build_opener(handler)
    request = urllib.request.Request(url, headers=headers, method="GET")
    digest = hashlib.sha256()
    total = 0
    target.parent.mkdir(parents=True, exist_ok=True)
    with opener.open(request, timeout=timeout) as response, target.open("wb") as output:
        final_url = _validate_https_url(response.geturl())
        _reject_private_dns(final_url)
        while True:
            chunk = response.read(65536)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise RetrievalError("document_too_large", "document exceeds configured byte limit")
            digest.update(chunk)
            output.write(chunk)
        output.flush()
        os.fsync(output.fileno())
        return {
            "status_code": response.status, "headers": dict(response.headers.items()),
            "final_url": final_url, "url_chain": [url, *handler.chain, final_url],
            "byte_count": total, "sha256": digest.hexdigest(),
        }


def retrieve_document(retrieval_input: dict, resolution_ref: str, *, config_path=None,
                      runtime_home=None, artifact_base=None,
                      download_transport: DownloadTransport | None = None) -> dict:
    errors = _shape(retrieval_input, RETRIEVAL_INPUT_CONTRACT)
    if errors:
        raise ValueError("invalid retrieval input: " + "; ".join(errors))
    if not isinstance(resolution_ref, str) or not resolution_ref.startswith(artifacts.SCHEME):
        raise ValueError("resolution_ref must use artifact://")
    resolution = artifacts.hydrate(resolution_ref, base=artifact_base)
    errors = _shape(resolution, RESOLUTION_CONTRACT)
    if errors:
        raise ValueError("invalid OA resolution: " + "; ".join(errors))
    if resolution["task_id"] != retrieval_input["task_id"]:
        raise ValueError("resolution task differs from retrieval input")
    approved = _source(retrieval_input, resolution["source_id"], "scholarly")
    operation_id = f"OP_{uuid.uuid4().hex.upper()}"
    config = provider_config.load_config(
        config_path, runtime_home=runtime_home, create_dirs=True
    )
    if config.retrieval_temp_dir is None:
        raise ValueError("retrieval temp directory is not configured")
    target_dir = config.retrieval_temp_dir / _safe(retrieval_input["task_id"])
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{_safe(resolution['source_id'])}.{operation_id}.part"
    selected = resolution.get("selected_candidate")
    attempts, issues = [], []
    status = "unavailable"
    temporary_ref = final_url = content_type = digest = signature = None
    byte_count = 0
    url_chain = []
    if resolution.get("status") == "resolved" and isinstance(selected, dict):
        url = _validate_https_url(selected.get("file_url"))
        section = config.data["retrieval"]
        request_cfg = section["request"]
        timeout = float(request_cfg["timeout_seconds"])
        max_retries = int(request_cfg["max_retries"])
        backoff = float(request_cfg["backoff_seconds"])
        max_bytes = int(request_cfg["max_document_bytes"])
        max_redirects = int(request_cfg["max_redirects"])
        runner = download_transport or _default_download_transport
        for attempt in range(max_retries + 1):
            try:
                request_headers = {
                    "Accept": "application/pdf,application/octet-stream;q=0.9",
                    "User-Agent": "EduMaterialsAgents/0.9",
                }
                if selected.get("provider") == "core":
                    key = config.retrieval_api_key("core")
                    if not key:
                        raise RetrievalError("core_key_missing", "CORE download requires CORE_API_KEY")
                    request_headers["Authorization"] = f"Bearer {key}"
                raw = runner(
                    url, request_headers,
                    timeout, max_bytes, target, max_redirects,
                )
                response_status = int(raw["status_code"])
                attempts.append({"attempt": attempt + 1, "url": url,
                                 "http_status": response_status, "status": "ok" if response_status == 200 else "failed"})
                if response_status != 200:
                    retryable = response_status in RETRYABLE_STATUS
                    if retryable and attempt < max_retries:
                        time.sleep(backoff * (2 ** attempt))
                        continue
                    raise RetrievalError("document_http_error",
                                         f"document host returned HTTP {response_status}", retryable)
                final_url = _validate_https_url(raw.get("final_url", url))
                url_chain = list(dict.fromkeys(raw.get("url_chain", [url, final_url])))
                for chain_url in url_chain:
                    _validate_https_url(chain_url)
                headers = {str(k).casefold(): str(v) for k, v in raw.get("headers", {}).items()}
                content_type = headers.get("content-type", "").split(";", 1)[0].strip().casefold() or None
                byte_count = int(raw.get("byte_count", target.stat().st_size))
                digest = str(raw.get("sha256") or "") or hashlib.sha256(target.read_bytes()).hexdigest()
                signature = target.read_bytes()[:5].decode("ascii", errors="replace")
                temporary_ref = corpus_ref(target, config)
                status = "downloaded"
                break
            except urllib.error.HTTPError as exc:
                response_status = int(exc.code)
                retryable = response_status in RETRYABLE_STATUS
                issues.append(_issue(
                    "document_http_error",
                    f"document host returned HTTP {response_status}",
                    retryable=retryable, provider=selected.get("provider"),
                ))
                attempts.append({"attempt": attempt + 1, "url": url,
                                 "http_status": response_status, "status": "failed"})
                target.unlink(missing_ok=True)
                if not retryable or attempt >= max_retries:
                    status = "failed"
                    break
                time.sleep(backoff * (2 ** attempt))
            except (RetrievalError, urllib.error.URLError, TimeoutError, OSError,
                    ValueError, KeyError) as exc:
                retryable = exc.retryable if isinstance(exc, RetrievalError) else True
                code = exc.code if isinstance(exc, RetrievalError) else "document_transport_error"
                issues.append(_issue(code, str(exc), retryable=retryable,
                                     provider=selected.get("provider")))
                attempts.append({"attempt": attempt + 1, "url": url,
                                 "http_status": getattr(exc, "http_status", None), "status": "failed"})
                target.unlink(missing_ok=True)
                if not retryable or attempt >= max_retries:
                    status = "failed"
                    break
                time.sleep(backoff * (2 ** attempt))
    else:
        issues.extend(resolution.get("issues", []))
    candidate = {
        "schema_version": FILE_CONTRACT, "operation_id": operation_id,
        "task_id": retrieval_input["task_id"], "source_id": approved["source_id"],
        "status": status, "resolution_ref": resolution_ref,
        "temporary_ref": temporary_ref, "final_url": final_url, "url_chain": url_chain,
        "content_type": content_type, "byte_count": byte_count, "sha256": digest,
        "signature": signature, "attempts": attempts, "issues": issues,
        "retrieved_at": _utc_now(),
    }
    errors = _shape(candidate, FILE_CONTRACT)
    if errors:
        target.unlink(missing_ok=True)
        raise ValueError("invalid retrieved file candidate: " + "; ".join(errors))
    ref = artifacts.store(f"g02/retrieved-files/{operation_id}.json", candidate,
                          base=artifact_base)
    return {**candidate, "artifact_ref": ref}


def validate_document(retrieval_input: dict, retrieved_file_ref: str, *, config_path=None,
                      runtime_home=None, artifact_base=None) -> dict:
    errors = _shape(retrieval_input, RETRIEVAL_INPUT_CONTRACT)
    if errors:
        raise ValueError("invalid retrieval input: " + "; ".join(errors))
    if not isinstance(retrieved_file_ref, str) or not retrieved_file_ref.startswith(artifacts.SCHEME):
        raise ValueError("retrieved_file_ref must use artifact://")
    candidate = artifacts.hydrate(retrieved_file_ref, base=artifact_base)
    errors = _shape(candidate, FILE_CONTRACT)
    if errors:
        raise ValueError("invalid retrieved file candidate: " + "; ".join(errors))
    source = _source(retrieval_input, candidate["source_id"], "scholarly")
    resolution = artifacts.hydrate(candidate["resolution_ref"], base=artifact_base)
    config = provider_config.load_config(
        config_path, runtime_home=runtime_home, create_dirs=True
    )
    issues = list(candidate.get("issues", []))
    content_type_valid = candidate.get("content_type") in {
        "application/pdf", "application/octet-stream", "binary/octet-stream", None,
    }
    signature_valid = candidate.get("signature") == "%PDF-"
    selected = resolution.get("selected_candidate") if isinstance(resolution, dict) else None
    identity_basis = list(selected.get("identity_basis", [])) if isinstance(selected, dict) else []
    identity_valid = any(
        basis.startswith(("doi_exact:", "isbn_exact:"))
        or basis in {"provider_record_arxiv_id", "approved_market_source_id"}
        for basis in identity_basis
    ) or (isinstance(selected, dict) and selected.get("provider") == "oapen"
          and "title_exact" in identity_basis)
    local_ref = None
    page_count = None
    duplicate_of = None
    status = "rejected"
    temp_path = None
    if candidate.get("status") in {"downloaded", "reused"} and candidate.get("temporary_ref"):
        temp_path = resolve_corpus_ref(candidate["temporary_ref"], config)
        if not temp_path.is_file() or temp_path.stat().st_size != candidate["byte_count"]:
            issues.append(_issue("retrieved_file_missing", "temporary document is missing or changed"))
        else:
            digest = hashlib.sha256(temp_path.read_bytes()).hexdigest()
            if digest != candidate.get("sha256"):
                issues.append(_issue("checksum_mismatch", "temporary document checksum changed"))
            elif not content_type_valid:
                issues.append(_issue("invalid_document_content_type", "download is not a PDF content type"))
            elif not signature_valid:
                issues.append(_issue("invalid_pdf_signature", "download does not begin with %PDF-"))
            elif not identity_valid:
                issues.append(_issue("document_identity_unverified", "resolver supplied no exact identity basis"))
            else:
                prefix = temp_path.read_bytes()[:2097152]
                observed = prefix.decode("latin-1", errors="ignore").casefold()
                expected_doi = _doi(source["source_record"].get("identifiers", {}).get("doi"))
                expected_isbn = _isbn(source["source_record"].get("identifiers", {}).get("isbn"))
                if expected_doi and expected_doi in observed:
                    identity_basis.append("file_doi_match")
                if expected_isbn and expected_isbn in re.sub(r"[^0-9x]", "", observed):
                    identity_basis.append("file_isbn_match")
                page_matches = re.findall(rb"/Type\s*/Page\b", prefix)
                page_count = len(page_matches) or None
                previous_documents = [item for item in retrieval_input.get("previous_documents", [])
                                      if isinstance(item, dict)]
                known = {item.get("sha256"): item.get("source_id")
                         for item in previous_documents
                         if isinstance(item.get("sha256"), str)
                         and isinstance(item.get("source_id"), str)}
                duplicate_of = known.get(digest)
                if duplicate_of:
                    status = "duplicate"
                    local_ref = next((item.get("local_ref") for item in previous_documents
                                      if item.get("source_id") == duplicate_of), None)
                else:
                    if config.retrieval_accepted_dir is None:
                        raise ValueError("retrieval accepted directory is not configured")
                    run_dir = (config.retrieval_accepted_dir / _safe(retrieval_input["task_id"])
                               / _safe(retrieval_input["approved_source_set_artifact_version"])
                               / "documents")
                    run_dir.mkdir(parents=True, exist_ok=True)
                    final_path = run_dir / f"{_safe(source['source_id'])}.pdf"
                    fd, temporary_name = tempfile.mkstemp(
                        prefix=f".{final_path.name}.", suffix=".tmp", dir=run_dir
                    )
                    os.close(fd)
                    promotion = Path(temporary_name)
                    try:
                        shutil.copyfile(temp_path, promotion)
                        os.replace(promotion, final_path)
                    finally:
                        promotion.unlink(missing_ok=True)
                    local_ref = corpus_ref(final_path, config)
                    status = "accepted"
    document = {
        "schema_version": DOCUMENT_CONTRACT, "task_id": retrieval_input["task_id"],
        "source_id": candidate["source_id"], "status": status, "local_ref": local_ref,
        "file_type": "pdf" if status in {"accepted", "duplicate"} else None,
        "byte_count": candidate["byte_count"], "sha256": candidate.get("sha256"),
        "content_type_valid": content_type_valid, "signature_valid": signature_valid,
        "identity_valid": identity_valid, "identity_basis": identity_basis,
        "version_type": selected.get("version_type", "unknown") if isinstance(selected, dict) else "unknown",
        "license": selected.get("license") if isinstance(selected, dict) else None,
        "page_count": page_count, "duplicate_of_source_id": duplicate_of,
        "resolution_ref": candidate["resolution_ref"], "retrieved_file_ref": retrieved_file_ref,
        "issues": issues, "validated_at": _utc_now(),
    }
    errors = _shape(document, DOCUMENT_CONTRACT)
    if errors:
        raise ValueError("invalid validated document: " + "; ".join(errors))
    ref = artifacts.store(
        f"g02/validated-documents/{_safe(document['source_id'])}.{uuid.uuid4().hex}.json",
        document, base=artifact_base,
    )
    if isinstance(temp_path, Path):
        temp_path.unlink(missing_ok=True)
    return {**document, "artifact_ref": ref}
