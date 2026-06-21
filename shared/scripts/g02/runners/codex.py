"""Codex-as-worker NodeRunner — run one graph node via `codex exec` (subscription, no API key).

Treats Codex as an isolated worker: builds a prompt from the node's agent `.md` + its scoped
input (+ upstream artifact refs), runs `codex exec` non-interactively, and reads the agent's
FINAL message (constrained to envelope@1) via `--output-last-message`. Plugs into
``g02_flow.run(..., node_runner=codex_node_runner)``.

Local/dev only: relies on the Codex ChatGPT login (cached tokens — treat as a password). Not for
CI/headless/SaaS, where an API key is the right path. Pure stdlib.

POC usage:
    python3 shared/scripts/research/runners/codex.py [node-name] [context.json]
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import pathlib as _pl

sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # -> shared/scripts

from core import contracts, graphs  # noqa: E402

ROOT = _pl.Path(__file__).resolve().parents[4]
AGENTS_DIR = ROOT / "agents"
GRAPH_ID = "g02"


def _codex_model(node: dict) -> str | None:
    """Model for `codex exec -m`, from the graph's complexity_class -> model_bindings (codex)."""
    try:
        bindings = graphs.load(GRAPH_ID).get("model_bindings", {})
    except FileNotFoundError:
        return None
    return bindings.get(node.get("complexity_class"), {}).get("codex")


def _agent_prompt(node_name: str) -> str:
    path = AGENTS_DIR / f"{node_name}.md"
    if not path.exists():
        raise FileNotFoundError(f"no agent prompt for node {node_name!r}: {path}")
    return path.read_text(encoding="utf-8")


def _json_block(label: str, value) -> str:
    if not value:
        return ""
    return f"\n{label}:\n```json\n{json.dumps(value, ensure_ascii=False, indent=2)}\n```\n"


def _build_prompt(node_name: str, ctx: dict, output_contract: str | None) -> str:
    scoped_input = ctx.get("input") or {}
    upstream = ctx.get("upstream") or {}
    review = ctx.get("review")
    revision = ctx.get("revision")

    artifact_line = (
        f'Put your typed result object (contract {output_contract}) in the "artifact" field.'
        if output_contract else 'Put any result object in the "artifact" field.'
    )
    role = (
        "You are the REVIEWER node. Review ONLY the target artifact against the review profile and "
        "acceptance criteria; do not redo the producer's work. Emit a ReviewDecision."
        if review else
        "You are running as an ISOLATED producer worker for the node defined above. Perform that "
        "node's task for the INPUT below."
    )
    return (
        f"{_agent_prompt(node_name)}\n\n"
        "----- RUN CONTEXT -----\n"
        f"{role} Do not ask the user anything.\n\n"
        "Your FINAL message must be ONLY a single JSON object: envelope@1 with an extra `artifact` key:\n"
        '{"status": "ok|needs_input|degraded|failed", "produced": [], "summary": "<concise note>", '
        '"issues": [], "artifact": { ... }}\n'
        f"{artifact_line} On needs_input/failed, omit `artifact`.\n"
        f"{_json_block('UPSTREAM ARTIFACT REFS (hydrate only what this node needs)', upstream)}"
        f"{_json_block('REVIEW TASK (target artifact + profile + attempt + prior findings)', review)}"
        f"{_json_block('REVISION (apply these findings to your prior artifact)', revision)}"
        f"{_json_block('INPUT (scoped research_graph_input)', scoped_input)}"
    )


def _fail(name: str, message: str) -> dict:
    return {"status": "failed", "produced": [],
            "summary": f"{name}: codex worker failed",
            "issues": [{"severity": "blocker", "type": "codex_worker", "message": message}]}


def codex_node_runner(node: dict, ctx: dict, log, *, codex_bin: str = "codex",
                      timeout: int = 600, sandbox: str = "read-only") -> dict:
    """Run one node as an isolated Codex worker; return a validated envelope@1 (or a failed one)."""
    name = node["name"]
    prompt = _build_prompt(name, ctx, node.get("output_contract"))
    log.append(name, "codex_exec", detail={"sandbox": sandbox, "upstream": sorted(ctx.get("upstream") or {})})
    with tempfile.TemporaryDirectory() as tmp:
        last = _pl.Path(tmp) / "last.txt"
        cmd = [codex_bin, "exec", "--skip-git-repo-check", "--ephemeral",
               "-s", sandbox, "--cd", str(ROOT)]
        model = _codex_model(node)
        if model:
            cmd += ["-m", model]
        cmd += ["--output-last-message", str(last), "-"]
        try:
            proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return _fail(name, f"codex exec timed out after {timeout}s")
        if not last.exists() or not last.read_text(encoding="utf-8").strip():
            return _fail(name, f"no final message (rc={proc.returncode}); stderr: {proc.stderr[-400:]}")
        raw = last.read_text(encoding="utf-8").strip()

    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        return _fail(name, f"final message has no JSON object: {raw[:300]}")
    try:
        envelope = json.loads(raw[start:end + 1])
    except json.JSONDecodeError as exc:
        return _fail(name, f"final message JSON invalid: {exc}")

    result = contracts.validate_envelope(envelope)
    if not result["ok"]:
        return _fail(name, "envelope@1 invalid: " + "; ".join(result["errors"]))
    return envelope


if __name__ == "__main__":
    from g02 import g02_flow as rf
    from core import event_log, graphs

    node_name = sys.argv[1] if len(sys.argv) > 1 else "research-planner"
    ctx_path = sys.argv[2] if len(sys.argv) > 2 else str(ROOT / "mocks/research/research_graph_input.json")

    rgi = rf.load_context(ctx_path)
    node = next((n for n in graphs.nodes(graphs.load(GRAPH_ID)) if n["name"] == node_name), None)
    if node is None:
        print(f"no such node: {node_name}", file=sys.stderr)
        raise SystemExit(2)
    log = event_log.open_log("research-codex-poc")
    envelope = codex_node_runner(node, {"input": rf.scoped_input(node, rgi), "upstream": {}}, log)
    print(json.dumps(envelope, indent=2, ensure_ascii=False))
