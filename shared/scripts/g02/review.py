"""Deterministic seam for the universal Research Graph reviewer.

The module validates review tasks and decisions, resolves exactly one authorized artifact,
persists valid decisions and standardizes the ``envelope@1`` returned by reviewer adapters.
Semantic review remains the responsibility of ``g02-a10-output-reviewer``.

Pure stdlib. Host adapters may call ``prepare_review`` before invoking the agent and
``finalize_review_decision`` after receiving its structured decision.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Callable

from core import artifacts, contracts

REVIEW_TASK_CONTRACT = "review_task@1"
REVIEW_DECISION_CONTRACT = "review_decision@1"
REVIEWER_AGENT = "g02-a10-output-reviewer"

RESERVED_CRITERIA = {"REVIEW_BASIS", "ARTIFACT_ACCESS", "EXTERNAL_DEPENDENCY"}
ROOT_CAUSES = {
    "producer_error",
    "insufficient_evidence",
    "invalid_or_incomplete_input",
    "upstream_plan_error",
    "review_profile_error",
    "external_dependency_blocked",
}
REVISE_ROOT_CAUSES = {"producer_error", "insufficient_evidence"}
BLOCKED_ROOT_CAUSES = {
    "invalid_or_incomplete_input",
    "upstream_plan_error",
    "review_profile_error",
    "external_dependency_blocked",
}

REVIEW_TO_REVISION_SEVERITY = {
    "minor": "low",
    "major": "high",
    "blocker": "critical",
}
REVISION_TO_REVIEW_SEVERITY = {
    "low": "minor",
    "medium": "major",
    "high": "major",
    "critical": "blocker",
}


def review_to_revision_severity(severity: str) -> str:
    """Map a reviewer finding severity to the existing revision engine scale."""
    try:
        return REVIEW_TO_REVISION_SEVERITY[severity]
    except KeyError as exc:
        raise ValueError(f"unknown review severity {severity!r}") from exc


def revision_to_review_severity(severity: str) -> str:
    """Map an existing revision-engine severity to the reviewer scale."""
    try:
        return REVISION_TO_REVIEW_SEVERITY[severity]
    except KeyError as exc:
        raise ValueError(f"unknown revision severity {severity!r}") from exc


def _issue(issue_type: str, message: str, *, root_cause: str,
           criterion_id: str, location: str) -> dict:
    return {
        "type": issue_type,
        "message": message,
        "root_cause": root_cause,
        "criterion_id": criterion_id,
        "location": location,
    }


def _duplicates(values: list[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def validate_review_task(task: object) -> dict:
    """Validate ``review_task@1`` shape plus reviewer-specific semantic invariants."""
    issues: list[dict] = []
    try:
        shape = contracts.validate(task, REVIEW_TASK_CONTRACT)
    except (KeyError, ValueError) as exc:
        return {"ok": False, "issues": [_issue(
            "contract_unavailable", str(exc),
            root_cause="external_dependency_blocked",
            criterion_id="EXTERNAL_DEPENDENCY",
            location="review_task.schema_version",
        )]}

    for error in shape["errors"]:
        profile_error = any(field in error for field in (
            "review_profile", "acceptance_criteria", "evidence_requirements",
            "prohibited_behaviors", "severity_rules",
        ))
        issues.append(_issue(
            "invalid_review_profile" if profile_error else "invalid_review_task",
            error,
            root_cause="review_profile_error" if profile_error
            else "invalid_or_incomplete_input",
            criterion_id="REVIEW_BASIS",
            location="review_task",
        ))

    if not isinstance(task, dict):
        return {"ok": False, "issues": issues}

    attempt = task.get("attempt")
    if isinstance(attempt, int) and not isinstance(attempt, bool) and attempt < 1:
        issues.append(_issue(
            "invalid_attempt", "attempt must be at least 1",
            root_cause="invalid_or_incomplete_input",
            criterion_id="REVIEW_BASIS", location="review_task.attempt",
        ))

    profile = task.get("review_profile")
    if isinstance(profile, str) and not profile.strip():
        issues.append(_issue(
            "empty_review_profile", "review_profile must not be empty",
            root_cause="review_profile_error",
            criterion_id="REVIEW_BASIS", location="review_task.review_profile",
        ))

    for field in ("review_id", "task_id", "logical_review_node", "producer_agent",
                  "expected_output_contract"):
        value = task.get(field)
        if isinstance(value, str) and not value.strip():
            issues.append(_issue(
                "empty_audit_field", f"{field} must not be empty",
                root_cause="invalid_or_incomplete_input",
                criterion_id="REVIEW_BASIS", location=f"review_task.{field}",
            ))

    for legacy_field in ("artifacts", "artifact_ref"):
        if legacy_field in task:
            issues.append(_issue(
                "multiple_artifact_inputs",
                f"legacy field {legacy_field!r} is not allowed; use exactly one artifact object",
                root_cause="invalid_or_incomplete_input",
                criterion_id="REVIEW_BASIS", location=f"review_task.{legacy_field}",
            ))

    criteria = task.get("acceptance_criteria")
    if isinstance(criteria, list):
        if not criteria:
            issues.append(_issue(
                "missing_acceptance_criteria", "at least one acceptance criterion is required",
                root_cause="review_profile_error",
                criterion_id="REVIEW_BASIS", location="review_task.acceptance_criteria",
            ))
        criterion_ids = [item.get("criterion_id") for item in criteria
                         if isinstance(item, dict) and isinstance(item.get("criterion_id"), str)]
        if any(isinstance(item, dict) and isinstance(item.get("description"), str)
               and not item["description"].strip() for item in criteria):
            issues.append(_issue(
                "empty_criterion_description", "criterion description must not be empty",
                root_cause="review_profile_error",
                criterion_id="REVIEW_BASIS", location="review_task.acceptance_criteria",
            ))
        if any(not value.strip() for value in criterion_ids):
            issues.append(_issue(
                "empty_criterion_id", "criterion_id must not be empty",
                root_cause="review_profile_error",
                criterion_id="REVIEW_BASIS", location="review_task.acceptance_criteria",
            ))
        collisions = set(criterion_ids) & RESERVED_CRITERIA
        if collisions:
            issues.append(_issue(
                "reserved_criterion_id",
                f"producer criteria use reserved IDs {sorted(collisions)}",
                root_cause="review_profile_error",
                criterion_id="REVIEW_BASIS", location="review_task.acceptance_criteria",
            ))
        for duplicate in sorted(_duplicates(criterion_ids)):
            issues.append(_issue(
                "duplicate_criterion_id", f"duplicate criterion_id {duplicate!r}",
                root_cause="review_profile_error",
                criterion_id="REVIEW_BASIS", location="review_task.acceptance_criteria",
            ))

    requirements = task.get("evidence_requirements")
    if isinstance(requirements, list):
        requirement_ids = [item.get("requirement_id") for item in requirements
                           if isinstance(item, dict)
                           and isinstance(item.get("requirement_id"), str)]
        if any(isinstance(item, dict) and isinstance(item.get("description"), str)
               and not item["description"].strip() for item in requirements):
            issues.append(_issue(
                "empty_requirement_description", "evidence requirement must not be empty",
                root_cause="review_profile_error",
                criterion_id="REVIEW_BASIS", location="review_task.evidence_requirements",
            ))
        if any(not value.strip() for value in requirement_ids):
            issues.append(_issue(
                "empty_requirement_id", "requirement_id must not be empty",
                root_cause="review_profile_error",
                criterion_id="REVIEW_BASIS", location="review_task.evidence_requirements",
            ))
        for duplicate in sorted(_duplicates(requirement_ids)):
            issues.append(_issue(
                "duplicate_requirement_id", f"duplicate requirement_id {duplicate!r}",
                root_cause="review_profile_error",
                criterion_id="REVIEW_BASIS", location="review_task.evidence_requirements",
            ))

    artifact = task.get("artifact")
    if isinstance(artifact, dict):
        for field in ("type", "ref", "schema_version", "artifact_version"):
            value = artifact.get(field)
            if isinstance(value, str) and not value.strip():
                issues.append(_issue(
                    "empty_artifact_field", f"artifact {field} must not be empty",
                    root_cause="invalid_or_incomplete_input",
                    criterion_id="REVIEW_BASIS", location=f"review_task.artifact.{field}",
                ))
        ref = artifact.get("ref")
        if isinstance(ref, str) and not ref.startswith(artifacts.SCHEME):
            issues.append(_issue(
                "invalid_artifact_ref", "artifact ref must use artifact://",
                root_cause="invalid_or_incomplete_input",
                criterion_id="ARTIFACT_ACCESS", location="review_task.artifact.ref",
            ))
        expected = task.get("expected_output_contract")
        actual = artifact.get("schema_version")
        if isinstance(expected, str) and isinstance(actual, str) and expected != actual:
            issues.append(_issue(
                "artifact_contract_mismatch",
                f"artifact schema {actual!r} does not match expected contract {expected!r}",
                root_cause="invalid_or_incomplete_input",
                criterion_id="REVIEW_BASIS",
                location="review_task.expected_output_contract",
            ))
        if isinstance(expected, str):
            try:
                expected_type, _ = contracts.parse_ref(expected)
                contracts.load_schema(expected)
            except (KeyError, ValueError) as exc:
                issues.append(_issue(
                    "invalid_expected_contract", str(exc),
                    root_cause="review_profile_error",
                    criterion_id="REVIEW_BASIS",
                    location="review_task.expected_output_contract",
                ))
            else:
                if artifact.get("type") != expected_type:
                    issues.append(_issue(
                        "artifact_type_mismatch",
                        f"artifact type {artifact.get('type')!r} does not match "
                        f"expected type {expected_type!r}",
                        root_cause="invalid_or_incomplete_input",
                        criterion_id="REVIEW_BASIS", location="review_task.artifact.type",
                    ))

    severity_rules = task.get("severity_rules")
    if isinstance(severity_rules, dict):
        for severity in ("minor", "major", "blocker"):
            value = severity_rules.get(severity)
            if isinstance(value, str) and not value.strip():
                issues.append(_issue(
                    "empty_severity_rule", f"severity rule {severity!r} must not be empty",
                    root_cause="review_profile_error",
                    criterion_id="REVIEW_BASIS",
                    location=f"review_task.severity_rules.{severity}",
                ))

    if isinstance(attempt, int) and attempt > 1 and not task.get("previous_decision_ref"):
        issues.append(_issue(
            "missing_revision_history",
            "attempt greater than 1 requires previous_decision_ref",
            root_cause="invalid_or_incomplete_input",
            criterion_id="REVIEW_BASIS", location="review_task.previous_decision_ref",
        ))

    return {"ok": not issues, "issues": issues}


def validate_review_decision(decision: object, task: dict | None = None,
                             previous_decision: dict | None = None) -> dict:
    """Validate decision shape, decision invariants and optional task correlation."""
    errors: list[str] = []
    try:
        shape = contracts.validate(decision, REVIEW_DECISION_CONTRACT)
    except (KeyError, ValueError) as exc:
        return {"ok": False, "errors": [str(exc)]}
    errors.extend(shape["errors"])

    if not isinstance(decision, dict):
        return {"ok": False, "errors": errors}

    findings = decision.get("findings")
    findings = findings if isinstance(findings, list) else []
    advisories = decision.get("advisories")
    advisories = advisories if isinstance(advisories, list) else []
    finding_ids = [item.get("finding_id") for item in findings
                   if isinstance(item, dict) and isinstance(item.get("finding_id"), str)]
    duplicates = _duplicates(finding_ids)
    if duplicates:
        errors.append(f"findings: duplicate finding IDs {sorted(duplicates)}")
    finding_text_fields = (
        "finding_id", "criterion_id", "location", "observed", "required_correction"
    )
    for index, item in enumerate(findings):
        if not isinstance(item, dict):
            continue
        for field in finding_text_fields:
            value = item.get(field)
            if isinstance(value, str) and not value.strip():
                errors.append(f"findings[{index}].{field} must not be empty")
        evidence_refs = item.get("evidence_refs")
        if isinstance(evidence_refs, list) and any(
                isinstance(ref, str) and not ref.strip() for ref in evidence_refs):
            errors.append(f"findings[{index}].evidence_refs contains an empty ref")
    for index, item in enumerate(advisories):
        if not isinstance(item, dict):
            continue
        for field in ("criterion_id", "location", "observation"):
            value = item.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"advisories[{index}].{field} must not be empty")

    closed_ids = decision.get("closed_finding_ids")
    closed_ids = closed_ids if isinstance(closed_ids, list) else []
    if _duplicates([item for item in closed_ids if isinstance(item, str)]):
        errors.append("closed_finding_ids: duplicate IDs")
    overlap = set(finding_ids) & {item for item in closed_ids if isinstance(item, str)}
    if overlap:
        errors.append(f"findings and closed_finding_ids overlap: {sorted(overlap)}")

    verdict = decision.get("decision")
    root_cause = decision.get("root_cause")
    revision_scope = decision.get("revision_scope")
    severities = {
        item.get("severity") for item in findings
        if isinstance(item, dict) and isinstance(item.get("severity"), str)
    }

    for field in ("review_id", "task_id", "logical_review_node", "producer_agent",
                  "artifact_ref", "artifact_version", "review_profile", "summary"):
        value = decision.get(field)
        if isinstance(value, str) and not value.strip():
            errors.append(f"{field} must not be empty")
    if isinstance(decision.get("artifact_ref"), str) \
            and not decision["artifact_ref"].startswith(artifacts.SCHEME):
        errors.append("artifact_ref must use artifact://")
    decision_attempt = decision.get("attempt")
    if isinstance(decision_attempt, int) and not isinstance(decision_attempt, bool) \
            and decision_attempt < 1:
        errors.append("attempt must be at least 1")

    if verdict == "APPROVED":
        if findings:
            errors.append("APPROVED requires empty findings")
        if root_cause is not None:
            errors.append("APPROVED requires null root_cause")
        if revision_scope is not None:
            errors.append("APPROVED requires null revision_scope")
    elif verdict == "REVISE":
        if not findings:
            errors.append("REVISE requires at least one finding")
        if not severities <= {"minor", "major"}:
            errors.append("REVISE permits only minor or major findings")
        if root_cause not in REVISE_ROOT_CAUSES:
            errors.append("REVISE requires producer_error or insufficient_evidence root_cause")
        if not isinstance(revision_scope, dict):
            errors.append("REVISE requires a revision_scope")
        else:
            if revision_scope.get("target_agent") != decision.get("producer_agent"):
                errors.append("revision_scope.target_agent must equal producer_agent")
            scoped = revision_scope.get("finding_ids")
            if isinstance(scoped, list) and _duplicates(
                    [item for item in scoped if isinstance(item, str)]):
                errors.append("revision_scope.finding_ids contains duplicate IDs")
            scoped = {
                item for item in scoped if isinstance(item, str)
            } if isinstance(scoped, list) else set()
            if scoped != set(finding_ids):
                errors.append("revision_scope.finding_ids must match current findings")
    elif verdict == "BLOCKED":
        if "blocker" not in severities:
            errors.append("BLOCKED requires at least one blocker finding")
        if root_cause not in BLOCKED_ROOT_CAUSES:
            errors.append("BLOCKED requires an input, upstream, profile or dependency root_cause")
        if revision_scope is not None:
            errors.append("BLOCKED requires null revision_scope")

    if task is not None:
        correlations = {
            "review_id": "review_id",
            "task_id": "task_id",
            "logical_review_node": "logical_review_node",
            "producer_agent": "producer_agent",
            "review_profile": "review_profile",
            "attempt": "attempt",
        }
        for decision_field, task_field in correlations.items():
            if decision.get(decision_field) != task.get(task_field):
                errors.append(f"{decision_field} does not match ReviewTask")
        artifact = task.get("artifact") if isinstance(task.get("artifact"), dict) else {}
        if decision.get("artifact_ref") != artifact.get("ref"):
            errors.append("artifact_ref does not match ReviewTask")
        if decision.get("artifact_version") != artifact.get("artifact_version"):
            errors.append("artifact_version does not match ReviewTask")

        task_criteria = task.get("acceptance_criteria")
        task_criteria = task_criteria if isinstance(task_criteria, list) else []
        allowed_criteria = {
            item.get("criterion_id") for item in task_criteria
            if isinstance(item, dict) and isinstance(item.get("criterion_id"), str)
        } | RESERVED_CRITERIA
        for item in findings:
            if isinstance(item, dict) and item.get("criterion_id") not in allowed_criteria:
                errors.append(
                    f"finding {item.get('finding_id')!r} uses unauthorized criterion_id "
                    f"{item.get('criterion_id')!r}"
                )
        for item in advisories:
            if isinstance(item, dict) and item.get("criterion_id") not in allowed_criteria:
                errors.append(
                    f"advisory uses unauthorized criterion_id {item.get('criterion_id')!r}"
                )

    attempt = decision.get("attempt")
    if attempt == 1 and closed_ids:
        errors.append("attempt 1 cannot close findings from an earlier decision")
    if previous_decision is not None:
        identity_fields = (
            "review_id", "task_id", "logical_review_node", "producer_agent", "review_profile"
        )
        for field in identity_fields:
            if previous_decision.get(field) != decision.get(field):
                errors.append(f"previous decision {field} does not match current decision")
        previous_attempt = previous_decision.get("attempt")
        if not isinstance(attempt, int) or previous_attempt != attempt - 1:
            errors.append("previous decision attempt must immediately precede current attempt")
        previous_ids = {
            item.get("finding_id") for item in previous_decision.get("findings", [])
            if isinstance(item, dict) and isinstance(item.get("finding_id"), str)
        }
        closed_set = {item for item in closed_ids if isinstance(item, str)}
        if not closed_set <= previous_ids:
            errors.append("closed_finding_ids may contain only findings from previous decision")
        missing = previous_ids - set(finding_ids) - closed_set
        if missing:
            errors.append(f"previous findings disappeared without closure: {sorted(missing)}")

    return {"ok": not errors, "errors": errors}


def _has_audit_identity(task: object) -> bool:
    required = ("review_id", "task_id", "logical_review_node", "producer_agent")
    return isinstance(task, dict) and all(
        isinstance(task.get(field), str) and task[field].strip() for field in required
    )


def _stable_finding_id(task: dict, issue: dict) -> str:
    material = "|".join((
        str(task.get("task_id", "unknown")),
        str(task.get("logical_review_node", "unknown")),
        str(issue["criterion_id"]),
        str(issue["location"]),
        str(issue["type"]),
    ))
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:12].upper()
    return f"RF_{digest}"


def _string_or(value: object, fallback: str) -> str:
    return value if isinstance(value, str) and value.strip() else fallback


def blocked_decision(task: dict, issue: dict) -> dict:
    """Build an auditable BLOCKED decision for a deterministic preflight failure."""
    artifact = task.get("artifact") if isinstance(task.get("artifact"), dict) else {}
    root_cause = issue.get("root_cause")
    if root_cause not in BLOCKED_ROOT_CAUSES:
        root_cause = "invalid_or_incomplete_input"
    artifact_ref = artifact.get("ref")
    if not isinstance(artifact_ref, str) or not artifact_ref.startswith(artifacts.SCHEME):
        artifact_ref = "artifact://unavailable"
    attempt = task.get("attempt")
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
        attempt = 1
    return {
        "schema_version": REVIEW_DECISION_CONTRACT,
        "review_id": _string_or(task.get("review_id"), "unavailable-review"),
        "task_id": _string_or(task.get("task_id"), "unavailable-task"),
        "logical_review_node": _string_or(
            task.get("logical_review_node"), "unavailable-review-node"
        ),
        "reviewer_agent": REVIEWER_AGENT,
        "producer_agent": _string_or(task.get("producer_agent"), "unavailable-producer"),
        "artifact_ref": artifact_ref,
        "artifact_version": _string_or(artifact.get("artifact_version"), "unavailable"),
        "review_profile": _string_or(task.get("review_profile"), "unavailable"),
        "decision": "BLOCKED",
        "findings": [{
            "finding_id": _stable_finding_id(task, issue),
            "criterion_id": issue["criterion_id"],
            "severity": "blocker",
            "location": issue["location"],
            "observed": issue["message"],
            "required_correction": "Correct the review basis or restore the required dependency.",
            "evidence_refs": [],
        }],
        "advisories": [],
        "closed_finding_ids": [],
        "revision_scope": None,
        "root_cause": root_cause,
        "confidence": "high",
        "attempt": attempt,
        "summary": f"Review blocked: {issue['message']}",
    }


def failed_envelope(issue_type: str, message: str) -> dict:
    """Return an execution failure without a decision artifact."""
    return {
        "status": "failed",
        "produced": [],
        "summary": "Universal review execution failed.",
        "issues": [{"severity": "blocker", "type": issue_type, "message": message}],
    }


def _safe_review_name(review_id: str, attempt: int) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", review_id).strip("-")
    return f"{safe or 'review-decision'}-attempt-{attempt}"


def _load_previous_decision(task: dict, *, base=None) -> dict | None:
    ref = task.get("previous_decision_ref")
    if not ref:
        return None
    if not isinstance(ref, str) or not ref.startswith(artifacts.SCHEME):
        raise ValueError("previous_decision_ref must use artifact://")
    previous = artifacts.hydrate(ref, base=base)
    validation = validate_review_decision(previous)
    if not validation["ok"]:
        raise ValueError("previous decision is invalid: " + "; ".join(validation["errors"]))
    return previous


def finalize_review_decision(task: dict | None, decision: dict, *, base=None) -> dict:
    """Validate, persist and wrap one reviewer decision in ``envelope@1``."""
    previous = None
    if task is not None:
        task_validation = validate_review_task(task)
        if not task_validation["ok"]:
            messages = "; ".join(issue["message"] for issue in task_validation["issues"])
            return failed_envelope("invalid_review_task_for_decision", messages)
    if task is not None and task["attempt"] > 1:
        try:
            previous = _load_previous_decision(task, base=base)
        except (OSError, ValueError, KeyError, IndexError) as exc:
            return failed_envelope("invalid_revision_history", str(exc))
    validation = validate_review_decision(decision, task, previous)
    if not validation["ok"]:
        return failed_envelope("invalid_review_decision", "; ".join(validation["errors"]))
    name = _safe_review_name(decision["review_id"], decision["attempt"])
    try:
        ref = artifacts.store(f"reviews/{name}.json", decision, base=base)
    except OSError as exc:
        return failed_envelope("review_decision_persistence_failed", str(exc))
    return {
        "status": "ok",
        "produced": [{
            "type": "review_decision",
            "path": ref,
            "schema_version": REVIEW_DECISION_CONTRACT,
        }],
        "summary": decision["summary"],
        "issues": [],
        "metrics": {
            "decision": decision["decision"],
            "attempt": decision["attempt"],
            "finding_count": len(decision["findings"]),
            "advisory_count": len(decision.get("advisories", [])),
        },
    }


def prepare_review(task: object, *, base=None) -> dict:
    """Validate a task and hydrate its single artifact for an isolated reviewer node."""
    validation = validate_review_task(task)
    if not validation["ok"]:
        if not _has_audit_identity(task):
            messages = "; ".join(issue["message"] for issue in validation["issues"])
            return {"ready": False, "envelope": failed_envelope(
                "invalid_review_task", messages or "ReviewTask lacks audit identity"
            )}
        first = validation["issues"][0]
        decision = blocked_decision(task, first)
        return {"ready": False, "envelope": finalize_review_decision(None, decision, base=base)}

    assert isinstance(task, dict)
    previous = None
    if task["attempt"] > 1:
        try:
            previous = _load_previous_decision(task, base=base)
        except (OSError, ValueError, KeyError, IndexError) as exc:
            issue = _issue(
                "revision_history_unavailable", str(exc),
                root_cause="external_dependency_blocked",
                criterion_id="ARTIFACT_ACCESS",
                location="review_task.previous_decision_ref",
            )
            decision = blocked_decision(task, issue)
            return {"ready": False, "envelope": finalize_review_decision(
                None, decision, base=base
            )}
    try:
        artifact = artifacts.hydrate(task["artifact"]["ref"], base=base)
    except (OSError, ValueError, KeyError, IndexError) as exc:
        issue = _issue(
            "artifact_unavailable", str(exc),
            root_cause="external_dependency_blocked",
            criterion_id="ARTIFACT_ACCESS", location="review_task.artifact.ref",
        )
        decision = blocked_decision(task, issue)
        return {"ready": False, "envelope": finalize_review_decision(task, decision, base=base)}
    try:
        artifact_validation = contracts.validate(artifact, task["expected_output_contract"])
    except (KeyError, ValueError) as exc:
        issue = _issue(
            "artifact_contract_unavailable", str(exc),
            root_cause="external_dependency_blocked",
            criterion_id="EXTERNAL_DEPENDENCY",
            location="review_task.expected_output_contract",
        )
        decision = blocked_decision(task, issue)
        return {"ready": False, "envelope": finalize_review_decision(task, decision, base=base)}
    return {
        "ready": True,
        "task": task,
        "artifact": artifact,
        "artifact_validation": artifact_validation,
        "previous_decision": previous,
    }


def validate_reviewer_envelope(task: dict, envelope: object, *, base=None) -> dict:
    """Validate an envelope returned by a host reviewer executor and its decision artifact."""
    task_validation = validate_review_task(task)
    if not task_validation["ok"]:
        messages = "; ".join(issue["message"] for issue in task_validation["issues"])
        return failed_envelope("invalid_review_task_for_envelope", messages)
    try:
        shape = contracts.validate_envelope(envelope)
    except (KeyError, ValueError) as exc:
        return failed_envelope("envelope_contract_unavailable", str(exc))
    if not shape["ok"]:
        return failed_envelope("invalid_reviewer_envelope", "; ".join(shape["errors"]))
    assert isinstance(envelope, dict)
    produced = envelope.get("produced")
    if envelope.get("status") == "failed":
        if produced == []:
            return envelope
        return failed_envelope(
            "invalid_reviewer_envelope", "failed reviewer envelope cannot produce artifacts"
        )
    if envelope.get("status") != "ok":
        return failed_envelope(
            "invalid_reviewer_envelope",
            "reviewer envelope must use status ok for a decision or failed without a decision",
        )
    if not isinstance(produced, list) or len(produced) != 1:
        return failed_envelope(
            "invalid_reviewer_envelope", "reviewer envelope must produce exactly one artifact"
        )
    descriptor = produced[0]
    if (descriptor.get("type") != "review_decision"
            or descriptor.get("schema_version") != REVIEW_DECISION_CONTRACT):
        return failed_envelope(
            "invalid_reviewer_envelope", "produced artifact must be review_decision@1"
        )
    try:
        decision = artifacts.hydrate(descriptor["path"], base=base)
    except (OSError, ValueError, KeyError, IndexError) as exc:
        return failed_envelope("unreadable_review_decision", str(exc))
    previous = None
    if task["attempt"] > 1:
        try:
            previous = _load_previous_decision(task, base=base)
        except (OSError, ValueError, KeyError, IndexError) as exc:
            return failed_envelope("invalid_revision_history", str(exc))
    validation = validate_review_decision(decision, task, previous)
    if not validation["ok"]:
        return failed_envelope("invalid_review_decision", "; ".join(validation["errors"]))
    return envelope


def execute_review_task(task: object, reviewer_executor: Callable | None, *, base=None) -> dict:
    """Prepare one review, invoke an injected host executor and validate its envelope.

    ``reviewer_executor`` receives ``(review_task, review_context)``. The context contains the
    hydrated artifact, deterministic artifact validation and previous decision when present.
    The function does not choose a model or host. A missing executor becomes an explicit
    dependency block.
    """
    prepared = prepare_review(task, base=base)
    if not prepared["ready"]:
        return prepared["envelope"]
    assert isinstance(task, dict)
    if reviewer_executor is None:
        issue = _issue(
            "reviewer_executor_unavailable", "no reviewer executor is configured",
            root_cause="external_dependency_blocked",
            criterion_id="EXTERNAL_DEPENDENCY", location="reviewer_executor",
        )
        return finalize_review_decision(task, blocked_decision(task, issue), base=base)
    try:
        review_context = {
            "artifact": prepared["artifact"],
            "artifact_validation": prepared["artifact_validation"],
            "previous_decision": prepared["previous_decision"],
        }
        envelope = reviewer_executor(task, review_context)
    except Exception as exc:
        return failed_envelope("reviewer_executor_failed", str(exc))
    return validate_reviewer_envelope(task, envelope, base=base)
