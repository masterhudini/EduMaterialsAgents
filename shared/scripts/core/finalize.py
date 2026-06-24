"""Shared producer write path — validate a typed artifact and persist it server-side.

Hosted (sandboxed) workers must never write the filesystem themselves. The deterministic finalize
op runs in the unsandboxed MCP/engine process: it validates the producer payload against its
contract, atomically stores it, and hands back only the ref in ``produced[]`` of an ``envelope@1``.
Both g01 (intake) and g03 (solution) reuse this — one write path, one place to harden. Pure stdlib.
"""
from __future__ import annotations

import uuid

from . import artifacts, contracts


def artifact_envelope(task_id, payload: dict, *, contract: str, type_name: str, subdir: str,
                      namespace: str, base=None, unknown_task: str = "TASK_UNKNOWN") -> dict:
    """Validate + atomically store a producer artifact; return an ``envelope@1`` with its ref.

    Stores at ``<namespace>/<subdir>/<task_id>.<rand>.json``. On a non-object payload or a contract
    failure, returns a ``failed`` envelope (blocker issue) instead of raising — the worker forwards
    that envelope as its final message.
    """
    if not isinstance(payload, dict):
        return {"status": "failed", "produced": [],
                "summary": f"{type_name}: payload must be an object",
                "issues": [{"severity": "blocker", "type": "contract",
                            "message": "finalize payload is not a JSON object"}]}
    res = contracts.validate(payload, contract)
    if not res["ok"]:
        return {"status": "failed", "produced": [],
                "summary": f"{type_name}: invalid {contract}",
                "issues": [{"severity": "blocker", "type": "contract",
                            "message": "; ".join(res["errors"])}]}
    tid = task_id if isinstance(task_id, str) and task_id else unknown_task
    rel = f"{namespace}/{subdir}/{tid}.{uuid.uuid4().hex[:8]}.json"
    ref = artifacts.store(rel, payload, base=base)
    return {"status": "ok",
            "produced": [{"type": type_name, "path": ref, "schema_version": contract}],
            "summary": f"{type_name} finalized to {ref}", "issues": []}
