"""g03 (Solution Graph) flow — a thin wrapper over the generic ``core.engine``.

The engine drives the manifest (single source of truth: shared/graphs/g03.graph.json) and the
reviewer/gate/checkpoint machinery. This module supplies only what is g03-specific: the boundary
contracts and the thin exit bundle. Solution consumes exactly what the Research Graph approved
(``user_approved_research_bundle@1``) and produces the approved deliverable
(``solution_blueprint@1``). Unlike g01 there is no upload/PDF seam — the input is already a typed
bundle — so g03 has no ``context_resolver`` and no ``deterministic_node``.

Run it directly:
    python3 shared/scripts/g03/g03_flow.py run mocks/g03/user_approved_research_bundle.json
"""
from __future__ import annotations

import sys as _sys
import pathlib as _pl

# Make `core` / `g03` importable whether run as a module or as a script.
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))

from core import engine  # noqa: E402

GRAPH_ID = "g03"
INPUT_CONTRACT = "user_approved_research_bundle@1"
OUTPUT_CONTRACT = "solution_blueprint@1"


def _scoped_input(node: dict, inp: dict) -> dict:
    """Thin harness: the architect receives the approved research bundle (compact cards + refs)."""
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
    input_state_field="user_approved_research_bundle",
    output_state_field="solution_blueprint",
    artifact_namespace="g03",
    emit_name="solution_blueprint",
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
