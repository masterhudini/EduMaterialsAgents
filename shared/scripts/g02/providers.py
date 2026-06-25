"""Deterministic scholarly metadata adapters for OpenAlex, Semantic Scholar and arXiv.

The module owns HTTPS, retry, rate limiting, cache, raw-response persistence and provider-to-
``source_record@1`` normalization. Agents receive only structured results through MCP.
"""
from __future__ import annotations

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
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core import artifacts, contracts
from g02 import provider_config, query_planning

TOOL_RESULT_CONTRACT = "literature_tool_result@1"
SOURCE_RECORD_CONTRACT = "source_record@1"
DOMAIN_INPUT_CONTRACT = "domain_research_input@1"
CANONICAL_INPUT_CONTRACT = "canonical_research_input@1"
RECENT_INPUT_CONTRACT = "recent_research_input@1"
RESEARCH_PLAN_CONTRACT = "research_plan@1"
PROVIDERS = ("openalex", "semantic_scholar", "arxiv")
ENDPOINTS = {
    "openalex": "https://api.openalex.org/works",
    "semantic_scholar": "https://api.semanticscholar.org/graph/v1/paper/search",
    "arxiv": "https://export.arxiv.org/api/query",
}
ALLOWED_HOSTS = {
    "openalex": "api.openalex.org",
    "semantic_scholar": "api.semanticscholar.org",
    "arxiv": "export.arxiv.org",
}
ACCEPTED_CONTENT_TYPES = {
    "openalex": ("application/json",),
    "semantic_scholar": ("application/json",),
    "arxiv": ("application/atom+xml", "application/xml", "text/xml"),
}
RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}
S2_FIELDS = (
    "paperId,title,abstract,year,authors,venue,externalIds,citationCount,"
    "isOpenAccess,openAccessPdf,publicationTypes,url"
)
OPENALEX_SELECT = (
    "id,doi,title,display_name,authorships,publication_year,primary_location,language,type,"
    "cited_by_count,abstract_inverted_index,open_access,best_oa_location"
)
ARXIV_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
    "arxiv": "http://arxiv.org/schemas/atom",
}

_RATE_LOCKS = {provider: threading.Lock() for provider in PROVIDERS}
_LAST_REQUEST: dict[str, float] = {}


@dataclass
class ProviderRequestError(Exception):
    code: str
    message: str
    retryable: bool
    http_status: int | None = None

    def __str__(self) -> str:
        return self.message


@dataclass
class PageResponse:
    status_code: int
    headers: dict[str, str]
    body_text: str
    cache_hit: bool
    request_id: str | None


Transport = Callable[[str, dict[str, str], float, int], dict]


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _issue(code: str, message: str, *, retryable: bool = False) -> dict:
    return {"code": code, "retryable": retryable, "message": message}


def _redact(message: object, secrets: list[str | None]) -> str:
    result = str(message)
    for secret in secrets:
        if secret:
            result = result.replace(secret, "<redacted>")
            result = result.replace(urllib.parse.quote_plus(secret), "<redacted>")
    return result


def _validate_url(provider: str, url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ProviderRequestError(
            "unsafe_provider_endpoint", "provider endpoint contains an invalid port", False
        ) from exc
    if parsed.scheme != "https" or parsed.hostname != ALLOWED_HOSTS[provider] \
            or port not in (None, 443) or parsed.username or parsed.password:
        raise ProviderRequestError(
            "unsafe_provider_endpoint",
            f"provider endpoint is outside the HTTPS allowlist for {provider}",
            False,
        )


class _SameOriginRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow redirects only when they remain on the initial HTTPS origin."""

    def __init__(self, provider: str):
        super().__init__()
        self.provider = provider

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_url(self.provider, newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _read_limited(response, max_bytes: int) -> bytes:
    payload = response.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise ProviderRequestError(
            "provider_response_too_large",
            f"provider response exceeds configured {max_bytes} byte limit",
            False,
        )
    return payload


def _default_transport(url: str, headers: dict[str, str], timeout: float,
                       max_bytes: int) -> dict:
    provider = next(
        name for name, host in ALLOWED_HOSTS.items()
        if urllib.parse.urlparse(url).hostname == host
    )
    request = urllib.request.Request(url, headers=headers, method="GET")
    opener = urllib.request.build_opener(_SameOriginRedirectHandler(provider))
    try:
        with opener.open(request, timeout=timeout) as response:
            final_url = response.geturl()
            body = _read_limited(response, max_bytes)
            if int(response.status) == 200:   # a real provider query succeeded -> creds proven; drop the file
                from g02 import credentials
                credentials.purge_once()
            return {
                "status_code": int(response.status),
                "headers": {key.lower(): value for key, value in response.headers.items()},
                "body": body,
                "final_url": final_url,
            }
    except urllib.error.HTTPError as exc:
        body = _read_limited(exc, max_bytes)
        return {
            "status_code": int(exc.code),
            "headers": {key.lower(): value for key, value in exc.headers.items()},
            "body": body,
            "final_url": exc.geturl(),
        }


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _cache_path(config: provider_config.ProviderRuntimeConfig,
                provider: str, url: str) -> Path:
    digest = hashlib.sha256(f"{provider}\0{url}".encode("utf-8")).hexdigest()
    return config.cache_dir / provider / f"{digest}.json"


def _cached_response(config: provider_config.ProviderRuntimeConfig,
                     provider: str, url: str) -> PageResponse | None:
    cache = config.data["cache"]
    assert isinstance(cache, dict)
    if cache.get("enabled") is not True:
        return None
    path = _cache_path(config, provider, url)
    if not path.is_file():
        return None
    request_cfg = config.data["request"]
    assert isinstance(request_cfg, dict)
    max_bytes = int(request_cfg["max_response_bytes"])
    if path.stat().st_size > max_bytes * 2 + 65536:
        return None
    ttl = int(cache["ttl_seconds"])
    if ttl == 0 or time.time() - path.stat().st_mtime > ttl:
        return None
    try:
        item = json.loads(path.read_text(encoding="utf-8"))
        response = PageResponse(
            status_code=int(item["status_code"]),
            headers=dict(item.get("headers", {})),
            body_text=str(item["body_text"]),
            cache_hit=True,
            request_id=item.get("request_id"),
        )
        if response.status_code != 200 \
                or len(response.body_text.encode("utf-8")) > max_bytes:
            return None
        _validate_content_type(provider, response.headers)
        return response
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError,
            ProviderRequestError):
        return None


def _write_cache(config: provider_config.ProviderRuntimeConfig, provider: str,
                 url: str, response: PageResponse) -> None:
    cache = config.data["cache"]
    assert isinstance(cache, dict)
    if cache.get("enabled") is not True or int(cache["ttl_seconds"]) == 0 \
            or response.status_code != 200:
        return
    _atomic_json(_cache_path(config, provider, url), {
        "status_code": response.status_code,
        "headers": {
            key: value for key, value in response.headers.items()
            if key in {"content-type", "etag", "last-modified"}
        },
        "body_text": response.body_text,
        "request_id": response.request_id,
        "cached_at": _utc_now(),
    })


def _rate_interval(config: provider_config.ProviderRuntimeConfig, provider: str) -> float:
    rates = config.data["rate_limits"]
    assert isinstance(rates, dict)
    return float(rates[f"{provider}_min_interval_seconds"])


def _wait_for_rate_limit(config: provider_config.ProviderRuntimeConfig, provider: str) -> None:
    interval = _rate_interval(config, provider)
    with _RATE_LOCKS[provider]:
        now = time.monotonic()
        remaining = interval - (now - _LAST_REQUEST.get(provider, 0.0))
        if remaining > 0:
            time.sleep(remaining)
        _LAST_REQUEST[provider] = time.monotonic()


def _decode_body(body: object, headers: dict[str, str]) -> str:
    if isinstance(body, str):
        return body
    if not isinstance(body, (bytes, bytearray)):
        raise ProviderRequestError(
            "invalid_transport_body", "provider transport returned a non-byte body", False
        )
    content_type = headers.get("content-type", "")
    match = re.search(r"charset=([^;\s]+)", content_type, flags=re.I)
    charset = match.group(1).strip('"') if match else "utf-8"
    try:
        return bytes(body).decode(charset)
    except (LookupError, UnicodeDecodeError) as exc:
        raise ProviderRequestError(
            "provider_decode_error", f"cannot decode provider response: {exc}", False
        ) from exc


def _validate_content_type(provider: str, headers: dict[str, str]) -> None:
    content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type and content_type not in ACCEPTED_CONTENT_TYPES[provider]:
        raise ProviderRequestError(
            "provider_content_type_error",
            f"{provider} returned unsupported content type {content_type!r}",
            False,
        )


def _request_page(config: provider_config.ProviderRuntimeConfig, provider: str, url: str,
                  headers: dict[str, str], transport: Transport | None) -> PageResponse:
    _validate_url(provider, url)
    cached = _cached_response(config, provider, url)
    if cached is not None:
        return cached
    request_cfg = config.data["request"]
    assert isinstance(request_cfg, dict)
    timeout = float(request_cfg["timeout_seconds"])
    max_retries = int(request_cfg["max_retries"])
    backoff = float(request_cfg["backoff_seconds"])
    max_bytes = int(request_cfg["max_response_bytes"])
    secrets = [config.api_key(provider), config.contact_email]
    runner = transport or _default_transport
    last_error: ProviderRequestError | None = None

    for attempt in range(max_retries + 1):
        _wait_for_rate_limit(config, provider)
        try:
            raw = runner(url, headers, timeout, max_bytes)
            if not isinstance(raw, dict):
                raise ProviderRequestError(
                    "invalid_transport_result", "provider transport returned a non-object", False
                )
            status = int(raw["status_code"])
            response_headers = {
                str(key).lower(): str(value)
                for key, value in dict(raw.get("headers", {})).items()
            }
            final_url = str(raw.get("final_url", url))
            _validate_url(provider, final_url)
            body_text = _decode_body(raw.get("body", b""), response_headers)
            request_id = next((response_headers.get(key) for key in (
                "x-request-id", "x-amzn-requestid", "cf-ray"
            ) if response_headers.get(key)), None)
            response = PageResponse(status, response_headers, body_text, False, request_id)
            if status == 200:
                _validate_content_type(provider, response_headers)
                try:
                    _write_cache(config, provider, url, response)
                except (OSError, TypeError, ValueError):
                    pass
                return response
            retryable = status in RETRYABLE_STATUS
            last_error = ProviderRequestError(
                "provider_http_error",
                _redact(f"{provider} returned HTTP {status}", secrets),
                retryable,
                status,
            )
            if not retryable or attempt >= max_retries:
                break
            retry_after = response_headers.get("retry-after")
            delay = backoff * (2 ** attempt)
            if retry_after and retry_after.isdigit():
                delay = min(float(retry_after), 60.0)
            time.sleep(delay)
        except ProviderRequestError as exc:
            last_error = ProviderRequestError(
                exc.code, _redact(exc.message, secrets), exc.retryable, exc.http_status
            )
            if not exc.retryable or attempt >= max_retries:
                break
            time.sleep(backoff * (2 ** attempt))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError) as exc:
            last_error = ProviderRequestError(
                "provider_transport_error", _redact(exc, secrets), True
            )
            if attempt >= max_retries:
                break
            time.sleep(backoff * (2 ** attempt))
    assert last_error is not None
    raise last_error


def _safe_provider_id(provider: str, provider_id: str) -> str:
    digest = hashlib.sha256(f"{provider}:{provider_id}".encode("utf-8")).hexdigest()[:16]
    return f"SRC_{provider.upper()}_{digest.upper()}"


def _doi(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    result = value.strip()
    for prefix in (
        "https://doi.org/", "http://doi.org/", "https://dx.doi.org/",
        "http://dx.doi.org/", "doi:",
    ):
        if result.lower().startswith(prefix):
            result = result[len(prefix):]
            break
    return result.lower() or None


def _abstract_from_inverted(value: object) -> str | None:
    if not isinstance(value, dict) or not value:
        return None
    positions: list[tuple[int, str]] = []
    for word, indices in value.items():
        if not isinstance(word, str) or not isinstance(indices, list):
            continue
        positions.extend((index, word) for index in indices
                         if isinstance(index, int) and not isinstance(index, bool))
    return " ".join(word for _, word in sorted(positions)) or None


def _canonical_work_type(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    token = re.sub(r"[^a-z]", "", value.lower())
    return {
        "article": "article",
        "journalarticle": "article",
        "review": "review",
        "book": "book",
        "bookchapter": "chapter",
        "booksection": "chapter",
        "chapter": "chapter",
        "preprint": "preprint",
        "proceedingsarticle": "conference",
        "conference": "conference",
    }.get(token, value.strip().lower())


def _base_record(provider: str, provider_id: str, *, query_id: str, topic_id: str,
                 raw_ref: str, retrieved_at: str) -> dict:
    return {
        "schema_version": SOURCE_RECORD_CONTRACT,
        "source_id": _safe_provider_id(provider, provider_id),
        "identifiers": {
            "doi": None,
            "openalex_id": None,
            "semantic_scholar_id": None,
            "arxiv_id": None,
            "isbn": None,
        },
        "bibliographic": {
            "title": "",
            "authors": [],
            "year": None,
            "venue": None,
            "publisher": None,
            "language": None,
            "work_type": None,
        },
        "content_available": {
            "abstract": None,
            "abstract_source": None,
            "table_of_contents_available": False,
        },
        "classification": {
            "related_topics": [topic_id],
            "related_claims": [],
            "source_roles": [],
            "category": None,
        },
        "signals": {
            "cited_by_count": None,
            "citation_percentile": None,
            "recent_citation_velocity": None,
            "internal_graph_centrality": None,
            "recommendation_signal": None,
            "canonical_score": None,
            "rising_score": None,
        },
        "access": {
            "oa_status": "unknown",
            "access_level": "metadata_only",
            "candidate_pdf_urls": [],
            "publisher_url": None,
            "library_access_required": False,
        },
        "provenance": {
            "source_apis": [provider],
            "provider_record_ids": {provider: provider_id},
            "retrieved_at": retrieved_at,
            "query_ids": [query_id],
            "raw_response_refs": [raw_ref],
            "merged_from_records": [],
        },
        "inclusion": {
            "reason_included": ["returned_by_approved_query"],
            "coverage_units": [],
            "pool": "domain_raw",
        },
    }


def _normalize_openalex(item: object, *, query_id: str, topic_id: str,
                        raw_ref: str, retrieved_at: str) -> dict | None:
    if not isinstance(item, dict) or not isinstance(item.get("id"), str):
        return None
    provider_id = item["id"].rsplit("/", 1)[-1]
    record = _base_record(
        "openalex", provider_id, query_id=query_id, topic_id=topic_id,
        raw_ref=raw_ref, retrieved_at=retrieved_at,
    )
    record["identifiers"]["openalex_id"] = provider_id
    record["identifiers"]["doi"] = _doi(item.get("doi"))
    authors = item.get("authorships") if isinstance(item.get("authorships"), list) else []
    record["bibliographic"]["authors"] = [
        author["author"]["display_name"] for author in authors
        if isinstance(author, dict) and isinstance(author.get("author"), dict)
        and isinstance(author["author"].get("display_name"), str)
    ]
    primary = item.get("primary_location") if isinstance(item.get("primary_location"), dict) else {}
    source = primary.get("source") if isinstance(primary.get("source"), dict) else {}
    record["bibliographic"].update({
        "title": item.get("title") or item.get("display_name") or "",
        "year": item.get("publication_year") if isinstance(item.get("publication_year"), int) else None,
        "venue": source.get("display_name") if isinstance(source.get("display_name"), str) else None,
        "publisher": source.get("host_organization_name") if isinstance(source.get("host_organization_name"), str) else None,
        "language": item.get("language") if isinstance(item.get("language"), str) else None,
        "work_type": _canonical_work_type(item.get("type")),
    })
    abstract = _abstract_from_inverted(item.get("abstract_inverted_index"))
    record["content_available"]["abstract"] = abstract
    record["content_available"]["abstract_source"] = "openalex" if abstract else None
    if abstract:
        record["access"]["access_level"] = "abstract"
    record["signals"]["cited_by_count"] = (
        item.get("cited_by_count") if isinstance(item.get("cited_by_count"), int) else None
    )
    open_access = item.get("open_access") if isinstance(item.get("open_access"), dict) else {}
    record["access"]["oa_status"] = open_access.get("oa_status") or (
        "open" if open_access.get("is_oa") is True else "unknown"
    )
    if open_access.get("is_oa") is False:
        record["access"]["library_access_required"] = True
    best_oa = item.get("best_oa_location") if isinstance(item.get("best_oa_location"), dict) else {}
    pdf_urls = [url for url in (best_oa.get("pdf_url"), primary.get("pdf_url"))
                if isinstance(url, str) and url.startswith("http")]
    record["access"]["candidate_pdf_urls"] = list(dict.fromkeys(pdf_urls))
    landing = primary.get("landing_page_url")
    record["access"]["publisher_url"] = landing if isinstance(landing, str) else item.get("id")
    return record if record["bibliographic"]["title"].strip() else None


def _normalize_semantic_scholar(item: object, *, query_id: str, topic_id: str,
                                raw_ref: str, retrieved_at: str) -> dict | None:
    if not isinstance(item, dict) or not isinstance(item.get("paperId"), str):
        return None
    provider_id = item["paperId"]
    record = _base_record(
        "semantic_scholar", provider_id, query_id=query_id, topic_id=topic_id,
        raw_ref=raw_ref, retrieved_at=retrieved_at,
    )
    external = item.get("externalIds") if isinstance(item.get("externalIds"), dict) else {}
    record["identifiers"].update({
        "doi": _doi(external.get("DOI")),
        "semantic_scholar_id": provider_id,
        "arxiv_id": external.get("ArXiv") if isinstance(external.get("ArXiv"), str) else None,
    })
    authors = item.get("authors") if isinstance(item.get("authors"), list) else []
    publication_types = item.get("publicationTypes") \
        if isinstance(item.get("publicationTypes"), list) else []
    record["bibliographic"].update({
        "title": item.get("title") if isinstance(item.get("title"), str) else "",
        "authors": [author["name"] for author in authors
                    if isinstance(author, dict) and isinstance(author.get("name"), str)],
        "year": item.get("year") if isinstance(item.get("year"), int) else None,
        "venue": item.get("venue") if isinstance(item.get("venue"), str) and item.get("venue") else None,
        "work_type": _canonical_work_type(publication_types[0]) if publication_types else None,
    })
    abstract = item.get("abstract") if isinstance(item.get("abstract"), str) else None
    record["content_available"]["abstract"] = abstract
    record["content_available"]["abstract_source"] = "semantic_scholar" if abstract else None
    if abstract:
        record["access"]["access_level"] = "abstract"
    record["signals"]["cited_by_count"] = (
        item.get("citationCount") if isinstance(item.get("citationCount"), int) else None
    )
    open_pdf = item.get("openAccessPdf") if isinstance(item.get("openAccessPdf"), dict) else {}
    pdf_url = open_pdf.get("url")
    if item.get("isOpenAccess") is True:
        record["access"]["oa_status"] = "open"
    elif item.get("isOpenAccess") is False:
        record["access"]["oa_status"] = "closed"
        record["access"]["library_access_required"] = True
    if isinstance(pdf_url, str) and pdf_url.startswith("http"):
        record["access"]["oa_status"] = "open"
        record["access"]["candidate_pdf_urls"] = [pdf_url]
    url = item.get("url")
    record["access"]["publisher_url"] = url if isinstance(url, str) else None
    return record if record["bibliographic"]["title"].strip() else None


def _text(element: ET.Element, path: str) -> str | None:
    child = element.find(path, ARXIV_NS)
    if child is None or child.text is None:
        return None
    return " ".join(child.text.split()) or None


def _normalize_arxiv(entry: ET.Element, *, query_id: str, topic_id: str,
                     raw_ref: str, retrieved_at: str) -> dict | None:
    identity = _text(entry, "atom:id")
    title = _text(entry, "atom:title")
    if not identity or not title:
        return None
    provider_record_id = identity.rsplit("/", 1)[-1]
    provider_id = re.sub(r"v\d+$", "", provider_record_id)
    record = _base_record(
        "arxiv", provider_id, query_id=query_id, topic_id=topic_id,
        raw_ref=raw_ref, retrieved_at=retrieved_at,
    )
    record["provenance"]["provider_record_ids"]["arxiv"] = provider_record_id
    doi = _text(entry, "arxiv:doi")
    published = _text(entry, "atom:published")
    authors = []
    for author in entry.findall("atom:author", ARXIV_NS):
        name = _text(author, "atom:name")
        if name:
            authors.append(name)
    summary = _text(entry, "atom:summary")
    record["identifiers"]["doi"] = _doi(doi)
    record["identifiers"]["arxiv_id"] = provider_id
    record["bibliographic"].update({
        "title": title,
        "authors": authors,
        "year": int(published[:4]) if published and published[:4].isdigit() else None,
        "venue": _text(entry, "arxiv:journal_ref"),
        "work_type": "preprint",
    })
    record["content_available"]["abstract"] = summary
    record["content_available"]["abstract_source"] = "arxiv" if summary else None
    if summary:
        record["access"]["access_level"] = "abstract"
    pdf_urls = []
    publisher_url = identity
    for link in entry.findall("atom:link", ARXIV_NS):
        href = link.attrib.get("href")
        if link.attrib.get("type") == "application/pdf" and href:
            pdf_urls.append(href)
        if link.attrib.get("rel") == "alternate" and href:
            publisher_url = href
    record["access"].update({
        "oa_status": "open",
        "candidate_pdf_urls": list(dict.fromkeys(pdf_urls)),
        "publisher_url": publisher_url,
    })
    return record


def _headers(config: provider_config.ProviderRuntimeConfig, provider: str) -> dict[str, str]:
    email = config.contact_email or "contact-not-configured"
    headers = {
        "Accept": "application/atom+xml" if provider == "arxiv" else "application/json",
        "User-Agent": f"EduMaterialsAgents/0.1 (mailto:{email})",
    }
    if provider == "semantic_scholar" and config.api_key(provider):
        headers["x-api-key"] = config.api_key(provider) or ""
    return headers


def _plain_text_query(route: dict) -> str:
    terms = []
    for field in ("origin_terms", "generated_terms"):
        for value in route.get(field, []):
            if isinstance(value, str) and value.strip() and value.strip() not in terms:
                terms.append(value.strip().replace("-", " "))
    return " ".join(terms)


def _arxiv_query(canonical_query: str) -> str:
    tokens = re.findall(r'"[^"\r\n]+"|\bANDNOT\b|\bAND\b|\bOR\b|[()]|[^\s()]+',
                        canonical_query, flags=re.I)
    rendered = []
    for token in tokens:
        upper = token.upper()
        if upper in {"AND", "OR", "ANDNOT"}:
            rendered.append(upper)
        elif token in {"(", ")"}:
            rendered.append(token)
        else:
            cleaned = token.replace(":", " ").strip()
            if cleaned:
                rendered.append(f"all:{cleaned}")
    return " ".join(rendered)


def _build_url(config: provider_config.ProviderRuntimeConfig, provider: str, route: dict,
               cursor: str | None, page_size: int) -> str:
    query = route["canonical_query"]
    filters = route["filters"]
    if provider == "openalex":
        filter_parts = []
        if filters.get("year_from") is not None:
            filter_parts.append(f"from_publication_date:{filters['year_from']}-01-01")
        if filters.get("year_to") is not None:
            filter_parts.append(f"to_publication_date:{filters['year_to']}-12-31")
        languages = [item for item in filters.get("languages", []) if isinstance(item, str)]
        if languages:
            filter_parts.append("language:" + "|".join(languages))
        openalex_types = {
            "article": "article", "review": "review", "book": "book",
            "chapter": "book-chapter", "preprint": "preprint",
        }
        work_types = [openalex_types[item] for item in filters.get("work_types", [])
                      if item in openalex_types]
        if work_types:
            filter_parts.append("type:" + "|".join(work_types))
        params = {
            "search": query,
            "per-page": page_size,
            "cursor": cursor or "*",
            "select": OPENALEX_SELECT,
            "mailto": config.contact_email or "",
        }
        if filter_parts:
            params["filter"] = ",".join(filter_parts)
        if config.api_key(provider):
            params["api_key"] = config.api_key(provider) or ""
        return ENDPOINTS[provider] + "?" + urllib.parse.urlencode(params)
    if provider == "semantic_scholar":
        offset = int(cursor or "0")
        params = {
            "query": _plain_text_query(route),
            "offset": offset,
            "limit": page_size,
            "fields": S2_FIELDS,
        }
        year_from, year_to = filters.get("year_from"), filters.get("year_to")
        if year_from is not None or year_to is not None:
            params["year"] = f"{year_from or ''}-{year_to or ''}"
        s2_types = {
            "article": "JournalArticle", "review": "Review", "book": "Book",
            "chapter": "BookSection",
        }
        publication_types = [s2_types[item] for item in filters.get("work_types", [])
                             if item in s2_types]
        if publication_types:
            params["publicationTypes"] = ",".join(publication_types)
        return ENDPOINTS[provider] + "?" + urllib.parse.urlencode(params)
    start = int(cursor or "0")
    search_query = _arxiv_query(query)
    year_from, year_to = filters.get("year_from"), filters.get("year_to")
    if year_from is not None or year_to is not None:
        lower = f"{year_from or 1900}01010000"
        upper = f"{year_to or 2999}12312359"
        search_query += f" AND submittedDate:[{lower} TO {upper}]"
    params = {
        "search_query": search_query,
        "start": start,
        "max_results": page_size,
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    return ENDPOINTS[provider] + "?" + urllib.parse.urlencode(params)


def _parse_page(provider: str, body_text: str, *, query_id: str, topic_id: str,
                raw_ref: str, retrieved_at: str, current_cursor: str | None) -> tuple[list[dict], str | None, bool]:
    if provider == "openalex":
        payload = json.loads(body_text)
        if not isinstance(payload, dict):
            raise ValueError("OpenAlex response root must be an object")
        records = [record for item in payload.get("results", [])
                   if (record := _normalize_openalex(
                       item, query_id=query_id, topic_id=topic_id,
                       raw_ref=raw_ref, retrieved_at=retrieved_at
                   )) is not None]
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        next_cursor = meta.get("next_cursor") if isinstance(meta.get("next_cursor"), str) else None
        return records, next_cursor, next_cursor is None
    if provider == "semantic_scholar":
        payload = json.loads(body_text)
        if not isinstance(payload, dict):
            raise ValueError("Semantic Scholar response root must be an object")
        data = payload.get("data") if isinstance(payload.get("data"), list) else []
        records = [record for item in data
                   if (record := _normalize_semantic_scholar(
                       item, query_id=query_id, topic_id=topic_id,
                       raw_ref=raw_ref, retrieved_at=retrieved_at
                   )) is not None]
        next_value = payload.get("next")
        next_cursor = str(next_value) if isinstance(next_value, int) else None
        exhausted = next_cursor is None
        return records, next_cursor, exhausted
    root = ET.fromstring(body_text)
    entries = root.findall("atom:entry", ARXIV_NS)
    records = [record for entry in entries
               if (record := _normalize_arxiv(
                   entry, query_id=query_id, topic_id=topic_id,
                   raw_ref=raw_ref, retrieved_at=retrieved_at
               )) is not None]
    start = int(current_cursor or "0")
    total_text = root.findtext("opensearch:totalResults", default="0", namespaces=ARXIV_NS)
    total = int(total_text) if total_text.isdigit() else start + len(entries)
    next_offset = start + len(entries)
    exhausted = not entries or next_offset >= total
    return records, None if exhausted else str(next_offset), exhausted


def _operation_scope(discovery_input: object) -> dict:
    value = discovery_input if isinstance(discovery_input, dict) else {}
    topic = value.get("topic") if isinstance(value.get("topic"), dict) else {}
    return {
        "input_contract": str(value.get("schema_version", "unknown")),
        "task_id": value.get("task_id") if isinstance(value.get("task_id"), str) else None,
        "topic_id": topic.get("topic_id") if isinstance(topic.get("topic_id"), str) else None,
        "research_plan_ref": value.get("research_plan_ref")
        if isinstance(value.get("research_plan_ref"), str) else None,
        "domain_candidates_ref": value.get("domain_candidates_ref")
        if isinstance(value.get("domain_candidates_ref"), str) else None,
    }


def _failed_result(provider: str, route: dict, *, started_at: str, status: str,
                   issue: dict, operation_scope: dict,
                   config_profile: str = "unavailable") -> dict:
    completed_at = _utc_now()
    return {
        "schema_version": TOOL_RESULT_CONTRACT,
        "operation_id": f"OP_{uuid.uuid4().hex.upper()}",
        "operation_type": "metadata_search",
        "provider": provider,
        "status": status,
        "started_at": started_at,
        "completed_at": completed_at,
        "request": {
            "route_id": str(route.get("route_id", "UNKNOWN")),
            "query_id": str(route.get("query_id", "UNKNOWN")),
            "canonical_query": str(route.get("canonical_query", "")),
            "filters": route.get("filters") if isinstance(route.get("filters"), dict) else {},
            "cursor": None,
            "limit": route.get("limit") if isinstance(route.get("limit"), int) else 0,
            "scope": operation_scope,
        },
        "records": [],
        "file_descriptors": [],
        "pagination": {"next_cursor": None, "exhausted": True, "pages_processed": 0},
        "provenance": {
            "raw_response_refs": [],
            "provider_request_ids": [],
            "cache_hit": False,
            "config_profile": config_profile,
        },
        "issues": [issue],
    }


def _store_result(result: dict, config: provider_config.ProviderRuntimeConfig, *, base=None) -> dict:
    validation = contracts.validate(result, TOOL_RESULT_CONTRACT)
    if not validation["ok"]:
        raise ValueError("invalid literature tool result: " + "; ".join(validation["errors"]))
    for index, record in enumerate(result["records"]):
        checked = contracts.validate(record, SOURCE_RECORD_CONTRACT)
        if not checked["ok"]:
            raise ValueError(
                f"invalid source record {index}: " + "; ".join(checked["errors"])
            )
    relative = f"g02/literature-results/{result['operation_id']}.json"
    ref = artifacts.store(relative, result, base=base)
    returned = dict(result)
    returned["artifact_ref"] = ref
    return returned


def _discovery_basis_errors(domain_input: object,
                            config: provider_config.ProviderRuntimeConfig, *, base=None) -> list[str]:
    version = domain_input.get("schema_version") if isinstance(domain_input, dict) else None
    contract_ref = version if version in {CANONICAL_INPUT_CONTRACT, RECENT_INPUT_CONTRACT} \
        else DOMAIN_INPUT_CONTRACT
    checked = contracts.validate(domain_input, contract_ref)
    if not checked["ok"] or not isinstance(domain_input, dict):
        return checked["errors"] or ["discovery input must be an object"]
    allowed_fields = ({
        "schema_version", "task_id", "research_plan_ref", "research_plan_artifact_version",
        "topic", "provider_capabilities", "output_language",
    } if contract_ref == DOMAIN_INPUT_CONTRACT else ({
        "schema_version", "task_id", "research_plan_ref", "research_plan_artifact_version",
        "domain_candidates_ref", "domain_candidates_artifact_version", "topic",
        "domain_candidates", "verified_seed_ids", "unresolved_plan_seed_ids",
        "required_roles", "target_coverage_units", "search_limits",
        "provider_capabilities", "output_language",
    } if contract_ref == CANONICAL_INPUT_CONTRACT else {
        "schema_version", "task_id", "research_plan_ref", "research_plan_artifact_version",
        "domain_candidates_ref", "domain_candidates_artifact_version", "topic",
        "domain_candidates", "verified_seed_ids", "recency_window", "required_roles",
        "target_coverage_units", "search_limits", "provider_capabilities", "output_language",
    }))
    unknown_fields = sorted(set(domain_input) - allowed_fields)
    if unknown_fields:
        return [f"discovery input contains unsupported fields {unknown_fields}"]
    ref = domain_input.get("research_plan_ref")
    if not isinstance(ref, str) or not ref.startswith(artifacts.SCHEME):
        return ["research_plan_ref must use artifact://"]
    try:
        plan = artifacts.hydrate(ref, base=base)
        plan_shape = contracts.validate(plan, RESEARCH_PLAN_CONTRACT)
        if not plan_shape["ok"]:
            return plan_shape["errors"]
    except (OSError, ValueError, KeyError, IndexError) as exc:
        return [f"cannot hydrate approved ResearchPlan: {exc}"]
    topic = domain_input.get("topic")
    topic_id = topic.get("topic_id") if isinstance(topic, dict) else None
    matches = [item for item in plan.get("topics", [])
               if isinstance(item, dict) and item.get("topic_id") == topic_id]
    errors = []
    if contract_ref != RECENT_INPUT_CONTRACT and (len(matches) != 1 or matches[0] != topic):
        errors.append("scoped topic differs from the approved ResearchPlan topic")
    for field, expected in (
        ("task_id", plan.get("task_id")),
        ("research_plan_artifact_version", plan.get("artifact_version")),
        ("output_language", plan.get("output_language")),
    ):
        if domain_input.get(field) != expected:
            errors.append(f"{field} differs from the approved ResearchPlan")
    current_capabilities = config.public_status()["capabilities"]
    if domain_input.get("provider_capabilities") != current_capabilities:
        errors.append("provider_capabilities differ from the active provider configuration")
    if contract_ref == CANONICAL_INPUT_CONTRACT:
        from g02 import canonical
        basis = canonical.validate_canonical_basis(domain_input, base=base)
        errors.extend(item["message"] for item in basis["issues"])
    elif contract_ref == RECENT_INPUT_CONTRACT:
        from g02 import recent
        basis = recent.validate_recent_basis(domain_input, base=base)
        errors.extend(item["message"] for item in basis["issues"])
    return errors


def search_metadata(query_plan: object, domain_input: object, *, route_id: str,
                    provider: str, cursor: str | None = None,
                    config_path: str | Path | None = None,
                    runtime_home: str | Path | None = None, artifact_base=None,
                    transport: Transport | None = None) -> dict:
    """Execute one authorized route/provider pull and return a persisted tool result."""
    started_at = _utc_now()
    operation_scope = _operation_scope(domain_input)
    placeholder = {
        "route_id": route_id,
        "query_id": "UNKNOWN",
        "canonical_query": "",
        "filters": {},
        "limit": 0,
    }
    if provider not in PROVIDERS:
        raise ValueError(f"unsupported provider {provider!r}")
    try:
        config = provider_config.load_config(
            config_path, runtime_home=runtime_home, create_dirs=True
        )
    except provider_config.ProviderConfigError as exc:
        return _failed_result(
            provider, placeholder, started_at=started_at, status="failed",
            issue=_issue("provider_configuration_error", str(exc)),
            operation_scope=operation_scope,
        )
    try:
        route = query_planning.route_by_id(query_plan, route_id) \
            if isinstance(query_plan, dict) else placeholder
    except KeyError as exc:
        result = _failed_result(
            provider, placeholder, started_at=started_at, status="failed",
            issue=_issue("unknown_query_route", str(exc)), operation_scope=operation_scope,
            config_profile=config.profile,
        )
        return _store_result(result, config, base=artifact_base)
    basis_errors = _discovery_basis_errors(domain_input, config, base=artifact_base)
    if basis_errors:
        result = _failed_result(
            provider, route, started_at=started_at, status="failed",
            issue=_issue("invalid_discovery_input_basis", "; ".join(basis_errors)),
            operation_scope=operation_scope,
            config_profile=config.profile,
        )
        return _store_result(result, config, base=artifact_base)
    preferred_providers = route.get("preferred_providers", [])
    if not isinstance(preferred_providers, list) or provider not in preferred_providers:
        result = _failed_result(
            provider, route, started_at=started_at, status="failed",
            issue=_issue("provider_not_authorized_for_route", provider),
            operation_scope=operation_scope,
            config_profile=config.profile,
        )
        return _store_result(result, config, base=artifact_base)
    if not config.enabled(provider):
        result = _failed_result(
            provider, route, started_at=started_at, status="unavailable",
            issue=_issue("provider_disabled", f"{provider} is disabled"),
            operation_scope=operation_scope,
            config_profile=config.profile,
        )
        return _store_result(result, config, base=artifact_base)
    limits = config.data["limits"]
    assert isinstance(limits, dict)
    validation = query_planning.validate_query_plan(
        query_plan, domain_input,
        max_records_per_query=int(limits["max_records_per_query"]),
    )
    if not validation["ok"]:
        message = "; ".join(
            f"{item['code']}: {item['message']}" for item in validation["issues"]
        )
        result = _failed_result(
            provider, route, started_at=started_at, status="failed",
            issue=_issue("invalid_query_plan", message), operation_scope=operation_scope,
            config_profile=config.profile,
        )
        return _store_result(result, config, base=artifact_base)
    operation_id = f"OP_{uuid.uuid4().hex.upper()}"
    records: list[dict] = []
    raw_refs: list[str] = []
    request_ids: list[str] = []
    issues: list[dict] = []
    request_failed = False
    pages_processed = 0
    next_cursor = cursor
    exhausted = False
    any_cache_hit = False
    max_pages = int(limits["max_pages_per_call"])
    per_page = int(limits["per_page"])
    route_limit = min(int(route["limit"]), int(limits["max_records_per_query"]))
    requested_languages = route.get("filters", {}).get("languages", [])
    if provider in {"semantic_scholar", "arxiv"} and requested_languages:
        issues.append(_issue(
            "provider_filter_unverifiable",
            f"{provider} metadata search cannot guarantee the requested language filter; "
            "record language remains null unless supplied by the provider",
        ))

    for page_number in range(1, max_pages + 1):
        remaining = route_limit - len(records)
        if remaining <= 0:
            break
        page_size = min(per_page, remaining)
        url = _build_url(config, provider, route, next_cursor, page_size)
        try:
            page = _request_page(config, provider, url, _headers(config, provider), transport)
            any_cache_hit = any_cache_hit or page.cache_hit
            retrieved_at = _utc_now()
            raw_payload = {
                "provider": provider,
                "operation_id": operation_id,
                "page": page_number,
                "retrieved_at": retrieved_at,
                "status_code": page.status_code,
                "content_type": page.headers.get("content-type"),
                "provider_request_id": page.request_id,
                "cache_hit": page.cache_hit,
                "body": page.body_text,
            }
            raw_ref = artifacts.store(
                f"{config.raw_artifact_subdir}/{operation_id}.page-{page_number}.json",
                raw_payload,
                base=artifact_base,
            )
            raw_refs.append(raw_ref)
            if page.request_id:
                request_ids.append(page.request_id)
            parsed, next_cursor, exhausted = _parse_page(
                provider, page.body_text,
                query_id=route["query_id"], topic_id=query_plan["topic_id"],
                raw_ref=raw_ref, retrieved_at=retrieved_at, current_cursor=next_cursor,
            )
            discovery_pool = {
                CANONICAL_INPUT_CONTRACT: "canonical_metadata",
                RECENT_INPUT_CONTRACT: "recent_metadata",
            }.get(domain_input.get("schema_version"), "domain_raw")
            for record in parsed:
                record["inclusion"]["pool"] = discovery_pool
            records.extend(parsed[:remaining])
            pages_processed += 1
            if exhausted:
                break
        except (ProviderRequestError, OSError, ValueError, ET.ParseError,
                json.JSONDecodeError) as exc:
            request_failed = True
            if isinstance(exc, ProviderRequestError):
                issues.append(_issue(exc.code, exc.message, retryable=exc.retryable))
            else:
                issues.append(_issue(
                    "provider_response_error", _redact(
                        exc, [config.api_key(provider), config.contact_email]
                    )
                ))
            break

    if request_failed and records:
        status = "partial"
    elif request_failed:
        status = "unavailable" if any(item["retryable"] for item in issues) else "failed"
    elif issues:
        status = "partial"
    else:
        status = "ok"
    result = {
        "schema_version": TOOL_RESULT_CONTRACT,
        "operation_id": operation_id,
        "operation_type": "metadata_search",
        "provider": provider,
        "status": status,
        "started_at": started_at,
        "completed_at": _utc_now(),
        "request": {
            "route_id": route["route_id"],
            "query_id": route["query_id"],
            "canonical_query": route["canonical_query"],
            "filters": route["filters"],
            "cursor": cursor,
            "limit": route_limit,
            "scope": operation_scope,
        },
        "records": records[:route_limit],
        "file_descriptors": [],
        "pagination": {
            "next_cursor": next_cursor,
            "exhausted": exhausted,
            "pages_processed": pages_processed,
        },
        "provenance": {
            "raw_response_refs": raw_refs,
            "provider_request_ids": request_ids,
            "cache_hit": any_cache_hit,
            "config_profile": config.profile,
        },
        "issues": issues,
    }
    return _store_result(result, config, base=artifact_base)
