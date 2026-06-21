"""Non-secret provider configuration and startup validation for G02.

The JSON file controls enabled services, limits, cache and relative runtime directories. Contact
data and API keys are read only from environment variables and are never included in public
status objects or provider artifacts.
"""
from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from core import contracts, paths

CONFIG_CONTRACT = "literature_provider_config@1"
CONFIG_ENV = "EMAGENTS_RESEARCH_CONFIG"
CONTACT_ENV = "EMAGENTS_RESEARCH_CONTACT_EMAIL"
OPENALEX_KEY_ENV = "OPENALEX_API_KEY"
SEMANTIC_SCHOLAR_KEY_ENV = "SEMANTIC_SCHOLAR_API_KEY"
PROVIDERS = ("openalex", "semantic_scholar", "arxiv")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

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

    def public_status(self) -> dict:
        capabilities = []
        for provider in PROVIDERS:
            enabled = self.enabled(provider)
            key = self.api_key(provider)
            contact_required = provider in {"openalex", "arxiv"}
            key_required = provider == "openalex"
            ready = enabled \
                and (not contact_required or self.contact_email is not None) \
                and (not key_required or key is not None)
            if provider == "openalex":
                authentication = "configured_key" if key else "required_key_missing"
            elif provider == "semantic_scholar":
                authentication = "configured_key" if key else "optional_key"
            else:
                authentication = "none"
            capabilities.append({
                "provider": provider,
                "enabled": enabled,
                "ready": ready,
                "authentication": authentication,
            })
        return {
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


def validate_config(payload: object, *, env: Mapping[str, str] | None = None,
                    runtime_home: str | Path | None = None) -> dict:
    """Validate shape, safe paths, limits and required contact configuration."""
    environment = env if env is not None else os.environ
    errors: list[str] = []
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
         "paths", "rate_limits"},
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
    if any(name in enabled for name in ("openalex", "arxiv")):
        if not contact:
            errors.append(
                f"{CONTACT_ENV} is required when OpenAlex or arXiv is enabled"
            )
        elif not EMAIL_RE.fullmatch(contact):
            errors.append(f"{CONTACT_ENV} must contain a valid email address")

    if "openalex" in enabled and not environment.get(OPENALEX_KEY_ENV, "").strip():
        errors.append(f"{OPENALEX_KEY_ENV} is required when OpenAlex is enabled")

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
             "arxiv_min_interval_seconds"},
            "rate_limits",
            errors,
        )
        for field in (
            "openalex_min_interval_seconds",
            "semantic_scholar_min_interval_seconds",
            "arxiv_min_interval_seconds",
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

    return {"ok": not errors, "errors": errors, "resolved_paths": resolved_paths}


def load_config(config_path: str | Path | None = None, *,
                env: Mapping[str, str] | None = None,
                runtime_home: str | Path | None = None,
                create_dirs: bool = True) -> ProviderRuntimeConfig:
    """Load a safe config and bind environment-only contact data and secrets."""
    environment = env if env is not None else os.environ
    source = _resolve_source(config_path, environment)
    payload = _read_json(source)
    home = (Path(runtime_home) if runtime_home is not None else paths.runtime_home()).resolve()
    validation = validate_config(payload, env=environment, runtime_home=home)
    if not validation["ok"]:
        raise ProviderConfigError("; ".join(validation["errors"]))

    cache_dir = validation["resolved_paths"]["cache_subdir"]
    corpus_dir = validation["resolved_paths"]["corpus_subdir"]
    assert isinstance(cache_dir, Path) and isinstance(corpus_dir, Path)
    if create_dirs:
        for directory in (home / "config", home / "artifacts", home / "logs",
                          cache_dir, corpus_dir):
            directory.mkdir(parents=True, exist_ok=True)

    contact = environment.get(CONTACT_ENV, "").strip() or None
    api_keys = MappingProxyType({
        "openalex": environment.get(OPENALEX_KEY_ENV, "").strip() or None,
        "semantic_scholar": environment.get(SEMANTIC_SCHOLAR_KEY_ENV, "").strip() or None,
        "arxiv": None,
    })
    return ProviderRuntimeConfig(
        data=MappingProxyType(deepcopy(payload)),
        source=str(source),
        runtime_home=home,
        cache_dir=cache_dir,
        corpus_dir=corpus_dir,
        raw_artifact_subdir=str(payload["paths"]["raw_artifact_subdir"]).strip("/\\"),
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
