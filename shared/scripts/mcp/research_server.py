#!/usr/bin/env python3
"""Pure-stdlib MCP (stdio) server exposing the Research Graph's deterministic seams as tools.

Implements the minimal MCP stdio protocol (JSON-RPC 2.0, newline-delimited) BY HAND — no
third-party dependencies, so it runs with the system python3 like the rest of the plugin.
Claude Code / Codex launch it via .mcp.json with ${CLAUDE_PLUGIN_ROOT}; the deterministic seams
wrap shared/scripts/g02/g02_flow.py.

Methods: initialize, notifications/* (ignored), ping, tools/list, tools/call.
Tools: research_front_door, research_node_input, research_planner_prepare,
research_planner_finalize, research_plan_review_task, research_provider_status,
research_domain_prepare, research_metadata_search, research_domain_finalize,
research_domain_review_task, research_review_prepare, research_review_finalize,
research_finalize, research_run_stub.
"""
from __future__ import annotations

import json
import sys
import pathlib

# Self-bootstrap sys.path so `core` and `g02` import however we're launched.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # -> shared/scripts

from g02 import g02_flow as rf  # noqa: E402
from g02 import domain  # noqa: E402
from g02 import planner  # noqa: E402
from g02 import provider_config  # noqa: E402
from g02 import providers  # noqa: E402
from g02 import review as reviewer  # noqa: E402
from core import artifacts, graphs, handoff  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "edu-materials-research", "version": "0.4.0"}


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


def _planner_payload(value):
    if isinstance(value, dict) and "schema_version" not in value \
            and isinstance(value.get("ref"), str):
        return artifacts.hydrate(value["ref"])
    if isinstance(value, str) and value.startswith(artifacts.SCHEME):
        return artifacts.hydrate(value)
    if isinstance(value, str):
        return json.loads(pathlib.Path(value).read_text(encoding="utf-8"))
    return value


def _planner_prepare(args: dict):
    return planner.prepare_planner(
        _planner_payload(args["input"]),
        previous_plan_ref=args.get("previous_plan_ref"),
        revision_items=args.get("revision_items"),
    )


def _planner_finalize(args: dict):
    prepared = planner.prepare_planner(
        _planner_payload(args["input"]),
        previous_plan_ref=args.get("previous_plan_ref"),
        revision_items=args.get("revision_items"),
    )
    if not prepared["ready"]:
        return prepared["envelope"]
    return planner.finalize_research_plan(
        prepared["planner_input"],
        args["plan"],
        previous_plan=prepared["previous_plan"],
        revision_items=prepared["revision_items"],
    )


def _plan_review_task(args: dict):
    prepared = planner.prepare_planner(_planner_payload(args["input"]))
    if not prepared["ready"]:
        return prepared["envelope"]
    return planner.build_research_plan_review_task(
        prepared["planner_input"],
        args["artifact"],
        review_id=args["review_id"],
        attempt=args.get("attempt", 1),
        previous_decision_ref=args.get("previous_decision_ref"),
        producer_revision_response=args.get("producer_revision_response"),
    )


def _provider_status(args: dict):
    return provider_config.provider_status(args.get("config"))


def _domain_prepare(args: dict):
    return domain.prepare_domain(
        args["research_plan_ref"],
        args["topic_id"],
        config_path=args.get("config"),
        previous_candidates_ref=args.get("previous_candidates_ref"),
        revision_items=args.get("revision_items"),
    )


def _metadata_search(args: dict):
    return providers.search_metadata(
        args["query_plan"],
        args["domain_input"],
        route_id=args["route_id"],
        provider=args["provider"],
        cursor=args.get("cursor"),
        config_path=args.get("config"),
    )


def _domain_finalize(args: dict):
    prepared = domain.prepare_domain(
        args["research_plan_ref"],
        args["topic_id"],
        config_path=args.get("config"),
        previous_candidates_ref=args.get("previous_candidates_ref"),
        revision_items=args.get("revision_items"),
    )
    if not prepared["ready"]:
        return prepared["envelope"]
    return domain.finalize_domain_candidates(
        prepared["domain_input"],
        args["output"],
        previous_candidates=prepared["previous_candidates"],
        revision_items=prepared["revision_items"],
    )


def _domain_review_task(args: dict):
    prepared = domain.prepare_domain(
        args["research_plan_ref"],
        args["topic_id"],
        config_path=args.get("config"),
    )
    if not prepared["ready"]:
        return prepared["envelope"]
    return domain.build_domain_review_task(
        prepared["domain_input"],
        args["artifact"],
        review_id=args["review_id"],
        attempt=args.get("attempt", 1),
        previous_decision_ref=args.get("previous_decision_ref"),
        producer_revision_response=args.get("producer_revision_response"),
    )


def _run_stub(args: dict):
    return rf.run(rf.front_door(args["context"])["ref"])


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
        "description": "Preview boundary-only no-op harness inputs, or one via 'node'. G02-A01 is "
                       "fully scoped here; dependency-based nodes use their dedicated prepare "
                       "operation, beginning with research_domain_prepare for G02-A02.",
        "inputSchema": {
            "type": "object",
            "properties": {"ref": {"type": "string", "description": "ref from research_front_door"},
                           "node": {"type": "string", "description": "optional single node name"}},
            "required": ["ref"],
        },
    },
    {
        "name": "research_planner_prepare",
        "description": "Validate and scope research_graph_input@1 for G02-A01 Planner. For a "
                       "revision, also validate and hydrate only the named previous ResearchPlan. "
                       "Returns the isolated research_planner_input@1 or a completed failure "
                       "envelope without invoking an agent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {
                    "description": "Research Graph input object, path or artifact:// ref"
                },
                "previous_plan_ref": {"type": "string"},
                "revision_items": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["input"],
        },
    },
    {
        "name": "research_planner_finalize",
        "description": "Validate a G02-A01 ResearchPlan against its scoped approved input, "
                       "persist a valid research_plan@1 and return envelope@1. Supports minimal "
                       "revision checks when previous_plan_ref and revision_items are supplied.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {
                    "description": "Research Graph or scoped planner input object, path or ref"
                },
                "plan": {"type": "object"},
                "previous_plan_ref": {"type": "string"},
                "revision_items": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["input", "plan"],
        },
    },
    {
        "name": "research_plan_review_task",
        "description": "Freeze the research_plan review profile and build one review_task@1 "
                       "for a persisted G02-A01 artifact descriptor.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {
                    "description": "Research Graph or scoped planner input object, path or ref"
                },
                "artifact": {"type": "object"},
                "review_id": {"type": "string"},
                "attempt": {"type": "integer"},
                "previous_decision_ref": {"type": "string"},
                "producer_revision_response": {"type": "object"},
            },
            "required": ["input", "artifact", "review_id"],
        },
    },
    {
        "name": "research_provider_status",
        "description": "Validate the G02 provider configuration at startup and return a "
                       "secret-free capability report for OpenAlex, Semantic Scholar and "
                       "arXiv. No provider request is made.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "config": {"type": "string", "description": "optional provider config path"},
            },
        },
    },
    {
        "name": "research_domain_prepare",
        "description": "Hydrate one approved ResearchPlan topic for G02-A02, validate provider "
                       "startup configuration and return domain_research_input@1 with only "
                       "secret-free provider capabilities.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "research_plan_ref": {"type": "string"},
                "topic_id": {"type": "string"},
                "config": {"type": "string"},
                "previous_candidates_ref": {"type": "string"},
                "revision_items": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["research_plan_ref", "topic_id"],
        },
    },
    {
        "name": "research_metadata_search",
        "description": "Execute exactly one authorized QueryPlan route against one configured "
                       "scholarly metadata provider. The deterministic adapter applies limits, "
                       "retry, caching, normalization, provenance and raw-response persistence.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query_plan": {"type": "object"},
                "domain_input": {"type": "object"},
                "route_id": {"type": "string"},
                "provider": {
                    "type": "string",
                    "enum": ["openalex", "semantic_scholar", "arxiv"],
                },
                "cursor": {"type": "string"},
                "config": {"type": "string"},
            },
            "required": ["query_plan", "domain_input", "route_id", "provider"],
        },
    },
    {
        "name": "research_domain_finalize",
        "description": "Validate G02-A02 output against its approved topic and every persisted "
                       "provider result, then store domain_candidate_sources@1 and return "
                       "envelope@1. Supports bounded revision of one previous artifact.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "research_plan_ref": {"type": "string"},
                "topic_id": {"type": "string"},
                "output": {"type": "object"},
                "config": {"type": "string"},
                "previous_candidates_ref": {"type": "string"},
                "revision_items": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["research_plan_ref", "topic_id", "output"],
        },
    },
    {
        "name": "research_domain_review_task",
        "description": "Freeze the domain_candidates review profile and build one "
                       "review_task@1 for a persisted G02-A02 artifact descriptor.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "research_plan_ref": {"type": "string"},
                "topic_id": {"type": "string"},
                "artifact": {"type": "object"},
                "review_id": {"type": "string"},
                "attempt": {"type": "integer"},
                "previous_decision_ref": {"type": "string"},
                "producer_revision_response": {"type": "object"},
                "config": {"type": "string"},
            },
            "required": ["research_plan_ref", "topic_id", "artifact", "review_id"],
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
]

DISPATCH = {
    "research_front_door": _front_door,
    "research_node_input": _node_input,
    "research_planner_prepare": _planner_prepare,
    "research_planner_finalize": _planner_finalize,
    "research_plan_review_task": _plan_review_task,
    "research_provider_status": _provider_status,
    "research_domain_prepare": _domain_prepare,
    "research_metadata_search": _metadata_search,
    "research_domain_finalize": _domain_finalize,
    "research_domain_review_task": _domain_review_task,
    "research_review_prepare": _review_prepare,
    "research_review_finalize": _review_finalize,
    "research_finalize": _finalize,
    "research_run_stub": _run_stub,
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
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        })
    if method == "ping":
        return _result(mid, {})
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
