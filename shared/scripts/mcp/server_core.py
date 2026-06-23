"""Shared MCP JSON-RPC plumbing (stdio, newline-delimited, pure stdlib).

One reusable scaffold for the per-graph MCP servers: builds a ``handle(msg)`` from a server's
tool registry + dispatch (+ optional prompts), and runs the stdin loop. Each graph server keeps
its own tools/dispatch; this module owns only the protocol. Mirrors the framing used by the
Research Graph server so every graph behaves identically to the host.
"""
from __future__ import annotations

import json
import os
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # -> shared/scripts

from core import event_log  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"


def _result(mid, result):
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _error(mid, code, message):
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def make_handle(*, server_info, tools, dispatch, prompts=(), prompt_handler=None,
                protocol_version=PROTOCOL_VERSION):
    """Build a JSON-RPC ``handle(msg)`` for one server. ``prompt_handler(name, args) -> result``
    is required only if ``prompts`` is non-empty."""
    log_ns = server_info.get("name", "mcp")

    def handle(msg: dict):
        method = msg.get("method")
        if method is None:                       # a response echoed back — ignore
            return None
        if method.startswith("notifications/"):  # notifications get no reply
            return None
        mid = msg.get("id")
        params = msg.get("params") or {}

        if method == "initialize":
            return _result(mid, {
                "protocolVersion": params.get("protocolVersion", protocol_version),
                "capabilities": {"prompts": {}, "tools": {}},
                "serverInfo": server_info,
            })
        if method == "ping":
            return _result(mid, {})
        if method == "prompts/list":
            return _result(mid, {"prompts": list(prompts)})
        if method == "prompts/get":
            name = params.get("name")
            if prompt_handler is None or name not in {p["name"] for p in prompts}:
                return _error(mid, -32602, f"unknown prompt {name!r}")
            try:
                return _result(mid, prompt_handler(name, params.get("arguments") or {}))
            except (ValueError, KeyError) as exc:
                return _error(mid, -32602, str(exc))
        if method == "tools/list":
            return _result(mid, {"tools": list(tools)})
        if method == "tools/call":
            name = params.get("name")
            fn = dispatch.get(name)
            if fn is None:
                return _error(mid, -32602, f"unknown tool {name!r}")
            arguments = params.get("arguments") or {}
            run_id = os.environ.get("EMAGENTS_RUN_ID", "unscoped")
            node_id = os.environ.get("EMAGENTS_NODE_ID", "mcp-client")
            audit = event_log.open_log(f"{run_id}-{log_ns}")
            audit.append(node_id, name, detail={"argument_keys": sorted(arguments)})
            try:
                out = fn(arguments)
                audit.append(node_id, name, status="ok", detail={"is_error": False})
                return _result(mid, {"content": [{"type": "text",
                                                  "text": json.dumps(out, ensure_ascii=False)}]})
            except Exception as exc:  # tool error -> result with isError, not a protocol error
                audit.append(node_id, name, status="failed",
                             detail={"is_error": True, "exception_type": type(exc).__name__})
                return _result(mid, {"content": [{"type": "text", "text": f"error: {exc}"}],
                                     "isError": True})
        return _error(mid, -32601, f"method not found: {method}")

    return handle


def run_loop(handle) -> None:
    """Read newline-delimited JSON-RPC from stdin; write responses to stdout."""
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
