"""End-to-end workflow across all three graphs: Intake (g01) -> Research (g02) -> Solution (g03).

Each graph stays independent and host-driven; this module owns only the BRIDGES between their
boundaries — the small, deterministic glue that turns one graph's output into the next graph's
input, honoring the targeted-context rule (cards + ``artifact://`` refs, never full state):

  g01 ──research_graph_input@1──────────────────────────────► g02
  g01 ──lecture_baseline@1──────────────┐
  g02 ──user_approved_research_bundle@1─┴──solution_graph_input@1──► g03 ──solution_blueprint@1──►

g01 has TWO exits: ``research_graph_input@1`` (its emitted handoff, straight into g02) and
``lecture_baseline@1`` (the a04 node artifact, the lecture skeleton g03 needs). The real-host path
(the orchestrate-workflow skill) drives each graph host-driven and captures those refs as it goes;
this module's ``run_stub`` chains the three deterministically for a no-LLM wiring smoke. Pure stdlib.

CLI:
    python3 shared/scripts/workflow.py run-stub mocks/g01/intake_graph_input.json
"""
from __future__ import annotations

import sys as _sys
import pathlib as _pl

_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[0]))  # -> shared/scripts

from core import artifacts, contracts  # noqa: E402
from g01 import g01_flow  # noqa: E402
from g02 import g02_flow  # noqa: E402
from g03 import g03_flow, solution  # noqa: E402


# ---- bridges (the only cross-graph glue) ---------------------------------

def bridge_g01_to_g02(g01_handoff_ref: str) -> str:
    """g01's emitted handoff IS ``research_graph_input@1`` — exactly g02's boundary input. Pass it
    through g02's front door (validates + registers) and return the g02 input ref."""
    return g02_flow.front_door(g01_handoff_ref)["ref"]


def bridge_to_g03(lecture_baseline_ref: str, research_bundle_ref: str, *, base=None) -> str:
    """Join g01's lecture_baseline (01) and g02's approved bundle (02) into g03's thin composite
    boundary (``solution_graph_input@1``) and return its ref."""
    return solution.build_solution_input(
        {"lecture_baseline_ref": lecture_baseline_ref, "research_bundle_ref": research_bundle_ref},
        base=base,
    )


def _validated_ref(ref, contract, *, base=None) -> str:
    artifact = artifacts.hydrate(ref, base=base)
    check = contracts.validate(artifact, contract)
    if not check["ok"]:
        raise ValueError(f"{contract} bridge artifact is invalid: " + "; ".join(check["errors"]))
    return ref


# ---- deterministic end-to-end (no LLM) -----------------------------------

def run_stub(intake_context, *, base=None) -> dict:
    """Chain all three graphs with no-op stub nodes (no LLM) to prove the boundaries connect.

    g01 and g02 produce their thin stub exits; g01's lecture_baseline is a hosted-node artifact (a
    no-op in stub mode), so a minimal stub stands in for the wiring check. Returns the refs at every
    boundary plus the final ``solution_blueprint@1`` descriptor."""
    # g01 -> research_graph_input@1
    g01_out = g01_flow.run(g01_flow.front_door(intake_context, base=base)["ref"], base=base)
    rgi_ref = g01_out["ref"]
    _validated_ref(rgi_ref, "research_graph_input@1", base=base)

    # g01 -> lecture_baseline@1 (hosted a04 is a no-op in stub mode; stand in a minimal valid one)
    rgi = artifacts.hydrate(rgi_ref, base=base)
    lecture_baseline = _stub_lecture_baseline(rgi)
    lb_ref = artifacts.store(f"g01/baseline/{rgi['task_id']}.stub.json", lecture_baseline, base=base)

    # g01 -> g02 -> user_approved_research_bundle@1
    g02_input_ref = bridge_g01_to_g02(rgi_ref)
    g02_out = g02_flow.run(g02_input_ref, base=base)          # reviewed=False stub path
    bundle_ref = g02_out["ref"]
    _validated_ref(bundle_ref, "user_approved_research_bundle@1", base=base)

    # {g01 lecture_baseline + g02 bundle} -> g03 -> solution_blueprint@1
    g03_input_ref = bridge_to_g03(lb_ref, bundle_ref, base=base)
    g03_out = g03_flow.run(g03_input_ref, base=base)
    _validated_ref(g03_out["ref"], "solution_blueprint@1", base=base)

    return {
        "status": "completed",
        "intake_input": rgi_ref,
        "lecture_baseline": lb_ref,
        "research_bundle": bundle_ref,
        "solution_graph_input": g03_input_ref,
        "solution_blueprint": g03_out["ref"],
    }


def _stub_lecture_baseline(rgi: dict) -> dict:
    return {
        "schema_version": "lecture_baseline@1",
        "task_id": rgi.get("task_id", "WORKFLOW_STUB"),
        "output_language": rgi.get("output_language", "English"),
        "lecture": {"title": "Workflow stub lecture", "course": "Workflow"},
        "slides": [{"slide_id": "p001", "order": 1, "title": "Stub slide",
                    "claim_ids": [], "concept_ids": [], "locked": False}],
        "sections": [], "flow_issues": [], "locked_sections": [],
    }


def _cli(argv):
    import argparse
    import json
    p = argparse.ArgumentParser(
        prog="workflow.py",
        description="Run the full Intake -> Research -> Solution workflow (stub wiring smoke).")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("run-stub", help="chain all three graphs with no-op stub nodes (no LLM)")
    sp.add_argument("context", help="path or artifact:// ref to an intake_graph_input bundle")
    a = p.parse_args(argv)
    try:
        out = run_stub(a.context)
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=_sys.stderr)
        return 1
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli(_sys.argv[1:]))
