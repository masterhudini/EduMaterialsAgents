"""Codex-as-worker NodeRunner — run one graph node via `codex exec` (subscription, no API key).

Treats Codex as an isolated worker: builds a prompt from the node's agent `.md` + its scoped
input (+ upstream artifact refs), runs `codex exec` non-interactively, and reads the agent's
FINAL message (constrained to envelope@1) via `--output-last-message`. Plugs into
``g02_flow.run(..., node_runner=codex_node_runner)``.

Local/dev only: relies on the Codex ChatGPT login (cached tokens — treat as a password). Not for
CI/headless/SaaS, where an API key is the right path. Pure stdlib.

POC usage:
    python3 shared/scripts/runners/codex.py [node-name] [context.json]
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import pathlib as _pl

sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))  # -> shared/scripts

from core import contracts, graphs  # noqa: E402

ROOT = _pl.Path(__file__).resolve().parents[3]
AGENTS_DIR = ROOT / "agents"
SKILLS_DIR = ROOT / "skills"
DEFAULT_GRAPH_ID = "g02"
ENVELOPE_SCHEMA = ROOT / "shared" / "contracts" / "envelope.schema.json"
ENVELOPE_FIELDS = {"status", "produced", "summary", "issues", "metrics", "resume_token"}


def _codex_model(node: dict, graph_id: str) -> str | None:
    """Model for `codex exec -m`, from the graph's complexity_class -> model_bindings (codex)."""
    try:
        bindings = graphs.load(graph_id).get("model_bindings", {})
    except FileNotFoundError:
        return None
    host_value = bindings.get(node.get("complexity_class"), {}).get("codex")
    if isinstance(host_value, str):
        return host_value
    if isinstance(host_value, dict):
        model = host_value.get("model")
        if isinstance(model, str):
            return model
    return None


def _agent_prompt(node_name: str) -> str:
    path = AGENTS_DIR / f"{node_name}.md"
    if not path.exists():
        raise FileNotFoundError(f"no agent prompt for node {node_name!r}: {path}")
    return path.read_text(encoding="utf-8")


def _required_skill_names(agent_text: str) -> list[str]:
    """Return the explicitly declared Required Skills, preserving source order."""
    section = re.search(
        r"^## Required Skills\s*$([\s\S]*?)(?=^## |\Z)",
        agent_text,
        flags=re.MULTILINE,
    )
    if not section:
        return []
    names: list[str] = []
    for name in re.findall(r"`([a-z0-9-]+)`", section.group(1)):
        if name not in names:
            names.append(name)
    return names


def _skill_prompt(name: str) -> str:
    """Load one rendered skill, or render the source Codex adapter in-place for local runs."""
    root = SKILLS_DIR / name
    path = root / "SKILL.md"
    if not path.is_file():
        raise FileNotFoundError(f"required skill {name!r} is unavailable: {path}")
    text = path.read_text(encoding="utf-8")
    adapter = root / "adapters" / "codex.md"
    if adapter.is_file():
        text = f"{text.rstrip()}\n\n## Codex execution adapter\n\n{adapter.read_text(encoding='utf-8').strip()}\n"
    return text


def _json_block(label: str, value) -> str:
    if not value:
        return ""
    return f"\n{label}:\n```json\n{json.dumps(value, ensure_ascii=False, indent=2)}\n```\n"


def _build_prompt(node_name: str, ctx: dict, output_contract: str | None) -> str:
    agent_text = _agent_prompt(node_name)
    skill_sections = "\n\n".join(
        f"----- REQUIRED SKILL: {name} -----\n{_skill_prompt(name)}"
        for name in _required_skill_names(agent_text)
    )
    scoped_input = ctx.get("input") or {}
    upstream = ctx.get("upstream") or {}
    review_task = ctx.get("review_task") or ctx.get("review")
    revision = ctx.get("revision")
    protocol = ctx.get("protocol")

    role = (
        "You are the REVIEWER node. Review ONLY the target artifact against the review profile and "
        "acceptance criteria; do not redo the producer's work. Emit a ReviewDecision."
        if review_task else
        "You are running as an ISOLATED producer worker for the node defined above. Perform that "
        "node's task for the INPUT below."
    )
    return (
        f"{agent_text}\n\n"
        f"{skill_sections}\n\n"
        "----- RUN CONTEXT -----\n"
        f"{role} Do not ask the user anything.\n\n"
        "Your FINAL message must be ONLY the exact envelope@1 returned by the final deterministic "
        "MCP operation. Do not wrap it, rewrite issues, add an `artifact` field, or place JSON in a "
        "Markdown fence. A producer must finish with its stage finalize operation. A reviewer must "
        "finish with research_review_finalize. On any failure, return a valid failed envelope@1.\n"
        f"The primary producer output contract is {output_contract or 'defined by the review task'}.\n"
        f"{_json_block('MANDATORY OPERATION PROTOCOL', protocol)}"
        f"{_json_block('UPSTREAM ARTIFACT REFS (hydrate only what this node needs)', upstream)}"
        f"{_json_block('REVIEW TASK (use exactly this object)', review_task)}"
        f"{_json_block('REVISION (apply these findings to your prior artifact)', revision)}"
        f"{_json_block('INPUT (scoped research_graph_input)', scoped_input)}"
    )


def _fail(name: str, message: str) -> dict:
    return {"status": "failed", "produced": [],
            "summary": f"{name}: codex worker failed",
            "issues": [{"severity": "blocker", "type": "codex_worker", "message": message}]}


def codex_node_runner(node: dict, ctx: dict, log, *, graph_id: str = DEFAULT_GRAPH_ID,
                      codex_bin: str = "codex", timeout: int = 600, sandbox: str = "read-only",
                      process_runner=subprocess.run) -> dict:
    """Run one node as an isolated Codex worker; return a validated envelope@1 (or a failed one).

    Host-level and graph-agnostic: ``graph_id`` selects the manifest used for the codex
    ``model_bindings`` lookup, so g01/g02/g03 reuse the same worker without cross-graph imports.
    """
    name = node["name"]
    prompt = _build_prompt(name, ctx, node.get("output_contract"))
    log.append(name, "codex_exec", detail={"sandbox": sandbox, "upstream": sorted(ctx.get("upstream") or {})})
    with tempfile.TemporaryDirectory() as tmp:
        last = _pl.Path(tmp) / "last.txt"
        cmd = [codex_bin, "exec", "--skip-git-repo-check", "--ephemeral",
               "-s", sandbox, "--cd", str(ROOT)]
        model = _codex_model(node, graph_id)
        if model:
            cmd += ["-m", model]
        cmd += [
            "--output-schema", str(ENVELOPE_SCHEMA),
            "--output-last-message", str(last), "-",
        ]
        try:
            environment = os.environ.copy()
            if isinstance(ctx.get("run_id"), str):
                environment["EMAGENTS_RUN_ID"] = ctx["run_id"]
            environment["EMAGENTS_NODE_ID"] = name
            proc = process_runner(
                cmd, input=prompt, capture_output=True, text=True, timeout=timeout,
                env=environment,
            )
        except subprocess.TimeoutExpired:
            return _fail(name, f"codex exec timed out after {timeout}s")
        if proc.returncode != 0:
            return _fail(name, f"codex exec exited with rc={proc.returncode}; stderr: {proc.stderr[-400:]}")
        if not last.exists() or not last.read_text(encoding="utf-8").strip():
            return _fail(name, f"no final message (rc={proc.returncode}); stderr: {proc.stderr[-400:]}")
        raw = last.read_text(encoding="utf-8").strip()

    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as exc:
        return _fail(name, f"final message JSON invalid: {exc}")

    result = contracts.validate_envelope(envelope)
    if not result["ok"]:
        return _fail(name, "envelope@1 invalid: " + "; ".join(result["errors"]))
    extras = set(envelope) - ENVELOPE_FIELDS
    if extras:
        return _fail(name, f"envelope@1 contains unsupported fields: {sorted(extras)}")
    return envelope


def make_codex_runner(graph_id: str = DEFAULT_GRAPH_ID, **options):
    """Bind a Codex NodeRunner to one graph (for the manifest model_bindings lookup).

    Usage: ``engine.make_cli(SPEC, codex_runner=make_codex_runner("g01"))``.
    """
    def runner(node: dict, ctx: dict, log) -> dict:
        return codex_node_runner(node, ctx, log, graph_id=graph_id, **options)
    return runner


if __name__ == "__main__":
    from g02 import g02_flow as rf
    from core import event_log, graphs

    node_name = sys.argv[1] if len(sys.argv) > 1 else "g02-a01-planner"
    ctx_path = sys.argv[2] if len(sys.argv) > 2 else str(
        ROOT / "mocks/g02/research_graph_input.json"
    )

    rgi = rf.load_context(ctx_path)
    node = next((n for n in graphs.nodes(graphs.load("g02")) if n["name"] == node_name), None)
    if node is None:
        print(f"no such node: {node_name}", file=sys.stderr)
        raise SystemExit(2)
    log = event_log.open_log("research-codex-poc")
    envelope = codex_node_runner(node, {"input": rf.scoped_input(node, rgi), "upstream": {}}, log)
    print(json.dumps(envelope, indent=2, ensure_ascii=False))
