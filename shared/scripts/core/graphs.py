"""Graph manifest loading + pipeline helpers.

Each ``shared/graphs/<id>.graph.json`` is the single source of truth for one graph. A parent
graph (e.g. ``system``) composes subgraphs via nodes of ``kind: "subgraph"`` whose ``graph``
field names another manifest. These helpers load manifests and read the pipeline structure;
they impose no specific graph. Pure stdlib.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GRAPHS_DIR = ROOT / "shared" / "graphs"
_SUFFIX = ".graph.json"


def manifest_path(graph_id: str, graphs_dir: Path | None = None) -> Path:
    return (graphs_dir or GRAPHS_DIR) / f"{graph_id}{_SUFFIX}"


def load(graph_id: str, graphs_dir: Path | None = None) -> dict:
    return json.loads(manifest_path(graph_id, graphs_dir).read_text())


def all_graph_ids(graphs_dir: Path | None = None) -> list[str]:
    gdir = graphs_dir or GRAPHS_DIR
    if not gdir.exists():
        return []
    return sorted(p.name[: -len(_SUFFIX)] for p in gdir.glob(f"*{_SUFFIX}"))


def nodes(manifest: dict) -> list[dict]:
    return manifest.get("nodes", [])


def subgraph_nodes(manifest: dict) -> list[dict]:
    """Nodes that delegate to another graph (kind == 'subgraph')."""
    return [n for n in nodes(manifest) if n.get("kind") == "subgraph"]


def subgraph_id(node: dict) -> str:
    """The referenced graph id for a subgraph node (``graph`` field, else ``name``)."""
    return node.get("graph") or node.get("name")


def entry_node(manifest: dict):
    return manifest.get("entry_node")


def exit_artifact(manifest: dict):
    return manifest.get("exit_artifact")
