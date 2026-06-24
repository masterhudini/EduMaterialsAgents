"""g03 (Solution Graph) flow — a thin wrapper over the generic ``core.engine``.

The engine drives the manifest (single source of truth: shared/graphs/g03.graph.json) and the
reviewer/gate/checkpoint machinery. This module supplies only what is g03-specific: the boundary
contracts and the thin exit bundle. g03 is the first place the two upstream sides meet, so its
boundary input is a thin composite (``solution_graph_input@1``): a ref to g01's
``lecture_baseline@1`` (the lecture skeleton) plus a ref to g02's
``user_approved_research_bundle@1`` (the approved research). The ``context_resolver`` builds that
composite from a front-door request. It produces the approved deliverable (``solution_blueprint@1``).

Run it directly:
    python3 shared/scripts/g03/g03_flow.py run mocks/g03/solution_request.json
"""
from __future__ import annotations

import sys as _sys
import pathlib as _pl

# Make `core` / `g03` importable whether run as a module or as a script.
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))

from core import engine  # noqa: E402
from g03 import solution  # noqa: E402

GRAPH_ID = "g03"
INPUT_CONTRACT = "solution_graph_input@1"
OUTPUT_CONTRACT = "solution_blueprint@1"


def _scoped_input(node: dict, inp: dict) -> dict:
    """Thin harness: the architect receives the composite boundary (the two upstream refs); it
    hydrates lecture_baseline (01) and the research bundle (02) and joins them itself."""
    return inp


def _stub_solution_output() -> dict:
    """Minimal valid solution_blueprint@1 — the approved Solution Graph deliverable."""
    return {
        "schema_version": "solution_blueprint@1",
        "task_id": "SOLUTION_STUB_001",
        "output_language": "English",
        "lecture_outline": [
            {"section_id": "S1", "title": "Stub section", "summary": "Placeholder outline section.",
             "slide_ids": []},
        ],
        "applied_updates": [],
        "deferred_items": [],
        "source_attribution": [],
    }


SPEC = engine.EngineSpec(
    graph_id=GRAPH_ID,
    input_contract=INPUT_CONTRACT,
    output_contract=OUTPUT_CONTRACT,
    scoped_input=_scoped_input,
    stub_exit_bundle=_stub_solution_output,
    input_state_field="solution_graph_input",
    output_state_field="solution_blueprint",
    artifact_namespace="g03",
    emit_name="solution_blueprint",
    context_resolver=solution.resolve_context,   # build the {01 ref, 02 ref} composite at the door
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


def make_g03_codex_runner(**options):
    """Codex runner for g03. No deterministic nodes — every producer is an LLM/reviewer worker."""
    from runners.codex import make_codex_runner
    return make_codex_runner(GRAPH_ID, **options)


def _cli(argv):
    return engine.make_cli(SPEC, codex_runner=make_g03_codex_runner())(argv)


if __name__ == "__main__":
    raise SystemExit(_cli(_sys.argv[1:]))
