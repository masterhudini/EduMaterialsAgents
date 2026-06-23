"""Deterministic Human Source Selection Gate for G02-A05 to G02-A06."""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy

from core import artifacts, contracts

INDEX_CONTRACT = "candidate_source_index@1"
SELECTION_CONTRACT = "human_source_selection@1"
APPROVED_SET_CONTRACT = "human_approved_source_set@1"
ACTIONS = {
    "DOWNLOAD": "approved_for_download",
    "LIBRARY": "request_library_access",
    "CITATION": "keep_citation_only",
    "RESERVE": "keep_in_reserve",
}


def _issue(severity: str, kind: str, message: str, location: str) -> dict:
    return {"severity": severity, "type": kind, "message": message, "location": location}


def _envelope(status: str, summary: str, issues: list[dict], *, produced=None,
              metrics=None, resume_token=None) -> dict:
    result = {"status": status, "produced": produced or [], "summary": summary, "issues": issues}
    if metrics is not None:
        result["metrics"] = metrics
    if resume_token is not None:
        result["resume_token"] = resume_token
    return result


def _strings(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str) and item.strip()] \
        if isinstance(value, list) else []


def _shape(payload: object, contract_ref: str) -> list[str]:
    try:
        return contracts.validate(payload, contract_ref)["errors"]
    except (KeyError, ValueError) as exc:
        return [str(exc)]


def _safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()) or "unknown"


def _load_index(candidate_source_index_ref: str, *, base=None) -> dict:
    if not isinstance(candidate_source_index_ref, str) \
            or not candidate_source_index_ref.startswith(artifacts.SCHEME):
        raise ValueError("candidate_source_index_ref must use artifact://")
    index = artifacts.hydrate(candidate_source_index_ref, base=base)
    errors = _shape(index, INDEX_CONTRACT)
    if errors:
        raise ValueError("; ".join(errors))
    document_ref = index.get("human_review_document_ref")
    if not isinstance(document_ref, str) or not document_ref.startswith(artifacts.SCHEME):
        raise ValueError("candidate index has no review-document ref")
    document_path = artifacts.resolve_path(document_ref, base=base)
    if not document_path.is_file():
        raise ValueError("candidate review document is unavailable")
    return index


def prepare_source_selection(candidate_source_index_ref: str, *, base=None) -> dict:
    """Return the user-facing gate prompt and exact IDs that require an action."""
    try:
        index = _load_index(candidate_source_index_ref, base=base)
    except (OSError, ValueError, KeyError, IndexError) as exc:
        return {"ready": False, "envelope": _envelope(
            "failed", "Human Source Selection Gate could not load the candidate index.",
            [_issue("blocker", "invalid_source_selection_basis", str(exc),
                    "candidate_source_index_ref")],
        )}
    by_id = {item["source_id"]: item for item in index["sources"]}
    language = str(index.get("output_language", "English"))
    polish = language.casefold().startswith("pl") or "pol" in language.casefold()
    cards = []
    for display_number, source_id in enumerate(index["displayed_source_ids"], start=1):
        item = by_id[source_id]
        cards.append({
            "display_number": display_number,
            "source_id": source_id,
            "title": item["record"]["bibliographic"]["title"],
            "record_type": item["record_type"],
            "description": item["human_annotation"]["content_summary"],
            "description_basis": item["human_annotation"]["description_basis"],
            "doi_verification": deepcopy(item.get("doi_verification")),
            "recommended_action": item["ranking"]["recommended_action"],
            "coverage_unit_ids": deepcopy(item["coverage_unit_ids"]),
        })
    prompt = {
        "task_id": index["task_id"],
        "candidate_source_index_ref": candidate_source_index_ref,
        "review_document_ref": index["human_review_document_ref"],
        "output_language": language,
        "instruction": (
            "Przejrzyj karty źródeł. Przypisz DOWNLOAD, LIBRARY, CITATION, RESERVE albo EXCLUDE "
            "każdemu prezentowanemu źródłu, używając numeru z listy lub stabilnego ID, albo wybierz "
            "SEARCH_MORE. Pokażę podsumowanie i poproszę o osobne finalne potwierdzenie przed "
            "jakimkolwiek pobraniem."
            if polish else
            "Review the linked source cards. Assign DOWNLOAD, LIBRARY, CITATION, RESERVE or "
            "EXCLUDE to every displayed source using its list number or stable ID, or request "
            "SEARCH_MORE. I will show the parsed "
            "decision and ask for a separate final confirmation before any retrieval."
        ),
        "required_source_ids": deepcopy(index["displayed_source_ids"]),
        "reserve_source_ids": deepcopy(index["reserve_source_ids"]),
        "cards": cards,
        "coverage_gaps": [deepcopy(item) for item in index["coverage_matrix"]
                          if item.get("status") != "covered"],
        "copyable_template": [
            "DOWNLOAD: <number or SRC_ID>", "LIBRARY: <number or SRC_ID>", "CITATION: SRC_...",
            "RESERVE: SRC_...", "EXCLUDE: SRC_... | reason=...",
            "SEARCH_MORE: coverage_id=... | request=...",
        ],
    }
    return {"ready": True, "gate_prompt": prompt, "user_prompt": render_gate_prompt(prompt)}


def render_gate_prompt(prompt: dict) -> str:
    """Render the structured gate payload as a concise terminal/chat prompt."""
    language = str(prompt.get("output_language", "English"))
    polish = language.casefold().startswith("pl") or "pol" in language.casefold()
    lines = ["Wybór źródeł do pobrania" if polish else "Source selection for retrieval", ""]
    review_ref = prompt.get("review_document_ref")
    if review_ref:
        lines.append(("Pełny przegląd: " if polish else "Full review: ") + str(review_ref))
        lines.append("")
    for card in prompt.get("cards", []):
        number = card.get("display_number", "?")
        title = card.get("title") or card.get("source_id") or "Untitled"
        kind = card.get("record_type", "source")
        recommendation = card.get("recommended_action", "")
        lines.append(f"[{number}] {title}")
        lines.append(f"    ID: {card.get('source_id')} | {kind} | "
                     f"{'sugestia' if polish else 'suggested'}: {recommendation}")
        description = card.get("description")
        if isinstance(description, str) and description.strip():
            lines.append(f"    {description.strip()}")
        coverage = card.get("coverage_unit_ids")
        if isinstance(coverage, list) and coverage:
            lines.append(f"    {'pokrycie' if polish else 'coverage'}: {', '.join(coverage)}")
        verification = card.get("doi_verification")
        if isinstance(verification, dict):
            lines.append(f"    Crossref: {verification.get('registry_status')} / "
                         f"{verification.get('match_status')}")
    lines.extend([
        "",
        ("Wpisz po jednej komendzie w linii, używając numerów lub ID:" if polish else
         "Enter one command per line, using numbers or IDs:"),
        "DOWNLOAD: 1",
        "LIBRARY: SRC_...",
        "CITATION: SRC_...",
        "RESERVE: SRC_...",
        "EXCLUDE: SRC_... | reason=...",
        "SEARCH_MORE: coverage_id=... | request=...",
        "CANCEL:",
    ])
    return "\n".join(lines)


def render_selection_summary(summary: dict, *, polish: bool = False) -> str:
    """Render the exact parsed decision before the separate confirmation step."""
    labels = {
        "download": "Pobierz" if polish else "Download",
        "library": "Biblioteka" if polish else "Library",
        "citation": "Tylko cytowanie" if polish else "Citation only",
        "reserve": "Rezerwa" if polish else "Reserve",
        "excluded": "Wykluczone" if polish else "Excluded",
        "search_more": "Dalsze wyszukiwanie" if polish else "Search more",
    }
    lines = ["Podsumowanie decyzji" if polish else "Selection summary"]
    for field in ("download", "library", "citation", "reserve", "excluded", "search_more"):
        lines.append(f"- {labels[field]}: "
                     f"{json.dumps(summary.get(field, []), ensure_ascii=False)}")
    if polish:
        lines.append(f"- Pliki do pobrania: {summary.get('download_count', 0)} "
                     f"(naukowe: {summary.get('scholarly_download_count', 0)}, "
                     f"przypadki rynkowe: {summary.get('market_case_download_count', 0)})")
    else:
        lines.append(f"- Downloads: {summary.get('download_count', 0)} "
                     f"(scholarly: {summary.get('scholarly_download_count', 0)}, "
                     f"market cases: {summary.get('market_case_download_count', 0)})")
    return "\n".join(lines)


def _resolve_source_tokens(index: dict, values: list[str]) -> list[str]:
    """Accept stable source IDs and convenient 1-based display numbers."""
    displayed = index["displayed_source_ids"]
    resolved = []
    for value in values:
        token = value.strip()
        if token.isdigit() and 1 <= int(token) <= len(displayed):
            resolved.append(displayed[int(token) - 1])
        else:
            resolved.append(token)
    return resolved


def parse_selection_template(candidate_source_index_ref: str, response_text: str,
                             *, base=None) -> dict:
    """Parse the copyable template. Natural language is mapped by the orchestrator to the same shape."""
    index = _load_index(candidate_source_index_ref, base=base)
    if not isinstance(response_text, str) or not response_text.strip():
        raise ValueError("selection response must be non-empty text")
    fields = {value: [] for value in ACTIONS.values()}
    excluded, extensions = [], []
    status = "approved"
    for raw in response_text.splitlines():
        line = raw.strip()
        if not line or ":" not in line:
            continue
        action, value = line.split(":", 1)
        action = action.strip().upper()
        value = value.strip()
        if action in ACTIONS:
            ids = [item for item in re.split(r"[,;\s]+", value) if item]
            fields[ACTIONS[action]].extend(_resolve_source_tokens(index, ids))
        elif action == "EXCLUDE":
            source_part, _, reason_part = value.partition("|")
            reason = reason_part.removeprefix("reason=").strip() or None
            ids = [item for item in re.split(r"[,;\s]+", source_part.strip()) if item]
            for source_id in _resolve_source_tokens(index, ids):
                excluded.append({"source_id": source_id, "reason": reason})
        elif action == "SEARCH_MORE":
            status = "needs_more_search"
            extension = {"request": value}
            for token in value.split("|"):
                key, separator, item = token.strip().partition("=")
                if separator and key in {"coverage_id", "topic_id", "claim_id", "missing_source_role", "request"}:
                    extension[key] = item.strip()
            extensions.append(extension)
        elif action == "CANCEL":
            status = "cancelled"
    return {
        "schema_version": SELECTION_CONTRACT, "artifact_version": "1.0.0",
        "task_id": index["task_id"],
        "candidate_source_index_ref": candidate_source_index_ref,
        "status": status, **fields, "excluded": excluded,
        "requested_search_extensions": extensions,
        "coverage_exceptions": [], "human_notes": None, "final_confirmation": False,
    }


def _normalize_selection(candidate_source_index_ref: str, selection: object,
                         *, base=None) -> tuple[dict, dict, list[dict]]:
    index = _load_index(candidate_source_index_ref, base=base)
    if not isinstance(selection, dict):
        raise ValueError("selection must be an object")
    normalized = deepcopy(selection)
    normalized.setdefault("schema_version", SELECTION_CONTRACT)
    normalized.setdefault("artifact_version", "1.0.0")
    normalized.setdefault("task_id", index["task_id"])
    normalized.setdefault("candidate_source_index_ref", candidate_source_index_ref)
    normalized.setdefault("status", "approved")
    for field in ACTIONS.values():
        normalized.setdefault(field, [])
    normalized.setdefault("excluded", [])
    normalized.setdefault("requested_search_extensions", [])
    normalized.setdefault("coverage_exceptions", [])
    normalized.setdefault("human_notes", None)
    normalized.setdefault("final_confirmation", False)
    errors = _shape(normalized, SELECTION_CONTRACT)
    if errors:
        raise ValueError("; ".join(errors))
    if normalized["task_id"] != index["task_id"] \
            or normalized["candidate_source_index_ref"] != candidate_source_index_ref:
        raise ValueError("selection task or candidate index binding is invalid")
    known_ids = {item["source_id"] for item in index["sources"]}
    action_ids = []
    for field in ACTIONS.values():
        values = _strings(normalized[field])
        if len(values) != len(normalized[field]):
            raise ValueError(f"{field} must contain non-empty source IDs")
        action_ids.extend(values)
    excluded_ids = []
    for item in normalized["excluded"]:
        if not isinstance(item, dict) or not isinstance(item.get("source_id"), str) \
                or not item["source_id"].strip():
            raise ValueError("excluded entries require source_id")
        excluded_ids.append(item["source_id"])
    assigned = action_ids + excluded_ids
    if len(assigned) != len(set(assigned)):
        raise ValueError("a source is assigned more than one gate action")
    unknown = set(assigned) - known_ids
    if unknown:
        raise ValueError(f"selection contains unknown source IDs {sorted(unknown)}")
    if normalized["status"] == "approved":
        missing = set(index["displayed_source_ids"]) - set(assigned)
        if missing:
            raise ValueError(f"displayed sources require an action: {sorted(missing)}")
        if normalized["requested_search_extensions"]:
            raise ValueError("approved selection cannot request SEARCH_MORE")
    if normalized["status"] == "needs_more_search" \
            and not normalized["requested_search_extensions"]:
        raise ValueError("needs_more_search requires at least one extension request")
    for item in normalized["requested_search_extensions"]:
        if not isinstance(item, dict) or not any(
                isinstance(item.get(field), str) and item[field].strip()
                for field in ("coverage_id", "topic_id", "claim_id", "missing_source_role", "request")):
            raise ValueError("each SEARCH_MORE request needs coverage, topic, claim, role or request")
    exceptions = {}
    for item in normalized["coverage_exceptions"]:
        if not isinstance(item, dict) or item.get("accepted_by_human") is not True \
                or not isinstance(item.get("coverage_unit_id"), str) \
                or not isinstance(item.get("reason"), str) or not item["reason"].strip():
            raise ValueError("coverage exceptions require coverage ID, acceptance and reason")
        exceptions[item["coverage_unit_id"]] = item
    retained = set(_strings(normalized["approved_for_download"])) \
        | set(_strings(normalized["request_library_access"])) \
        | set(_strings(normalized["keep_citation_only"]))
    coverage = []
    for requirement in index["coverage_matrix"]:
        contributors = set(requirement.get("displayed_source_ids", [])) \
            | set(requirement.get("reserve_source_ids", []))
        selected = sorted(contributors & retained)
        count = len(selected)
        minimum = int(requirement.get("minimum_sources", 0))
        status = "covered" if count >= minimum else ("partial" if count else "missing")
        coverage_id = requirement.get("coverage_id")
        if requirement.get("mandatory") and status != "covered" and coverage_id not in exceptions \
                and normalized["status"] == "approved":
            raise ValueError(f"mandatory coverage {coverage_id!r} needs SEARCH_MORE or an accepted exception")
        coverage.append({
            "topic_id": requirement.get("topic_id"), "coverage_id": coverage_id,
            "minimum_sources": minimum, "selected_source_ids": selected, "status": status,
            "exception_accepted": coverage_id in exceptions,
        })
    return normalized, index, coverage


def _confirmation_token(selection: dict) -> str:
    value = deepcopy(selection)
    value["final_confirmation"] = False
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_source_selection(candidate_source_index_ref: str, *, selection: dict | None = None,
                              response_text: str | None = None, base=None) -> dict:
    if (selection is None) == (response_text is None):
        raise ValueError("provide exactly one of selection or response_text")
    if response_text is not None:
        selection = parse_selection_template(candidate_source_index_ref, response_text, base=base)
    normalized, index, coverage = _normalize_selection(
        candidate_source_index_ref, selection, base=base
    )
    normalized["final_confirmation"] = False
    by_id = {item["source_id"]: item for item in index["sources"]}
    download_ids = normalized["approved_for_download"]
    scholarly_download_count = sum(
        by_id[source_id]["record_type"] == "scholarly" for source_id in download_ids
    )
    market_case_download_count = sum(
        by_id[source_id]["record_type"] == "market_case" for source_id in download_ids
    )
    return {
        "ready_for_confirmation": normalized["status"] in {"approved", "cancelled", "needs_more_search"},
        "selection_draft": normalized,
        "confirmation_token": _confirmation_token(normalized),
        "summary": {
            "status": normalized["status"],
            "download": deepcopy(normalized["approved_for_download"]),
            "download_count": len(download_ids),
            "scholarly_download_count": scholarly_download_count,
            "market_case_download_count": market_case_download_count,
            "library": deepcopy(normalized["request_library_access"]),
            "citation": deepcopy(normalized["keep_citation_only"]),
            "reserve": deepcopy(normalized["keep_in_reserve"]),
            "excluded": deepcopy(normalized["excluded"]),
            "search_more": deepcopy(normalized["requested_search_extensions"]),
            "coverage": coverage,
        },
        "instruction": (
            "Pokaż to podsumowanie użytkownikowi i poproś o osobne finalne potwierdzenie."
            if str(index.get("output_language", "")).casefold().startswith("pl")
            or "pol" in str(index.get("output_language", "")).casefold()
            else "Show this summary to the user and ask for a separate final confirmation."
        ),
    }


def _market_stream_ref(index: dict, source_id: str, *, base=None) -> str | None:
    matches = []
    for descriptor in index.get("reviewed_upstreams", []):
        if not isinstance(descriptor, dict) or descriptor.get("stream") != "market_cases":
            continue
        ref = descriptor.get("artifact_ref")
        if not isinstance(ref, str) or not ref.startswith(artifacts.SCHEME):
            continue
        artifact = artifacts.hydrate(ref, base=base)
        if any(isinstance(item, dict) and item.get("source_id") == source_id
               for item in artifact.get("candidates", [])):
            matches.append(ref)
    if len(matches) != 1:
        raise ValueError("approved market case must resolve in exactly one reviewed A11 artifact")
    return matches[0]


def finalize_source_selection(candidate_source_index_ref: str, selection: dict,
                              confirmation_token: str, *, base=None) -> dict:
    try:
        normalized, index, coverage = _normalize_selection(
            candidate_source_index_ref, selection, base=base
        )
        if normalized.get("final_confirmation") is not True:
            return _envelope(
                "needs_input", "A separate final source-selection confirmation is required.",
                [_issue("blocker", "final_confirmation_required",
                        "Confirm the parsed source actions before retrieval.", "final_confirmation")],
            )
        if not isinstance(confirmation_token, str) \
                or confirmation_token != _confirmation_token(normalized):
            raise ValueError("confirmation token does not match the parsed selection summary")
        if normalized["status"] != "approved":
            return _envelope(
                "needs_input", "Source selection does not authorize retrieval.", [],
                metrics={"status": normalized["status"],
                         "search_extension_count": len(normalized["requested_search_extensions"])},
            )
        task = _safe(index["task_id"])
        version = _safe(normalized["artifact_version"])
        selection_ref = artifacts.store(
            f"g02/source-selection/{task}.{version}.json", normalized, base=base
        )
        by_id = {item["source_id"]: item for item in index["sources"]}
        approved_sources = []
        for source_id in normalized["approved_for_download"]:
            item = by_id[source_id]
            market_ref = _market_stream_ref(index, source_id, base=base) \
                if item["record_type"] == "market_case" else None
            approved_sources.append({
                "source_id": source_id, "action": "DOWNLOAD",
                "record_type": item["record_type"], "source_record": deepcopy(item["record"]),
                "related_topics": deepcopy(item["topic_ids"]),
                "related_claims": deepcopy(item["claim_ids"]),
                "source_roles": [role.get("role") for role in item["role_assignments"]
                                 if isinstance(role, dict) and isinstance(role.get("role"), str)],
                "doi_verification": deepcopy(item.get("doi_verification")),
                "market_candidate_sources_ref": market_ref,
            })
        approved_set = {
            "schema_version": APPROVED_SET_CONTRACT,
            "artifact_version": normalized["artifact_version"], "task_id": index["task_id"],
            "source_selection_ref": selection_ref,
            "candidate_source_index_ref": candidate_source_index_ref,
            "approved_sources": approved_sources,
            "library_queue": deepcopy(normalized["request_library_access"]),
            "citation_only": deepcopy(normalized["keep_citation_only"]),
            "reserve": deepcopy(normalized["keep_in_reserve"]),
            "excluded": deepcopy(normalized["excluded"]),
            "coverage_at_approval": coverage,
            "accepted_coverage_exceptions": deepcopy(normalized["coverage_exceptions"]),
            "final_confirmation": True,
        }
        errors = _shape(approved_set, APPROVED_SET_CONTRACT)
        if errors:
            raise ValueError("; ".join(errors))
        approved_ref = artifacts.store(
            f"g02/approved-source-sets/{task}.{version}.json", approved_set, base=base
        )
    except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        return _envelope(
            "failed", "Human source selection failed deterministic finalization.",
            [_issue("blocker", "source_selection_finalize_failed", str(exc), "source_selection")],
        )
    return _envelope(
        "ok", f"Finally authorized {len(approved_sources)} DOWNLOAD source(s).", [],
        produced=[
            {"type": "human_source_selection", "path": selection_ref,
             "schema_version": SELECTION_CONTRACT, "artifact_version": normalized["artifact_version"]},
            {"type": "human_approved_source_set", "path": approved_ref,
             "schema_version": APPROVED_SET_CONTRACT, "artifact_version": normalized["artifact_version"]},
        ],
        metrics={"download_count": len(approved_sources),
                 "scholarly_count": sum(item["record_type"] == "scholarly" for item in approved_sources),
                 "market_case_count": sum(item["record_type"] == "market_case" for item in approved_sources)},
    )
