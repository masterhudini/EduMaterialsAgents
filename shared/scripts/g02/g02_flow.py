"""g02 (Research Graph) flow — a thin wrapper over the generic ``core.engine``.

The engine drives the manifest (single source of truth: shared/graphs/g02.graph.json) and the
reviewer/gate/checkpoint machinery. This module supplies only what is g02-specific: the boundary
contracts, the per-node scoped input (G02-A01 gets a typed research_planner_input@1), the thin
stub exit bundle, and the human source-selection gate hooks. The public API
(run / front_door / finalize / node_input_map / load_context / scoped_input / _load_any /
terminal_gate_handler / GRAPH_ID / INPUT_CONTRACT / OUTPUT_CONTRACT / _cli) is preserved for the
MCP server, the Codex runner and the tests.

Run it directly:
    python3 shared/scripts/g02/g02_flow.py run mocks/g02/research_graph_input.json
"""
from __future__ import annotations

import sys as _sys
import pathlib as _pl

# Make `core` / `g02` importable whether run as a module or as a script.
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))

from core import artifacts, contracts, event_log, gate, graphs, handoff, paths  # noqa: E402
from core import state as st  # noqa: E402
from core import validate_state as vs  # noqa: E402
from g02.runners.stub import stub_node_runner  # noqa: E402
from g02 import planner  # noqa: E402
from g02 import source_selection  # noqa: E402

GRAPH_ID = "g02"
INPUT_CONTRACT = "research_graph_input@1"
OUTPUT_CONTRACT = "user_approved_research_bundle@1"

_SOURCE_GATE = "user-source-selection-gate"
_SOURCE_INDEX_NODE = "g02-a05-candidate-source-index"
_SOURCE_INDEX_TYPE = "candidate_source_index"
_SOURCE_INDEX_CONTRACT = "candidate_source_index@1"


def _scoped_input(node: dict, rgi: dict) -> dict:
    """G02-A01 receives a typed research_planner_input@1; other producers get the boundary input
    in this no-op harness (their approved upstream artifacts do not exist here)."""
    if node.get("name") == planner.PLANNER_AGENT:
        return planner.scope_planner_input(rgi)
    return rgi


def _stub_bundle() -> dict:
    """Minimal UserApprovedResearchBundle that satisfies the output contract."""
    return {
        "approved_research_summary_ref": "artifact://g02/research_summary.approved.md",
        "approved_update_findings": [],
        "approved_optional_findings": [],
        "rejected_findings": [],
        "unresolved_claim_policy": {"action": "move_to_speaker_note_or_remove"},
        "solution_handoff": {
            "evidence_cards": [], "slide_impact_cards": [],
            "source_cards": [], "unresolved_claim_cards": [],
        },
    }


def _source_index_ref(produced_refs: dict, base):
    stored = produced_refs.get(_SOURCE_INDEX_NODE)
    if not isinstance(stored, str):
        return None
    return engine._produced_artifact_ref(stored, _SOURCE_INDEX_TYPE, _SOURCE_INDEX_CONTRACT, base=base)


def _gate_prepare(gname: str, produced_refs: dict, base) -> dict:
    """Attach the source-selection prompt to the gate payload when the index is ready."""
    if gname != _SOURCE_GATE:
        return {}
    ref = _source_index_ref(produced_refs, base)
    if not ref:
        return {}
    prepared = source_selection.prepare_source_selection(ref, base=base)
    if prepared.get("ready"):
        return {"payload": {"source_selection": prepared["gate_prompt"]}}
    return {}


def _gate_finalize(gname: str, decision, produced_refs: dict, base):
    """Resolve / validate the human-approved source set after the source-selection gate."""
    if gname != _SOURCE_GATE:
        return None
    ref = _source_index_ref(produced_refs, base)
    if not ref:
        return None
    approved_ref = decision.get("human_approved_source_set_ref") if isinstance(decision, dict) else None
    if (isinstance(decision, dict) and not approved_ref
            and isinstance(decision.get("selection"), dict)
            and isinstance(decision.get("confirmation_token"), str)):
        finalized = source_selection.finalize_source_selection(
            ref, decision["selection"], decision["confirmation_token"], base=base)
        approved_ref = next((item.get("path") for item in finalized.get("produced", [])
                             if item.get("type") == "human_approved_source_set"), None)
    if isinstance(approved_ref, str):
        approved_set = artifacts.hydrate(approved_ref, base=base)
        validation = contracts.validate(approved_set, "human_approved_source_set@1")
        if not validation["ok"]:
            raise ValueError("invalid human approved source set: " + "; ".join(validation["errors"]))
        return approved_ref
    return None


SPEC = engine.EngineSpec(
    graph_id=GRAPH_ID,
    input_contract=INPUT_CONTRACT,
    output_contract=OUTPUT_CONTRACT,
    scoped_input=_scoped_input,
    stub_exit_bundle=_stub_bundle,
    input_state_field="research_graph_input",
    output_state_field="user_approved_research_bundle",
    artifact_namespace="research",
    emit_name="research_bundle",
    gate_prepare=_gate_prepare,
    gate_finalize=_gate_finalize,
)


# ---- preserved public API (bound to the g02 spec) ------------------------

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


def scoped_input(node, rgi):
    return _scoped_input(node, rgi)


def _load_any(path_or_ref, *, base=None):
    return engine._load_any(SPEC, path_or_ref, base=base)


terminal_gate_handler = engine.terminal_gate_handler


def _cli(argv):
    from g02.runners.codex import codex_node_runner
    return engine.make_cli(SPEC, codex_runner=codex_node_runner)(argv)


if __name__ == "__main__":
    raise SystemExit(_cli(_sys.argv[1:]))
