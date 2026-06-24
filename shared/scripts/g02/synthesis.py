"""Fast G02-A09 synthesis without A08 claim assessment."""
from __future__ import annotations

from copy import deepcopy
try:
    from datetime import UTC, datetime
except ImportError:  # Python < 3.11
    from datetime import datetime, timezone
    UTC = timezone.utc
import hashlib
import json
import re

from core import artifacts, contracts, handoff


AGENT = "g02-a09-synthesizer"
OUTPUT_CONTRACT = "research_state@1"
BUNDLE_CONTRACT = "user_approved_research_bundle@1"
PLAN_CONTRACT = "research_plan@1"
INDEX_CONTRACT = "candidate_source_index@1"
APPROVED_SET_CONTRACT = "human_approved_source_set@1"
CORPUS_CONTRACT = "retrieved_corpus@1"
PAPER_REVIEW_CONTRACT = "paper_review@1"
REVIEW_DECISION_CONTRACT = "review_decision@1"
REVISION_COMPLETION_CONTRACT = "revision_completion@1"
REVIEW_PROFILE = "research_synthesis"
DEFAULT_ARTIFACT_VERSION = "1.0.0"
SYNTHESIS_MODE_FAST = "evidence_without_claim_assessment"
ALLOWED_FINDING_STATUS = {
    "supported_by_reviewed_source",
    "needs_human_check",
    "insufficient_evidence",
    "context_only",
    "market_case_signal",
}
FULL_TEXT_KEYS = {
    "full_text", "pdf", "pdf_bytes", "pdf_text", "document_text", "raw_page_text",
    "paper_review_full", "retrieved_corpus", "paper_reviews",
}
MAX_RESEARCH_STATE_BYTES = 90000
MAX_HANDOFF_STRING = 1800
ALLOWED_UNRESOLVED_HANDLING = {
    "keep_as_unresolved_items",
    "exclude_from_graph03_handoff",
    "return_for_research",
}

ACCEPTANCE_CRITERIA = [
    {"criterion_id": f"SY-{index:02d}", "mandatory": True, "description": description}
    for index, description in enumerate([
        "The synthesis is bound to one ResearchPlan, CandidateSourceIndex, HumanApprovedSourceSet, RetrievedCorpus and reviewed A07 set.",
        "Fast mode states that A08 Claim Verification was skipped and avoids final truth-verification labels.",
        "Every finding has an allowed conservative status and evidence refs or source refs.",
        "Required updates, optional improvements, unresolved items and market-case signals remain distinct.",
        "The evidence map and SolutionInputCandidate are compact and contain refs, not full papers or full reviews.",
        "The human validation packet exposes limitations, unresolved items, confidence and decisions required.",
        "No Graph03 bundle is emitted before the Human Research Gate approval.",
    ], 1)
]
EVIDENCE_REQUIREMENTS = [
    {"requirement_id": "SY-E01", "mandatory": True,
     "description": "Every material finding links to A07 evidence cards and source refs."},
    {"requirement_id": "SY-E02", "mandatory": True,
     "description": "The absence of A08 ClaimAssessment is preserved as a fast-mode limitation."},
    {"requirement_id": "SY-E03", "mandatory": True,
     "description": "The Graph03 candidate excludes full PDFs, full extracted text and verbose PaperReview payloads."},
]
PROHIBITED_BEHAVIORS = [
    "Using labels such as fully verified or claim verified when A08 was skipped.",
    "Introducing new evidence, new web search or new claim assessment.",
    "Passing full PDFs, complete document text, full retrieved corpus or verbose PaperReview artifacts downstream.",
    "Finalizing the user-approved bundle before the Human Research Gate approval.",
]
SEVERITY_RULES = {
    "minor": "A wording or ordering issue that leaves refs, status labels and A08 limitation intact.",
    "major": "A correctable gap in evidence mapping, confidence, unresolved items or human packet clarity.",
    "blocker": "Identity mismatch, missing evidence refs, hidden A08 skip, full-text forwarding or premature handoff.",
}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _safe(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip()) or "unknown"


def _issue(severity: str, issue_type: str, message: str, location: str) -> dict:
    return {"severity": severity, "type": issue_type, "message": message, "location": location}


def _envelope(status: str, summary: str, issues: list[dict], *, produced=None,
              metrics=None, resume_token=None) -> dict:
    result = {"status": status, "produced": produced or [], "summary": summary, "issues": [
        {"severity": item["severity"], "type": item["type"],
         "message": f"{item['message']} (location: {item['location']})"}
        for item in issues
    ]}
    if metrics is not None:
        result["metrics"] = metrics
    if resume_token is not None:
        result["resume_token"] = resume_token
    return result


def _shape(payload: object, contract_ref: str) -> list[str]:
    try:
        return contracts.validate(payload, contract_ref)["errors"]
    except (KeyError, ValueError) as exc:
        return [str(exc)]


def _strings(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str) and item.strip()] \
        if isinstance(value, list) else []


def _unique(values) -> list[str]:
    return list(dict.fromkeys(item for item in values if isinstance(item, str) and item.strip()))


def _truncate(value: object, limit: int = 700) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit].rstrip()


def _hydrate(ref: str, contract: str, *, base=None) -> dict:
    if not isinstance(ref, str) or not ref.startswith(artifacts.SCHEME):
        raise ValueError(f"{contract} ref must use artifact://")
    value = artifacts.hydrate(ref, base=base)
    errors = _shape(value, contract)
    if errors:
        raise ValueError(f"invalid {contract}: " + "; ".join(errors))
    return value


def _review_identity(ref: str, review: dict) -> dict:
    cards = review.get("evidence_cards") if isinstance(review.get("evidence_cards"), list) else []
    compact_cards = []
    for index, card in enumerate(cards[:10]):
        if not isinstance(card, dict):
            continue
        compact_cards.append({
            "evidence_id": card.get("evidence_id") or card.get("card_id")
            or f"{review['source_id']}::E{index + 1:02d}",
            "source_id": review.get("source_id"),
            "topic_ids": _strings(card.get("topic_ids")) or _strings(review.get("topic_ids")),
            "claim_ids": _strings(card.get("claim_ids")) or _strings(review.get("claim_ids")),
            "relation": card.get("relation") or card.get("status") or "contextualizes",
            "summary": _truncate(card.get("summary") or card.get("finding") or review.get("findings")),
            "locations": deepcopy(card.get("locations", [])),
            "confidence": card.get("confidence") or review.get("confidence"),
            "evidence_ref": f"{ref}#/evidence_cards/{index}",
        })
    return {
        "paper_review_ref": ref,
        "artifact_version": review.get("artifact_version"),
        "source_id": review.get("source_id"),
        "source_kind": review.get("source_kind"),
        "reviewed_document_ref": review.get("reviewed_document_ref"),
        "topic_ids": _strings(review.get("topic_ids")),
        "claim_ids": _strings(review.get("claim_ids")),
        "review_status": review.get("review_status"),
        "confidence": review.get("confidence"),
        "contribution": _truncate(review.get("contribution")),
        "method_or_source_basis": _truncate(review.get("method_or_source_basis") or review.get("method")),
        "limitations": _truncate(review.get("limitations")),
        "evidence_cards": compact_cards,
        "evidence_access_level": review.get("evidence_access_level"),
        "conflict_flags": deepcopy(review.get("conflict_flags", [])),
        "prompt_injection_flags": deepcopy(review.get("prompt_injection_flags", [])),
    }


def _reviewed_paper_review(descriptor: dict, task_id: str, *, base=None) -> tuple[str, dict, dict]:
    """Validate the exact A10 decision chain for one A07 artifact."""
    if not isinstance(descriptor, dict):
        raise ValueError("every reviewed A07 descriptor must be an object")
    review_ref = descriptor.get("paper_review_ref") or descriptor.get("artifact_ref")
    decision_ref = descriptor.get("review_decision_ref")
    completion_ref = descriptor.get("revision_completion_ref")
    if not isinstance(review_ref, str) or not review_ref.startswith(artifacts.SCHEME):
        raise ValueError("reviewed A07 paper_review_ref must use artifact://")
    if not isinstance(decision_ref, str) or not decision_ref.startswith(artifacts.SCHEME):
        raise ValueError("reviewed A07 review_decision_ref must use artifact://")
    review = _hydrate(review_ref, PAPER_REVIEW_CONTRACT, base=base)
    decision = _hydrate(decision_ref, REVIEW_DECISION_CONTRACT, base=base)
    expected = {
        "task_id": task_id,
        "logical_review_node": "g02-a07-paper-review-review",
        "producer_agent": "g02-a07-paper-review",
        "review_profile": "paper_evidence",
    }
    for field, value in expected.items():
        if review.get("task_id") != task_id or decision.get(field) != value:
            raise ValueError(f"reviewed A07 {field} binding is invalid")
    if decision.get("decision") == "APPROVED" and not decision.get("findings"):
        if completion_ref is not None:
            raise ValueError("APPROVED A07 artifact cannot carry revision completion")
        if decision.get("artifact_ref") != review_ref \
                or decision.get("artifact_version") != review.get("artifact_version"):
            raise ValueError("A07 approval does not bind the exact paper review")
    elif decision.get("decision") == "REVISE" and decision.get("findings"):
        if not isinstance(completion_ref, str) or not completion_ref.startswith(artifacts.SCHEME):
            raise ValueError("revised A07 artifact requires revision_completion_ref")
        completion = _hydrate(completion_ref, REVISION_COMPLETION_CONTRACT, base=base)
        expected_completion = {
            "review_decision_ref": decision_ref,
            "review_id": decision["review_id"],
            "task_id": task_id,
            "producer_agent": "g02-a07-paper-review",
            "original_artifact_ref": decision["artifact_ref"],
            "original_artifact_version": decision["artifact_version"],
            "revised_artifact_ref": review_ref,
            "revised_artifact_version": review.get("artifact_version"),
            "finding_ids": [item["finding_id"] for item in decision["findings"]],
            "deterministic_validation_passed": True,
        }
        for field, value in expected_completion.items():
            if completion.get(field) != value:
                raise ValueError(f"A07 revision completion {field} is invalid")
    else:
        raise ValueError("A07 input requires APPROVED or one completed REVISE decision")
    frozen = {
        "paper_review_ref": review_ref,
        "artifact_version": review.get("artifact_version"),
        "review_decision_ref": decision_ref,
        "revision_completion_ref": completion_ref,
        "review_id": decision.get("review_id"),
    }
    return review_ref, review, frozen


def _revision_snapshot(state: dict | None, revision_items: list[dict] | None) -> dict | None:
    if not isinstance(state, dict):
        return None
    finding_ids = {
        item.get("finding_id") for item in revision_items or []
        if isinstance(item, dict) and isinstance(item.get("finding_id"), str)
    }

    def selected(values: object) -> list[dict]:
        items = [deepcopy(item) for item in values if isinstance(item, dict)] \
            if isinstance(values, list) else []
        if not finding_ids:
            return items
        return [item for item in items if item.get("finding_id") in finding_ids]

    return {
        "artifact_version": state.get("artifact_version"),
        "findings": selected(state.get("findings")),
        "required_updates": selected(state.get("required_updates")),
        "optional_improvements": selected(state.get("optional_improvements")),
        "unresolved": selected(state.get("unresolved")),
        "limitations": deepcopy(state.get("limitations", [])),
        "confidence": state.get("confidence"),
    }


def _make_evidence_map(paper_reviews: list[dict], approved: dict, corpus: dict) -> dict:
    sources = {
        item.get("source_id"): item
        for item in approved.get("approved_sources", [])
        if isinstance(item, dict) and isinstance(item.get("source_id"), str)
    }
    claims: dict[str, dict] = {}
    source_cards = []
    for review in paper_reviews:
        source_id = review["source_id"]
        source = sources.get(source_id, {})
        all_claims = review.get("claim_ids") or ["UNASSIGNED_CLAIM_SCOPE"]
        for claim_id in all_claims:
            entry = claims.setdefault(claim_id, {
                "claim_id": claim_id,
                "evidence_refs": [],
                "source_ids": [],
                "limitations": [],
                "_statuses": [],
            })
            entry["source_ids"].append(source_id)
            for card in review.get("evidence_cards", []):
                if claim_id in (card.get("claim_ids") or all_claims):
                    entry["evidence_refs"].append(card["evidence_ref"])
            if review.get("conflict_flags") or review.get("review_status") == "partial":
                entry["_statuses"].append("needs_human_check")
            elif review.get("review_status") == "insufficient" or not review.get("evidence_cards"):
                entry["_statuses"].append("insufficient_evidence")
            elif review.get("source_kind") == "market_case":
                entry["_statuses"].append("market_case_signal")
            else:
                entry["_statuses"].append("supported_by_reviewed_source")
            entry["limitations"].append(review.get("limitations"))
        source_cards.append({
            "source_id": source_id,
            "record_type": source.get("record_type") or review.get("source_kind"),
            "title": source.get("source_record", {}).get("bibliographic", {}).get("title"),
            "paper_review_ref": review["paper_review_ref"],
            "reviewed_document_ref": review.get("reviewed_document_ref"),
            "evidence_card_count": len(review.get("evidence_cards", [])),
            "confidence": review.get("confidence"),
        })
    for entry in claims.values():
        entry["source_ids"] = _unique(entry["source_ids"])
        entry["evidence_refs"] = _unique(entry["evidence_refs"])
        entry["limitations"] = [_truncate(item, 300) for item in _unique(entry["limitations"])]
        statuses = set(entry.pop("_statuses", []))
        if "needs_human_check" in statuses or len(statuses) > 1:
            entry["status"] = "needs_human_check"
        elif "supported_by_reviewed_source" in statuses:
            entry["status"] = "supported_by_reviewed_source"
        elif "market_case_signal" in statuses:
            entry["status"] = "market_case_signal"
        else:
            entry["status"] = "insufficient_evidence"
    return {
        "schema_version": "evidence_map@1",
        "task_id": corpus["task_id"],
        "synthesis_mode": SYNTHESIS_MODE_FAST,
        "claim_assessment_performed": False,
        "claim_assessment_status": "skipped_fast_profile",
        "claims": sorted(claims.values(), key=lambda item: item["claim_id"]),
        "sources": sorted(source_cards, key=lambda item: item["source_id"]),
    }


def prepare_synthesis(research_plan_ref: str, candidate_source_index_ref: str,
                      approved_source_set_ref: str, retrieved_corpus_ref: str,
                      paper_review_refs: list[str] | None, *, profile: dict | None = None,
                      reviewed_paper_reviews: list[dict] | None = None,
                      previous_state_ref: str | None = None,
                      revision_items: list[dict] | None = None,
                      base=None) -> dict:
    try:
        plan = _hydrate(research_plan_ref, PLAN_CONTRACT, base=base)
        index = _hydrate(candidate_source_index_ref, INDEX_CONTRACT, base=base)
        approved = _hydrate(approved_source_set_ref, APPROVED_SET_CONTRACT, base=base)
        corpus = _hydrate(retrieved_corpus_ref, CORPUS_CONTRACT, base=base)
        if len({plan["task_id"], index["task_id"], approved["task_id"], corpus["task_id"]}) != 1:
            raise ValueError("A09 upstream artifacts do not share one task_id")
        if index.get("research_plan_ref") != research_plan_ref \
                or approved.get("candidate_source_index_ref") != candidate_source_index_ref \
                or corpus.get("approved_source_set_ref") != approved_source_set_ref:
            raise ValueError("A09 upstream refs are not transitively bound")
        active_profile = profile if isinstance(profile, dict) else {}
        if paper_review_refs is None:
            paper_review_refs = []
        if not isinstance(paper_review_refs, list) \
                or any(not isinstance(ref, str) for ref in paper_review_refs):
            raise ValueError("paper_review_refs must be a list of artifact refs")
        review_provenance = []
        reviewed_values: dict[str, dict] = {}
        if reviewed_paper_reviews is not None:
            if not isinstance(reviewed_paper_reviews, list):
                raise ValueError("reviewed_paper_reviews must be a list")
            reviewed_refs = []
            for descriptor in reviewed_paper_reviews:
                ref, review, frozen = _reviewed_paper_review(
                    descriptor, plan["task_id"], base=base
                )
                reviewed_refs.append(ref)
                reviewed_values[ref] = review
                review_provenance.append(frozen)
            if paper_review_refs and paper_review_refs != reviewed_refs:
                raise ValueError("paper_review_refs differ from reviewed A07 descriptors")
            paper_review_refs = reviewed_refs
        elif active_profile.get("require_reviewed_a07_provenance"):
            raise ValueError("fast runtime requires reviewed_paper_reviews provenance")
        paper_reviews = []
        seen_sources = set()
        for ref in paper_review_refs:
            review = reviewed_values.get(ref) or _hydrate(ref, PAPER_REVIEW_CONTRACT, base=base)
            if review.get("task_id") != plan["task_id"]:
                raise ValueError("paper review belongs to another task")
            if review.get("source_id") in seen_sources:
                raise ValueError("duplicate paper review for one source")
            seen_sources.add(review.get("source_id"))
            paper_reviews.append(_review_identity(ref, review))
        accepted_ids = {
            item.get("source_id") for item in [
                *corpus.get("documents", []),
                *corpus.get("market_cases", []),
            ] if isinstance(item, dict) and item.get("status") in {"accepted", "duplicate"}
        }
        unexpected_reviews = sorted(seen_sources - accepted_ids)
        if unexpected_reviews:
            raise ValueError(f"paper reviews are outside accepted corpus: {unexpected_reviews}")
        missing_reviews = sorted(accepted_ids - seen_sources)
        if active_profile.get("require_reviewed_a07_provenance") and missing_reviews:
            raise ValueError(
                f"accepted corpus sources are missing reviewed A07 artifacts: {missing_reviews}"
            )
        evidence_map = _make_evidence_map(paper_reviews, approved, corpus)
        previous_state = None
        if previous_state_ref is not None:
            previous_state = _hydrate(previous_state_ref, OUTPUT_CONTRACT, base=base)
            if previous_state.get("task_id") != plan["task_id"]:
                raise ValueError("previous ResearchState belongs to another task")
            expected_previous_refs = {
                "research_plan_ref": research_plan_ref,
                "candidate_source_index_ref": candidate_source_index_ref,
                "approved_source_set_ref": approved_source_set_ref,
                "retrieved_corpus_ref": retrieved_corpus_ref,
                "paper_review_refs": paper_review_refs,
            }
            for field, value in expected_previous_refs.items():
                if previous_state.get("upstream_refs", {}).get(field) != value:
                    raise ValueError(f"previous ResearchState {field} differs from current input")
        if revision_items is not None and (
                not isinstance(revision_items, list)
                or any(not isinstance(item, dict) for item in revision_items)):
            raise ValueError("revision_items must be a list of findings")
        if revision_items and previous_state is None:
            raise ValueError("revision_items require previous_state_ref")
        for item in revision_items or []:
            for field in ("finding_id", "location", "required_correction"):
                if not isinstance(item.get(field), str) or not item[field].strip():
                    raise ValueError(f"revision item {field} must be a non-empty string")
        retrieval_gaps = [
            {
                "source_id": item.get("source_id"),
                "reason": item.get("reason") or "retrieval_unavailable",
                "status": field,
                "source_ref": f"{retrieved_corpus_ref}#/{field}/{index}",
            }
            for field in ("unavailable", "failed")
            for index, item in enumerate(corpus.get(field, []))
            if isinstance(item, dict) and isinstance(item.get("source_id"), str)
        ]
        synthesis_input = {
            "schema_version": "research_synthesis_input@1",
            "task_id": plan["task_id"],
            "research_plan_ref": research_plan_ref,
            "research_plan_artifact_version": plan["artifact_version"],
            "candidate_source_index_ref": candidate_source_index_ref,
            "candidate_source_index_artifact_version": index["artifact_version"],
            "approved_source_set_ref": approved_source_set_ref,
            "approved_source_set_artifact_version": approved["artifact_version"],
            "retrieved_corpus_ref": retrieved_corpus_ref,
            "retrieved_corpus_artifact_version": corpus["artifact_version"],
            "paper_review_refs": deepcopy(paper_review_refs),
            "reviewed_paper_reviews": review_provenance,
            "paper_reviews": paper_reviews,
            "previous_state_ref": previous_state_ref,
            "previous_state_artifact_version": (
                previous_state.get("artifact_version") if previous_state else None
            ),
            "previous_state_snapshot": _revision_snapshot(previous_state, revision_items),
            "revision_items": deepcopy(revision_items or []),
            "output_language": index.get("output_language") or plan.get("output_language") or "English",
            "topics": [{
                "topic_id": item.get("topic_id"),
                "name": item.get("name"),
                "related_claims": deepcopy(item.get("related_claims", [])),
                "purpose": item.get("purpose"),
            } for item in plan.get("topics", []) if isinstance(item, dict)],
            "source_selection_summary": {
                "approved_download_count": len(approved.get("approved_sources", [])),
                "accepted_document_count": len(corpus.get("documents", [])),
                "accepted_market_case_count": len(corpus.get("market_cases", [])),
                "missing_a07_review_source_ids": missing_reviews,
                "retrieval_gap_count": len(retrieval_gaps),
            },
            "retrieval_gaps": retrieval_gaps,
            "draft_evidence_map": evidence_map,
            "synthesis_mode": active_profile.get("synthesis_mode") or SYNTHESIS_MODE_FAST,
            "skip_nodes": deepcopy(active_profile.get("skip_nodes", ["g02-a08-claim-verification"])),
            "claim_assessment_required": False,
            "claim_assessment_performed": False,
            "fast_mode_limitation": (
                "A08 Claim Verification was skipped by the fast execution profile; findings are "
                "evidence-linked synthesis signals, not full claim-truth verification."
            ),
            "rules": [
                "Use only reviewed A07 paper reviews, A06 corpus metadata, A05 index, source selection and ResearchPlan.",
                "Do not introduce A08 ClaimAssessment or labels implying full verification.",
                "Return the exact envelope from research_synthesis_finalize.",
                "Keep Graph03 handoff compact: refs, cards, limitations, confidence and unresolved items only.",
                "When revision_items are present, change only their scope and preserve unaffected finding IDs.",
            ],
        }
    except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        return {"ready": False, "envelope": _envelope(
            "failed", "G02-A09 synthesis input failed deterministic validation.",
            [_issue("blocker", "invalid_synthesis_basis", str(exc), "research_synthesis_input")],
        )}
    return {"ready": True, "synthesis_input": synthesis_input}


def _default_human_packet(state: dict, synthesis_input: dict) -> dict:
    language = str(synthesis_input.get("output_language") or "English")
    polish = language.casefold().startswith("pl") or "pol" in language.casefold()
    return {
        "schema_version": "user_research_validation_packet@1",
        "task_id": synthesis_input["task_id"],
        "output_language": synthesis_input.get("output_language"),
        "synthesis_ref": state.get("research_state_ref"),
        "instructions": (
            "Przejrzyj wymagane aktualizacje, zdecyduj o opcjonalnych usprawnieniach i wybierz "
            "sposób obsługi nierozstrzygniętych pozycji przed zatwierdzeniem przekazania do Graph03."
            if polish else
            "Review required updates, decide whether to include optional improvements, and choose "
            "how unresolved items should be handled before approving the Graph03 handoff."
        ),
        "decisions_required": [
            "approve_required_updates",
            "approve_optional_improvements",
            "unresolved_claim_handling",
        ],
        "fast_mode_limitation": synthesis_input["fast_mode_limitation"],
        "required_updates": deepcopy(state.get("required_updates", [])),
        "optional_improvements": deepcopy(state.get("optional_improvements", [])),
        "unresolved": deepcopy(state.get("unresolved", [])),
        "confidence": state.get("confidence"),
    }


def _default_solution_candidate(state: dict, synthesis_input: dict) -> dict:
    return {
        "schema_version": "solution_input_candidate@1",
        "task_id": synthesis_input["task_id"],
        "synthesis_mode": SYNTHESIS_MODE_FAST,
        "claim_assessment_performed": False,
        "graph03_handoff_constraints": {
            "no_full_pdfs": True,
            "no_full_extracted_text": True,
            "no_verbose_paper_reviews": True,
        },
        "suggested_updates": deepcopy(state.get("required_updates", [])),
        "optional_improvements": deepcopy(state.get("optional_improvements", [])),
        "evidence_map_ref": state.get("evidence_map_ref"),
        "source_refs": deepcopy(state.get("source_refs", [])),
        "limitations": deepcopy(state.get("limitations", [])),
        "unresolved_items": deepcopy(state.get("unresolved", [])),
        "confidence": state.get("confidence"),
        "a08_status": "skipped_fast_profile",
    }


def _normalize_state(synthesis_input: dict, output: object, artifact_version: str) -> dict:
    if not isinstance(output, dict):
        raise ValueError("research synthesis output must be an object")
    state = deepcopy(output)
    state.setdefault("schema_version", OUTPUT_CONTRACT)
    state["artifact_version"] = artifact_version
    state.setdefault("task_id", synthesis_input["task_id"])
    state.setdefault("synthesis_mode", SYNTHESIS_MODE_FAST)
    state.setdefault("claim_assessment_performed", False)
    state.setdefault("claim_assessment_status", "skipped_fast_profile")
    state.setdefault("skipped_nodes", ["g02-a08-claim-verification"])
    state.setdefault("fast_mode_limitation", synthesis_input["fast_mode_limitation"])
    state["evidence_map"] = deepcopy(synthesis_input["draft_evidence_map"])
    state.setdefault("findings", [])
    state.setdefault("required_updates", [])
    state.setdefault("optional_improvements", [])
    state.setdefault("unresolved", [])
    state.setdefault("limitations", [synthesis_input["fast_mode_limitation"]])
    default_confidence = "medium" if any(
        review.get("review_status") == "sufficient"
        for review in synthesis_input.get("paper_reviews", []) if isinstance(review, dict)
    ) else "low"
    state.setdefault("confidence", default_confidence)
    if not synthesis_input.get("paper_reviews"):
        state["confidence"] = "low"
    state["upstream_refs"] = {
        "research_plan_ref": synthesis_input["research_plan_ref"],
        "candidate_source_index_ref": synthesis_input["candidate_source_index_ref"],
        "approved_source_set_ref": synthesis_input["approved_source_set_ref"],
        "retrieved_corpus_ref": synthesis_input["retrieved_corpus_ref"],
        "paper_review_refs": deepcopy(synthesis_input.get("paper_review_refs", [])),
        "reviewed_paper_reviews": deepcopy(synthesis_input.get("reviewed_paper_reviews", [])),
    }
    if not state["findings"]:
        for claim in state["evidence_map"].get("claims", []):
            refs = claim.get("evidence_refs") or [
                f"{synthesis_input['retrieved_corpus_ref']}#/source/{source_id}"
                for source_id in claim.get("source_ids", [])
            ]
            status = claim.get("status")
            state["findings"].append({
                "finding_id": f"FIND_{_safe(claim.get('claim_id')).upper()}",
                "status": status if status in ALLOWED_FINDING_STATUS else "needs_human_check",
                "claim_ids": [claim.get("claim_id")],
                "topic_ids": [],
                "source_ids": deepcopy(claim.get("source_ids", [])),
                "evidence_refs": refs,
                "summary": "Evidence-linked synthesis from reviewed A07 source(s).",
                "limitations": deepcopy(claim.get("limitations", [])),
                "confidence": "medium",
            })
    evidence_source = {
        card.get("evidence_ref"): review.get("source_id")
        for review in synthesis_input.get("paper_reviews", [])
        if isinstance(review, dict)
        for card in review.get("evidence_cards", [])
        if isinstance(card, dict) and isinstance(card.get("evidence_ref"), str)
    }
    for index, finding in enumerate(state["findings"]):
        if not isinstance(finding, dict):
            continue
        finding.setdefault("finding_id", f"FINDING_{index + 1:03d}")
        finding.setdefault("status", "needs_human_check")
        finding.setdefault("claim_ids", [])
        finding.setdefault("topic_ids", [])
        finding.setdefault("evidence_refs", [])
        if "source_ids" not in finding:
            finding["source_ids"] = _unique(
                evidence_source.get(ref) for ref in finding.get("evidence_refs", [])
            )
        finding.setdefault("summary", "Evidence-linked fast-mode synthesis finding.")
        finding.setdefault("limitations", [synthesis_input["fast_mode_limitation"]])
        finding.setdefault("confidence", state.get("confidence", "medium"))
    if not state["required_updates"] and state["findings"]:
        for finding in state["findings"]:
            status = finding.get("status")
            if status in {"supported_by_reviewed_source", "needs_human_check", "market_case_signal"}:
                state["required_updates"].append({
                    "finding_id": finding["finding_id"],
                    "impact": _truncate(finding.get("summary"), 800),
                    "priority": "medium",
                    "status": status,
                    "related_claims": deepcopy(finding.get("claim_ids", [])),
                    "related_topics": deepcopy(finding.get("topic_ids", [])),
                    "evidence_refs": deepcopy(finding.get("evidence_refs", [])),
                    "source_refs": deepcopy(finding.get("source_ids", [])),
                    "confidence": finding.get("confidence", state.get("confidence")),
                })
            elif status == "insufficient_evidence":
                state["unresolved"].append({
                    "finding_id": finding["finding_id"],
                    "reason": "insufficient_evidence",
                    "evidence_refs": deepcopy(finding.get("evidence_refs", [])),
                    "source_refs": deepcopy(finding.get("source_ids", [])),
                })
    if not state["unresolved"]:
        for gap in synthesis_input.get("retrieval_gaps", []):
            state["unresolved"].append({
                "finding_id": f"RETRIEVAL_{_safe(gap.get('source_id')).upper()}",
                "reason": gap.get("reason") or "retrieval_unavailable",
                "source_refs": [gap.get("source_id")],
                "evidence_refs": [gap.get("source_ref")],
                "status": "insufficient_evidence",
            })
    state["source_refs"] = [{
        "source_id": item.get("source_id"),
        "paper_review_ref": item.get("paper_review_ref"),
        "reviewed_document_ref": item.get("reviewed_document_ref"),
    } for item in synthesis_input.get("paper_reviews", [])]
    state["human_validation_packet"] = _default_human_packet(state, synthesis_input)
    state["solution_input_candidate"] = _default_solution_candidate(state, synthesis_input)
    return state


def _walk_forbidden(value: object, path: str = "$") -> list[dict]:
    issues = []
    if isinstance(value, dict):
        for key, item in value.items():
            next_path = f"{path}.{key}"
            if key in FULL_TEXT_KEYS:
                issues.append(_issue("blocker", "full_text_forwarding",
                                     f"{key} must not be included in synthesis handoff", next_path))
            issues.extend(_walk_forbidden(item, next_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            issues.extend(_walk_forbidden(item, f"{path}[{index}]"))
    elif isinstance(value, str) and len(value) > MAX_HANDOFF_STRING and path.startswith(
            "$.solution_input_candidate"):
        issues.append(_issue("blocker", "handoff_text_too_large",
                             "SolutionInputCandidate contains an oversized string", path))
    return issues


def validate_research_state(state: object, synthesis_input: dict) -> dict:
    issues = []
    if not isinstance(state, dict):
        return {"ok": False, "issues": [_issue(
            "blocker", "invalid_research_state_contract",
            "research_state must be an object", "research_state"
        )]}
    for error in _shape(state, OUTPUT_CONTRACT):
        issues.append(_issue("blocker", "invalid_research_state_contract", error, "research_state"))
    if state.get("task_id") != synthesis_input.get("task_id"):
        issues.append(_issue("blocker", "research_state_identity_mismatch",
                             "task_id differs from synthesis input", "task_id"))
    if state.get("synthesis_mode") != SYNTHESIS_MODE_FAST:
        issues.append(_issue("blocker", "invalid_fast_synthesis_mode",
                             "fast synthesis must use evidence_without_claim_assessment",
                             "synthesis_mode"))
    limitation = str(state.get("fast_mode_limitation") or "")
    if state.get("claim_assessment_performed") is not False \
            or "A08" not in limitation \
            or "skipped" not in limitation.casefold():
        issues.append(_issue("blocker", "hidden_a08_skip",
                             "research_state must explicitly state that A08 was skipped",
                             "fast_mode_limitation"))
    serialized = json.dumps(state, ensure_ascii=False)
    if re.search(r"fully verified|claim verified|verified truth", serialized, re.IGNORECASE):
        issues.append(_issue("blocker", "forbidden_truth_verification_label",
                             "A09 output uses a label implying full claim verification",
                             "research_state"))
    if len(serialized.encode("utf-8")) > MAX_RESEARCH_STATE_BYTES:
        issues.append(_issue("blocker", "research_state_too_large",
                             "research_state@1 exceeds the compactness limit", "research_state"))
    allowed_evidence_refs = {
        card.get("evidence_ref")
        for review in synthesis_input.get("paper_reviews", [])
        if isinstance(review, dict)
        for card in review.get("evidence_cards", [])
        if isinstance(card, dict) and isinstance(card.get("evidence_ref"), str)
    }
    allowed_evidence_refs.update(
        gap.get("source_ref") for gap in synthesis_input.get("retrieval_gaps", [])
        if isinstance(gap, dict) and isinstance(gap.get("source_ref"), str)
    )
    allowed_source_ids = {
        review.get("source_id") for review in synthesis_input.get("paper_reviews", [])
        if isinstance(review, dict) and isinstance(review.get("source_id"), str)
    }
    allowed_evidence_refs.update(
        f"{synthesis_input['retrieved_corpus_ref']}#/source/{source_id}"
        for source_id in allowed_source_ids
    )
    allowed_source_ids.update(
        gap.get("source_id") for gap in synthesis_input.get("retrieval_gaps", [])
        if isinstance(gap, dict) and isinstance(gap.get("source_id"), str)
    )
    allowed_topic_ids = {
        topic.get("topic_id") for topic in synthesis_input.get("topics", [])
        if isinstance(topic, dict) and isinstance(topic.get("topic_id"), str)
    }
    allowed_claim_ids = {"UNASSIGNED_CLAIM_SCOPE"}
    allowed_claim_ids.update(
        claim_id for topic in synthesis_input.get("topics", []) if isinstance(topic, dict)
        for claim_id in _strings(topic.get("related_claims"))
    )
    for index, finding in enumerate(state.get("findings", [])):
        if not isinstance(finding, dict):
            issues.append(_issue("major", "invalid_finding",
                                 "finding must be an object", f"findings[{index}]"))
            continue
        if finding.get("status") not in ALLOWED_FINDING_STATUS:
            issues.append(_issue("blocker", "invalid_finding_status",
                                 "finding status is not allowed in fast synthesis",
                                 f"findings[{index}].status"))
        refs = finding.get("evidence_refs")
        if not isinstance(refs, list) or not any(isinstance(ref, str) and ref.strip() for ref in refs):
            issues.append(_issue("blocker", "missing_finding_evidence_refs",
                                  "every finding needs compact evidence refs",
                                  f"findings[{index}].evidence_refs"))
        elif any(ref not in allowed_evidence_refs for ref in refs):
            issues.append(_issue("blocker", "unbound_finding_evidence_ref",
                                 "finding contains an evidence ref outside prepared A07 or retrieval gaps",
                                 f"findings[{index}].evidence_refs"))
        source_ids = finding.get("source_ids")
        if isinstance(source_ids, list) and any(
                source_id not in allowed_source_ids for source_id in source_ids):
            issues.append(_issue("blocker", "unbound_finding_source_ref",
                                 "finding contains a source outside prepared A07 or retrieval gaps",
                                 f"findings[{index}].source_ids"))
        if isinstance(finding.get("topic_ids"), list) and any(
                topic_id not in allowed_topic_ids for topic_id in finding["topic_ids"]):
            issues.append(_issue("blocker", "unbound_finding_topic",
                                 "finding contains a topic outside the ResearchPlan",
                                 f"findings[{index}].topic_ids"))
        if isinstance(finding.get("claim_ids"), list) and any(
                claim_id not in allowed_claim_ids for claim_id in finding["claim_ids"]):
            issues.append(_issue("blocker", "unbound_finding_claim",
                                 "finding contains a claim outside the ResearchPlan",
                                 f"findings[{index}].claim_ids"))
    for collection in ("required_updates", "optional_improvements", "unresolved"):
        for index, item in enumerate(state.get(collection, [])):
            if not isinstance(item, dict):
                continue
            refs = item.get("evidence_refs")
            source_refs = item.get("source_refs")
            if collection != "optional_improvements" and (
                    not isinstance(refs, list) or not refs) \
                    and (not isinstance(source_refs, list) or not source_refs):
                issues.append(_issue("blocker", "missing_update_evidence_refs",
                                     f"{collection} item lacks evidence refs",
                                     f"{collection}[{index}]"))
            if isinstance(refs, list) and any(ref not in allowed_evidence_refs for ref in refs):
                issues.append(_issue("blocker", "unbound_update_evidence_ref",
                                     f"{collection} contains an unprepared evidence ref",
                                     f"{collection}[{index}].evidence_refs"))
            if isinstance(source_refs, list) and any(
                    source_ref not in allowed_source_ids for source_ref in source_refs):
                issues.append(_issue("blocker", "unbound_update_source_ref",
                                     f"{collection} contains an unprepared source ref",
                                     f"{collection}[{index}].source_refs"))
    issues.extend(_walk_forbidden(state, "$"))
    return {"ok": not any(item["severity"] == "blocker" for item in issues), "issues": issues}


def _store_auxiliary(state: dict, synthesis_input: dict, artifact_version: str, *, base=None) -> dict:
    task = _safe(state["task_id"])
    version = _safe(artifact_version)
    evidence_map = deepcopy(state["evidence_map"])
    evidence_map["artifact_version"] = artifact_version
    evidence_errors = _shape(evidence_map, "evidence_map@1")
    if evidence_errors:
        raise ValueError("invalid evidence_map@1: " + "; ".join(evidence_errors))
    evidence_map_ref = artifacts.store(
        f"g02/synthesis/{task}.{version}.evidence-map.json", evidence_map, base=base
    )
    packet = deepcopy(state["human_validation_packet"])
    packet["artifact_version"] = artifact_version
    packet["synthesis_ref"] = f"artifact://g02/synthesis/{task}.{version}.research-state.json"
    packet_errors = _shape(packet, "user_research_validation_packet@1")
    if packet_errors:
        raise ValueError(
            "invalid user_research_validation_packet@1: " + "; ".join(packet_errors)
        )
    packet_ref = artifacts.store(
        f"g02/synthesis/{task}.{version}.human-validation-packet.json", packet, base=base
    )
    solution = deepcopy(state["solution_input_candidate"])
    solution["artifact_version"] = artifact_version
    solution["evidence_map_ref"] = evidence_map_ref
    solution_errors = _shape(solution, "solution_input_candidate@1")
    if solution_errors:
        raise ValueError("invalid solution_input_candidate@1: " + "; ".join(solution_errors))
    solution_ref = artifacts.store(
        f"g02/synthesis/{task}.{version}.solution-input-candidate.json", solution, base=base
    )
    summary = {
        "schema_version": "research_summary@1",
        "artifact_version": artifact_version,
        "task_id": state["task_id"],
        "synthesis_mode": SYNTHESIS_MODE_FAST,
        "fast_mode_limitation": synthesis_input["fast_mode_limitation"],
        "required_updates": deepcopy(state.get("required_updates", [])),
        "optional_improvements": deepcopy(state.get("optional_improvements", [])),
        "unresolved": deepcopy(state.get("unresolved", [])),
        "confidence": state.get("confidence"),
        "created_at": _utc_now(),
    }
    summary_errors = _shape(summary, "research_summary@1")
    if summary_errors:
        raise ValueError("invalid research_summary@1: " + "; ".join(summary_errors))
    summary_ref = artifacts.store(
        f"g02/synthesis/{task}.{version}.research-summary.json", summary, base=base
    )
    return {
        "evidence_map_ref": evidence_map_ref,
        "human_validation_packet_ref": packet_ref,
        "solution_input_candidate_ref": solution_ref,
        "research_summary_ref": summary_ref,
    }


def finalize_synthesis(synthesis_input: dict, output: object, *,
                       artifact_version: str = DEFAULT_ARTIFACT_VERSION,
                       base=None) -> dict:
    try:
        if not isinstance(synthesis_input, dict) \
                or synthesis_input.get("schema_version") != "research_synthesis_input@1":
            raise ValueError("research_synthesis_input@1 is required")
        state = _normalize_state(synthesis_input, output, artifact_version)
        previous_version = synthesis_input.get("previous_state_artifact_version")
        if previous_version is not None and artifact_version == previous_version:
            raise ValueError("a revised ResearchState must advance artifact_version")
        validation = validate_research_state(state, synthesis_input)
        if not validation["ok"]:
            blockers = [item for item in validation["issues"] if item["severity"] == "blocker"]
            raise ValueError("; ".join(item["message"] for item in blockers))
        aux = _store_auxiliary(state, synthesis_input, artifact_version, base=base)
        state.update(aux)
        state["evidence_map"]["artifact_version"] = artifact_version
        state["human_validation_packet"]["artifact_version"] = artifact_version
        state["solution_input_candidate"]["artifact_version"] = artifact_version
        state["solution_input_candidate"]["evidence_map_ref"] = aux["evidence_map_ref"]
        state["human_validation_packet"]["synthesis_ref"] = artifacts.ref_for(
            f"g02/synthesis/{_safe(state['task_id'])}.{_safe(artifact_version)}.research-state.json"
        )
        for error in _shape(state, OUTPUT_CONTRACT):
            raise ValueError(error)
        rel = f"g02/synthesis/{_safe(state['task_id'])}.{_safe(artifact_version)}.research-state.json"
        state_ref = artifacts.store(rel, state, base=base)
    except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        return _envelope(
            "failed", "ResearchState failed deterministic finalization.",
            [_issue("blocker", "synthesis_finalize_failed", str(exc), "research_state")],
        )
    metrics = {
        "finding_count": len(state.get("findings", [])),
        "required_update_count": len(state.get("required_updates", [])),
        "optional_improvement_count": len(state.get("optional_improvements", [])),
        "unresolved_count": len(state.get("unresolved", [])),
        "a08_skipped": True,
    }
    return _envelope(
        "ok",
        "Stored fast ResearchState, evidence map, human validation packet and SolutionInputCandidate.",
        [item for item in validation["issues"] if item["severity"] != "blocker"],
        produced=[
            {"type": "research_state", "path": state_ref,
             "schema_version": OUTPUT_CONTRACT, "artifact_version": artifact_version},
            {"type": "evidence_map", "path": state["evidence_map_ref"],
             "schema_version": "evidence_map@1", "artifact_version": artifact_version},
            {"type": "user_research_validation_packet", "path": state["human_validation_packet_ref"],
             "schema_version": "user_research_validation_packet@1",
             "artifact_version": artifact_version},
            {"type": "solution_input_candidate", "path": state["solution_input_candidate_ref"],
             "schema_version": "solution_input_candidate@1",
             "artifact_version": artifact_version},
            {"type": "research_summary", "path": state["research_summary_ref"],
             "schema_version": "research_summary@1", "artifact_version": artifact_version},
        ],
        metrics=metrics,
    )


def build_synthesis_review_task(synthesis_input: dict, artifact_descriptor: dict, *,
                                review_id: str, attempt: int = 1,
                                previous_decision_ref: str | None = None,
                                producer_revision_response: dict | None = None,
                                base=None) -> dict:
    if not isinstance(synthesis_input, dict) \
            or synthesis_input.get("schema_version") != "research_synthesis_input@1":
        raise ValueError("synthesis input is invalid")
    if not isinstance(artifact_descriptor, dict):
        raise ValueError("artifact descriptor must be an object")
    ref = artifact_descriptor.get("path") or artifact_descriptor.get("ref")
    if artifact_descriptor.get("type") != "research_state" \
            or artifact_descriptor.get("schema_version") != OUTPUT_CONTRACT \
            or not isinstance(ref, str) or not ref.startswith(artifacts.SCHEME):
        raise ValueError("artifact descriptor must identify research_state@1")
    state = artifacts.hydrate(ref, base=base)
    validation = validate_research_state(state, synthesis_input)
    if not validation["ok"]:
        raise ValueError("research_state is not reviewable: " + "; ".join(
            item["message"] for item in validation["issues"]
            if item["severity"] == "blocker"
        ))
    if state.get("artifact_version") != artifact_descriptor.get("artifact_version"):
        raise ValueError("artifact descriptor version differs from stored ResearchState")
    task = {
        "schema_version": "review_task@1",
        "review_id": review_id,
        "task_id": synthesis_input["task_id"],
        "logical_review_node": "g02-a09-synthesizer-review",
        "producer_agent": AGENT,
        "attempt": attempt,
        "review_profile": REVIEW_PROFILE,
        "original_task": {
            "objective": "Synthesize reviewed A07 evidence into compact fast-mode Graph03 input.",
            "input_contract": "research_synthesis_input@1",
            "output_contract": OUTPUT_CONTRACT,
        },
        "producer_input": deepcopy(synthesis_input),
        "artifact": {
            "type": "research_state",
            "ref": ref,
            "schema_version": OUTPUT_CONTRACT,
            "artifact_version": state["artifact_version"],
        },
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
        raise ValueError("invalid synthesis review task: " + "; ".join(
            item["message"] for item in checked["issues"]
        ))
    return task


def prepare_human_research_gate(research_state_ref: str, *, base=None) -> dict:
    state = _hydrate(research_state_ref, OUTPUT_CONTRACT, base=base)
    packet_ref = state.get("human_validation_packet_ref")
    packet = artifacts.hydrate(packet_ref, base=base) \
        if isinstance(packet_ref, str) and packet_ref.startswith(artifacts.SCHEME) \
        else state.get("human_validation_packet", {})
    # Surface the clean executive digest (research_summary@1) so the human reads the summary, not
    # the raw research state. This is the "light gate over a digest": A09 already produced it.
    summary_ref = state.get("research_summary_ref")
    research_summary = artifacts.hydrate(summary_ref, base=base) \
        if isinstance(summary_ref, str) and summary_ref.startswith(artifacts.SCHEME) else {}
    return {
        "graph": "g02",
        "gate": "user-research-gate",
        "research_state_ref": research_state_ref,
        "research_summary_ref": summary_ref,
        "research_summary": research_summary,
        "human_validation_packet_ref": packet_ref,
        "human_validation_packet": packet,
        "required_decisions": [
            "approve_required_updates",
            "approve_optional_improvements",
            "unresolved_claim_handling",
        ],
        "decision_template": {
            "status": "approved",
            "approve_required_updates": True,
            "approve_optional_improvements": True,
            "unresolved_claim_handling": "keep_as_unresolved_items",
        },
        "context": {
            "task_id": state.get("task_id"),
            "synthesis_mode": state.get("synthesis_mode"),
            "a08_status": state.get("claim_assessment_status"),
        },
    }


def validate_human_research_decision(decision: object) -> dict:
    """Validate all three explicit Human Research Gate decisions."""
    issues = []
    if not isinstance(decision, dict):
        return {"ok": False, "issues": ["decision must be an object"]}
    status = str(decision.get("status") or decision.get("decision") or "").casefold()
    if status not in {"approved", "approve", "accepted"}:
        issues.append("status must explicitly approve the research bundle")
    if decision.get("approve_required_updates") is not True:
        issues.append("approve_required_updates must be true")
    if not isinstance(decision.get("approve_optional_improvements"), bool):
        issues.append("approve_optional_improvements must be true or false")
    unresolved = decision.get("unresolved_claim_handling")
    if unresolved not in ALLOWED_UNRESOLVED_HANDLING:
        issues.append(
            "unresolved_claim_handling must be keep_as_unresolved_items, "
            "exclude_from_graph03_handoff or return_for_research"
        )
    if unresolved == "return_for_research":
        issues.append("return_for_research does not authorize a Graph03 handoff")
    return {"ok": not issues, "issues": issues}


def finalize_research_bundle(research_state_ref: str, decision: dict, *,
                             artifact_version: str = DEFAULT_ARTIFACT_VERSION,
                             emit_handoff_descriptor: bool = False,
                             base=None) -> dict:
    try:
        gate_validation = validate_human_research_decision(decision)
        if not gate_validation["ok"]:
            return _envelope(
                "needs_input",
                "Human Research Gate decision is incomplete or does not authorize handoff.",
                [_issue(
                    "major", "research_gate_not_approved", message,
                    "user-research-gate"
                ) for message in gate_validation["issues"]],
                metrics={"approved": False},
            )
        state = _hydrate(research_state_ref, OUTPUT_CONTRACT, base=base)
        solution = deepcopy(state.get("solution_input_candidate", {}))
        validation_issues = _walk_forbidden(solution, "$.solution_handoff")
        if validation_issues:
            raise ValueError("; ".join(item["message"] for item in validation_issues))
        include_optional = decision["approve_optional_improvements"]
        unresolved_action = decision["unresolved_claim_handling"]
        optional = deepcopy(state.get("optional_improvements", []))
        rejected = deepcopy(decision.get("rejected_findings", []))
        if not include_optional:
            rejected.extend(optional)
        unresolved_items = deepcopy(state.get("unresolved", [])) \
            if unresolved_action == "keep_as_unresolved_items" else []
        solution["optional_improvements"] = optional if include_optional else []
        solution["unresolved_items"] = unresolved_items
        decision_material = {
            "research_state_ref": research_state_ref,
            "approve_required_updates": True,
            "approve_optional_improvements": include_optional,
            "unresolved_claim_handling": unresolved_action,
            "rejected_findings": rejected,
        }
        decision_id = hashlib.sha256(json.dumps(
            decision_material, sort_keys=True, ensure_ascii=False
        ).encode("utf-8")).hexdigest()[:12]
        approved_at = _utc_now()
        approved_summary = {
            "schema_version": "research_summary@1",
            "artifact_version": artifact_version,
            "task_id": state["task_id"],
            "synthesis_mode": SYNTHESIS_MODE_FAST,
            "fast_mode_limitation": state.get("fast_mode_limitation"),
            "required_updates": deepcopy(state.get("required_updates", [])),
            "optional_improvements": optional if include_optional else [],
            "unresolved": unresolved_items,
            "confidence": state.get("confidence"),
            "created_at": approved_at,
            "human_gate_decision": {
                "approve_required_updates": True,
                "approve_optional_improvements": include_optional,
                "unresolved_claim_handling": unresolved_action,
            },
        }
        approved_summary_errors = _shape(approved_summary, "research_summary@1")
        if approved_summary_errors:
            raise ValueError("invalid approved research summary: " + "; ".join(
                approved_summary_errors
            ))
        approved_summary_ref = artifacts.store(
            f"g02/approved-research-bundles/{_safe(state['task_id'])}."
            f"{_safe(artifact_version)}.{decision_id}.research-summary.json",
            approved_summary, base=base,
        )
        bundle = {
            "schema_version": BUNDLE_CONTRACT,
            "artifact_version": artifact_version,
            "task_id": state["task_id"],
            "research_state_ref": research_state_ref,
            "approved_research_summary_ref": approved_summary_ref,
            "approved_update_findings": deepcopy(state.get("required_updates", [])),
            "approved_optional_findings": optional if include_optional else [],
            "rejected_findings": rejected,
            "unresolved_claim_policy": {
                "action": unresolved_action,
                "a08_status": "skipped_fast_profile",
                "fast_mode_limitation": state.get("fast_mode_limitation"),
            },
            "human_gate_decision": {
                "status": "approved",
                "approve_required_updates": True,
                "approve_optional_improvements": include_optional,
                "unresolved_claim_handling": unresolved_action,
            },
            "solution_handoff": {
                **solution,
                "research_state_ref": research_state_ref,
                "research_summary_ref": approved_summary_ref,
                "human_validation_packet_ref": state.get("human_validation_packet_ref"),
                "explicit_limitations": deepcopy(state.get("limitations", [])),
                "unresolved_items": unresolved_items,
                "claim_assessment_performed": False,
                "a08_status": "skipped_fast_profile",
            },
            "approved_at": approved_at,
        }
        errors = _shape(bundle, BUNDLE_CONTRACT)
        if errors:
            raise ValueError("; ".join(errors))
        ref = artifacts.store(
            f"g02/approved-research-bundles/{_safe(state['task_id'])}."
            f"{_safe(artifact_version)}.{decision_id}.json",
            bundle, base=base,
        )
        descriptor = None
        if emit_handoff_descriptor:
            descriptor = handoff.emit_handoff(
                bundle, BUNDLE_CONTRACT,
                name=f"research_bundle.{_safe(state['task_id'])}",
                base=base,
            )
    except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        return _envelope(
            "failed", "UserApprovedResearchBundle failed deterministic finalization.",
            [_issue("blocker", "research_bundle_finalize_failed", str(exc),
                    "user_approved_research_bundle")],
        )
    produced = [{
        "type": "user_approved_research_bundle",
        "path": ref,
        "schema_version": BUNDLE_CONTRACT,
        "artifact_version": artifact_version,
    }]
    if descriptor is not None:
        produced.append({
            "type": descriptor["type"],
            "path": descriptor["ref"],
            "schema_version": descriptor["schema_version"],
            "artifact_version": artifact_version,
        })
    return _envelope(
        "ok",
        "Stored user-approved compact research bundle for Graph03.",
        [],
        produced=produced,
        metrics={"approved": True, "a08_skipped": True},
    )
