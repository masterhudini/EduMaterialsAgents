"""Append-only diagnostic trail for one graph run.

Separate from the state file: the state says WHAT the state is now (declarative); the log says
WHAT KIND of thing happened and WHEN (the path taken). Every node appends one line per action,
so a stuck or wrong run can be reconstructed step by step — including irreversible events
(blocks, escalations, freeze), each with its reason.

A fresh log file is created per run (named from graph + run id). It NEVER feeds the product:
it is pure diagnostics, written outside the state, so the freeze filter has nothing to strip.

Each entry: ``{ts, run_id, node, action, status, detail}``. Pure stdlib.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from . import paths


class EventLog:
    """Append-only run log. One instance per graph run."""

    def __init__(self, graph_id: str, run_id: str | None = None, log_dir: Path | None = None):
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.graph_id = graph_id
        self.dir = Path(log_dir) if log_dir else paths.logs_dir()
        safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in graph_id)
        self.path = self.dir / f"run-{safe}-{self.run_id}.log"

    def append(self, node: str, action: str, *, status: str = "ok", detail: dict | None = None) -> dict:
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "run_id": self.run_id,
            "node": node,
            "action": action,
            "status": status,
            "detail": detail or {},
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]


def open_log(graph_id: str, run_id: str | None = None, log_dir: Path | None = None) -> EventLog:
    return EventLog(graph_id, run_id=run_id, log_dir=log_dir)
