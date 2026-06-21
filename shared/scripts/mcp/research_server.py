#!/usr/bin/env python3
"""Pure-stdlib MCP (stdio) server exposing the Research Graph's deterministic seams as tools.

Implements the minimal MCP stdio protocol (JSON-RPC 2.0, newline-delimited) BY HAND — no
third-party dependencies, so it runs with the system python3 like the rest of the plugin.
Claude Code / Codex launch it via .mcp.json with ${CLAUDE_PLUGIN_ROOT}; the deterministic seams
wrap shared/scripts/g02/g02_flow.py.

Methods: initialize, notifications/* (ignored), ping, tools/list, tools/call.
Tools: research_front_door, research_node_input, research_review_prepare,
research_review_finalize, research_finalize, research_run_stub.
"""
from __future__ import annotations

import json
import sys
import pathlib

# Self-bootstrap sys.path so `core` and `g02` import however we're launched.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # -> shared/scripts

from g02 import g02_flow as rf  # noqa: E402
from g02 import review as reviewer  # noqa: E402
from core import graphs, handoff  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "edu-materials-research", "version": "0.2.0"}


# ---- tool implementations (return JSON-serializable values) --------------

def _front_door(args: dict):
    return rf.front_door(args["context"])


def _node_input(args: dict):
    rgi = rf._load_any(args["ref"])
    inputs = rf.node_input_map(rgi, graphs.load(rf.GRAPH_ID))
    node = args.get("node")
    if not node:
        return inputs
    if node not in inputs:
        raise ValueError(f"no agent node {node!r}; have: {', '.join(inputs)}")
    return {node: inputs[node]}


def _finalize(args: dict):
    bundle = args["bundle"]
    if isinstance(bundle, str):                       # a path
        return rf.finalize(bundle)
    return handoff.emit_handoff(bundle, rf.OUTPUT_CONTRACT, name="research_bundle")  # inline


def _review_prepare(args: dict):
    return reviewer.prepare_review(args["task"])


def _review_finalize(args: dict):
    return reviewer.finalize_review_decision(args["task"], args["decision"])


def _run_stub(args: dict):
    return rf.run(rf.front_door(args["context"])["ref"])


def _run_codex(args: dict):
    """Run or resume the graph through Codex workers.

    MCP tools are not an interactive stdin surface, so the default gate behavior is pause/resume.
    Use gates=auto only for deterministic smoke runs where human approvals may be simulated.
    """
    from research.runners.codex import codex_node_runner

    gates = args.get("gates", "pause")
    if gates not in {"pause", "auto"}:
        raise ValueError("gates must be 'pause' or 'auto'")

    resume_token = args.get("resume_token")
    decisions = args.get("decisions")
    if resume_token:
        return rf.run(
            None,
            node_runner=codex_node_runner,
            pause_on_gate=(gates == "pause"),
            resume_token=resume_token,
            decisions=decisions,
        )

    context = args.get("context")
    if not context:
        raise ValueError("context is required when resume_token is absent")
    ref = rf.front_door(context)["ref"]
    return rf.run(ref, node_runner=codex_node_runner, pause_on_gate=(gates == "pause"))


TOOLS = [
    {
        "name": "research_front_door",
        "description": "Validate a research_graph_input bundle against research_graph_input@1 "
                       "and register it in the artifact store. Returns {ref, task_id}. "
                       "Fail-fast on invalid input. Call this first.",
        "inputSchema": {
            "type": "object",
            "properties": {"context": {"type": "string",
                           "description": "path or artifact:// ref to a research_graph_input bundle"}},
            "required": ["context"],
        },
    },
    {
        "name": "research_node_input",
        "description": "Return the scoped input bundle each agent node receives, or just one via "
                       "'node'. Use to prepare the input you hand a research agent.",
        "inputSchema": {
            "type": "object",
            "properties": {"ref": {"type": "string", "description": "ref from research_front_door"},
                           "node": {"type": "string", "description": "optional single node name"}},
            "required": ["ref"],
        },
    },
    {
        "name": "research_review_prepare",
        "description": "Validate one review_task@1, enforce one artifact and hydrate only that "
                       "artifact for the isolated universal reviewer. Invalid review basis or "
                       "unavailable artifact returns a completed BLOCKED decision envelope when "
                       "audit identity is available.",
        "inputSchema": {
            "type": "object",
            "properties": {"task": {"type": "object"}},
            "required": ["task"],
        },
    },
    {
        "name": "research_review_finalize",
        "description": "Validate one review_decision@1 against its ReviewTask, persist it and "
                       "return envelope@1 with one review_decision descriptor.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "object"},
                "decision": {"type": "object"},
            },
            "required": ["task", "decision"],
        },
    },
    {
        "name": "research_finalize",
        "description": "Validate a UserApprovedResearchBundle (inline object or path) against "
                       "user_approved_research_bundle@1 and emit it as the typed handoff. "
                       "Returns the handoff descriptor.",
        "inputSchema": {
            "type": "object",
            "properties": {"bundle": {"description": "the bundle object, or a path to a JSON file"}},
            "required": ["bundle"],
        },
    },
    {
        "name": "research_run_stub",
        "description": "Run the whole Research Graph with STUB nodes (no LLM) — wiring test. "
                       "Returns the output handoff descriptor.",
        "inputSchema": {
            "type": "object",
            "properties": {"context": {"type": "string"}},
            "required": ["context"],
        },
    },
    {
        "name": "research_run_codex",
        "description": "Semantic entrypoint for 'zrob research', 'zrób research' or "
                       "'run research graph' in Codex. "
                       "Validate the input and run the full Research Graph with isolated Codex "
                       "workers. Defaults to pause/resume user gates because MCP tools cannot "
                       "read interactive stdin; use gates='auto' only for smoke/dev runs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "context": {
                    "type": "string",
                    "description": "Path or artifact:// ref to a research_graph_input bundle. "
                                   "Required unless resume_token is provided.",
                },
                "gates": {
                    "type": "string",
                    "enum": ["pause", "auto"],
                    "description": "pause for human gate handoff/resume (default), auto for dev smoke.",
                },
                "resume_token": {
                    "type": "string",
                    "description": "Token from an awaiting_user response to resume a paused run.",
                },
                "decisions": {
                    "type": "object",
                    "description": "Gate decisions keyed by gate name when resuming.",
                },
            },
        },
    },
]

PROMPTS = [
    {
        "name": "research",
        "description": "Semantic 'zrob research' / 'zrób research' entrypoint for running the "
                       "Research Graph over an approved research_graph_input bundle.",
        "arguments": [
            {
                "name": "context",
                "description": "Path or artifact:// ref to a research_graph_input bundle.",
                "required": True,
            },
        ],
    },
]


def _research_prompt(context: str) -> dict:
    return {
        "description": "Semantic 'zrob research' entrypoint for a research_graph_input bundle.",
        "messages": [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": (
                        "The user asked to zrob research / zrób research. Use the "
                        "edu-materials-agents orchestrate-research workflow for this "
                        f"research_graph_input bundle: {context}\n\n"
                        "For the full Codex workflow, call research_run_codex with gates='pause' "
                        "so human gates return an awaiting_user resume token. For a deterministic "
                        "wiring check only, use research_run_stub."
                    ),
                },
            },
        ],
    }


DISPATCH = {
    "research_front_door": _front_door,
    "research_node_input": _node_input,
    "research_review_prepare": _review_prepare,
    "research_review_finalize": _review_finalize,
    "research_finalize": _finalize,
    "research_run_stub": _run_stub,
    "research_run_codex": _run_codex,
}


# ---- JSON-RPC plumbing ---------------------------------------------------

def _result(mid, result):
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _error(mid, code, message):
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def handle(msg: dict):
    """Handle one JSON-RPC message. Returns a response dict, or None for notifications."""
    method = msg.get("method")
    if method is None:                       # a response echoed back to us — ignore
        return None
    if method.startswith("notifications/"):  # notifications get no reply
        return None
    mid = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        return _result(mid, {
            "protocolVersion": params.get("protocolVersion", PROTOCOL_VERSION),
            "capabilities": {"prompts": {}, "tools": {}},
            "serverInfo": SERVER_INFO,
        })
    if method == "ping":
        return _result(mid, {})
    if method == "prompts/list":
        return _result(mid, {"prompts": PROMPTS})
    if method == "prompts/get":
        name = params.get("name")
        if name != "research":
            return _error(mid, -32602, f"unknown prompt {name!r}")
        args = params.get("arguments") or {}
        context = args.get("context")
        if not context:
            return _error(mid, -32602, "missing required prompt argument 'context'")
        return _result(mid, _research_prompt(context))
    if method == "tools/list":
        return _result(mid, {"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name")
        fn = DISPATCH.get(name)
        if fn is None:
            return _error(mid, -32602, f"unknown tool {name!r}")
        try:
            out = fn(params.get("arguments") or {})
            return _result(mid, {"content": [{"type": "text",
                                              "text": json.dumps(out, ensure_ascii=False)}]})
        except Exception as exc:  # tool error -> result with isError, not a protocol error
            return _result(mid, {"content": [{"type": "text", "text": f"error: {exc}"}],
                                 "isError": True})
    return _error(mid, -32601, f"method not found: {method}")


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
