"""Controlled Tavily/SearXNG discovery and post-gate Tavily extraction for G02-A11."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import socket
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core import artifacts, contracts
from g02 import market_cases, provider_config, query_planning

WEB_TOOL_RESULT_CONTRACT = "web_case_tool_result@1"
EXTRACT_RESULT_CONTRACT = "web_case_extract_result@1"
SOURCE_RECORD_CONTRACT = "source_record@1"
SELECTION_CONTRACT = "human_source_selection@1"
CANDIDATE_CONTRACT = "candidate_sources@1"
CANDIDATE_INDEX_CONTRACT = "candidate_source_index@1"
TAVILY_SEARCH_ENDPOINT = "https://api.tavily.com/search"
TAVILY_EXTRACT_ENDPOINT = "https://api.tavily.com/extract"
RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}
Transport = Callable[..., dict]

_RATE_LOCKS = {name: threading.Lock() for name in ("tavily", "searxng")}
_BUDGET_LOCK = threading.Lock()
_LAST_REQUEST = {name: 0.0 for name in ("tavily", "searxng")}
_INJECTION_PATTERNS = {
    "ignore_previous_instructions": re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions", re.I),
    "system_message_impersonation": re.compile(r"(?:^|\n)\s*(?:system|assistant)\s*:", re.I),
    "tool_execution_request": re.compile(r"(?:call|invoke|run)\s+(?:the\s+)?(?:tool|command|shell)", re.I),
    "credential_request": re.compile(r"(?:api\s*key|password|credential|secret)\s*(?:is|=|:)", re.I),
}


class WebProviderError(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool = False,
                 http_status: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.http_status = http_status


@dataclass(frozen=True)
class PageResponse:
    status_code: int
    headers: dict[str, str]
    body_text: str
    cache_hit: bool
    request_id: str | None
    final_url: str


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _issue(code: str, message: str, *, retryable: bool = False) -> dict:
    return {"code": code, "retryable": retryable, "message": message}


def _redact(value: object, secrets: list[str | None]) -> str:
    rendered = str(value)
    for secret in secrets:
        if secret:
            rendered = rendered.replace(secret, "<redacted>")
            rendered = rendered.replace(urllib.parse.quote_plus(secret), "<redacted>")
    return rendered


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


def _origin(value: str) -> tuple[str, str, int | None]:
    parsed = urllib.parse.urlparse(value)
    return parsed.scheme.casefold(), (parsed.hostname or "").casefold(), parsed.port


def _validate_provider_url(config: provider_config.ProviderRuntimeConfig,
                           provider: str, url: str, *, final: bool = False) -> None:
    parsed = urllib.parse.urlparse(url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise WebProviderError(
            "unsafe_web_endpoint", "web endpoint contains an invalid port"
        ) from exc
    if parsed.username or parsed.password or parsed.fragment:
        raise WebProviderError(
            "unsafe_web_endpoint", "web endpoint contains credentials or a fragment"
        )
    if provider == "tavily":
        allowed_paths = {"/search", "/extract"}
        if parsed.scheme != "https" or parsed.hostname != "api.tavily.com" \
                or port not in (None, 443) or parsed.path not in allowed_paths:
            raise WebProviderError(
                "unsafe_web_endpoint", "Tavily endpoint is outside the fixed HTTPS allowlist"
            )
        return
    if provider != "searxng":
        raise WebProviderError("unsupported_web_provider", provider)
    endpoint = config.searxng_endpoint()
    if endpoint is None:
        raise WebProviderError("searxng_endpoint_missing", "SearXNG endpoint is not configured")
    expected = urllib.parse.urlparse(endpoint)
    if _origin(url) != _origin(endpoint) or parsed.path != expected.path:
        raise WebProviderError(
            "unsafe_searxng_endpoint",
            "SearXNG request or redirect differs from the administrator-pinned endpoint",
        )
    if not final and parsed.scheme not in {"http", "https"}:
        raise WebProviderError("unsafe_searxng_endpoint", "unsupported SearXNG URL scheme")


def _validate_public_resolution(host: str) -> None:
    if host.casefold() == "localhost":
        return
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, None)}
    except socket.gaierror as exc:
        raise WebProviderError(
            "searxng_dns_error", f"cannot resolve configured SearXNG host: {exc}", True
        ) from exc
    for value in addresses:
        address = ipaddress.ip_address(value)
        if address.is_private or address.is_link_local or address.is_loopback \
                or address.is_multicast or address.is_reserved or address.is_unspecified:
            raise WebProviderError(
                "unsafe_searxng_resolution",
                "configured SearXNG hostname resolved to a private or reserved address",
            )


class _PinnedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, initial_url: str):
        super().__init__()
        self.initial_url = initial_url

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if _origin(newurl) != _origin(self.initial_url):
            raise WebProviderError(
                "cross_origin_redirect_blocked", "web provider redirect changed origin"
            )
        if urllib.parse.urlparse(newurl).path != urllib.parse.urlparse(self.initial_url).path:
            raise WebProviderError(
                "provider_redirect_target_mismatch",
                "web provider redirect changed the authorized operation endpoint",
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _read_limited(response, max_bytes: int) -> bytes:
    payload = response.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise WebProviderError(
            "web_response_too_large",
            f"web provider response exceeds configured {max_bytes} byte limit",
        )
    return payload


def _default_transport(url: str, headers: dict[str, str], timeout: float, max_bytes: int,
                       *, method: str, body: bytes | None) -> dict:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    opener = urllib.request.build_opener(_PinnedRedirectHandler(url))
    try:
        with opener.open(request, timeout=timeout) as response:
            return {
                "status_code": int(response.status),
                "headers": {key.lower(): value for key, value in response.headers.items()},
                "body": _read_limited(response, max_bytes),
                "final_url": response.geturl(),
            }
    except urllib.error.HTTPError as exc:
        return {
            "status_code": int(exc.code),
            "headers": {key.lower(): value for key, value in exc.headers.items()},
            "body": _read_limited(exc, max_bytes),
            "final_url": exc.geturl(),
        }


def _web_section(config: provider_config.ProviderRuntimeConfig, field: str) -> dict:
    web = config.data.get("web")
    value = web.get(field) if isinstance(web, dict) else None
    if not isinstance(value, dict):
        raise WebProviderError("web_configuration_missing", f"web.{field} is unavailable")
    return value


def _cache_key(provider: str, method: str, url: str, public_body: object) -> str:
    canonical = json.dumps(public_body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(
        f"{provider}\0{method}\0{url}\0{canonical}".encode("utf-8")
    ).hexdigest()


def _cache_path(config: provider_config.ProviderRuntimeConfig, provider: str,
                method: str, url: str, public_body: object) -> Path | None:
    if config.web_cache_dir is None:
        return None
    return config.web_cache_dir / provider / f"{_cache_key(provider, method, url, public_body)}.json"


def _cached_response(config: provider_config.ProviderRuntimeConfig, provider: str,
                     method: str, url: str, public_body: object) -> PageResponse | None:
    cache = _web_section(config, "cache")
    if cache.get("enabled") is not True:
        return None
    path = _cache_path(config, provider, method, url, public_body)
    if path is None or not path.is_file():
        return None
    ttl = int(cache["ttl_seconds"])
    request_cfg = _web_section(config, "request")
    max_bytes = int(request_cfg["max_response_bytes"])
    if ttl == 0 or time.time() - path.stat().st_mtime > ttl \
            or path.stat().st_size > max_bytes * 2 + 65536:
        return None
    try:
        item = json.loads(path.read_text(encoding="utf-8"))
        response = PageResponse(
            status_code=int(item["status_code"]),
            headers=dict(item.get("headers", {})),
            body_text=str(item["body_text"]),
            cache_hit=True,
            request_id=item.get("request_id"),
            final_url=str(item["final_url"]),
        )
        if response.status_code != 200 \
                or len(response.body_text.encode("utf-8")) > max_bytes:
            return None
        json.loads(response.body_text)
        return response
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def _write_cache(config: provider_config.ProviderRuntimeConfig, provider: str,
                 method: str, url: str, public_body: object,
                 response: PageResponse) -> None:
    cache = _web_section(config, "cache")
    path = _cache_path(config, provider, method, url, public_body)
    if cache.get("enabled") is not True or int(cache["ttl_seconds"]) == 0 \
            or response.status_code != 200 or path is None:
        return
    _atomic_json(path, {
        "status_code": response.status_code,
        "headers": {key: value for key, value in response.headers.items()
                    if key in {"content-type", "etag", "last-modified"}},
        "body_text": response.body_text,
        "request_id": response.request_id,
        "final_url": response.final_url,
        "cached_at": _utc_now(),
    })


def _budget_path(config: provider_config.ProviderRuntimeConfig, task_id: str) -> Path:
    if config.web_cache_dir is None:
        raise WebProviderError("web_cache_unavailable", "web budget store is unavailable")
    digest = hashlib.sha256(task_id.encode("utf-8")).hexdigest()
    return config.web_cache_dir / "budgets" / f"{digest}.json"


def _budget_state(config: provider_config.ProviderRuntimeConfig, task_id: str) -> dict:
    path = _budget_path(config, task_id)
    default = {
        "task_hash": hashlib.sha256(task_id.encode("utf-8")).hexdigest(),
        "search_total": 0, "tavily_search": 0, "searxng_search": 0,
        "tavily_extract": 0,
    }
    if not path.is_file():
        return default
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if loaded.get("task_hash") != default["task_hash"]:
            return default
        for field in default:
            if field != "task_hash" and not isinstance(loaded.get(field), int):
                return default
        return loaded
    except (OSError, ValueError, json.JSONDecodeError):
        return default


def _consume_budget(config: provider_config.ProviderRuntimeConfig, task_id: str,
                    provider: str, operation: str) -> dict:
    with _BUDGET_LOCK:
        limits = _web_section(config, "limits")
        state = _budget_state(config, task_id)
        if operation == "search":
            provider_field = f"{provider}_search"
            if state["search_total"] >= int(limits["max_queries_per_task"]) \
                    or state[provider_field] >= int(limits[f"max_{provider}_queries_per_task"]):
                raise WebProviderError(
                    "web_query_budget_exhausted",
                    f"configured {provider} or shared per-task query budget is exhausted",
                )
            state["search_total"] += 1
            state[provider_field] += 1
        elif operation == "extract":
            if state["tavily_extract"] >= int(limits["max_extractions_per_task"]):
                raise WebProviderError(
                    "web_extract_budget_exhausted",
                    "configured per-task extraction budget is exhausted",
                )
            state["tavily_extract"] += 1
        else:
            raise ValueError(f"unsupported budget operation {operation!r}")
        _atomic_json(_budget_path(config, task_id), state)
        return state


def _public_budget(config: provider_config.ProviderRuntimeConfig, task_id: str) -> dict:
    state = _budget_state(config, task_id)
    return {key: value for key, value in state.items() if key != "task_hash"}


def _wait_rate_limit(config: provider_config.ProviderRuntimeConfig, provider: str) -> None:
    rates = _web_section(config, "rate_limits")
    interval = float(rates[f"{provider}_min_interval_seconds"])
    with _RATE_LOCKS[provider]:
        remaining = interval - (time.monotonic() - _LAST_REQUEST[provider])
        if remaining > 0:
            time.sleep(remaining)
        _LAST_REQUEST[provider] = time.monotonic()


def _decode_body(body: object, headers: dict[str, str]) -> str:
    if isinstance(body, str):
        return body
    if not isinstance(body, (bytes, bytearray)):
        raise WebProviderError(
            "invalid_web_transport_body", "web transport returned a non-byte body"
        )
    content_type = headers.get("content-type", "")
    match = re.search(r"charset=([^;\s]+)", content_type, flags=re.I)
    charset = match.group(1).strip('"') if match else "utf-8"
    try:
        return bytes(body).decode(charset)
    except (LookupError, UnicodeDecodeError) as exc:
        raise WebProviderError(
            "web_decode_error", f"cannot decode web provider response: {exc}"
        ) from exc


def _request_json(config: provider_config.ProviderRuntimeConfig, provider: str, *,
                  task_id: str, operation: str, url: str, method: str,
                  public_body: object, actual_body: dict | None, headers: dict[str, str],
                  transport: Transport | None) -> tuple[dict, PageResponse, dict]:
    _validate_provider_url(config, provider, url)
    cached = _cached_response(config, provider, method, url, public_body)
    if cached is not None:
        _validate_provider_url(config, provider, cached.final_url, final=True)
        if _origin(cached.final_url) != _origin(url) \
                or urllib.parse.urlparse(cached.final_url).path \
                != urllib.parse.urlparse(url).path:
            raise WebProviderError(
                "provider_redirect_target_mismatch",
                "cached provider response changed the authorized operation endpoint",
            )
        return json.loads(cached.body_text), cached, _public_budget(config, task_id)
    budget = _consume_budget(config, task_id, provider, operation)
    request_cfg = _web_section(config, "request")
    timeout = float(request_cfg["timeout_seconds"])
    max_retries = int(request_cfg["max_retries"])
    backoff = float(request_cfg["backoff_seconds"])
    max_bytes = int(request_cfg["max_response_bytes"])
    body = json.dumps(actual_body, ensure_ascii=False).encode("utf-8") \
        if actual_body is not None else None
    secrets = [config.web_api_key("tavily")]
    runner = transport or _default_transport
    if provider == "searxng" and transport is None:
        host = urllib.parse.urlparse(url).hostname or ""
        providers_cfg = _web_section(config, "providers")
        searx = providers_cfg.get("searxng") \
            if isinstance(providers_cfg.get("searxng"), dict) else {}
        allow_loopback = searx.get("allow_http_loopback_dev") is True
        loopback = host.casefold() == "localhost"
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            pass
        if not (allow_loopback and loopback):
            _validate_public_resolution(host)
    last_error: WebProviderError | None = None
    for attempt in range(max_retries + 1):
        _wait_rate_limit(config, provider)
        try:
            raw = runner(
                url, headers, timeout, max_bytes, method=method, body=body
            )
            if not isinstance(raw, dict):
                raise WebProviderError(
                    "invalid_web_transport_result", "web transport returned a non-object"
                )
            response_headers = {
                str(key).lower(): str(value)
                for key, value in dict(raw.get("headers", {})).items()
            }
            final_url = str(raw.get("final_url", url))
            _validate_provider_url(config, provider, final_url, final=True)
            requested = urllib.parse.urlparse(url)
            if _origin(final_url) != _origin(url) \
                    or urllib.parse.urlparse(final_url).path != requested.path:
                raise WebProviderError(
                    "provider_redirect_target_mismatch",
                    "web provider redirect changed the authorized operation endpoint",
                )
            status = int(raw["status_code"])
            body_text = _redact(
                _decode_body(raw.get("body", b""), response_headers), secrets
            )
            if len(body_text.encode("utf-8")) > max_bytes:
                raise WebProviderError(
                    "web_response_too_large",
                    f"web provider response exceeds configured {max_bytes} byte limit",
                )
            request_id = next((response_headers.get(key) for key in (
                "x-request-id", "x-amzn-requestid", "cf-ray"
            ) if response_headers.get(key)), None)
            response = PageResponse(
                status, response_headers, body_text, False, request_id, final_url
            )
            if status == 200:
                content_type = response_headers.get("content-type", "").split(";", 1)[0].strip()
                if content_type != "application/json":
                    raise WebProviderError(
                        "web_content_type_error",
                        f"{provider} must return application/json, got {content_type!r}",
                    )
                try:
                    payload = json.loads(body_text)
                except json.JSONDecodeError as exc:
                    raise WebProviderError(
                        "invalid_web_json", f"{provider} returned invalid JSON: {exc}"
                    ) from exc
                if not isinstance(payload, dict):
                    raise WebProviderError(
                        "invalid_web_payload", "web provider JSON root must be an object"
                    )
                try:
                    _write_cache(config, provider, method, url, public_body, response)
                except (OSError, ValueError, TypeError):
                    pass
                return payload, response, budget
            retryable = status in RETRYABLE_STATUS
            last_error = WebProviderError(
                "web_provider_http_error",
                _redact(f"{provider} returned HTTP {status}", secrets),
                retryable, status,
            )
            if not retryable or attempt >= max_retries:
                break
            retry_after = response_headers.get("retry-after")
            delay = backoff * (2 ** attempt)
            if retry_after and retry_after.isdigit():
                delay = min(float(retry_after), 60.0)
            time.sleep(delay)
        except WebProviderError as exc:
            last_error = WebProviderError(
                exc.code, _redact(exc.message, secrets), exc.retryable, exc.http_status
            )
            if not exc.retryable or attempt >= max_retries:
                break
            time.sleep(backoff * (2 ** attempt))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError) as exc:
            last_error = WebProviderError(
                "web_provider_transport_error", _redact(exc, secrets), True
            )
            if attempt >= max_retries:
                break
            time.sleep(backoff * (2 ** attempt))
    assert last_error is not None
    raise last_error


def _domain_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith(f".{domain}")


def _source_tier(market_input: dict, url: str) -> str | None:
    host = (urllib.parse.urlparse(url).hostname or "").casefold().rstrip(".")
    policy = market_input.get("source_tier_policy", {})
    for field, tier in (
        ("tier_1_domains", "tier_1_authoritative"),
        ("tier_2_domains", "tier_2_reputable_media"),
        ("tier_3_domains", "tier_3_signal_only"),
    ):
        for domain in policy.get(field, []):
            if isinstance(domain, str) and _domain_matches(host, domain):
                return tier
    return None


def _safe_source_id(provider: str, provider_id: str) -> str:
    digest = hashlib.sha256(f"{provider}:{provider_id}".encode("utf-8")).hexdigest()[:16]
    return f"SRC_{provider.upper()}_{digest.upper()}"


def _date_value(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    match = re.match(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?", value.strip())
    return match.group(0) if match else None


def _record(provider: str, item: dict, *, route: dict, topic_id: str,
            retrieved_at: str, raw_ref: str) -> dict | None:
    title = item.get("title")
    url = item.get("url")
    if not isinstance(title, str) or not title.strip() \
            or not isinstance(url, str) or not url.strip():
        return None
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname \
            or parsed.username or parsed.password:
        return None
    tier = _source_tier(route["_market_input"], url)
    if tier is None:
        return None
    tier_rank = {
        "tier_1_authoritative": 1,
        "tier_2_reputable_media": 2,
        "tier_3_signal_only": 3,
    }
    floor = route.get("web", {}).get("source_tier_floor")
    if floor not in tier_rank or tier_rank[tier] > tier_rank[floor]:
        return None
    include_domains = route.get("web", {}).get("include_domains", [])
    exclude_domains = route.get("web", {}).get("exclude_domains", [])
    host = parsed.hostname.casefold().rstrip(".")
    if not any(_domain_matches(host, domain) for domain in include_domains) \
            or any(_domain_matches(host, domain) for domain in exclude_domains):
        return None
    snippet = item.get("content")
    if not isinstance(snippet, str):
        snippet = item.get("snippet") if isinstance(item.get("snippet"), str) else None
    if isinstance(snippet, str):
        snippet = snippet.strip()[:4000] or None
    provider_date = _date_value(
        item.get("published_date") or item.get("publishedDate") or item.get("publishedDateTime")
    )
    year = int(provider_date[:4]) if provider_date else None
    provider_id = str(item.get("id") or url.strip())
    query_id = route["query_id"]
    language_values = route.get("filters", {}).get("languages", [])
    language = language_values[0] if len(language_values) == 1 else None
    return {
        "schema_version": SOURCE_RECORD_CONTRACT,
        "source_id": _safe_source_id(provider, provider_id),
        "record_type": "market_case",
        "identifiers": {
            "doi": None, "openalex_id": None, "semantic_scholar_id": None,
            "arxiv_id": None, "isbn": None,
        },
        "bibliographic": {
            "title": title.strip(), "authors": [], "year": year,
            "venue": host, "publisher": None, "language": language, "work_type": None,
        },
        "content_available": {
            "abstract": snippet, "abstract_source": "search_snippet" if snippet else None,
            "table_of_contents_available": False,
        },
        "classification": {
            "related_topics": [topic_id], "related_claims": [], "source_roles": [],
            "category": "market_case",
        },
        "signals": {
            "cited_by_count": None, "citation_percentile": None,
            "recent_citation_velocity": None, "internal_graph_centrality": None,
            "recommendation_signal": None, "canonical_score": None, "rising_score": None,
        },
        "access": {
            "oa_status": "web_public", "access_level": "web_page",
            "candidate_pdf_urls": [], "publisher_url": url.strip(),
            "library_access_required": False,
        },
        "web_case": {
            "institution": None, "event_label": title.strip(),
            "provider_date": provider_date, "event_date": None,
            "source_tier": tier, "evidence_type": None,
            "corroborating_source_urls": [], "weakly_sourced": tier == "tier_3_signal_only",
            "materiality_note": None, "regime_context_note": None, "raw_page_ref": None,
        },
        "provenance": {
            "source_apis": [provider], "provider_record_ids": {provider: provider_id},
            "retrieved_at": retrieved_at, "query_ids": [query_id],
            "raw_response_refs": [raw_ref], "merged_from_records": [],
        },
        "inclusion": {
            "reason_included": [f"matched approved web route {route['route_id']}"],
            "coverage_units": list(route.get("coverage_unit_ids", [])),
            "pool": "market_web",
        },
    }


def _store_raw(config: provider_config.ProviderRuntimeConfig, operation_id: str,
               provider: str, run_index: int, payload: dict, *, base=None) -> str:
    subdir = config.web_raw_artifact_subdir or "g02/web-provider-raw"
    return artifacts.store(
        f"{subdir}/{operation_id}.{provider}.{run_index}.json", payload, base=base
    )


def _provider_ready(config: provider_config.ProviderRuntimeConfig, provider: str) -> bool:
    return any(item.get("provider") == provider and item.get("ready") is True
               for item in config.public_web_status()["capabilities"])


def _search_provider(config: provider_config.ProviderRuntimeConfig, provider: str, *,
                     market_input: dict, route: dict, limit: int, cursor: str | None,
                     operation_id: str, run_index: int, transport: Transport | None,
                     base=None) -> dict:
    if not config.web_provider_enabled(provider):
        return {
            "provider": provider, "status": "unavailable", "records": [],
            "raw_refs": [], "request_ids": [], "cache_hit": False,
            "next_cursor": None, "pages_processed": 0,
            "issues": [_issue("web_provider_disabled", f"{provider} is disabled")],
        }
    if not _provider_ready(config, provider):
        code = "tavily_key_missing" if provider == "tavily" else "searxng_endpoint_missing"
        return {
            "provider": provider, "status": "unavailable", "records": [],
            "raw_refs": [], "request_ids": [], "cache_hit": False,
            "next_cursor": None, "pages_processed": 0,
            "issues": [_issue(code, f"{provider} is not ready")],
        }
    query = route["canonical_query"]
    if provider == "tavily":
        url = TAVILY_SEARCH_ENDPOINT
        public_body = {
            "query": query, "search_depth": "basic", "max_results": limit,
            "include_domains": route["web"]["include_domains"],
            "exclude_domains": route["web"]["exclude_domains"],
            "include_answer": False, "include_raw_content": False,
        }
        actual_body = {"api_key": config.web_api_key("tavily"), **public_body}
        method = "POST"
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
    else:
        endpoint = config.searxng_endpoint()
        assert endpoint is not None
        providers_cfg = _web_section(config, "providers")
        categories = providers_cfg["searxng"]["categories"]
        domain_terms = " OR ".join(
            f"site:{domain}" for domain in route["web"]["include_domains"]
        )
        exclusion_terms = " ".join(
            f"-site:{domain}" for domain in route["web"]["exclude_domains"]
        )
        scoped_query = f"{query} ({domain_terms}) {exclusion_terms}".strip()
        page = int(cursor) if isinstance(cursor, str) and cursor.isdigit() else 1
        language_values = route.get("filters", {}).get("languages", [])
        params = {
            "q": scoped_query, "format": "json", "categories": ",".join(categories),
            "pageno": page,
        }
        if len(language_values) == 1:
            params["language"] = language_values[0]
        url = f"{endpoint}?{urllib.parse.urlencode(params)}"
        public_body = params
        actual_body = None
        method = "GET"
        headers = {"Accept": "application/json"}
    try:
        payload, response, budget = _request_json(
            config, provider, task_id=market_input["task_id"], operation="search",
            url=url, method=method, public_body=public_body, actual_body=actual_body,
            headers=headers, transport=transport,
        )
    except WebProviderError as exc:
        status = "unavailable" if exc.code.endswith("budget_exhausted") else "failed"
        return {
            "provider": provider, "status": status, "records": [], "raw_refs": [],
            "request_ids": [], "cache_hit": False, "next_cursor": None,
            "pages_processed": 0,
            "issues": [_issue(exc.code, exc.message, retryable=exc.retryable)],
        }
    raw_ref = _store_raw(config, operation_id, provider, run_index, payload, base=base)
    raw_items = payload.get("results") if isinstance(payload.get("results"), list) else []
    retrieved_at = _utc_now()
    normalized_route = dict(route)
    normalized_route["_market_input"] = market_input
    records = []
    dropped = 0
    for item in raw_items[:limit]:
        record = _record(
            provider, item, route=normalized_route, topic_id=market_input["topic"]["topic_id"],
            retrieved_at=retrieved_at, raw_ref=raw_ref,
        ) if isinstance(item, dict) else None
        if record is None:
            dropped += 1
        else:
            records.append(record)
    request_id = payload.get("request_id") if isinstance(payload.get("request_id"), str) \
        else response.request_id
    next_cursor = None
    if provider == "searxng" and len(raw_items) >= limit:
        current = int(cursor) if isinstance(cursor, str) and cursor.isdigit() else 1
        next_cursor = str(current + 1)
    issues = []
    if dropped:
        issues.append(_issue(
            "web_results_dropped",
            f"{dropped} results lacked an allowlisted URL, title or valid provider observation",
        ))
    return {
        "provider": provider, "status": "partial" if issues else "ok", "records": records,
        "raw_refs": [raw_ref], "request_ids": [request_id] if request_id else [],
        "cache_hit": response.cache_hit, "next_cursor": next_cursor,
        "pages_processed": 1, "issues": issues, "budget": budget,
    }


def _operation_scope(market_input: object) -> dict:
    value = market_input if isinstance(market_input, dict) else {}
    topic = value.get("topic") if isinstance(value.get("topic"), dict) else {}
    return {
        "input_contract": str(value.get("schema_version", "unknown")),
        "task_id": value.get("task_id") if isinstance(value.get("task_id"), str) else "unknown",
        "topic_id": topic.get("topic_id") if isinstance(topic.get("topic_id"), str) else "unknown",
        "research_plan_ref": value.get("research_plan_ref")
        if isinstance(value.get("research_plan_ref"), str) else "unknown",
        "domain_candidates_ref": value.get("domain_candidates_ref")
        if isinstance(value.get("domain_candidates_ref"), str) else "unknown",
    }


def _result(provider: str, route: dict, scope: dict, *, started_at: str,
            status: str, operation_id: str, records: list[dict], runs: list[dict],
            issues: list[dict], config_profile: str, cursor: str | None,
            budget: dict) -> dict:
    raw_refs = [ref for run in runs for ref in run.get("raw_refs", [])]
    request_ids = [item for run in runs for item in run.get("request_ids", [])]
    next_cursor = next((run.get("next_cursor") for run in reversed(runs)
                        if run.get("next_cursor") is not None), None)
    pages = sum(int(run.get("pages_processed", 0)) for run in runs)
    return {
        "schema_version": WEB_TOOL_RESULT_CONTRACT,
        "operation_id": operation_id,
        "operation_type": "web_case_search",
        "provider": provider,
        "status": status,
        "started_at": started_at,
        "completed_at": _utc_now(),
        "request": {
            "route_id": str(route.get("route_id", "UNKNOWN")),
            "query_id": str(route.get("query_id", "UNKNOWN")),
            "canonical_query": str(route.get("canonical_query", "")),
            "filters": deepcopy_dict(route.get("filters")),
            "web": deepcopy_dict(route.get("web")),
            "cursor": cursor,
            "limit": route.get("limit") if isinstance(route.get("limit"), int) else 0,
            "scope": scope,
        },
        "records": records,
        "pagination": {
            "next_cursor": next_cursor, "exhausted": next_cursor is None,
            "pages_processed": pages,
        },
        "provenance": {
            "raw_response_refs": raw_refs, "provider_request_ids": request_ids,
            "cache_hit": any(run.get("cache_hit") is True for run in runs),
            "config_profile": config_profile,
            "provider_runs": [{
                "provider": run.get("provider"), "status": run.get("status"),
                "result_count": len(run.get("records", [])),
                "cache_hit": run.get("cache_hit", False),
                "issues": run.get("issues", []),
            } for run in runs],
            "budget": budget,
        },
        "issues": issues,
    }


def deepcopy_dict(value: object) -> dict:
    return json.loads(json.dumps(value)) if isinstance(value, dict) else {}


def _store_result(result: dict, *, base=None) -> dict:
    checked = contracts.validate(result, WEB_TOOL_RESULT_CONTRACT)
    if not checked["ok"]:
        raise ValueError("invalid web case tool result: " + "; ".join(checked["errors"]))
    for index, record in enumerate(result["records"]):
        shape = contracts.validate(record, SOURCE_RECORD_CONTRACT)
        if not shape["ok"]:
            raise ValueError(
                f"invalid market source record {index}: " + "; ".join(shape["errors"])
            )
    ref = artifacts.store(
        f"g02/web-case-results/{result['operation_id']}.json", result, base=base
    )
    returned = dict(result)
    returned["artifact_ref"] = ref
    return returned


def search_web_cases(query_plan: object, market_input: object, *, route_id: str,
                     provider: str, cursor: str | None = None,
                     config_path: str | Path | None = None,
                     runtime_home: str | Path | None = None, artifact_base=None,
                     transport: Transport | None = None) -> dict:
    """Execute one A11 route through the configured Tavily/SearXNG mode."""
    started_at = _utc_now()
    operation_id = f"OP_{uuid.uuid4().hex.upper()}"
    scope = _operation_scope(market_input)
    placeholder = {
        "route_id": route_id, "query_id": "UNKNOWN", "canonical_query": "",
        "filters": {}, "web": {}, "limit": 0,
    }
    if provider not in {"tavily", "searxng", "auto_budgeted"}:
        raise ValueError(f"unsupported web provider mode {provider!r}")
    try:
        config = provider_config.load_config(
            config_path, runtime_home=runtime_home, create_dirs=True
        )
    except provider_config.ProviderConfigError as exc:
        result = _result(
            provider, placeholder, scope, started_at=started_at, status="failed",
            operation_id=operation_id, records=[], runs=[],
            issues=[_issue("web_provider_configuration_error", str(exc))],
            config_profile="unavailable", cursor=cursor, budget={},
        )
        return _store_result(result, base=artifact_base)
    try:
        route = query_planning.route_by_id(query_plan, route_id) \
            if isinstance(query_plan, dict) else placeholder
    except KeyError as exc:
        result = _result(
            provider, placeholder, scope, started_at=started_at, status="failed",
            operation_id=operation_id, records=[], runs=[],
            issues=[_issue("unknown_market_query_route", str(exc))],
            config_profile=config.profile, cursor=cursor,
            budget=_public_budget(config, scope["task_id"]),
        )
        return _store_result(result, base=artifact_base)
    basis = market_cases.validate_market_case_basis(
        market_input, base=artifact_base, config=config
    )
    if not basis["ok"]:
        result = _result(
            provider, route, scope, started_at=started_at, status="failed",
            operation_id=operation_id, records=[], runs=[],
            issues=[_issue(
                "invalid_market_case_input_basis",
                "; ".join(item["message"] for item in basis["issues"]),
            )],
            config_profile=config.profile, cursor=cursor,
            budget=_public_budget(config, scope["task_id"]),
        )
        return _store_result(result, base=artifact_base)
    if not isinstance(market_input, dict):
        raise ValueError("market_input must be an object")
    limits = _web_section(config, "limits")
    validation = query_planning.validate_query_plan(
        query_plan, market_input,
        max_records_per_query=int(limits["max_results_per_query"]),
    )
    if not validation["ok"]:
        result = _result(
            provider, route, scope, started_at=started_at, status="failed",
            operation_id=operation_id, records=[], runs=[],
            issues=[_issue(
                "invalid_market_query_plan",
                "; ".join(f"{item['code']}: {item['message']}"
                          for item in validation["issues"]),
            )], config_profile=config.profile, cursor=cursor,
            budget=_public_budget(config, scope["task_id"]),
        )
        return _store_result(result, base=artifact_base)
    if provider != market_input.get("provider_mode") \
            or route.get("preferred_providers") != [provider]:
        result = _result(
            provider, route, scope, started_at=started_at, status="failed",
            operation_id=operation_id, records=[], runs=[],
            issues=[_issue(
                "market_provider_not_authorized",
                "provider must equal the prepared mode and the route authorization",
            )], config_profile=config.profile, cursor=cursor,
            budget=_public_budget(config, scope["task_id"]),
        )
        return _store_result(result, base=artifact_base)

    route_limit = min(
        int(route["limit"]), int(limits["max_results_per_query"]),
        int(market_input["search_limits"]["max_results_per_route"]),
    )
    runs = []
    if provider in {"tavily", "searxng"}:
        runs.append(_search_provider(
            config, provider, market_input=market_input, route=route, limit=route_limit,
            cursor=cursor, operation_id=operation_id, run_index=0,
            transport=transport, base=artifact_base,
        ))
    else:
        searx_ready = _provider_ready(config, "searxng")
        tavily_ready = _provider_ready(config, "tavily")
        if searx_ready:
            searx_limit = min(route_limit, int(limits["auto_searxng_results_per_route"]))
            runs.append(_search_provider(
                config, "searxng", market_input=market_input, route=route,
                limit=searx_limit, cursor=cursor, operation_id=operation_id, run_index=0,
                transport=transport, base=artifact_base,
            ))
        elif config.web_provider_enabled("searxng"):
            runs.append(_search_provider(
                config, "searxng", market_input=market_input, route=route,
                limit=min(route_limit, int(limits["auto_searxng_results_per_route"])),
                cursor=cursor, operation_id=operation_id, run_index=0,
                transport=transport, base=artifact_base,
            ))
        found = sum(len(run.get("records", [])) for run in runs)
        high_priority = route.get("purpose") == "qualifying_or_critical" \
            or route.get("web", {}).get("preferred_tier") == "tier_1_authoritative"
        supplement = tavily_ready and (found < route_limit or high_priority)
        if supplement:
            runs.append(_search_provider(
                config, "tavily", market_input=market_input, route=route,
                limit=max(1, route_limit - min(found, route_limit - 1)), cursor=None,
                operation_id=operation_id, run_index=len(runs),
                transport=transport, base=artifact_base,
            ))
        elif not runs and config.web_provider_enabled("tavily"):
            runs.append(_search_provider(
                config, "tavily", market_input=market_input, route=route,
                limit=route_limit, cursor=None, operation_id=operation_id, run_index=0,
                transport=transport, base=artifact_base,
            ))

    records = [record for run in runs for record in run.get("records", [])][:route_limit]
    issues = [issue for run in runs if run.get("status") != "ok"
              for issue in run.get("issues", [])]
    if not runs:
        issues = [_issue(
            "web_provider_unavailable", "no configured provider is ready for this web mode"
        )]
        status = "unavailable"
    elif records:
        status = "partial" if issues else "ok"
    elif all(run.get("status") == "ok" for run in runs):
        status = "ok"
    elif any(run.get("status") == "failed" for run in runs):
        status = "failed"
    else:
        status = "unavailable"
    result = _result(
        provider, route, scope, started_at=started_at, status=status,
        operation_id=operation_id, records=records, runs=runs, issues=issues,
        config_profile=config.profile, cursor=cursor,
        budget=_public_budget(config, market_input["task_id"]),
    )
    return _store_result(result, base=artifact_base)


def _safe_extract_source_url(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("approved market case has no source URL")
    parsed = urllib.parse.urlparse(value.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("approved market-case URL must be credential-free HTTPS")
    host = parsed.hostname.casefold()
    if host == "localhost":
        raise ValueError("approved market-case URL cannot use loopback")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and (
            address.is_private or address.is_loopback or address.is_link_local
            or address.is_reserved or address.is_unspecified):
        raise ValueError("approved market-case URL cannot use a private address")
    return value.strip()


def _extract_failure(operation_id: str, started_at: str, *, task_id: str,
                     source_id: str, selection_ref: str, candidate_sources_ref: str,
                     source_url: str, status: str, issue: dict,
                     config_profile: str = "unavailable") -> dict:
    return {
        "schema_version": EXTRACT_RESULT_CONTRACT,
        "operation_id": operation_id, "operation_type": "web_case_extract",
        "provider": "tavily", "status": status, "started_at": started_at,
        "completed_at": _utc_now(),
        "request": {
            "task_id": task_id, "source_id": source_id, "source_url": source_url,
            "selection_ref": selection_ref, "candidate_sources_ref": candidate_sources_ref,
        },
        "content_artifact": None,
        "provenance": {
            "raw_response_refs": [], "provider_request_ids": [], "cache_hit": False,
            "config_profile": config_profile,
        },
        "safety": {
            "external_content_untrusted": True,
            "prompt_injection_patterns_detected": [],
            "full_text_forwarding_prohibited": True,
        },
        "issues": [issue],
    }


def _store_extract_result(result: dict, *, base=None) -> dict:
    checked = contracts.validate(result, EXTRACT_RESULT_CONTRACT)
    if not checked["ok"]:
        raise ValueError("invalid web extract result: " + "; ".join(checked["errors"]))
    ref = artifacts.store(
        f"g02/web-case-extract-results/{result['operation_id']}.json", result, base=base
    )
    returned = dict(result)
    returned["artifact_ref"] = ref
    return returned


def extract_web_case(selection_ref: str, candidate_sources_ref: str, source_id: str, *,
                     config_path: str | Path | None = None,
                     runtime_home: str | Path | None = None, artifact_base=None,
                     transport: Transport | None = None) -> dict:
    """Extract one exact human-approved market-case URL through Tavily only."""
    started_at = _utc_now()
    operation_id = f"OP_{uuid.uuid4().hex.upper()}"
    placeholder_task = "unknown"
    placeholder_url = "https://invalid.local/blocked"
    try:
        if not isinstance(selection_ref, str) or not selection_ref.startswith(artifacts.SCHEME) \
                or not isinstance(candidate_sources_ref, str) \
                or not candidate_sources_ref.startswith(artifacts.SCHEME):
            raise ValueError("selection_ref and candidate_sources_ref must use artifact://")
        selection = artifacts.hydrate(selection_ref, base=artifact_base)
        candidates = artifacts.hydrate(candidate_sources_ref, base=artifact_base)
        for payload, contract_ref in (
            (selection, SELECTION_CONTRACT), (candidates, CANDIDATE_CONTRACT),
        ):
            checked = contracts.validate(payload, contract_ref)
            if not checked["ok"]:
                raise ValueError("; ".join(checked["errors"]))
        placeholder_task = str(selection.get("task_id", "unknown"))
        if selection.get("status") != "approved" or selection.get("final_confirmation") is not True:
            raise ValueError("source selection is not finally approved")
        if not isinstance(selection.get("candidate_source_index_ref"), str) \
                or not selection["candidate_source_index_ref"].startswith(artifacts.SCHEME):
            raise ValueError("source selection has no candidate index artifact ref")
        candidate_index = artifacts.hydrate(
            selection["candidate_source_index_ref"], base=artifact_base
        )
        checked_index = contracts.validate(candidate_index, CANDIDATE_INDEX_CONTRACT)
        if not checked_index["ok"]:
            raise ValueError("; ".join(checked_index["errors"]))
        indexed = [item for item in candidate_index.get("sources", [])
                   if isinstance(item, dict) and item.get("source_id") == source_id]
        if len(indexed) != 1:
            raise ValueError("approved source does not resolve once in the candidate index")
        action_lists = [selection.get(field, []) for field in (
            "approved_for_download", "keep_citation_only", "request_library_access",
            "keep_in_reserve",
        )]
        action_ids = [item for values in action_lists if isinstance(values, list)
                      for item in values if isinstance(item, str)]
        excluded_ids = [item.get("source_id") for item in selection.get("excluded", [])
                        if isinstance(item, dict) and isinstance(item.get("source_id"), str)]
        if len(action_ids + excluded_ids) != len(set(action_ids + excluded_ids)):
            raise ValueError("source selection assigns a source more than once")
        if source_id not in selection.get("approved_for_download", []):
            raise ValueError("market case is not approved for extraction")
        if candidates.get("stream") != "market_cases" \
                or candidates.get("task_id") != selection.get("task_id"):
            raise ValueError("market candidates and human selection do not share task identity")
        matches = [item for item in candidates.get("candidates", [])
                   if isinstance(item, dict) and item.get("source_id") == source_id]
        if len(matches) != 1 or matches[0].get("record_type") != "market_case":
            raise ValueError("approved source does not resolve to one stored market case")
        source_url = _safe_extract_source_url(matches[0].get("access", {}).get("publisher_url"))
        placeholder_url = source_url
    except (OSError, ValueError, KeyError, IndexError) as exc:
        result = _extract_failure(
            operation_id, started_at, task_id=placeholder_task, source_id=str(source_id),
            selection_ref=str(selection_ref), candidate_sources_ref=str(candidate_sources_ref),
            source_url=placeholder_url, status="failed",
            issue=_issue("web_extract_authorization_failed", str(exc)),
        )
        return _store_extract_result(result, base=artifact_base)
    try:
        config = provider_config.load_config(
            config_path, runtime_home=runtime_home, create_dirs=True
        )
    except provider_config.ProviderConfigError as exc:
        result = _extract_failure(
            operation_id, started_at, task_id=placeholder_task, source_id=source_id,
            selection_ref=selection_ref, candidate_sources_ref=candidate_sources_ref,
            source_url=source_url, status="failed",
            issue=_issue("web_provider_configuration_error", str(exc)),
        )
        return _store_extract_result(result, base=artifact_base)
    if not _provider_ready(config, "tavily"):
        result = _extract_failure(
            operation_id, started_at, task_id=placeholder_task, source_id=source_id,
            selection_ref=selection_ref, candidate_sources_ref=candidate_sources_ref,
            source_url=source_url, status="unavailable",
            issue=_issue("tavily_extract_unavailable", "Tavily extraction is not ready"),
            config_profile=config.profile,
        )
        return _store_extract_result(result, base=artifact_base)
    public_body = {
        "urls": [source_url], "extract_depth": "basic", "format": "markdown",
        "include_images": False,
    }
    actual_body = {"api_key": config.web_api_key("tavily"), **public_body}
    try:
        payload, response, _ = _request_json(
            config, "tavily", task_id=placeholder_task, operation="extract",
            url=TAVILY_EXTRACT_ENDPOINT, method="POST", public_body=public_body,
            actual_body=actual_body,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            transport=transport,
        )
        raw_ref = _store_raw(
            config, operation_id, "tavily-extract", 0, payload, base=artifact_base
        )
        raw_items = payload.get("results") if isinstance(payload.get("results"), list) else []
        matches = [item for item in raw_items if isinstance(item, dict)
                   and item.get("url") == source_url]
        if len(matches) != 1:
            raise WebProviderError(
                "web_extract_result_mismatch",
                "Tavily extraction did not return the exact approved source URL",
            )
        content = matches[0].get("raw_content") or matches[0].get("content")
        if not isinstance(content, str) or not content.strip():
            raise WebProviderError("web_extract_empty", "Tavily extraction returned no text")
        content = content.replace("\x00", "").strip()
        max_chars = int(_web_section(config, "limits")["max_extracted_characters"])
        truncated = len(content) > max_chars
        bounded = content[:max_chars]
        digest = hashlib.sha256(bounded.encode("utf-8")).hexdigest()
        flags = [name for name, pattern in _INJECTION_PATTERNS.items()
                 if pattern.search(bounded)]
        subdir = config.web_extract_artifact_subdir or "g02/web-case-content"
        content_ref = artifacts.store(
            f"{subdir}/{operation_id}.{_safe_source_id('case', source_id)}.json",
            {
                "schema_version": "untrusted_web_content@1",
                "source_id": source_id, "source_url": source_url,
                "content_boundary": "untrusted_external_research",
                "content": bounded, "content_sha256": digest,
                "character_count": len(bounded), "truncated": truncated,
                "prompt_injection_patterns_detected": flags,
            }, base=artifact_base,
        )
        request_id = payload.get("request_id") if isinstance(payload.get("request_id"), str) \
            else response.request_id
        result = {
            "schema_version": EXTRACT_RESULT_CONTRACT,
            "operation_id": operation_id, "operation_type": "web_case_extract",
            "provider": "tavily", "status": "partial" if truncated else "ok",
            "started_at": started_at, "completed_at": _utc_now(),
            "request": {
                "task_id": placeholder_task, "source_id": source_id,
                "source_url": source_url, "selection_ref": selection_ref,
                "candidate_sources_ref": candidate_sources_ref,
            },
            "content_artifact": {
                "ref": content_ref, "content_sha256": digest,
                "character_count": len(bounded), "truncated": truncated,
                "content_boundary": "untrusted_external_research",
            },
            "provenance": {
                "raw_response_refs": [raw_ref],
                "provider_request_ids": [request_id] if request_id else [],
                "cache_hit": response.cache_hit, "config_profile": config.profile,
            },
            "safety": {
                "external_content_untrusted": True,
                "prompt_injection_patterns_detected": flags,
                "full_text_forwarding_prohibited": True,
            },
            "issues": [_issue(
                "web_extract_truncated",
                f"content was truncated at {max_chars} configured characters",
            )] if truncated else [],
        }
    except WebProviderError as exc:
        status = "unavailable" if exc.code.endswith("budget_exhausted") else "failed"
        result = _extract_failure(
            operation_id, started_at, task_id=placeholder_task, source_id=source_id,
            selection_ref=selection_ref, candidate_sources_ref=candidate_sources_ref,
            source_url=source_url, status=status,
            issue=_issue(exc.code, exc.message, retryable=exc.retryable),
            config_profile=config.profile,
        )
    return _store_extract_result(result, base=artifact_base)
