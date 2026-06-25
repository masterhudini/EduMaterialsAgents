"""Append-only diagnostic trail for one graph run.

Separate from the state file: the state says WHAT the state is now (declarative); the log says
WHAT KIND of thing happened and WHEN (the path taken). Every node appends one line per action,
so a stuck or wrong run can be reconstructed step by step — including irreversible events
(blocks, escalations, freeze), each with its reason.

A fresh log file is created per run (named from graph + run id). It NEVER feeds the product:
it is pure diagnostics, written outside the state, so the freeze filter has nothing to strip.

Each entry: ``{ts, run_id, node, action, status, detail}``. Pure stdlib.

Beyond the plain action trail this also carries the two tracing planes (host-agnostic):
- ``span`` entries — DURATIONS the runtime measured itself (a tool dispatch, a nested ``codex exec``,
  the yield->resume gap of a host-driven agent). Works identically for Claude and Codex because it is
  measured at the orchestration seam our code controls.
- ``usage`` entries — model TOKENS (input/output). Only the host knows these when it plays the node,
  so they are REPORTED IN at the finalize/resume seam (or auto-parsed for nested ``codex exec``).
  When a host cannot supply them the fields are simply null — absent, never an error.
``summary()`` rolls both up per node/kind.
"""
from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from . import paths


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


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
            "ts": _now_iso(),
            "run_id": self.run_id,
            "node": node,
            "action": action,
            "status": status,
            "detail": detail or {},
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    # ---- tracing plane A: durations the runtime measures itself --------------

    def span(self, node: str, name: str, *, kind: str, duration_ms: float,
             status: str = "ok", detail: dict | None = None) -> dict:
        """Record one measured duration. ``kind`` is agent|reviewer|tool|gate|node."""
        return self.append(node, "span", status=status,
                           detail={"kind": kind, "name": name,
                                   "duration_ms": round(float(duration_ms), 1), **(detail or {})})

    @contextmanager
    def timed(self, node: str, name: str, *, kind: str, detail: dict | None = None):
        """Bracket a SYNCHRONOUS unit (tool dispatch, nested codex exec) and log its span.

        Not for host-driven agents — their work spans separate calls; time those from the
        checkpoint timestamp instead (see ``runtime_gap_ms``)."""
        t0 = time.perf_counter()
        status = "ok"
        try:
            yield
        except BaseException:
            status = "failed"
            raise
        finally:
            self.span(node, name, kind=kind,
                      duration_ms=(time.perf_counter() - t0) * 1000.0, status=status, detail=detail)

    # ---- tracing plane B: model tokens the host reports in -------------------

    def usage(self, node: str, *, input_tokens=None, output_tokens=None, model=None,
              source: str = "unavailable", detail: dict | None = None) -> dict:
        """Record model token usage for a node. Fields stay null when the host cannot supply them
        (Claude/Codex host-driven) — that is graceful degradation, not a failure. ``source`` is
        codex_nested | host_reported | unavailable."""
        have = input_tokens is not None or output_tokens is not None
        total = ((input_tokens or 0) + (output_tokens or 0)) if have else None
        return self.append(node, "usage",
                           detail={"input_tokens": input_tokens, "output_tokens": output_tokens,
                                   "total_tokens": total, "model": model, "source": source,
                                   **(detail or {})})

    # ---- read side ----------------------------------------------------------

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def summary(self) -> dict:
        """Roll up spans (count + total duration per node/kind) and usage (in/out per node),
        plus run-level totals. Tokens that were never reported simply do not add to the totals."""
        spans: dict = {}
        usage: dict = {}
        totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "duration_ms": 0.0,
                  "token_sources": {}}
        for e in self.entries():
            node = e.get("node")
            d = e.get("detail") or {}
            if e.get("action") == "span":
                bucket = spans.setdefault(node, {})
                k = d.get("kind", "node")
                agg = bucket.setdefault(k, {"count": 0, "duration_ms": 0.0})
                agg["count"] += 1
                agg["duration_ms"] = round(agg["duration_ms"] + (d.get("duration_ms") or 0.0), 1)
                totals["duration_ms"] = round(totals["duration_ms"] + (d.get("duration_ms") or 0.0), 1)
            elif e.get("action") == "usage":
                u = usage.setdefault(node, {"input_tokens": 0, "output_tokens": 0,
                                            "total_tokens": 0, "models": [], "sources": []})
                for f in ("input_tokens", "output_tokens", "total_tokens"):
                    if isinstance(d.get(f), int):
                        u[f] += d[f]
                        totals[f] += d[f]
                if d.get("model") and d["model"] not in u["models"]:
                    u["models"].append(d["model"])
                src = d.get("source", "unavailable")
                if src not in u["sources"]:
                    u["sources"].append(src)
                totals["token_sources"][src] = totals["token_sources"].get(src, 0) + 1
        return {"run_id": self.run_id, "graph_id": self.graph_id,
                "spans": spans, "usage": usage, "totals": totals}


def open_log(graph_id: str, run_id: str | None = None, log_dir: Path | None = None) -> EventLog:
    return EventLog(graph_id, run_id=run_id, log_dir=log_dir)
