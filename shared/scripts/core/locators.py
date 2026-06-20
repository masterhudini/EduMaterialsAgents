"""Locate skills/agents by NAME in the nested layout.

Directory placement is organisational only — components are addressed by name, never by path,
so a component can move between graph folders without breaking references. Pure stdlib.
"""
from __future__ import annotations

from pathlib import Path


def find_skill_dir(root: str | Path, name: str) -> Path | None:
    """Return the directory of skill ``name`` (the dir containing its SKILL.md)."""
    for p in sorted((Path(root) / "skills").rglob("SKILL.md")):
        if p.parent.name == name:
            return p.parent
    return None


def find_agent_file(root: str | Path, name: str) -> Path | None:
    """Return the .md file of agent ``name`` anywhere under agents/."""
    for p in sorted((Path(root) / "agents").rglob(f"{name}.md")):
        return p
    return None
