"""Deterministic one-hop citation expansion for G02-A03 and G02-A04."""
from __future__ import annotations

import json
import urllib.parse
import uuid
from pathlib import Path

from core import artifacts
from g02 import canonical, provider_config, providers

TOOL_RESULT_CONTRACT = "literature_tool_result@1"
SOURCE_RECORD_CONTRACT = "source_record@1"
SUPPORTED = {
    "openalex": {"cited_by"},
    "semantic_scholar": {"references", "cited_by", "recommendations"},
}


def _issue(code: str, message: str, *, retryable: bool = False) -> dict:
    return {"code": code, "retryable": retryable, "message": message}


def _request(seed_source_id: str, seed_provider_id: str | None, relation: str,
             cursor: str | None, limit: int, scope: dict) -> dict:
    token = f"CIT_{seed_source_id}_{relation}"[:120]
    return {
        "route_id": token,
        "query_id": token,
        "canonical_query": seed_source_id,
        "filters": {},
        "cursor": cursor,
        "limit": limit,
        "seed_source_id": seed_source_id,
        "seed_provider_id": seed_provider_id or "",
        "relation": relation,
        "depth": 1,
        "scope": scope,
    }


def _failed_result(provider: str, request: dict, *, started_at: str, status: str,
                   issue: dict, config_profile: str = "unavailable") -> dict:
    return {
        "schema_version": TOOL_RESULT_CONTRACT,
        "operation_id": f"OP_{uuid.uuid4().hex.upper()}",
        "operation_type": "citation_expand",
        "provider": provider,
        "status": status,
        "started_at": started_at,
        "completed_at": providers._utc_now(),
        "request": request,
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


def _seed_record(canonical_input: dict, source_id: str) -> dict | None:
    matches = [record for record in canonical_input.get("domain_candidates", [])
               if isinstance(record, dict) and record.get("source_id") == source_id]
    return matches[0] if len(matches) == 1 else None


def _seed_identifier(record: dict, provider: str) -> str | None:
    identifiers = record.get("identifiers") if isinstance(record.get("identifiers"), dict) else {}
    if provider == "openalex":
        value = identifiers.get("openalex_id")
        return value.strip() if isinstance(value, str) and value.strip() else None
    if provider == "semantic_scholar":
        candidates = (
            identifiers.get("semantic_scholar_id"),
            f"DOI:{identifiers['doi']}" if isinstance(identifiers.get("doi"), str)
            and identifiers["doi"].strip() else None,
            f"ARXIV:{identifiers['arxiv_id']}" if isinstance(identifiers.get("arxiv_id"), str)
            and identifiers["arxiv_id"].strip() else None,
        )
        return next((value.strip() for value in candidates
                     if isinstance(value, str) and value.strip()), None)
    return None


def _build_url(provider: str, provider_id: str, relation: str,
               cursor: str | None, limit: int) -> str:
    if provider == "openalex":
        params = {
            "filter": f"cites:{provider_id}",
            "per-page": str(limit),
            "cursor": cursor or "*",
            "select": providers.OPENALEX_SELECT,
        }
        return f"{providers.ENDPOINTS['openalex']}?{urllib.parse.urlencode(params)}"
    encoded = urllib.parse.quote(provider_id, safe="")
    if relation == "recommendations":
        base = f"https://api.semanticscholar.org/recommendations/v1/papers/forpaper/{encoded}"
        params = {"limit": str(limit), "fields": providers.S2_FIELDS}
    else:
        suffix = "citations" if relation == "cited_by" else "references"
        base = f"https://api.semanticscholar.org/graph/v1/paper/{encoded}/{suffix}"
        params = {"limit": str(limit), "fields": providers.S2_FIELDS}
        if cursor is not None:
            params["offset"] = cursor
    return f"{base}?{urllib.parse.urlencode(params)}"


def _parse_semantic_scholar(body: str, relation: str, *, query_id: str,
                            topic_id: str, raw_ref: str, retrieved_at: str,
                            current_cursor: str | None,
                            inclusion_pool: str) -> tuple[list[dict], str | None, bool]:
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError("Semantic Scholar citation response must be an object")
    if relation == "recommendations":
        rows = payload.get("recommendedPapers")
        rows = rows if isinstance(rows, list) else []
        next_cursor = None
        exhausted = True
    else:
        data = payload.get("data")
        data = data if isinstance(data, list) else []
        key = "citingPaper" if relation == "cited_by" else "citedPaper"
        rows = [row.get(key) for row in data if isinstance(row, dict)]
        next_value = payload.get("next")
        next_cursor = str(next_value) if isinstance(next_value, int) else None
        exhausted = next_cursor is None or next_cursor == current_cursor
    records = []
    for row in rows:
        record = providers._normalize_semantic_scholar(
            row, query_id=query_id, topic_id=topic_id,
            raw_ref=raw_ref, retrieved_at=retrieved_at,
        )
        if record is not None:
            record["inclusion"]["pool"] = inclusion_pool
            record["inclusion"]["reason_included"] = [f"citation_{relation}"]
            records.append(record)
    return records, next_cursor, exhausted


def _parse_openalex(body: str, *, query_id: str, topic_id: str, raw_ref: str,
                    retrieved_at: str, current_cursor: str | None,
                    inclusion_pool: str) \
        -> tuple[list[dict], str | None, bool]:
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError("OpenAlex citation response must be an object")
    rows = payload.get("results") if isinstance(payload.get("results"), list) else []
    records = []
    for row in rows:
        record = providers._normalize_openalex(
            row, query_id=query_id, topic_id=topic_id,
            raw_ref=raw_ref, retrieved_at=retrieved_at,
        )
        if record is not None:
            record["inclusion"]["pool"] = inclusion_pool
            record["inclusion"]["reason_included"] = ["citation_cited_by"]
            records.append(record)
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    next_cursor = meta.get("next_cursor") if isinstance(meta.get("next_cursor"), str) else None
    return records, next_cursor, next_cursor is None or next_cursor == current_cursor


def _basis_errors(discovery_input: object,
                  config: provider_config.ProviderRuntimeConfig, *, base=None) -> list[str]:
    version = discovery_input.get("schema_version") \
        if isinstance(discovery_input, dict) else None
    if version == canonical.CANONICAL_INPUT_CONTRACT:
        checked = canonical.validate_canonical_basis(discovery_input, base=base)
    elif version == "recent_research_input@1":
        from g02 import recent
        checked = recent.validate_recent_basis(discovery_input, base=base)
    else:
        return ["citation expansion requires canonical_research_input@1 or recent_research_input@1"]
    if not checked["ok"] or not isinstance(discovery_input, dict):
        return [item["message"] for item in checked["issues"]] or [
            "discovery input must be an object"
        ]
    errors = []
    if discovery_input.get("provider_capabilities") != config.public_status()["capabilities"]:
        errors.append("provider_capabilities differ from active provider configuration")
    return errors


def expand_citations(discovery_input: object, *, seed_source_id: str,
                     provider: str, relation: str, cursor: str | None = None,
                     limit: int | None = None, config_path: str | Path | None = None,
                     runtime_home: str | Path | None = None, artifact_base=None,
                     transport: providers.Transport | None = None) -> dict:
    """Execute one bounded provider citation relation and persist its normalized result."""
    started_at = providers._utc_now()
    requested_limit = limit if isinstance(limit, int) and not isinstance(limit, bool) else 0
    operation_scope = providers._operation_scope(discovery_input)
    placeholder = _request(
        seed_source_id, None, relation, cursor, requested_limit, operation_scope
    )
    if provider not in canonical.PROVIDERS:
        raise ValueError(f"unsupported provider {provider!r}")
    try:
        config = provider_config.load_config(
            config_path, runtime_home=runtime_home, create_dirs=True
        )
    except provider_config.ProviderConfigError as exc:
        return _failed_result(
            provider, placeholder, started_at=started_at, status="failed",
            issue=_issue("provider_configuration_error", str(exc)),
        )
    basis_errors = _basis_errors(discovery_input, config, base=artifact_base)
    if basis_errors:
        basis_code = "invalid_canonical_input_basis" if isinstance(discovery_input, dict) \
            and discovery_input.get("schema_version") == canonical.CANONICAL_INPUT_CONTRACT \
            else "invalid_recent_input_basis"
        result = _failed_result(
            provider, placeholder, started_at=started_at, status="failed",
            issue=_issue(basis_code, "; ".join(basis_errors)),
            config_profile=config.profile,
        )
        return providers._store_result(result, config, base=artifact_base)
    assert isinstance(discovery_input, dict)
    inclusion_pool = "recent_expansion" \
        if discovery_input.get("schema_version") == "recent_research_input@1" \
        else "canonical_expansion"
    seed = _seed_record(discovery_input, seed_source_id)
    if seed is None or seed_source_id not in discovery_input.get("verified_seed_ids", []):
        result = _failed_result(
            provider, placeholder, started_at=started_at, status="failed",
            issue=_issue("unapproved_citation_seed", seed_source_id),
            config_profile=config.profile,
        )
        return providers._store_result(result, config, base=artifact_base)
    allowed_relations = discovery_input.get("search_limits", {}).get("allowed_relations", [])
    if relation not in allowed_relations:
        result = _failed_result(
            provider, placeholder, started_at=started_at, status="failed",
            issue=_issue("unapproved_citation_relation", relation),
            config_profile=config.profile,
        )
        return providers._store_result(result, config, base=artifact_base)
    if provider not in SUPPORTED or relation not in SUPPORTED[provider]:
        result = _failed_result(
            provider, placeholder, started_at=started_at, status="unavailable",
            issue=_issue(
                "citation_relation_unsupported",
                f"{provider} does not expose {relation} through the configured adapter",
            ),
            config_profile=config.profile,
        )
        return providers._store_result(result, config, base=artifact_base)
    provider_id = _seed_identifier(seed, provider)
    request = _request(
        seed_source_id, provider_id, relation, cursor, requested_limit, operation_scope
    )
    if provider_id is None:
        result = _failed_result(
            provider, request, started_at=started_at, status="unavailable",
            issue=_issue("citation_seed_identifier_unavailable", seed_source_id),
            config_profile=config.profile,
        )
        return providers._store_result(result, config, base=artifact_base)
    maximum = int(discovery_input["search_limits"]["per_seed_relation_limit"])
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > maximum:
        result = _failed_result(
            provider, request, started_at=started_at, status="failed",
            issue=_issue("citation_limit_invalid", f"limit must be between 1 and {maximum}"),
            config_profile=config.profile,
        )
        return providers._store_result(result, config, base=artifact_base)
    if not config.enabled(provider):
        result = _failed_result(
            provider, request, started_at=started_at, status="unavailable",
            issue=_issue("provider_disabled", f"{provider} is disabled"),
            config_profile=config.profile,
        )
        return providers._store_result(result, config, base=artifact_base)
    capability = next((item for item in discovery_input["provider_capabilities"]
                       if item.get("provider") == provider), None)
    if not isinstance(capability, dict) or capability.get("ready") is not True:
        result = _failed_result(
            provider, request, started_at=started_at, status="unavailable",
            issue=_issue("provider_not_ready", provider), config_profile=config.profile,
        )
        return providers._store_result(result, config, base=artifact_base)

    operation_id = f"OP_{uuid.uuid4().hex.upper()}"
    records: list[dict] = []
    raw_refs: list[str] = []
    request_ids: list[str] = []
    issues: list[dict] = []
    next_cursor = cursor
    pages_processed = 0
    exhausted = False
    any_cache_hit = False
    failed = False
    limits = config.data["limits"]
    assert isinstance(limits, dict)
    max_pages = int(limits["max_pages_per_call"])
    per_page = int(limits["per_page"])
    seen_ids: set[str] = set()
    for page_number in range(1, max_pages + 1):
        remaining = limit - len(records)
        if remaining <= 0:
            break
        page_size = min(per_page, remaining)
        url = _build_url(provider, provider_id, relation, next_cursor, page_size)
        try:
            page = providers._request_page(
                config, provider, url, providers._headers(config, provider), transport
            )
            any_cache_hit = any_cache_hit or page.cache_hit
            retrieved_at = providers._utc_now()
            raw_ref = artifacts.store(
                f"{config.raw_artifact_subdir}/{operation_id}.page-{page_number}.json",
                {
                    "provider": provider,
                    "operation_id": operation_id,
                    "operation_type": "citation_expand",
                    "seed_source_id": seed_source_id,
                    "relation": relation,
                    "page": page_number,
                    "retrieved_at": retrieved_at,
                    "status_code": page.status_code,
                    "content_type": page.headers.get("content-type"),
                    "provider_request_id": page.request_id,
                    "cache_hit": page.cache_hit,
                    "body": page.body_text,
                },
                base=artifact_base,
            )
            raw_refs.append(raw_ref)
            if page.request_id:
                request_ids.append(page.request_id)
            if provider == "openalex":
                parsed, new_cursor, exhausted = _parse_openalex(
                    page.body_text, query_id=request["query_id"],
                    topic_id=discovery_input["topic"]["topic_id"], raw_ref=raw_ref,
                    retrieved_at=retrieved_at, current_cursor=next_cursor,
                    inclusion_pool=inclusion_pool,
                )
            else:
                parsed, new_cursor, exhausted = _parse_semantic_scholar(
                    page.body_text, relation, query_id=request["query_id"],
                    topic_id=discovery_input["topic"]["topic_id"], raw_ref=raw_ref,
                    retrieved_at=retrieved_at, current_cursor=next_cursor,
                    inclusion_pool=inclusion_pool,
                )
            for record in parsed:
                if record["source_id"] not in seen_ids and len(records) < limit:
                    records.append(record)
                    seen_ids.add(record["source_id"])
            pages_processed += 1
            next_cursor = new_cursor
            if exhausted:
                break
        except (providers.ProviderRequestError, OSError, ValueError,
                KeyError, json.JSONDecodeError) as exc:
            failed = True
            if isinstance(exc, providers.ProviderRequestError):
                issues.append(_issue(exc.code, exc.message, retryable=exc.retryable))
            else:
                issues.append(_issue(
                    "provider_response_error",
                    providers._redact(exc, [config.api_key(provider), config.contact_email]),
                ))
            break
    status = "partial" if failed and records else (
        "unavailable" if failed and any(item["retryable"] for item in issues) else
        "failed" if failed else "ok"
    )
    result = {
        "schema_version": TOOL_RESULT_CONTRACT,
        "operation_id": operation_id,
        "operation_type": "citation_expand",
        "provider": provider,
        "status": status,
        "started_at": started_at,
        "completed_at": providers._utc_now(),
        "request": request,
        "records": records,
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
    return providers._store_result(result, config, base=artifact_base)
