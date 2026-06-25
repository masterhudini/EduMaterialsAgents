"""g03 producer write path + dual-input front door.

g03 is the first place the two upstream sides meet: the lecture skeleton from g01
(``lecture_baseline@1``) and the research hand-off from g02 — either the human-gated
``user_approved_research_bundle@1`` or, on the deterministic evidence_without_claim_assessment path,
``solution_input_candidate@1`` (selected by ``research_bundle_kind``).
Neither is the other graph's full state — each is a purpose-built, targeted slice. This module
builds the thin composite boundary (``solution_graph_input@1``, a pair of refs) the engine drives
on, and persists the producer artifact server-side. Pure stdlib.
"""
from __future__ import annotations

import sys as _sys
import pathlib as _pl
import json
import uuid

_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))  # -> shared/scripts

from core import artifacts, contracts, finalize  # noqa: E402

INPUT_CONTRACT = "solution_graph_input@1"
LECTURE_CONTRACT = "lecture_baseline@1"
RESEARCH_CONTRACT = "user_approved_research_bundle@1"
SCOUT_RESEARCH_CONTRACT = "solution_input_candidate@1"
# Map research_bundle_kind -> the g02 contract the research side satisfies.
RESEARCH_CONTRACT_BY_KIND = {
    "user_approved_research_bundle": RESEARCH_CONTRACT,
    "solution_input_candidate": SCOUT_RESEARCH_CONTRACT,
}


def _research_contract_and_kind(request: dict) -> tuple[str, str]:
    """Pick the g02 research contract + kind for this input.

    Explicit ``research_bundle_kind`` wins; otherwise infer from an inline bundle's
    ``schema_version``; otherwise default to the legacy reviewed bundle. evidence_without_claim_assessment
    runs hand off ``solution_input_candidate@1`` instead of the human-gated bundle.
    """
    kind = request.get("research_bundle_kind")
    if kind in RESEARCH_CONTRACT_BY_KIND:
        return RESEARCH_CONTRACT_BY_KIND[kind], kind
    inline = request.get("research_bundle")
    if isinstance(inline, dict):
        version = inline.get("schema_version")
        if version == SCOUT_RESEARCH_CONTRACT:
            return SCOUT_RESEARCH_CONTRACT, "solution_input_candidate"
        if version == RESEARCH_CONTRACT:
            return RESEARCH_CONTRACT, "user_approved_research_bundle"
    return RESEARCH_CONTRACT, "user_approved_research_bundle"


def finalize_blueprint(task_id: str, blueprint: dict, *, base=None) -> dict:
    """G03-A01 write path: persist a validated solution_blueprint@1; return envelope@1."""
    return finalize.artifact_envelope(task_id, blueprint, contract="solution_blueprint@1",
                                      type_name="solution_blueprint", subdir="blueprint",
                                      namespace="g03", base=base, unknown_task="SOLUTION_UNKNOWN")


def _ensure_ref(request: dict, ref_key: str, inline_key: str, contract: str, *, base) -> str:
    """Resolve one side of the boundary to a stored artifact ref, validating its contract.

    Accepts either an existing ``*_ref`` (passed through) or an inline object (validated + stored).
    The inline path keeps mocks/tests self-contained without pre-populating the store.
    """
    ref = request.get(ref_key)
    if isinstance(ref, str) and ref:
        return ref
    inline = request.get(inline_key)
    if not isinstance(inline, dict):
        raise ValueError(f"solution_graph_input requires {ref_key!r} or inline {inline_key!r}")
    res = contracts.validate(inline, contract)
    if not res["ok"]:
        raise ValueError(f"inline {inline_key} is not a valid {contract}: " + "; ".join(res["errors"]))
    tid = inline.get("task_id") or "G03_INPUT"
    return artifacts.store(f"g03/inputs/{tid}.{inline_key}.{uuid.uuid4().hex[:8]}.json", inline, base=base)


def build_solution_input(request: dict, *, base=None) -> str:
    """Build + store the thin ``solution_graph_input@1`` composite; return its artifact ref.

    ``request`` carries the two sides as refs or inline objects:
    ``{lecture_baseline_ref|lecture_baseline, research_bundle_ref|research_bundle, task_id?,
    output_language?}``.
    """
    lb_ref = _ensure_ref(request, "lecture_baseline_ref", "lecture_baseline", LECTURE_CONTRACT, base=base)
    research_contract, research_kind = _research_contract_and_kind(request)
    rb_ref = _ensure_ref(request, "research_bundle_ref", "research_bundle", research_contract, base=base)
    task_id = request.get("task_id")
    output_language = request.get("output_language")
    if not task_id or not output_language:
        lb = artifacts.hydrate(lb_ref, base=base)
        task_id = task_id or lb.get("task_id") or "G03_INPUT"
        output_language = output_language or lb.get("output_language") or "English"
    composite = {
        "schema_version": INPUT_CONTRACT, "task_id": task_id, "output_language": output_language,
        "lecture_baseline_ref": lb_ref, "research_bundle_ref": rb_ref,
        "research_bundle_kind": research_kind,
    }
    res = contracts.validate(composite, INPUT_CONTRACT)
    if not res["ok"]:
        raise ValueError("built solution_graph_input is invalid: " + "; ".join(res["errors"]))
    return artifacts.store(f"handoffs/{task_id}.solution_input.json", composite, base=base)


def resolve_context(path_or_ref, *, base=None):
    """Front-door normalizer: build the composite from a request (dict or *.json path); pass an
    existing ``solution_graph_input@1`` artifact ref through unchanged."""
    if isinstance(path_or_ref, dict):
        return build_solution_input(path_or_ref, base=base)
    s = str(path_or_ref)
    if s.startswith("artifact://"):
        return path_or_ref
    request = json.loads(_pl.Path(s).read_text(encoding="utf-8"))
    return build_solution_input(request, base=base)
