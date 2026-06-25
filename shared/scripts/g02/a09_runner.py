"""Run the obligatory G02-A09 pass through a host model executor.

A09 is the verifier/refiner of the deterministic evidence_without_claim_assessment baseline. This
module prepares the bounded deep-dive windows, builds one ``a09_synthesis_task@1``,
invokes an injected or external executor (opus/medium), and finalizes the
``solution_input_candidate@1`` that ends Graph 02. The model pass runs by
default; if the executor is missing or fails, it falls back to the deterministic
baseline and marks ``a09_model_pass=false`` so the difference is auditable. Full
PDFs are never read.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from g02 import a09_synthesis  # noqa: E402
from g02.a07_runner import command_executor, parse_model_json  # noqa: E402

__all__ = [
    "command_executor",
    "parse_model_json",
    "build_a09_task",
    "run_a09",
]


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    tmp.replace(path)


def build_a09_task(
    a07_reviews: str | Path | dict,
    *,
    intake: str | Path | dict | None = None,
    max_deep_dive_sources: int = a09_synthesis.DEFAULT_MAX_DEEP_DIVE_SOURCES,
    deep_dive_windows: int = a09_synthesis.A09_DEEP_DIVE_WINDOWS,
    deep_dive_chars: int = a09_synthesis.A09_DEEP_DIVE_CHARS,
) -> dict:
    """Prepare synthesis input, bounded deep-dive windows and one A09 model task."""
    if deep_dive_windows < 1 or deep_dive_windows > a09_synthesis.A09_DEEP_DIVE_WINDOWS:
        raise ValueError("A09 deep_dive_windows must be between 1 and 8")
    if deep_dive_chars < 1 or deep_dive_chars > a09_synthesis.A09_DEEP_DIVE_CHARS:
        raise ValueError("A09 deep_dive_chars must be between 1 and 1200")
    prepared = a09_synthesis.prepare_a09_synthesis(
        a07_reviews,
        intake=intake,
        max_deep_dive_sources=max_deep_dive_sources,
    )
    synthesis_input = prepared["synthesis_input"]
    deep_dive = a09_synthesis.gather_deep_dive_windows(
        synthesis_input["reviews"],
        synthesis_input["deep_dive_requests"],
        max_windows=deep_dive_windows,
        max_chars=deep_dive_chars,
    )
    task = a09_synthesis.build_a09_synthesis_task(synthesis_input, deep_dive)
    return {"synthesis_input": synthesis_input, "deep_dive": deep_dive, "task": task}


def run_a09(
    a07_reviews: str | Path | dict,
    executor=None,
    *,
    intake: str | Path | dict | None = None,
    max_deep_dive_sources: int = a09_synthesis.DEFAULT_MAX_DEEP_DIVE_SOURCES,
    deep_dive_windows: int = a09_synthesis.A09_DEEP_DIVE_WINDOWS,
    deep_dive_chars: int = a09_synthesis.A09_DEEP_DIVE_CHARS,
    artifact_version: str = "1.0.0",
    output_path: str | Path | None = None,
    fail_fast: bool = False,
) -> dict:
    """Run A09 verify/refine through ``executor`` and finalize the G02 contract.

    The model pass is obligatory by default. On executor absence or failure the
    deterministic baseline is finalized instead and flagged in the result.
    """
    built = build_a09_task(
        a07_reviews,
        intake=intake,
        max_deep_dive_sources=max_deep_dive_sources,
        deep_dive_windows=deep_dive_windows,
        deep_dive_chars=deep_dive_chars,
    )
    synthesis_input = built["synthesis_input"]
    deep_dive = built["deep_dive"]
    model_output = None
    executor_error = "executor_unavailable" if executor is None else None
    if executor is not None:
        try:
            model_output = executor(built["task"])
            if not isinstance(model_output, dict) or not model_output:
                raise ValueError("A09 executor must return a non-empty JSON object")
            model_output = a09_synthesis.validate_a09_output(model_output)
        except Exception as exc:  # noqa: BLE001
            if fail_fast:
                raise
            model_output = None
            executor_error = f"{type(exc).__name__}: {exc}"
    solution = a09_synthesis.finalize_a09_solution(
        synthesis_input,
        model_output,
        deep_dive=deep_dive,
        artifact_version=artifact_version,
        output_path=output_path,
    )
    return {
        "solution": solution,
        "a09_model_pass": solution["a09_model_pass"],
        "synthesis_engine": solution["synthesis_engine"],
        "executor_error": executor_error,
        "deep_dive_source_count": len(deep_dive.get("requests", [])),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bounded A09 verify/refine runner")
    sub = parser.add_subparsers(dest="cmd", required=True)

    prepare = sub.add_parser("prepare-task", help="Write the a09_synthesis_task@1 JSON")
    prepare.add_argument("reviews_json")
    prepare.add_argument("--intake", default="")
    prepare.add_argument("--max-deep-dive-sources", type=int,
                         default=a09_synthesis.DEFAULT_MAX_DEEP_DIVE_SOURCES)
    prepare.add_argument("--out", default="")

    run_cmd = sub.add_parser("run-command",
                             help="Run the A09 pass through an external JSON stdin/stdout command")
    run_cmd.add_argument("reviews_json")
    run_cmd.add_argument("--intake", default="")
    run_cmd.add_argument("--max-deep-dive-sources", type=int,
                         default=a09_synthesis.DEFAULT_MAX_DEEP_DIVE_SOURCES)
    run_cmd.add_argument("--out", default="")
    run_cmd.add_argument("--fail-fast", action="store_true")
    run_cmd.add_argument("command", nargs=argparse.REMAINDER)

    args = parser.parse_args(argv)
    if args.cmd == "prepare-task":
        built = build_a09_task(
            args.reviews_json,
            intake=args.intake or None,
            max_deep_dive_sources=args.max_deep_dive_sources,
        )
        if args.out:
            _write_json(Path(args.out).expanduser().resolve(), built["task"])
        print(json.dumps({
            "task_id": built["task"]["task_id"],
            "deep_dive_source_count": len(built["deep_dive"].get("requests", [])),
            "baseline_update_count": len(built["task"]["deterministic_baseline"]["slide_update_plan"]),
        }, ensure_ascii=False, indent=2))
        return 0

    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    executor = command_executor(command)
    result = run_a09(
        args.reviews_json,
        executor,
        intake=args.intake or None,
        max_deep_dive_sources=args.max_deep_dive_sources,
        output_path=args.out or None,
        fail_fast=args.fail_fast,
    )
    print(json.dumps({
        "task_id": result["solution"]["task_id"],
        "synthesis_engine": result["synthesis_engine"],
        "a09_model_pass": result["a09_model_pass"],
        "slide_update_count": len(result["solution"]["slide_update_plan"]),
        "executor_error": result["executor_error"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
