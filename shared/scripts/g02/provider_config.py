"""Non-secret provider configuration and startup validation for G02.

The JSON file controls enabled services, limits, cache and relative runtime directories. Contact
data and API keys are read only from environment variables and are never included in public
status objects or provider artifacts.
"""
from __future__ import annotations

import json
import ipaddress
import os
import re
import urllib.parse
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from core import contracts, graphs, paths

CONFIG_CONTRACT = "literature_provider_config@1"
CONFIG_ENV = "EMAGENTS_RESEARCH_CONFIG"
CONTACT_ENV = "EMAGENTS_RESEARCH_CONTACT_EMAIL"
OPENALEX_KEY_ENV = "OPENALEX_API_KEY"
SEMANTIC_SCHOLAR_KEY_ENV = "SEMANTIC_SCHOLAR_API_KEY"
TAVILY_KEY_ENV = "TAVILY_API_KEY"
CORE_KEY_ENV = "CORE_API_KEY"
PROVIDERS = ("openalex", "semantic_scholar", "arxiv", "crossref")
WEB_PROVIDERS = ("tavily", "searxng")
RETRIEVAL_PROVIDERS = ("record", "unpaywall", "core", "doab", "oapen")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
EXECUTION_PROFILE_ENV = "EMAGENTS_G02_PROFILE"

SOURCE_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_CONFIG = SOURCE_ROOT / "config" / "g02.providers.example.json"


class ProviderConfigError(ValueError):
    """Raised when provider startup configuration is unsafe or incomplete."""


@dataclass(frozen=True)
class ProviderRuntimeConfig:
    data: Mapping[str, object]
    source: str
    runtime_home: Path
    cache_dir: Path
    corpus_dir: Path
    raw_artifact_subdir: str
    web_cache_dir: Path | None
    web_raw_artifact_subdir: str | None
    web_extract_artifact_subdir: str | None
    retrieval_temp_dir: Path | None
    retrieval_accepted_dir: Path | None
    retrieval_market_case_dir: Path | None
    contact_email: str | None
    _api_keys: Mapping[str, str | None]

    @property
    def profile(self) -> str:
        return str(self.data["profile"])

    def enabled(self, provider: str) -> bool:
        _require_provider(provider)
        providers = self.data["providers"]
        assert isinstance(providers, Mapping)
        item = providers[provider]
        assert isinstance(item, Mapping)
        return item.get("enabled") is True

    def api_key(self, provider: str) -> str | None:
        _require_provider(provider)
        return self._api_keys.get(provider)

    def web_enabled(self) -> bool:
        web = self.data.get("web")
        return isinstance(web, Mapping) and web.get("enabled") is True

    def web_mode(self) -> str | None:
        web = self.data.get("web")
        return str(web.get("mode")) if isinstance(web, Mapping) and self.web_enabled() else None

    def web_provider_enabled(self, provider: str) -> bool:
        if provider not in WEB_PROVIDERS:
            raise KeyError(f"unsupported web provider {provider!r}")
        web = self.data.get("web")
        providers = web.get("providers") if isinstance(web, Mapping) else None
        item = providers.get(provider) if isinstance(providers, Mapping) else None
        return self.web_enabled() and isinstance(item, Mapping) and item.get("enabled") is True

    def web_api_key(self, provider: str) -> str | None:
        if provider != "tavily":
            return None
        return self._api_keys.get("tavily")

    def searxng_endpoint(self) -> str | None:
        web = self.data.get("web")
        providers = web.get("providers") if isinstance(web, Mapping) else None
        item = providers.get("searxng") if isinstance(providers, Mapping) else None
        endpoint = item.get("endpoint") if isinstance(item, Mapping) else None
        return endpoint.strip() if isinstance(endpoint, str) and endpoint.strip() else None

    def public_web_status(self) -> dict:
        tavily_enabled = self.web_provider_enabled("tavily") if self.web_enabled() else False
        searxng_enabled = self.web_provider_enabled("searxng") if self.web_enabled() else False
        tavily_ready = tavily_enabled and self.web_api_key("tavily") is not None
        searxng_ready = searxng_enabled and self.searxng_endpoint() is not None
        mode = self.web_mode()
        auto_ready = (tavily_ready or searxng_ready) if mode == "auto_budgeted" else False
        return {
            "enabled": self.web_enabled(),
            "mode": mode,
            "capabilities": [
                {
                    "provider": "tavily", "enabled": tavily_enabled,
                    "ready": tavily_ready,
                    "authentication": "configured_key" if tavily_ready else "required_key_missing",
                },
                {
                    "provider": "searxng", "enabled": searxng_enabled,
                    "ready": searxng_ready,
                    "authentication": "configured_endpoint" if searxng_ready else "endpoint_missing",
                },
                {
                    "provider": "auto_budgeted", "enabled": mode == "auto_budgeted",
                    "ready": auto_ready, "authentication": "composite",
                },
            ],
            "searxng_endpoint_configured": self.searxng_endpoint() is not None,
        }

    def retrieval_enabled(self) -> bool:
        section = self.data.get("retrieval")
        return isinstance(section, Mapping) and section.get("enabled") is True

    def retrieval_provider_enabled(self, provider: str) -> bool:
        if provider not in RETRIEVAL_PROVIDERS:
            raise KeyError(f"unsupported retrieval provider {provider!r}")
        section = self.data.get("retrieval")
        providers = section.get("providers") if isinstance(section, Mapping) else None
        item = providers.get(provider) if isinstance(providers, Mapping) else None
        return self.retrieval_enabled() and isinstance(item, Mapping) \
            and item.get("enabled") is True

    def retrieval_api_key(self, provider: str) -> str | None:
        return self._api_keys.get(provider) if provider == "core" else None

    def public_retrieval_status(self) -> dict:
        capabilities = []
        for provider in RETRIEVAL_PROVIDERS:
            enabled = self.retrieval_provider_enabled(provider) \
                if self.retrieval_enabled() else False
            key_required = provider == "core"
            contact_required = provider == "unpaywall"
            ready = enabled \
                and (not key_required or self.retrieval_api_key(provider) is not None) \
                and (not contact_required or self.contact_email is not None)
            capabilities.append({
                "provider": provider, "enabled": enabled, "ready": ready,
                "authentication": (
                    "configured_key" if key_required and ready else
                    "required_key_missing" if key_required else
                    "configured_email" if contact_required and ready else
                    "required_email_missing" if contact_required else "none"
                ),
            })
        return {"enabled": self.retrieval_enabled(), "capabilities": capabilities}

    def public_status(self) -> dict:
        capabilities = []
        for provider in PROVIDERS:
            enabled = self.enabled(provider)
            key = self.api_key(provider)
            contact_required = provider in {"openalex", "arxiv", "crossref"}
            key_required = provider == "openalex"   # OpenAlex needs BOTH the email and its API token
            ready = enabled \
                and (not contact_required or self.contact_email is not None) \
                and (not key_required or key is not None)
            if provider == "openalex":
                authentication = (
                    "configured" if (key and self.contact_email is not None) else
                    "incomplete_missing_token" if self.contact_email is not None else
                    "incomplete_missing_email"
                )
            elif provider == "semantic_scholar":
                authentication = "configured_key" if key else "optional_key"
            elif provider == "arxiv":
                authentication = "none"
            else:
                authentication = (
                    "disabled" if not enabled else
                    "configured_email" if self.contact_email is not None else
                    "required_email_missing"
                )
            capabilities.append({
                "provider": provider,
                "enabled": enabled,
                "ready": ready,
                "authentication": authentication,
            })
        status = {
            "schema_version": CONFIG_CONTRACT,
            "profile": self.profile,
            "source": self.source,
            "contact_email_configured": self.contact_email is not None,
            "capabilities": capabilities,
            "runtime_paths": {
                "home": str(self.runtime_home),
                "cache": str(self.cache_dir),
                "corpus": str(self.corpus_dir),
                "artifacts": str(self.runtime_home / "artifacts"),
                "logs": str(self.runtime_home / "logs"),
            },
        }
        status["web"] = self.public_web_status()
        status["retrieval"] = self.public_retrieval_status()
        return status


def _require_provider(provider: str) -> None:
    if provider not in PROVIDERS:
        raise KeyError(f"unsupported provider {provider!r}; expected one of {PROVIDERS}")


def _read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ProviderConfigError(f"cannot read provider config {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ProviderConfigError(f"invalid JSON in provider config {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ProviderConfigError("provider config root must be an object")
    return payload


def _resolve_source(config_path: str | Path | None, env: Mapping[str, str]) -> Path:
    if config_path is not None:
        requested = Path(config_path).expanduser()
        if not requested.is_file():
            raise ProviderConfigError(f"explicit provider config does not exist: {requested}")
        return requested
    env_path = env.get(CONFIG_ENV)
    if env_path:
        requested = Path(env_path).expanduser()
        if not requested.is_file():
            raise ProviderConfigError(
                f"{CONFIG_ENV} points to a missing file: {requested}"
            )
        return requested
    project_config = paths.config_dir() / "g02-providers.json"
    return project_config if project_config.is_file() else EXAMPLE_CONFIG


def _positive_number(value: object, field: str, errors: list[str], *, allow_zero=False) -> None:
    valid = isinstance(value, (int, float)) and not isinstance(value, bool)
    if not valid or (value < 0 if allow_zero else value <= 0):
        qualifier = "non-negative" if allow_zero else "positive"
        errors.append(f"{field} must be a {qualifier} number")


def _positive_integer(value: object, field: str, errors: list[str], *, allow_zero=False) -> None:
    valid = isinstance(value, int) and not isinstance(value, bool)
    if not valid or (value < 0 if allow_zero else value <= 0):
        qualifier = "non-negative" if allow_zero else "positive"
        errors.append(f"{field} must be a {qualifier} integer")


def _reject_unknown_keys(value: object, allowed: set[str], field: str,
                         errors: list[str]) -> None:
    if not isinstance(value, dict):
        return
    unknown = sorted(set(value) - allowed)
    if unknown:
        errors.append(f"{field} contains unsupported fields {unknown}")


def _safe_subdir(root: Path, raw: object, field: str, errors: list[str]) -> Path | None:
    if not isinstance(raw, str) or not raw.strip():
        errors.append(f"{field} must be a non-empty relative path")
        return None
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        errors.append(f"{field} must stay under the runtime home")
        return None
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        errors.append(f"{field} escapes the runtime home")
        return None
    return resolved


def _valid_domain(value: object) -> bool:
    if not isinstance(value, str) or not value or len(value) > 253:
        return False
    if "://" in value or "/" in value or "@" in value:
        return False
    normalized = value.rstrip(".")
    if "." not in normalized or normalized.casefold() == "localhost":
        return False
    return all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", part)
               for part in normalized.split("."))


def _validate_searxng_endpoint(value: object, allow_http_loopback: bool,
                               errors: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append("web.providers.searxng.endpoint is required when SearXNG is enabled")
        return
    parsed = urllib.parse.urlparse(value.strip())
    try:
        port = parsed.port
    except ValueError:
        errors.append("web.providers.searxng.endpoint has an invalid port")
        return
    host = parsed.hostname
    if parsed.username or parsed.password or not host or parsed.query or parsed.fragment:
        errors.append("web.providers.searxng.endpoint must be a credential-free exact endpoint")
        return
    loopback = host.casefold() == "localhost"
    try:
        address = ipaddress.ip_address(host)
        loopback = address.is_loopback
        if (address.is_private or address.is_link_local or address.is_reserved) and not loopback:
            errors.append("web.providers.searxng.endpoint cannot use a private or reserved address")
    except ValueError:
        pass
    if parsed.scheme == "http":
        if not (loopback and allow_http_loopback):
            errors.append("SearXNG requires HTTPS except for explicitly enabled loopback DEV")
    elif parsed.scheme != "https":
        errors.append("web.providers.searxng.endpoint must use HTTPS")
    if parsed.scheme == "https" and port not in (None, 443):
        errors.append("HTTPS SearXNG endpoint must use port 443")
    if parsed.scheme == "http" and port is None:
        errors.append("loopback HTTP SearXNG endpoint must use an explicit port")


def _with_crossref_defaults(payload: object) -> object:
    """Migrate pre-Crossref v1 configs in memory without enabling a new network provider."""
    if not isinstance(payload, dict):
        return payload
    normalized = deepcopy(payload)
    providers = normalized.get("providers")
    if isinstance(providers, dict):
        providers.setdefault("crossref", {"enabled": False})
    rates = normalized.get("rate_limits")
    if isinstance(rates, dict):
        rates.setdefault("crossref_min_interval_seconds", 0.2)
    return normalized


def _execution_profile_config(environment: Mapping[str, str]) -> tuple[str, dict]:
    try:
        manifest = graphs.load("g02")
    except (OSError, ValueError, KeyError, TypeError):
        manifest = {}
    requested = environment.get(EXECUTION_PROFILE_ENV, "").strip()
    default = manifest.get("default_execution_profile") if isinstance(manifest, dict) else None
    name = requested or (default if isinstance(default, str) else "strict")
    profiles = manifest.get("execution_profiles") if isinstance(manifest, dict) else {}
    profile = profiles.get(name) if isinstance(profiles, dict) else {}
    return name.casefold(), profile if isinstance(profile, dict) else {}


def _cap_positive(container: object, field: str, ceiling: object) -> None:
    if not isinstance(container, dict) or not isinstance(ceiling, int) \
            or isinstance(ceiling, bool) or ceiling < 1:
        return
    current = container.get(field)
    if isinstance(current, int) and not isinstance(current, bool) and current > 0:
        container[field] = min(current, ceiling)


def _apply_execution_profile_limits(payload: dict, environment: Mapping[str, str]) -> dict:
    """Cap provider fan-out for fast without changing stored non-fast configuration."""
    name, profile = _execution_profile_config(environment)
    if name != "fast":
        return payload
    result = deepcopy(payload)
    discovery = profile.get("discovery") if isinstance(profile.get("discovery"), dict) else {}
    limits = result.get("limits")
    _cap_positive(limits, "per_page", discovery.get("per_page"))
    _cap_positive(limits, "max_pages_per_call", discovery.get("max_pages_per_call"))
    _cap_positive(limits, "max_records_per_query", discovery.get("max_records_per_query"))

    web_profile = profile.get("web") if isinstance(profile.get("web"), dict) else {}
    web = result.get("web") if isinstance(result.get("web"), dict) else {}
    web_limits = web.get("limits")
    _cap_positive(web_limits, "max_queries_per_task", web_profile.get("max_queries_per_task"))
    _cap_positive(
        web_limits, "max_tavily_queries_per_task",
        web_profile.get("max_tavily_queries_per_task"),
    )
    _cap_positive(
        web_limits, "max_searxng_queries_per_task",
        web_profile.get("max_queries_per_task"),
    )
    _cap_positive(
        web_limits, "max_results_per_query", web_profile.get("max_results_per_query")
    )
    _cap_positive(
        web_limits, "auto_searxng_results_per_route",
        web_profile.get("max_results_per_query"),
    )
    _cap_positive(
        web_limits, "max_extractions_per_task",
        web_profile.get("max_extractions_per_task"),
    )

    retrieval_profile = profile.get("retrieval") \
        if isinstance(profile.get("retrieval"), dict) else {}
    retrieval = result.get("retrieval") \
        if isinstance(result.get("retrieval"), dict) else {}
    _cap_positive(
        retrieval.get("limits"), "max_documents_per_task",
        retrieval_profile.get("max_documents_per_task"),
    )
    return result


def validate_config(payload: object, *, env: Mapping[str, str] | None = None,
                    runtime_home: str | Path | None = None) -> dict:
    """Validate shape, safe paths, limits and required contact configuration."""
    environment = env if env is not None else os.environ
    errors: list[str] = []
    payload = _with_crossref_defaults(payload)
    try:
        shape = contracts.validate(payload, CONFIG_CONTRACT)
    except (KeyError, ValueError) as exc:
        return {"ok": False, "errors": [str(exc)]}
    errors.extend(shape["errors"])
    if not isinstance(payload, dict):
        return {"ok": False, "errors": errors}

    _reject_unknown_keys(
        payload,
        {"schema_version", "profile", "providers", "request", "limits", "cache",
         "paths", "rate_limits", "web", "retrieval"},
        "provider config",
        errors,
    )

    if not isinstance(payload.get("profile"), str) or not payload["profile"].strip():
        errors.append("profile must not be empty")
    provider_map = payload.get("providers")
    enabled: list[str] = []
    if isinstance(provider_map, dict):
        _reject_unknown_keys(provider_map, set(PROVIDERS), "providers", errors)
        for provider in PROVIDERS:
            _reject_unknown_keys(
                provider_map.get(provider), {"enabled"}, f"providers.{provider}", errors
            )
        enabled = [name for name in PROVIDERS
                   if isinstance(provider_map.get(name), dict)
                   and provider_map[name].get("enabled") is True]
    if not enabled:
        errors.append("at least one scholarly provider must be enabled")

    contact = environment.get(CONTACT_ENV, "").strip()
    if any(name in enabled for name in ("openalex", "arxiv", "crossref")):
        if not contact:
            errors.append(
                f"{CONTACT_ENV} is required when OpenAlex, arXiv or Crossref is enabled"
            )
        elif not EMAIL_RE.fullmatch(contact):
            errors.append(f"{CONTACT_ENV} must contain a valid email address")

    # OpenAlex needs its (free) API token to be USABLE, but a missing token is NOT a hard config
    # error: without it OpenAlex is simply not-ready while the other providers (Semantic Scholar,
    # arXiv, Crossref, Unpaywall on the contact email) keep working. The token is collected from the
    # user at the credential-setup step; we never block the whole graph just because it is absent.

    request = payload.get("request")
    if isinstance(request, dict):
        _reject_unknown_keys(
            request,
            {"timeout_seconds", "max_retries", "backoff_seconds", "max_response_bytes"},
            "request",
            errors,
        )
        _positive_number(request.get("timeout_seconds"), "request.timeout_seconds", errors)
        _positive_integer(request.get("max_retries"), "request.max_retries", errors,
                          allow_zero=True)
        _positive_number(request.get("backoff_seconds"), "request.backoff_seconds", errors,
                         allow_zero=True)
        _positive_integer(request.get("max_response_bytes"),
                          "request.max_response_bytes", errors)
        if isinstance(request.get("timeout_seconds"), (int, float)) \
                and request["timeout_seconds"] > 120:
            errors.append("request.timeout_seconds cannot exceed 120")
        if isinstance(request.get("max_retries"), int) and request["max_retries"] > 10:
            errors.append("request.max_retries cannot exceed 10")
        if isinstance(request.get("max_response_bytes"), int) \
                and request["max_response_bytes"] > 104857600:
            errors.append("request.max_response_bytes cannot exceed 100 MiB")

    limits = payload.get("limits")
    if isinstance(limits, dict):
        _reject_unknown_keys(
            limits, {"per_page", "max_pages_per_call", "max_records_per_query"},
            "limits", errors,
        )
        for field in ("per_page", "max_pages_per_call", "max_records_per_query"):
            _positive_integer(limits.get(field), f"limits.{field}", errors)
        if isinstance(limits.get("per_page"), int) and limits["per_page"] > 100:
            errors.append("limits.per_page cannot exceed 100")
        if isinstance(limits.get("max_pages_per_call"), int) \
                and limits["max_pages_per_call"] > 20:
            errors.append("limits.max_pages_per_call cannot exceed 20")

    cache = payload.get("cache")
    if isinstance(cache, dict):
        _reject_unknown_keys(cache, {"enabled", "ttl_seconds"}, "cache", errors)
        _positive_integer(cache.get("ttl_seconds"), "cache.ttl_seconds", errors,
                          allow_zero=True)

    rates = payload.get("rate_limits")
    if isinstance(rates, dict):
        _reject_unknown_keys(
            rates,
            {"openalex_min_interval_seconds", "semantic_scholar_min_interval_seconds",
             "arxiv_min_interval_seconds", "crossref_min_interval_seconds"},
            "rate_limits",
            errors,
        )
        for field in (
            "openalex_min_interval_seconds",
            "semantic_scholar_min_interval_seconds",
            "arxiv_min_interval_seconds",
            "crossref_min_interval_seconds",
        ):
            _positive_number(rates.get(field), f"rate_limits.{field}", errors,
                             allow_zero=True)
        arxiv_interval = rates.get("arxiv_min_interval_seconds")
        if "arxiv" in enabled and isinstance(arxiv_interval, (int, float)) \
                and arxiv_interval < 3:
            errors.append("rate_limits.arxiv_min_interval_seconds must be at least 3")

    home = (Path(runtime_home) if runtime_home is not None else paths.runtime_home()).resolve()
    config_paths = payload.get("paths")
    resolved_paths = {}
    if isinstance(config_paths, dict):
        _reject_unknown_keys(
            config_paths, {"cache_subdir", "corpus_subdir", "raw_artifact_subdir"},
            "paths", errors,
        )
        for field in ("cache_subdir", "corpus_subdir"):
            resolved_paths[field] = _safe_subdir(
                home, config_paths.get(field), f"paths.{field}", errors
            )
        raw_subdir = config_paths.get("raw_artifact_subdir")
        raw_path = _safe_subdir(
            home / "artifacts", raw_subdir, "paths.raw_artifact_subdir", errors
        )
        resolved_paths["raw_artifact_subdir"] = raw_subdir if raw_path else None

    web = payload.get("web")
    if web is not None and not isinstance(web, dict):
        errors.append("web must be an object")
    if isinstance(web, dict):
        _reject_unknown_keys(
            web, {"enabled", "mode", "providers", "request", "limits", "cache", "paths",
                  "rate_limits", "source_tiers"}, "web", errors,
        )
        if not isinstance(web.get("enabled"), bool):
            errors.append("web.enabled must be boolean")
        mode = web.get("mode")
        if mode not in {"tavily", "searxng", "auto_budgeted"}:
            errors.append("web.mode must be tavily, searxng or auto_budgeted")
        web_providers = web.get("providers")
        enabled_web: list[str] = []
        if not isinstance(web_providers, dict):
            errors.append("web.providers must be an object")
        else:
            _reject_unknown_keys(web_providers, set(WEB_PROVIDERS), "web.providers", errors)
            for provider in WEB_PROVIDERS:
                item = web_providers.get(provider)
                if not isinstance(item, dict):
                    errors.append(f"web.providers.{provider} must be an object")
                    continue
                allowed = {"enabled"} if provider == "tavily" else {
                    "enabled", "endpoint", "allow_http_loopback_dev", "categories"
                }
                _reject_unknown_keys(item, allowed, f"web.providers.{provider}", errors)
                if not isinstance(item.get("enabled"), bool):
                    errors.append(f"web.providers.{provider}.enabled must be boolean")
                if item.get("enabled") is True:
                    enabled_web.append(provider)
            searx = web_providers.get("searxng")
            if isinstance(searx, dict):
                allow_loopback = searx.get("allow_http_loopback_dev") is True
                if not isinstance(searx.get("allow_http_loopback_dev"), bool):
                    errors.append("web.providers.searxng.allow_http_loopback_dev must be boolean")
                categories = searx.get("categories")
                if not isinstance(categories, list) or not categories \
                        or any(item not in {"general", "news"} for item in categories):
                    errors.append("web.providers.searxng.categories must use general/news")
                if searx.get("enabled") is True:
                    _validate_searxng_endpoint(searx.get("endpoint"), allow_loopback, errors)
        if web.get("enabled") is True:
            if not enabled_web:
                errors.append("at least one web provider must be enabled")
            if mode in WEB_PROVIDERS and mode not in enabled_web:
                errors.append(f"web.mode {mode} requires that provider to be enabled")

        web_request = web.get("request")
        if not isinstance(web_request, dict):
            errors.append("web.request must be an object")
        else:
            _reject_unknown_keys(
                web_request,
                {"timeout_seconds", "max_retries", "backoff_seconds", "max_response_bytes"},
                "web.request", errors,
            )
            _positive_number(web_request.get("timeout_seconds"), "web.request.timeout_seconds", errors)
            _positive_integer(web_request.get("max_retries"), "web.request.max_retries", errors, allow_zero=True)
            _positive_number(web_request.get("backoff_seconds"), "web.request.backoff_seconds", errors, allow_zero=True)
            _positive_integer(web_request.get("max_response_bytes"), "web.request.max_response_bytes", errors)
            if isinstance(web_request.get("timeout_seconds"), (int, float)) \
                    and web_request["timeout_seconds"] > 60:
                errors.append("web.request.timeout_seconds cannot exceed 60")
            if isinstance(web_request.get("max_retries"), int) and web_request["max_retries"] > 5:
                errors.append("web.request.max_retries cannot exceed 5")
            if isinstance(web_request.get("max_response_bytes"), int) \
                    and web_request["max_response_bytes"] > 10485760:
                errors.append("web.request.max_response_bytes cannot exceed 10 MiB")

        web_limits = web.get("limits")
        limit_fields = {
            "max_queries_per_task", "max_tavily_queries_per_task",
            "max_searxng_queries_per_task", "max_results_per_query",
            "auto_searxng_results_per_route", "max_extractions_per_task",
            "max_extracted_characters",
        }
        if not isinstance(web_limits, dict):
            errors.append("web.limits must be an object")
        else:
            _reject_unknown_keys(web_limits, limit_fields, "web.limits", errors)
            for field in limit_fields:
                _positive_integer(web_limits.get(field), f"web.limits.{field}", errors)
            if isinstance(web_limits.get("max_queries_per_task"), int) \
                    and web_limits["max_queries_per_task"] > 100:
                errors.append("web.limits.max_queries_per_task cannot exceed 100")
            if isinstance(web_limits.get("max_results_per_query"), int) \
                    and web_limits["max_results_per_query"] > 50:
                errors.append("web.limits.max_results_per_query cannot exceed 50")
            if isinstance(web_limits.get("max_extracted_characters"), int) \
                    and web_limits["max_extracted_characters"] > 200000:
                errors.append("web.limits.max_extracted_characters cannot exceed 200000")

        web_cache = web.get("cache")
        if not isinstance(web_cache, dict):
            errors.append("web.cache must be an object")
        else:
            _reject_unknown_keys(web_cache, {"enabled", "ttl_seconds"}, "web.cache", errors)
            if not isinstance(web_cache.get("enabled"), bool):
                errors.append("web.cache.enabled must be boolean")
            _positive_integer(web_cache.get("ttl_seconds"), "web.cache.ttl_seconds", errors, allow_zero=True)

        web_rates = web.get("rate_limits")
        rate_fields = {"tavily_min_interval_seconds", "searxng_min_interval_seconds"}
        if not isinstance(web_rates, dict):
            errors.append("web.rate_limits must be an object")
        else:
            _reject_unknown_keys(web_rates, rate_fields, "web.rate_limits", errors)
            for field in rate_fields:
                _positive_number(web_rates.get(field), f"web.rate_limits.{field}", errors, allow_zero=True)

        web_paths = web.get("paths")
        if not isinstance(web_paths, dict):
            errors.append("web.paths must be an object")
        else:
            _reject_unknown_keys(
                web_paths,
                {"cache_subdir", "raw_artifact_subdir", "extract_artifact_subdir"},
                "web.paths", errors,
            )
            resolved_paths["web_cache_subdir"] = _safe_subdir(
                home, web_paths.get("cache_subdir"), "web.paths.cache_subdir", errors
            )
            for field in ("raw_artifact_subdir", "extract_artifact_subdir"):
                valid = _safe_subdir(
                    home / "artifacts", web_paths.get(field), f"web.paths.{field}", errors
                )
                resolved_paths[f"web_{field}"] = web_paths.get(field) if valid else None

        tiers = web.get("source_tiers")
        tier_fields = {"tier_1_domains", "tier_2_domains", "tier_3_domains", "excluded_domains"}
        if not isinstance(tiers, dict):
            errors.append("web.source_tiers must be an object")
        else:
            _reject_unknown_keys(tiers, tier_fields, "web.source_tiers", errors)
            seen_domains: set[str] = set()
            for field in tier_fields:
                values = tiers.get(field)
                if not isinstance(values, list) or any(not _valid_domain(item) for item in values):
                    errors.append(f"web.source_tiers.{field} must contain valid bare domains")
                    continue
                normalized = [item.casefold().rstrip(".") for item in values]
                if len(normalized) != len(set(normalized)):
                    errors.append(f"web.source_tiers.{field} contains duplicates")
                overlap = seen_domains & set(normalized)
                if overlap:
                    errors.append(f"web.source_tiers domain appears in multiple lists: {sorted(overlap)}")
                seen_domains.update(normalized)

    retrieval = payload.get("retrieval")
    if retrieval is not None and not isinstance(retrieval, dict):
        errors.append("retrieval must be an object")
    if isinstance(retrieval, dict):
        _reject_unknown_keys(
            retrieval, {"enabled", "providers", "request", "limits", "rate_limits", "paths"},
            "retrieval", errors,
        )
        if not isinstance(retrieval.get("enabled"), bool):
            errors.append("retrieval.enabled must be boolean")
        retrieval_providers = retrieval.get("providers")
        if not isinstance(retrieval_providers, dict):
            errors.append("retrieval.providers must be an object")
        else:
            _reject_unknown_keys(
                retrieval_providers, set(RETRIEVAL_PROVIDERS), "retrieval.providers", errors
            )
            for provider in RETRIEVAL_PROVIDERS:
                item = retrieval_providers.get(provider)
                if not isinstance(item, dict) or not isinstance(item.get("enabled"), bool):
                    errors.append(f"retrieval.providers.{provider}.enabled must be boolean")
                else:
                    _reject_unknown_keys(item, {"enabled"},
                                         f"retrieval.providers.{provider}", errors)
        retrieval_request = retrieval.get("request")
        request_fields = {
            "timeout_seconds", "max_retries", "backoff_seconds", "max_metadata_response_bytes",
            "max_document_bytes", "max_redirects",
        }
        if not isinstance(retrieval_request, dict):
            errors.append("retrieval.request must be an object")
        else:
            _reject_unknown_keys(retrieval_request, request_fields, "retrieval.request", errors)
            _positive_number(retrieval_request.get("timeout_seconds"),
                             "retrieval.request.timeout_seconds", errors)
            _positive_integer(retrieval_request.get("max_retries"),
                              "retrieval.request.max_retries", errors, allow_zero=True)
            _positive_number(retrieval_request.get("backoff_seconds"),
                             "retrieval.request.backoff_seconds", errors, allow_zero=True)
            for field in ("max_metadata_response_bytes", "max_document_bytes", "max_redirects"):
                _positive_integer(retrieval_request.get(field), f"retrieval.request.{field}", errors)
            if isinstance(retrieval_request.get("max_document_bytes"), int) \
                    and retrieval_request["max_document_bytes"] > 209715200:
                errors.append("retrieval.request.max_document_bytes cannot exceed 200 MiB")
            if isinstance(retrieval_request.get("max_redirects"), int) \
                    and retrieval_request["max_redirects"] > 10:
                errors.append("retrieval.request.max_redirects cannot exceed 10")
        retrieval_limits = retrieval.get("limits")
        if not isinstance(retrieval_limits, dict):
            errors.append("retrieval.limits must be an object")
        else:
            _reject_unknown_keys(retrieval_limits, {"max_documents_per_task"},
                                 "retrieval.limits", errors)
            _positive_integer(retrieval_limits.get("max_documents_per_task"),
                              "retrieval.limits.max_documents_per_task", errors)
        retrieval_rates = retrieval.get("rate_limits")
        retrieval_rate_fields = {
            f"{provider}_min_interval_seconds" for provider in RETRIEVAL_PROVIDERS
        }
        if not isinstance(retrieval_rates, dict):
            errors.append("retrieval.rate_limits must be an object")
        else:
            _reject_unknown_keys(retrieval_rates, retrieval_rate_fields,
                                 "retrieval.rate_limits", errors)
            for field in retrieval_rate_fields:
                _positive_number(retrieval_rates.get(field), f"retrieval.rate_limits.{field}",
                                 errors, allow_zero=True)
        retrieval_paths = retrieval.get("paths")
        if not isinstance(retrieval_paths, dict):
            errors.append("retrieval.paths must be an object")
        else:
            retrieval_path_fields = {"temp_subdir", "accepted_subdir", "market_case_subdir"}
            _reject_unknown_keys(retrieval_paths, retrieval_path_fields,
                                 "retrieval.paths", errors)
            for field in retrieval_path_fields:
                resolved_paths[f"retrieval_{field}"] = _safe_subdir(
                    home, retrieval_paths.get(field), f"retrieval.paths.{field}", errors
                )

    return {"ok": not errors, "errors": errors, "resolved_paths": resolved_paths}


def load_config(config_path: str | Path | None = None, *,
                env: Mapping[str, str] | None = None,
                runtime_home: str | Path | None = None,
                create_dirs: bool = True) -> ProviderRuntimeConfig:
    """Load a safe config and bind environment-only contact data and secrets."""
    if env is None:                         # real path: pick up any host-supplied session creds
        from g02 import credentials
        credentials.overlay()
        environment = credentials.managed_environment(os.environ)
    else:
        environment = env
    source = _resolve_source(config_path, environment)
    payload = _with_crossref_defaults(_read_json(source))
    assert isinstance(payload, dict)
    payload = _apply_execution_profile_limits(payload, environment)
    home = (Path(runtime_home) if runtime_home is not None else paths.runtime_home()).resolve()
    validation = validate_config(payload, env=environment, runtime_home=home)
    if not validation["ok"]:
        raise ProviderConfigError("; ".join(validation["errors"]))

    cache_dir = validation["resolved_paths"]["cache_subdir"]
    corpus_dir = validation["resolved_paths"]["corpus_subdir"]
    assert isinstance(cache_dir, Path) and isinstance(corpus_dir, Path)
    web_cache_dir = validation["resolved_paths"].get("web_cache_subdir")
    retrieval_temp_dir = validation["resolved_paths"].get("retrieval_temp_subdir")
    retrieval_accepted_dir = validation["resolved_paths"].get("retrieval_accepted_subdir")
    retrieval_market_case_dir = validation["resolved_paths"].get("retrieval_market_case_subdir")
    if create_dirs:
        for directory in (home / "config", home / "artifacts", home / "logs",
                          cache_dir, corpus_dir, web_cache_dir, retrieval_temp_dir,
                          retrieval_accepted_dir, retrieval_market_case_dir):
            if directory is None:
                continue
            directory.mkdir(parents=True, exist_ok=True)

    contact = environment.get(CONTACT_ENV, "").strip() or None
    api_keys = MappingProxyType({
        "openalex": environment.get(OPENALEX_KEY_ENV, "").strip() or None,
        "semantic_scholar": environment.get(SEMANTIC_SCHOLAR_KEY_ENV, "").strip() or None,
        "arxiv": None,
        "crossref": None,
        "tavily": environment.get(TAVILY_KEY_ENV, "").strip() or None,
        "core": environment.get(CORE_KEY_ENV, "").strip() or None,
    })
    return ProviderRuntimeConfig(
        data=MappingProxyType(deepcopy(payload)),
        source=str(source),
        runtime_home=home,
        cache_dir=cache_dir,
        corpus_dir=corpus_dir,
        raw_artifact_subdir=str(payload["paths"]["raw_artifact_subdir"]).strip("/\\"),
        web_cache_dir=web_cache_dir if isinstance(web_cache_dir, Path) else None,
        web_raw_artifact_subdir=(str(payload.get("web", {}).get("paths", {}).get(
            "raw_artifact_subdir", "")).strip("/\\") or None),
        web_extract_artifact_subdir=(str(payload.get("web", {}).get("paths", {}).get(
            "extract_artifact_subdir", "")).strip("/\\") or None),
        retrieval_temp_dir=retrieval_temp_dir if isinstance(retrieval_temp_dir, Path) else None,
        retrieval_accepted_dir=(retrieval_accepted_dir
                                if isinstance(retrieval_accepted_dir, Path) else None),
        retrieval_market_case_dir=(retrieval_market_case_dir
                                   if isinstance(retrieval_market_case_dir, Path) else None),
        contact_email=contact,
        _api_keys=api_keys,
    )


def provider_status(config_path: str | Path | None = None, *,
                    env: Mapping[str, str] | None = None,
                    runtime_home: str | Path | None = None) -> dict:
    """Return a secret-free startup report suitable for MCP and diagnostics."""
    try:
        config = load_config(
            config_path, env=env, runtime_home=runtime_home, create_dirs=True
        )
    except ProviderConfigError as exc:
        return {
            "ok": False,
            "schema_version": CONFIG_CONTRACT,
            "errors": [str(exc)],
            "capabilities": [],
        }
    status = config.public_status()
    status["ok"] = True
    status["errors"] = []
    return status
