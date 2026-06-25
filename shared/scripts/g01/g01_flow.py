"""g01 (Intake / Understanding Graph) flow — a thin wrapper over the generic ``core.engine``.

The engine drives the manifest (single source of truth: shared/graphs/g01.graph.json) and the
reviewer/gate/checkpoint machinery. This module supplies only what is g01-specific: the boundary
contracts and the thin exit bundle. Intake produces exactly what the Research Graph consumes:
``research_graph_input@1``. In this no-op wiring harness the synthesizer is a stub, so the exit
bundle is a minimal valid research_graph_input@1.

Run it directly:
    python3 shared/scripts/g01/g01_flow.py run mocks/g01/intake_graph_input.json
"""
from __future__ import annotations

import sys as _sys
import pathlib as _pl

# Make `core` / `g01` importable whether run as a module or as a script.
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))

from core import engine  # noqa: E402
from g01 import intake, pdf_extract  # noqa: E402

GRAPH_ID = "g01"
INPUT_CONTRACT = "intake_graph_input@1"
OUTPUT_CONTRACT = "research_graph_input@1"
GATE_DECISIONS_CONTRACT = "intake_gate_decisions@1"


def _scoped_input(node: dict, inp: dict) -> dict:
    """Thin harness: every producer receives the boundary input. Real scoping (slide views ->
    understanding -> synthesizer) is added with the producers."""
    return inp


def _stub_intake_output() -> dict:
    """Minimal valid research_graph_input@1 — the approved intake handoff to the Research Graph."""
    return {
        "schema_version": "research_graph_input@1",
        "task_id": "INTAKE_STUB_001",
        "user_approved_context": {
            "audience_level": "master",
            "course_name": "Intake Stub Course",
            "teaching_goal": "refresh and improve logical flow",
        },
        "approved_domains": [{"domain_id": "D1", "label": "primary domain"}],
        "approved_research_scope": {
            "verify_claims": {"priority": ["high"]},
            "include_recent_developments": True,
            "include_canonical_sources": True,
            "include_didactic_examples": True,
            "recency_window_years": 5,
        },
        "research_drivers": [{
            "driver_id": "DRV_001", "driver_type": "claim", "priority": "high",
            "purpose": "Verify the primary approved claim.",
            "related_claims": ["CLM_001"], "related_concepts": ["C1"],
            "related_flow_issues": [], "related_update_needs": [],
        }],
        "claim_cards": [{"claim_id": "CLM_001", "text": "Primary approved claim from intake."}],
        "concept_context_cards": [{"concept_id": "C1", "label": "Core concept"}],
        "selected_flow_issue_cards": [],
        "selected_update_need_cards": [],
        "existing_source_cards": [],
        "constraints": {
            "max_topics": 4, "candidate_limit_per_topic": 12, "no_new_coverage_passes": 2,
            "allowed_languages": ["en"], "allowed_work_types": ["article"],
            "year_from": None, "year_to": None,
        },
        "selection_profile": {
            "candidate_pool_target_per_topic": 8,
            "minimum_sources_per_required_role": 1,
            "open_access_preference": "preferred",
        },
        "locked_sections": [],
        "artifact_refs_for_lazy_hydration": {},
        "output_language": "English",
    }


def _deterministic_node(node: dict, ctx: dict, log):
    """In-process executor for deterministic g01 nodes; return None to defer a node to host/codex.

    G01-A01 is a pure technical PDF->SlideViews conversion, so it runs in-process (no LLM, no
    sandbox write) for both the codex runner and the host-driven (pause_on_node) path.
    """
    if node.get("name") != "g01-a01-pdf-intake":
        return None
    try:
        views = pdf_extract.slide_views(ctx.get("input") or {}, store=True)
    except Exception as exc:
        return {"status": "failed", "produced": [],
                "summary": f"{node['name']}: deterministic slide extraction failed",
                "issues": [{"severity": "blocker", "type": "deterministic_pdf_intake",
                            "message": str(exc)}]}
    extraction_status = views.get("source_extraction_status")
    issues = [] if extraction_status in {"ok", "degraded"} else [{
        "severity": "blocker", "type": "pdf_text_extraction",
        "message": "; ".join(views.get("warnings") or ["PDF text extraction did not complete."])}]
    status = "ok" if extraction_status == "ok" else (
        "degraded" if extraction_status == "degraded" else "failed")
    return {
        "status": status,
        "produced": [{"type": "slide_views", "path": views.get("slide_views_ref", ""),
                      "schema_version": "slide_views@1"}],
        "summary": f"{node['name']}: produced {views.get('slide_count', 0)} slide views "
                   f"from PDF extraction status {extraction_status}",
        "issues": issues,
        "artifact": views,
    }


def _gate_finalize(gname: str, decision: dict, produced_refs: dict, base=None):
    """Persist the user intake gate decisions as intake_gate_decisions@1 so a03/a04 receive them
    through ``upstream`` (the gate runs before both). Returns the stored ref, or None when the
    decision is not a gate-decisions object (e.g. the auto-approve stub ``{"auto": True}``) — that
    keeps the no-LLM wiring harness behaving exactly as before.
    """
    if not isinstance(decision, dict) or decision.get("schema_version") != GATE_DECISIONS_CONTRACT:
        return None
    env = intake.finalize_gate_decisions(decision.get("task_id"), decision, base=base)
    if env.get("status") != "ok":
        return None
    return (env.get("produced") or [{}])[0].get("path")


SPEC = engine.EngineSpec(
    graph_id=GRAPH_ID,
    input_contract=INPUT_CONTRACT,
    output_contract=OUTPUT_CONTRACT,
    scoped_input=_scoped_input,
    stub_exit_bundle=_stub_intake_output,
    input_state_field="intake_graph_input",
    output_state_field="research_graph_input",
    artifact_namespace="g01",
    emit_name="intake_bundle",
    context_resolver=intake.resolve_context,   # a *.pdf path is uploaded into the store first
    deterministic_node=_deterministic_node,    # a01 runs in-process; a02/a03 yield to the host
    gate_finalize=_gate_finalize,              # persist gate decisions -> upstream for a03/a04
)


def run(input_ref=None, **kwargs):
    return engine.run(SPEC, input_ref, **kwargs)


def front_door(path_or_ref, *, base=None):
    return engine.front_door(SPEC, path_or_ref, base=base)


def finalize(bundle_path, *, base=None):
    return engine.finalize(SPEC, bundle_path, base=base)


def node_input_map(rgi, manifest):
    return engine.node_input_map(SPEC, rgi, manifest)


def load_context(path, *, validate=True):
    return engine.load_context(SPEC, path, validate=validate)


def scoped_input(node, inp):
    return _scoped_input(node, inp)


def _load_any(path_or_ref, *, base=None):
    return engine._load_any(SPEC, path_or_ref, base=base)


terminal_gate_handler = engine.terminal_gate_handler


def make_g01_codex_runner(**options):
    """Codex runner for g01 with deterministic technical PDF intake.

    G01-A01 is a pure technical conversion step. Running it as an LLM worker makes Codex call back
    into MCP for a deterministic operation and can be cancelled by the host. Execute it in-process
    and reserve Codex workers for semantic/reviewer nodes.
    """
    from runners.codex import make_codex_runner

    codex_runner = make_codex_runner(GRAPH_ID, **options)

    def runner(node: dict, ctx: dict, log) -> dict:
        env = _deterministic_node(node, ctx, log)   # g01-a01 in-process; others -> Codex worker
        return env if env is not None else codex_runner(node, ctx, log)

    return runner


def _upload_cli(argv):
    import argparse
    import json
    p = argparse.ArgumentParser(
        prog="g01_flow.py upload",
        description="Copy a PDF into the artifact store and emit a validated intake_graph_input@1.")
    p.add_argument("pdf", help="path to a lecture PDF")
    p.add_argument("--title"); p.add_argument("--course")
    p.add_argument("--audience"); p.add_argument("--language")
    a = p.parse_args(argv)
    hints = {k: v for k, v in (("title", a.title), ("course", a.course),
                               ("audience", a.audience), ("language", a.language)) if v}
    try:
        out = intake.upload(a.pdf, hints=hints or None)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=_sys.stderr)
        return 1
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def _cli(argv):
    if argv and argv[0] == "upload":      # g01-specific seam: a raw PDF -> boundary contract
        return _upload_cli(argv[1:])
    return engine.make_cli(SPEC, codex_runner=make_g01_codex_runner())(argv)


if __name__ == "__main__":
    raise SystemExit(_cli(_sys.argv[1:]))
