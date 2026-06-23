"""Default no-op NodeRunner — wiring/test harness, no LLM.

Returns an empty ``envelope@1`` and records what context it was handed (proves the engine
threads the scoped input + upstream refs to every node).
"""
from __future__ import annotations


def empty_envelope(node_name: str) -> dict:
    return {"status": "ok", "produced": [], "summary": f"{node_name}: stub no-op", "issues": []}


def stub_node_runner(node: dict, ctx: dict, log) -> dict:
    name = node["name"]
    log.append(name, "run", detail={
        "kind": node.get("kind"),
        "received_task_id": (ctx.get("input") or {}).get("task_id"),
        "upstream": sorted((ctx.get("upstream") or {})),
        "stub": True,
    })
    return empty_envelope(name)
