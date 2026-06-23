"""Reviewed aggregation and human-readable source choice for G02-A05."""
from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from copy import deepcopy

from core import artifacts, contracts

INPUT_CONTRACT = "candidate_index_input@1"
OUTPUT_CONTRACT = "candidate_source_index@1"
PLAN_CONTRACT = "research_plan@1"
DOMAIN_CONTRACT = "domain_candidate_sources@1"
CANDIDATE_CONTRACT = "candidate_sources@1"
REVIEW_CONTRACT = "review_decision@1"
AGENT = "g02-a05-candidate-source-index"
REVIEW_PROFILE = "candidate_index"

STREAM_PROFILE = {
    "domain": ("domain_candidates", "g02-a02-domain", DOMAIN_CONTRACT),
    "canonical": ("canonical_sources", "g02-a03-canonical-sources", CANDIDATE_CONTRACT),
    "recent": ("recent_developments", "g02-a04-recent-developments", CANDIDATE_CONTRACT),
    "market_cases": ("market_cases", "g02-a11-market-cases", CANDIDATE_CONTRACT),
}
ANNOTATION_FIELD = {
    "canonical": "canonical_annotations",
    "recent": "recent_annotations",
    "market_cases": "market_case_annotations",
}
DEFAULT_PROFILE = {
    "display_limit": 18,
    "reserve_limit": 12,
    "per_topic_limit": 8,
    "required_stream_policy": "strict",
    "mandatory_streams": [],
    "ranking_weights": {
        "coverage_contribution": 0.30,
        "role_fit": 0.18,
        "topic_relevance": 0.12,
        "access": 0.12,
        "canonical_signal": 0.10,
        "recency_signal": 0.08,
        "market_case_value": 0.10,
        "redundancy_penalty": 0.10,
    },
}

ACCEPTANCE_CRITERIA = [
    {"criterion_id": f"CI-{i:02d}", "mandatory": True, "description": text}
    for i, text in enumerate([
        "Every displayed record has stable identity, bibliographic provenance and provider APIs.",
        "Deduplication is reproducible and retains merged IDs and ambiguous groups.",
        "Roles and visible ranking components remain separate and traceable to observations.",
        "Every approved coverage requirement is reported as covered, partial or missing.",
        "Every human annotation names its basis and does not imply unseen closed content.",
        "The review document explains all gate actions, gaps and a copyable response format.",
        "Display, reserve and topic limits do not silently remove mandatory coverage.",
        "The index recommends actions but records no human source-selection decision.",
        "Every DOI-bearing scholarly source exposes an auditable Crossref status and identity conflicts remain visible.",
    ], 1)
]
EVIDENCE_REQUIREMENTS = [
    {"requirement_id": "CI-E01", "mandatory": True,
     "description": "Every upstream artifact has an APPROVED decision or one completed REVISE receipt bound to its exact ref and version."},
    {"requirement_id": "CI-E02", "mandatory": True,
     "description": "Content summaries quote or condense only available abstract, metadata or reviewed A11 annotations."},
    {"requirement_id": "CI-E03", "mandatory": True,
     "description": "Coverage, roles, access and ranking retain source and plan identifiers."},
]
PROHIBITED_BEHAVIORS = [
    "Downloading or extracting source content before the Human Source Selection Gate.",
    "Inventing abstracts, contents, metadata, canonicality, maturity or scientific quality.",
    "Treating a market-case source tier as a scientific-quality assessment.",
    "Recording a human approval, exclusion or final selection in CandidateSourceIndex.",
]
SEVERITY_RULES = {
    "minor": "A wording defect that does not change scope, evidence basis or selection meaning.",
    "major": "A correctable ranking, coverage, annotation or display defect.",
    "blocker": "Unreviewed input, fabricated description basis, identity loss or a recorded human decision.",
}


def _issue(severity: str, kind: str, message: str, location: str, *, required=True) -> dict:
    return {
        "severity": severity,
        "type": kind,
        "message": message,
        "location": location,
        "required": required,
    }


def _envelope(status: str, summary: str, issues: list[dict], *, produced=None,
              metrics=None, resume_token=None) -> dict:
    value = {"status": status, "produced": produced or [], "summary": summary, "issues": issues}
    if metrics is not None:
        value["metrics"] = metrics
    if resume_token is not None:
        value["resume_token"] = resume_token
    return value


def _safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()) or "unknown"


def _strings(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str) and item.strip()] \
        if isinstance(value, list) else []


def _unique(values) -> list:
    return list(dict.fromkeys(values))


def _norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def _shape(payload: object, ref: str) -> list[str]:
    try:
        return contracts.validate(payload, ref)["errors"]
    except (KeyError, ValueError) as exc:
        return [str(exc)]


def _validate_profile(value: object) -> dict:
    profile = deepcopy(DEFAULT_PROFILE)
    if value is None:
        return profile
    if not isinstance(value, dict):
        raise ValueError("selection_profile must be an object")
    unknown = set(value) - set(profile)
    if unknown:
        raise ValueError(f"unsupported selection_profile fields {sorted(unknown)}")
    for field in ("display_limit", "reserve_limit", "per_topic_limit"):
        if field in value:
            item = value[field]
            if not isinstance(item, int) or isinstance(item, bool) or item < 1:
                raise ValueError(f"selection_profile.{field} must be a positive integer")
            profile[field] = item
    if "required_stream_policy" in value:
        policy = value["required_stream_policy"]
        if policy not in {"strict", "available_streams"}:
            raise ValueError(
                "selection_profile.required_stream_policy must be strict or available_streams"
            )
        profile["required_stream_policy"] = policy
    if "mandatory_streams" in value:
        mandatory = value["mandatory_streams"]
        if not isinstance(mandatory, list) or any(
                not isinstance(item, str) or item not in STREAM_PROFILE for item in mandatory):
            raise ValueError(
                "selection_profile.mandatory_streams must contain supported stream names"
            )
        profile["mandatory_streams"] = _unique(mandatory)
    if "ranking_weights" in value:
        weights = value["ranking_weights"]
        if not isinstance(weights, dict) or set(weights) != set(profile["ranking_weights"]):
            raise ValueError("ranking_weights must provide exactly the documented components")
        if any(not isinstance(item, (int, float)) or isinstance(item, bool) or item < 0
               for item in weights.values()):
            raise ValueError("ranking_weights must be non-negative numbers")
        profile["ranking_weights"] = deepcopy(weights)
    return profile


def _planned_streams(plan: dict) -> set[tuple[str, str]]:
    planned = {("domain", topic["topic_id"]) for topic in plan["topics"]}
    scope = plan.get("approved_research_scope", {})
    for topic in plan["topics"]:
        topic_id = topic["topic_id"]
        roles = topic.get("source_roles_required", {})
        if scope.get("include_canonical_sources") and any(
                roles.get(role) for role in ("canonical", "survey", "didactic")):
            planned.add(("canonical", topic_id))
        if scope.get("include_recent_developments") and roles.get("current"):
            planned.add(("recent", topic_id))
        if scope.get("include_didactic_examples") and roles.get("didactic"):
            planned.add(("market_cases", topic_id))
    return planned


def _required_streams(plan: dict, profile: dict) -> set[tuple[str, str]]:
    planned = _planned_streams(plan)
    if profile["required_stream_policy"] == "strict":
        return planned
    required = {("domain", topic["topic_id"]) for topic in plan["topics"]}
    mandatory = set(profile.get("mandatory_streams", []))
    required.update(
        (stream, topic["topic_id"])
        for stream in mandatory for topic in plan["topics"]
    )
    return required


def _reviewed_artifact(descriptor: dict, plan: dict, *, base=None) -> tuple[dict, dict]:
    if not isinstance(descriptor, dict):
        raise ValueError("every upstream descriptor must be an object")
    stream = descriptor.get("stream")
    if stream not in STREAM_PROFILE:
        raise ValueError(f"unsupported upstream stream {stream!r}")
    artifact_ref = descriptor.get("artifact_ref")
    decision_ref = descriptor.get("review_decision_ref")
    completion_ref = descriptor.get("revision_completion_ref")
    if not isinstance(artifact_ref, str) or not artifact_ref.startswith(artifacts.SCHEME):
        raise ValueError("upstream artifact_ref must use artifact://")
    if not isinstance(decision_ref, str) or not decision_ref.startswith(artifacts.SCHEME):
        raise ValueError("upstream review_decision_ref must use artifact://")
    artifact = artifacts.hydrate(artifact_ref, base=base)
    decision = artifacts.hydrate(decision_ref, base=base)
    profile, producer, contract = STREAM_PROFILE[stream]
    errors = _shape(artifact, contract)
    errors += _shape(decision, REVIEW_CONTRACT)
    if errors:
        raise ValueError("; ".join(errors))
    if stream != "domain" and artifact.get("stream") != stream:
        raise ValueError("upstream stream differs from stored artifact stream")
    if artifact.get("task_id") != plan["task_id"]:
        raise ValueError("upstream artifact task binding is invalid")
    if artifact.get("research_plan_ref") != plan["_ref"]:
        raise ValueError("upstream artifact does not bind the exact ResearchPlan ref")
    expected = {"task_id": plan["task_id"], "review_profile": profile,
                "producer_agent": producer}
    for field, value in expected.items():
        if decision.get(field) != value:
            raise ValueError(f"review decision {field} does not match the upstream artifact")
    if decision.get("decision") == "APPROVED" and not decision.get("findings"):
        if completion_ref is not None:
            raise ValueError("APPROVED upstream cannot carry a revision completion")
        if decision.get("artifact_ref") != artifact_ref \
                or decision.get("artifact_version") != artifact.get("artifact_version"):
            raise ValueError("approved review decision does not bind the exact upstream artifact")
    elif decision.get("decision") == "REVISE" and decision.get("findings"):
        if not isinstance(completion_ref, str) or not completion_ref.startswith(artifacts.SCHEME):
            raise ValueError("revised upstream requires revision_completion_ref")
        completion = artifacts.hydrate(completion_ref, base=base)
        completion_errors = _shape(completion, "revision_completion@1")
        if completion_errors:
            raise ValueError("; ".join(completion_errors))
        expected_completion = {
            "review_decision_ref": decision_ref,
            "review_id": decision["review_id"],
            "task_id": plan["task_id"],
            "producer_agent": producer,
            "original_artifact_ref": decision["artifact_ref"],
            "original_artifact_version": decision["artifact_version"],
            "revised_artifact_ref": artifact_ref,
            "revised_artifact_version": artifact.get("artifact_version"),
            "finding_ids": [item["finding_id"] for item in decision["findings"]],
            "deterministic_validation_passed": True,
        }
        for field, value in expected_completion.items():
            if completion.get(field) != value:
                raise ValueError(f"revision completion {field} does not match the upstream artifact")
    else:
        raise ValueError("upstream requires APPROVED or one completed REVISE decision")
    frozen = {
        "stream": stream, "topic_id": artifact.get("topic_id"), "artifact_ref": artifact_ref,
        "artifact_version": artifact["artifact_version"], "review_decision_ref": decision_ref,
        "revision_completion_ref": completion_ref, "review_id": decision["review_id"],
    }
    return artifact, frozen


def _project_entries(stream: str, topic_id: str, artifact: dict) -> list[dict]:
    coverage = {item.get("source_id"): _strings(item.get("coverage_unit_ids"))
                for item in artifact.get("coverage_map", []) if isinstance(item, dict)}
    field = ANNOTATION_FIELD.get(stream)
    annotations = {item.get("source_id"): item for item in artifact.get(field, [])
                   if isinstance(item, dict)} if field else {}
    verifications = {item.get("source_id"): item for item in artifact.get("doi_verifications", [])
                     if isinstance(item, dict)}
    result = []
    for record in artifact.get("candidates", []):
        if _shape(record, "source_record@1"):
            raise ValueError(f"invalid source_record {record.get('source_id')!r}")
        if not isinstance(record.get("source_id"), str) or not record["source_id"].strip():
            raise ValueError("source_record has no stable source_id")
        if not isinstance(record.get("bibliographic", {}).get("title"), str) \
                or not record["bibliographic"]["title"].strip():
            raise ValueError(f"source_record {record['source_id']!r} has no title")
        if not _strings(record.get("provenance", {}).get("source_apis")):
            raise ValueError(f"source_record {record['source_id']!r} has no provider provenance")
        annotation = annotations.get(record["source_id"])
        roles = annotation.get("role_assignments", []) if isinstance(annotation, dict) else []
        if stream == "domain":
            roles = [{"role": role, "confidence": "low", "observed_signals": ["provider classification"]}
                     for role in _strings(record.get("classification", {}).get("source_roles"))]
        annotation_coverage = _strings(annotation.get("coverage_unit_ids")) \
            if isinstance(annotation, dict) else []
        cov = _unique([*coverage.get(record["source_id"], []), *annotation_coverage])
        result.append({
            "stream": stream, "topic_id": topic_id, "record": deepcopy(record),
            "coverage_unit_ids": cov, "role_assignments": deepcopy(roles),
            "stream_annotation": deepcopy(annotation),
            "doi_verification": deepcopy(verifications.get(record["source_id"])),
        })
    return result


def prepare_candidate_index(research_plan_ref: str, reviewed_upstreams: list[dict], *,
                            selection_profile: dict | None = None,
                            previous_index_ref: str | None = None,
                            search_extension_refs: list[str] | None = None,
                            artifact_base=None) -> dict:
    try:
        if not isinstance(research_plan_ref, str) or not research_plan_ref.startswith(artifacts.SCHEME):
            raise ValueError("research_plan_ref must use artifact://")
        plan = artifacts.hydrate(research_plan_ref, base=artifact_base)
        errors = _shape(plan, PLAN_CONTRACT)
        if errors:
            raise ValueError("; ".join(errors))
        if not isinstance(reviewed_upstreams, list) or not reviewed_upstreams:
            raise ValueError("reviewed_upstreams must be a non-empty list")
        profile = _validate_profile(selection_profile)
        scoped_plan = deepcopy(plan)
        scoped_plan["_ref"] = research_plan_ref
        frozen, entries, seen = [], [], set()
        for descriptor in reviewed_upstreams:
            artifact, item = _reviewed_artifact(descriptor, scoped_plan, base=artifact_base)
            key = (item["stream"], item["topic_id"])
            if key in seen:
                raise ValueError(f"duplicate reviewed upstream for {key}")
            seen.add(key)
            frozen.append(item)
            entries.extend(_project_entries(item["stream"], item["topic_id"], artifact))
        topic_ids = {topic["topic_id"] for topic in plan["topics"]}
        if any(topic_id not in topic_ids for _, topic_id in seen):
            raise ValueError("upstream topic is outside the approved ResearchPlan")
        required_streams = _required_streams(plan, profile)
        missing_required = required_streams - seen
        missing_optional = (_planned_streams(plan) - required_streams) - seen
        upstream_issues = [
            _issue("major", "missing_reviewed_stream",
                   f"No approved required {stream} artifact is available for {topic_id}.",
                   f"reviewed_upstreams.{stream}.{topic_id}")
            for stream, topic_id in sorted(missing_required)
        ]
        upstream_issues.extend(
            _issue("minor", "missing_optional_reviewed_stream",
                   f"No approved optional {stream} artifact is available for {topic_id}; "
                   "the fast index continues with available streams.",
                   f"reviewed_upstreams.{stream}.{topic_id}", required=False)
            for stream, topic_id in sorted(missing_optional)
        )
        previous_source_id_map = {}
        if previous_index_ref is not None:
            if not isinstance(previous_index_ref, str) or not previous_index_ref.startswith(artifacts.SCHEME):
                raise ValueError("previous_index_ref must use artifact://")
            previous = artifacts.hydrate(previous_index_ref, base=artifact_base)
            if _shape(previous, OUTPUT_CONTRACT) or previous.get("task_id") != plan["task_id"]:
                raise ValueError("previous index is invalid or belongs to another task")
            previous_source_id_map = {
                ":".join(_dedup_key(item["record"])): item["source_id"]
                for item in previous["sources"]
            }
        extensions = search_extension_refs or []
        if not isinstance(extensions, list) or any(
                not isinstance(ref, str) or not ref.startswith(artifacts.SCHEME) for ref in extensions):
            raise ValueError("search_extension_refs must contain artifact:// refs")
        topics = [{key: deepcopy(topic[key]) for key in (
            "topic_id", "name", "purpose", "related_claims", "source_roles_required",
            "coverage_requirements")}
            for topic in plan["topics"]]
        candidate_input = {
            "schema_version": INPUT_CONTRACT, "task_id": plan["task_id"],
            "research_plan_ref": research_plan_ref,
            "research_plan_artifact_version": plan["artifact_version"],
            "output_language": plan["output_language"], "topics": topics,
            "selection_profile": profile, "reviewed_upstreams": frozen,
            "source_entries": entries, "upstream_issues": upstream_issues,
            "previous_index_ref": previous_index_ref,
            "previous_source_id_map": previous_source_id_map,
            "search_extension_refs": deepcopy(extensions),
        }
        errors = _shape(candidate_input, INPUT_CONTRACT)
        if errors:
            raise ValueError("; ".join(errors))
    except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        return {"ready": False, "envelope": _envelope(
            "failed", "Candidate-index input failed deterministic validation.",
            [_issue("blocker", "invalid_candidate_index_basis", str(exc), "candidate_index_input")],
        )}
    return {"ready": True, "candidate_index_input": candidate_input}


def _dedup_key(record: dict) -> tuple[str, str]:
    ids = record.get("identifiers", {})
    for field in ("doi", "arxiv_id", "isbn", "semantic_scholar_id", "openalex_id"):
        value = ids.get(field)
        if isinstance(value, str) and value.strip():
            return field, _norm(value)
    if record.get("record_type", "scholarly") == "market_case":
        url = record.get("access", {}).get("publisher_url")
        if isinstance(url, str) and url.strip():
            return "market_url", url.casefold().rstrip("/")
    bib = record.get("bibliographic", {})
    author = (_strings(bib.get("authors")) or [""])[0]
    return "title_year_author", "|".join((_norm(bib.get("title")), str(bib.get("year")), _norm(author)))


def _entry_quality(entry: dict) -> tuple:
    record = entry["record"]
    content = record.get("content_available", {})
    access = record.get("access", {})
    stream_order = {"canonical": 4, "recent": 3, "market_cases": 2, "domain": 1}
    return (bool(content.get("abstract")), access.get("access_level") != "metadata_only",
            len([v for v in record.get("identifiers", {}).values() if v]),
            stream_order.get(entry["stream"], 0))


def _roles(entries: list[dict]) -> list[dict]:
    result, seen = [], set()
    fallback = {"canonical": "canonical", "recent": "current", "market_cases": "applied_case"}
    for entry in entries:
        assignments = entry["role_assignments"] or ([{"role": fallback[entry["stream"]],
            "confidence": "medium", "observed_signals": [f"reviewed {entry['stream']} stream"]}]
            if entry["stream"] in fallback else [])
        for item in assignments:
            role = item.get("role") if isinstance(item, dict) else None
            if isinstance(role, str) and role not in seen:
                result.append(deepcopy(item)); seen.add(role)
    return result


def _annotation(group: list[dict], topic_map: dict[str, dict], language: str) -> dict:
    primary = max(group, key=_entry_quality)
    record = primary["record"]
    market = next((item.get("stream_annotation") for item in group
                   if item["stream"] == "market_cases" and isinstance(item.get("stream_annotation"), dict)), None)
    pl = language.casefold().startswith("pl") or "pol" in language.casefold()
    topics = _unique(item["topic_id"] for item in group)
    coverage_ids = _unique(cov for item in group for cov in item["coverage_unit_ids"])
    coverage_text = [req.get("description", "") for topic_id in topics
                     for req in topic_map[topic_id].get("coverage_requirements", [])
                     if req.get("coverage_id") in coverage_ids and req.get("description")]
    relevance = ("Powiązanie: " if pl else "Relevance: ") + "; ".join(
        _unique([topic_map[item]["name"] for item in topics] + coverage_text))
    if market:
        fact = str(market.get("market_fact", {}).get("statement", "")).strip()
        mechanism = str(market.get("didactic_interpretation", {}).get("mechanism", "")).strip()
        summary = " ".join(part for part in (fact, mechanism) if part)
        limitations = ["Opis opiera się na zatwierdzonej adnotacji A11 i fragmencie wyniku wyszukiwania; strona nie została jeszcze wyodrębniona."
                       if pl else "Description is based on the approved A11 annotation and search-result snippet; the page has not yet been extracted."]
        return {"content_summary": summary, "description_basis": "market_case_annotation",
                "selection_relevance": relevance, "limitations": limitations,
                "basis_excerpt": fact or None}
    abstract = record.get("content_available", {}).get("abstract")
    if isinstance(abstract, str) and abstract.strip():
        excerpt = re.sub(r"\s+", " ", abstract).strip()[:600]
        limitation = "Opis opiera się na abstrakcie; pełny tekst nie został jeszcze sprawdzony." \
            if pl else "Description is based on the abstract; full text has not yet been reviewed."
        return {"content_summary": excerpt, "description_basis": "abstract",
                "selection_relevance": relevance, "limitations": [limitation],
                "basis_excerpt": excerpt}
    bib = record["bibliographic"]
    parts = [str(bib.get("work_type") or "source"), str(bib.get("venue") or bib.get("publisher") or ""),
             str(bib.get("year") or "")]
    summary = ("Zakres możliwy do oceny wyłącznie z metadanych: " if pl
               else "Scope assessable from metadata only: ") + ", ".join(part for part in parts if part)
    limitation = "Brak abstraktu i treści, opis nie streszcza zawartości publikacji." if pl \
        else "No abstract or content is available, so this description does not summarize the publication."
    return {"content_summary": summary, "description_basis": "metadata",
            "selection_relevance": relevance, "limitations": [limitation], "basis_excerpt": None}


def _components(item: dict, topic_map: dict[str, dict]) -> dict:
    roles = {role.get("role") for role in item["role_assignments"] if isinstance(role, dict)}
    if "applied_case" in roles:
        roles.add("didactic")
    required_roles = {role for topic_id in item["topic_ids"]
                      for role, required in topic_map[topic_id]["source_roles_required"].items() if required}
    access = item["record"].get("access", {})
    level = access.get("access_level")
    access_score = {"full_text": 1.0, "web_page": 0.9, "partial_text": 0.8, "preview": 0.7,
                    "abstract": 0.65, "table_of_contents": 0.5, "metadata_only": 0.25}.get(level, 0.25)
    if access.get("library_access_required"):
        access_score = max(access_score, 0.35)
    signals = item["record"].get("signals", {})
    canonical = 0.9 if "canonical" in item["origin_streams"] else 0.3
    value = signals.get("canonical_score")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        canonical = max(canonical, min(1.0, value if value <= 1 else value / 100))
    recent = 0.9 if "recent" in item["origin_streams"] else 0.3
    market = 0.5
    if item["record_type"] == "market_case":
        annotation = item.get("_market_annotation") or {}
        documented = annotation.get("documentation_status") == "documented"
        passes = annotation.get("materiality_assessment", {}).get("passes_threshold") is True
        market = 1.0 if documented and passes else 0.2
        canonical = 0.2
        recent = 0.7 if annotation.get("regime_context", {}).get("status") == "current_regime" else 0.3
    return {
        "coverage_contribution": min(1.0, len(item["coverage_unit_ids"]) / 2),
        "role_fit": 1.0 if roles & required_roles else (0.6 if roles else 0.2),
        "topic_relevance": 1.0 if item["topic_ids"] else 0.0,
        "access": access_score, "canonical_signal": canonical,
        "recency_signal": recent, "market_case_value": market,
        "redundancy_penalty": min(0.3, 0.1 * len(item["duplicate_source_ids"])),
    }


def _action(item: dict) -> str:
    access = item["record"].get("access", {})
    if access.get("library_access_required"):
        return "LIBRARY"
    if access.get("candidate_pdf_urls") or access.get("access_level") in {"full_text", "partial_text", "web_page"}:
        return "DOWNLOAD"
    if item["human_annotation"]["description_basis"] == "metadata":
        return "CITATION"
    return "RESERVE"


def _roles_support_requirement(source: dict, requirement: dict) -> bool:
    roles = {item.get("role") for item in source["role_assignments"] if isinstance(item, dict)}
    if "applied_case" in roles:
        roles.add("didactic")
    required = set(_strings(requirement.get("source_roles")))
    return not required or bool(roles & required)


def build_candidate_index(candidate_input: dict, *, artifact_version: str = "1.0.0") -> dict:
    errors = _shape(candidate_input, INPUT_CONTRACT)
    if errors:
        raise ValueError("invalid candidate index input: " + "; ".join(errors))
    topic_map = {item["topic_id"]: item for item in candidate_input["topics"]}
    groups = defaultdict(list)
    for entry in candidate_input["source_entries"]:
        groups[_dedup_key(entry["record"])].append(entry)
    sources, merge_log = [], []
    for key, group in groups.items():
        previous_id = candidate_input.get("previous_source_id_map", {}).get(":".join(key))
        primary = next((entry for entry in group
                        if entry["record"]["source_id"] == previous_id), None)
        primary = primary or max(group, key=_entry_quality)
        record = deepcopy(primary["record"])
        source_ids = _unique(item["record"]["source_id"] for item in group)
        roles = _roles(group)
        market_annotation = next((item["stream_annotation"] for item in group
                                  if item["stream"] == "market_cases" and isinstance(item["stream_annotation"], dict)), None)
        recent_annotation = next((item["stream_annotation"] for item in group
                                  if item["stream"] == "recent" and isinstance(item["stream_annotation"], dict)), None)
        claim_ids = []
        for entry in group:
            claim_ids.extend(_strings(entry["record"].get("classification", {}).get("related_claims")))
            for assignment in entry["role_assignments"]:
                if isinstance(assignment, dict):
                    claim_ids.extend(_strings(assignment.get("claim_ids")))
            annotation = entry.get("stream_annotation")
            if isinstance(annotation, dict):
                claim_ids.extend(_strings(annotation.get("didactic_interpretation", {}).get("claim_ids")))
        item = {
            "source_id": record["source_id"],
            "record_type": record.get("record_type", "scholarly"), "record": record,
            "origin_streams": _unique(entry["stream"] for entry in group),
            "topic_ids": _unique(entry["topic_id"] for entry in group),
            "claim_ids": _unique(claim_ids),
            "role_assignments": roles,
            "coverage_unit_ids": _unique(cov for entry in group for cov in entry["coverage_unit_ids"]),
            "duplicate_source_ids": [value for value in source_ids if value != record["source_id"]],
            "doi_verification": deepcopy(next((entry.get("doi_verification") for entry in group
                                                if entry.get("doi_verification")), None)),
            "provenance_records": [{"source_id": entry["record"]["source_id"],
                                    "stream": entry["stream"],
                                    "provenance": deepcopy(entry["record"].get("provenance", {}))}
                                   for entry in group],
            "human_annotation": _annotation(group, topic_map, candidate_input["output_language"]),
            "access_summary": deepcopy(record.get("access", {})),
            "signal_summary": {
                "canonicality": deepcopy(record.get("signals", {}).get("canonical_score")),
                "maturity": deepcopy(recent_annotation.get("maturity_assessment")) if isinstance(recent_annotation, dict) else None,
                "market_source_tier": deepcopy(market_annotation.get("source_assessment", {}).get("source_tier")) if isinstance(market_annotation, dict) else None,
                "scientific_quality": "not_assessed",
            },
            "_market_annotation": market_annotation,
        }
        components = _components(item, topic_map)
        weights = candidate_input["selection_profile"]["ranking_weights"]
        score = sum(components[name] * weight for name, weight in weights.items()
                    if name != "redundancy_penalty") - components["redundancy_penalty"] * weights["redundancy_penalty"]
        item["ranking"] = {"score": round(score, 4), "rank": 0, "components": components,
                           "recommended_action": _action(item), "rationale": [
                               f"covers {len(item['coverage_unit_ids'])} approved requirement(s)",
                               f"description basis: {item['human_annotation']['description_basis']}",
                               f"access level: {record.get('access', {}).get('access_level', 'unknown')}",
                           ]}
        item.pop("_market_annotation", None)
        sources.append(item)
        if len(group) > 1:
            merge_log.append({"dedup_key_type": key[0], "dedup_key_value": key[1],
                              "retained_source_id": item["source_id"],
                              "merged_source_ids": item["duplicate_source_ids"],
                              "input_occurrences": len(group),
                              "rule": "exact stable identifier or conservative title-year-author key"})
    sources.sort(key=lambda item: (-item["ranking"]["score"], item["source_id"]))
    retained_ids = [item["source_id"] for item in sources]
    if len(retained_ids) != len(set(retained_ids)):
        raise ValueError("one source_id resolves to more than one deduplication group")
    for rank, item in enumerate(sources, 1):
        item["ranking"]["rank"] = rank

    title_groups = defaultdict(list)
    for source in sources:
        title_groups[_norm(source["record"]["bibliographic"].get("title"))].append(source)
    ambiguous = [{"normalized_title": title, "source_ids": [item["source_id"] for item in items],
                  "reason": "same normalized title retained because stable identifiers or bibliographic identity conflict"}
                 for title, items in title_groups.items() if title and len(items) > 1]

    profile = candidate_input["selection_profile"]
    displayed, topic_counts = [], Counter()
    required_cov = {req["coverage_id"] for topic in candidate_input["topics"]
                    for req in topic["coverage_requirements"] if req.get("mandatory")}
    requirement_map = {req["coverage_id"]: req for topic in candidate_input["topics"]
                       for req in topic["coverage_requirements"]}
    uncovered = set(required_cov)
    for source in sources:
        contribution = {coverage_id for coverage_id in uncovered & set(source["coverage_unit_ids"])
                        if _roles_support_requirement(source, requirement_map[coverage_id])}
        if contribution and len(displayed) < profile["display_limit"]:
            primary_topic = source["topic_ids"][0] if source["topic_ids"] else "unknown"
            if topic_counts[primary_topic] < profile["per_topic_limit"]:
                displayed.append(source["source_id"]); topic_counts[primary_topic] += 1
                uncovered -= contribution
    for source in sources:
        if len(displayed) >= profile["display_limit"]:
            break
        if source["source_id"] in displayed:
            continue
        primary_topic = source["topic_ids"][0] if source["topic_ids"] else "unknown"
        if topic_counts[primary_topic] < profile["per_topic_limit"]:
            displayed.append(source["source_id"]); topic_counts[primary_topic] += 1
    reserve = [item["source_id"] for item in sources if item["source_id"] not in displayed][
              :profile["reserve_limit"]]
    by_id = {item["source_id"]: item for item in sources}
    matrix = []
    for topic in candidate_input["topics"]:
        stream_warnings = [
            deepcopy(issue) for issue in candidate_input["upstream_issues"]
            if issue.get("location", "").endswith(f".{topic['topic_id']}")
        ]
        for req in topic["coverage_requirements"]:
            display_hits = [sid for sid in displayed if req["coverage_id"] in by_id[sid]["coverage_unit_ids"]
                            and _roles_support_requirement(by_id[sid], req)]
            reserve_hits = [sid for sid in reserve if req["coverage_id"] in by_id[sid]["coverage_unit_ids"]
                            and _roles_support_requirement(by_id[sid], req)]
            count = len(display_hits)
            status = "covered" if count >= req["minimum_sources"] else ("partial" if count else "missing")
            matrix.append({"topic_id": topic["topic_id"], "coverage_id": req["coverage_id"],
                           "description": req["description"], "required_roles": req["source_roles"],
                           "minimum_sources": req["minimum_sources"], "mandatory": req["mandatory"],
                           "status": status, "displayed_source_ids": display_hits,
                           "reserve_source_ids": reserve_hits,
                           "stream_warnings": deepcopy(stream_warnings)})
    streams = Counter(entry["stream"] for entry in candidate_input["source_entries"])
    return {
        "schema_version": OUTPUT_CONTRACT, "artifact_version": artifact_version,
        "task_id": candidate_input["task_id"], "research_plan_ref": candidate_input["research_plan_ref"],
        "research_plan_artifact_version": candidate_input["research_plan_artifact_version"],
        "output_language": candidate_input["output_language"],
        "reviewed_upstreams": deepcopy(candidate_input["reviewed_upstreams"]),
        "selection_profile": deepcopy(profile), "sources": sources,
        "displayed_source_ids": displayed, "reserve_source_ids": reserve,
        "merge_log": merge_log, "ambiguous_duplicate_groups": ambiguous, "coverage_matrix": matrix,
        "search_summary": {"input_record_count": len(candidate_input["source_entries"]),
                           "deduplicated_source_count": len(sources), "stream_record_counts": dict(streams),
                           "upstream_issues": deepcopy(candidate_input["upstream_issues"]),
                           "search_extension_refs": deepcopy(candidate_input.get("search_extension_refs", []))},
        "annotation_policy": {
            "allowed_bases": ["abstract", "metadata", "market_case_annotation"],
            "full_text_reviewed": False, "scientific_quality_assessed": False,
            "market_source_tier_is_scientific_quality": False,
        },
        "human_review_document_ref": "artifact://pending/candidate_source_review.md",
        "review_profile_ref": REVIEW_PROFILE,
    }


def render_review_document(index: dict, output_language: str, *, index_ref: str | None = None) -> str:
    pl = output_language.casefold().startswith("pl") or "pol" in output_language.casefold()
    by_id = {item["source_id"]: item for item in index["sources"]}
    lines = ["# Wybór źródeł do dalszej pracy" if pl else "# Source selection for further work", ""]
    if pl:
        lines += [
            "Poniższa lista opisuje przybliżoną zawartość źródeł na podstawie jawnie wskazanych danych. Pełne teksty nie były jeszcze pobierane ani oceniane.", "",
            "## Jak odpowiedzieć", "",
            "Dla każdego źródła wybierz: `DOWNLOAD`, `LIBRARY`, `CITATION`, `RESERVE` albo `EXCLUDE`. Użyj `SEARCH_MORE`, jeżeli luka wymaga rozszerzenia wyszukiwania.", "",
        ]
    else:
        lines += [
            "This list describes approximate source contents using the explicitly named basis. Full texts have not yet been downloaded or assessed.", "",
            "## How to respond", "",
            "Choose `DOWNLOAD`, `LIBRARY`, `CITATION`, `RESERVE` or `EXCLUDE` for each source. Use `SEARCH_MORE` when a gap requires another search pass.", "",
        ]
    if index_ref:
        lines += [(f"Powiązany indeks maszynowy: `{index_ref}`" if pl
                   else f"Linked machine-readable index: `{index_ref}`"), ""]
    lines += ["## Pokrycie planu" if pl else "## Plan coverage", ""]
    for item in index["coverage_matrix"]:
        lines.append(f"- `{item['status'].upper()}` {item['description']} ({len(item['displayed_source_ids'])}/{item['minimum_sources']})")
    lines += ["", "## Proponowane źródła" if pl else "## Proposed sources", ""]
    for sid in index["displayed_source_ids"]:
        item = by_id[sid]; bib = item["record"]["bibliographic"]; note = item["human_annotation"]
        authors = ", ".join(bib.get("authors", [])) or ("autor nieznany" if pl else "unknown author")
        verification = item.get("doi_verification")
        crossref_status = (
            f"{verification.get('registry_status')} / {verification.get('match_status')}"
            if isinstance(verification, dict) else ("nie dotyczy" if pl else "not applicable")
        )
        lines += [f"### {item['ranking']['rank']}. {bib['title']}", "",
                  f"- **ID:** `{sid}`", f"- **Cytowanie skrócone:** {authors} ({bib.get('year') or 'b.d.'}). {bib.get('venue') or bib.get('publisher') or ''}",
                  f"- **Typ:** {item['record_type']}; **role:** {', '.join(r.get('role', '') for r in item['role_assignments']) or 'unclassified'}",
                  f"- **Co zawiera według dostępnych danych:** {note['content_summary']}",
                  f"- **Dlaczego może pasować:** {note['selection_relevance']}",
                  f"- **Podstawa opisu:** `{note['description_basis']}`",
                  f"- **Crossref DOI:** `{crossref_status}`",
                  f"- **Dostęp:** `{item['access_summary'].get('access_level', 'unknown')}`; rekomendacja `{item['ranking']['recommended_action']}`",
                  f"- **Ograniczenia:** {' '.join(note['limitations'])}", ""]
    lines += ["## Rezerwa" if pl else "## Reserve", ""]
    for sid in index["reserve_source_ids"]:
        item = by_id[sid]
        lines.append(f"- `{sid}` {item['record']['bibliographic']['title']} ({item['human_annotation']['description_basis']})")
    gaps = [item for item in index["coverage_matrix"] if item["status"] != "covered"]
    lines += ["", "## Luki i ograniczenia" if pl else "## Gaps and limitations", ""]
    if gaps:
        for item in gaps:
            lines.append(f"- `{item['status'].upper()}` {item['description']}")
    else:
        lines.append("- Brak luk według kandydackiej macierzy pokrycia." if pl else "- No gaps in the candidate-stage coverage matrix.")
    upstream_issues = index.get("search_summary", {}).get("upstream_issues", [])
    if upstream_issues:
        lines += ["", "### Brakujące strumienie" if pl else "### Missing streams", ""]
        for issue in upstream_issues:
            marker = "REQUIRED" if issue.get("required", True) else "OPTIONAL"
            lines.append(f"- `{marker}` {issue.get('message', '')}")
    lines += ["", "## Szablon decyzji" if pl else "## Decision template", "", "```text",
              "DOWNLOAD: SRC_...", "LIBRARY: SRC_...", "CITATION: SRC_...", "RESERVE: SRC_...",
              "EXCLUDE: SRC_... | reason=...", "SEARCH_MORE: coverage_id=... | request=...",
              "FINAL_CONFIRMATION: yes", "```", ""]
    return "\n".join(lines)


def finalize_candidate_index(candidate_input: dict, *, artifact_version: str = "1.0.0",
                             base=None) -> dict:
    try:
        index = build_candidate_index(candidate_input, artifact_version=artifact_version)
        task = _safe(index["task_id"]); version = _safe(artifact_version)
        md_rel = f"g02/candidate-index/{task}.{version}.candidate_source_review.md"
        json_rel = f"g02/candidate-index/{task}.{version}.json"
        index["human_review_document_ref"] = artifacts.ref_for(md_rel)
        errors = _shape(index, OUTPUT_CONTRACT)
        if errors:
            raise ValueError("; ".join(errors))
        document = render_review_document(
            index, candidate_input["output_language"], index_ref=artifacts.ref_for(json_rel)
        )
        document_ref = artifacts.store_text(md_rel, document, base=base)
        index_ref = artifacts.store(json_rel, index, base=base)
    except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
        return _envelope("failed", "CandidateSourceIndex failed deterministic finalization.",
                         [_issue("blocker", "candidate_index_finalize_failed", str(exc), "candidate_index")])
    incomplete = any(item["status"] != "covered" and item["mandatory"] for item in index["coverage_matrix"])
    incomplete = incomplete or any(
        issue.get("required", True) for issue in candidate_input["upstream_issues"]
    )
    status = "degraded" if incomplete else "ok"
    descriptors = [
        {"type": "candidate_source_index", "path": index_ref, "schema_version": OUTPUT_CONTRACT,
         "artifact_version": artifact_version},
        {"type": "candidate_source_review", "path": document_ref, "schema_version": "candidate_source_review.md",
         "artifact_version": artifact_version},
    ]
    return _envelope(status, f"Stored {len(index['sources'])} deduplicated candidate sources and the human review document.",
                     deepcopy(candidate_input["upstream_issues"]), produced=descriptors,
                     metrics={"source_count": len(index["sources"]),
                              "displayed_count": len(index["displayed_source_ids"]),
                              "reserve_count": len(index["reserve_source_ids"]),
                              "coverage_gap_count": sum(item["status"] != "covered" for item in index["coverage_matrix"])},
                     resume_token=index_ref if status == "degraded" else None)


def build_candidate_index_review_task(candidate_input: dict, artifact_descriptor: dict, *,
                                      review_id: str, attempt: int = 1,
                                      previous_decision_ref: str | None = None,
                                      producer_revision_response: dict | None = None,
                                      base=None) -> dict:
    if _shape(candidate_input, INPUT_CONTRACT):
        raise ValueError("candidate input is invalid")
    if not isinstance(artifact_descriptor, dict):
        raise ValueError("artifact descriptor must be an object")
    ref = artifact_descriptor.get("path") or artifact_descriptor.get("ref")
    if artifact_descriptor.get("type") != "candidate_source_index" \
            or artifact_descriptor.get("schema_version") != OUTPUT_CONTRACT \
            or not isinstance(ref, str) or not ref.startswith(artifacts.SCHEME):
        raise ValueError("artifact descriptor must identify candidate_source_index@1")
    index = artifacts.hydrate(ref, base=base)
    if _shape(index, OUTPUT_CONTRACT) or index.get("task_id") != candidate_input["task_id"]:
        raise ValueError("stored candidate index is invalid or belongs to another task")
    if index.get("artifact_version") != artifact_descriptor.get("artifact_version"):
        raise ValueError("artifact descriptor version differs from stored index")
    document_ref = index.get("human_review_document_ref")
    if not isinstance(document_ref, str) or not document_ref.startswith(artifacts.SCHEME):
        raise ValueError("candidate index has no review-document artifact ref")
    try:
        document = artifacts.resolve_path(document_ref, base=base).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"candidate review document cannot be read: {exc}") from exc
    if not all(token in document for token in ("DOWNLOAD", "LIBRARY", "CITATION", "RESERVE",
                                               "EXCLUDE", "SEARCH_MORE", "FINAL_CONFIRMATION")):
        raise ValueError("candidate review document does not contain the complete gate template")
    task = {
        "schema_version": "review_task@1", "review_id": review_id,
        "task_id": candidate_input["task_id"],
        "logical_review_node": "g02-a05-candidate-source-index-review", "producer_agent": AGENT,
        "attempt": attempt, "review_profile": REVIEW_PROFILE,
        "original_task": {"objective": "Build an auditable, content-described source list for the human gate.",
                          "input_contract": INPUT_CONTRACT, "output_contract": OUTPUT_CONTRACT},
        "producer_input": deepcopy(candidate_input),
        "artifact": {"type": "candidate_source_index", "ref": ref, "schema_version": OUTPUT_CONTRACT,
                     "artifact_version": index["artifact_version"]},
        "expected_output_contract": OUTPUT_CONTRACT,
        "acceptance_criteria": deepcopy(ACCEPTANCE_CRITERIA),
        "evidence_requirements": deepcopy(EVIDENCE_REQUIREMENTS),
        "prohibited_behaviors": deepcopy(PROHIBITED_BEHAVIORS),
        "severity_rules": deepcopy(SEVERITY_RULES),
        "previous_decision_ref": previous_decision_ref,
        "producer_revision_response": producer_revision_response,
    }
    from g02 import review
    checked = review.validate_review_task(task)
    if not checked["ok"]:
        raise ValueError("invalid candidate-index review task: " + "; ".join(
            item["message"] for item in checked["issues"]))
    return task
