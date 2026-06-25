"""Build a deterministic ``presentation_prompt@1`` draft for G03-A04 (Generator Prompt Builder).

Assembles a single ready-to-paste Markdown prompt from the approved ``slide_design_set@1``, tailored
to the chosen generator tool (NotebookLM / Gamma / GPT Pro). This is the deterministic draft + the
render path; the agent (via one of the three tool skills) authors the final wording. Pure stdlib.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys as _sys

_sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> shared/scripts

from core import artifacts, contracts  # noqa: E402
from g03 import solution  # noqa: E402

INPUT_CONTRACT = "slide_design_set@1"
OUTPUT_CONTRACT = "presentation_prompt@1"
ALLOWED_TARGET_TOOLS = ("notebooklm", "gamma", "gpt_pro")
DEFAULT_TARGET_TOOL = "gamma"


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _strings(value: object) -> list[str]:
    return [str(item) for item in _as_list(value) if str(item or "").strip()]


def _safe_task_id(task_id: object) -> str:
    value = str(task_id or "solution").strip()
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
    return safe.strip("._") or "solution"


def _load_design(path_or_ref, *, base=None) -> dict:
    if isinstance(path_or_ref, dict):
        if path_or_ref.get("schema_version") == INPUT_CONTRACT and "slides" in path_or_ref:
            design = path_or_ref
        elif isinstance(path_or_ref.get("ref"), str):
            design = artifacts.hydrate(path_or_ref["ref"], base=base)
        else:
            raise ValueError("expected slide_design_set@1 object or a descriptor with ref")
    else:
        text = str(path_or_ref)
        if text.startswith(artifacts.SCHEME):
            design = artifacts.hydrate(text, base=base)
        else:
            loaded = json.loads(Path(text).read_text(encoding="utf-8"))
            design = artifacts.hydrate(loaded["ref"], base=base) if isinstance(loaded.get("ref"), str) else loaded
    checked = contracts.validate(design, INPUT_CONTRACT)
    if not checked["ok"]:
        raise ValueError("invalid slide_design_set@1: " + "; ".join(checked["errors"]))
    return design


def _load_prompt(path_or_ref, *, base=None) -> dict:
    if isinstance(path_or_ref, dict):
        if path_or_ref.get("schema_version") == OUTPUT_CONTRACT and "prompt_markdown" in path_or_ref:
            prompt = path_or_ref
        elif isinstance(path_or_ref.get("ref"), str):
            prompt = artifacts.hydrate(path_or_ref["ref"], base=base)
        else:
            raise ValueError("expected presentation_prompt@1 object or a descriptor with ref")
    else:
        text = str(path_or_ref)
        if text.startswith(artifacts.SCHEME):
            prompt = artifacts.hydrate(text, base=base)
        else:
            loaded = json.loads(Path(text).read_text(encoding="utf-8"))
            prompt = artifacts.hydrate(loaded["ref"], base=base) if isinstance(loaded.get("ref"), str) else loaded
    checked = contracts.validate(prompt, OUTPUT_CONTRACT)
    if not checked["ok"]:
        raise ValueError("invalid presentation_prompt@1: " + "; ".join(checked["errors"]))
    return prompt


def _slide_block(slide: dict) -> str:
    lines = [f"### {slide.get('position')}. {slide.get('title')} [{slide.get('status')}]"]
    if slide.get("narrative"):
        lines.append(str(slide["narrative"]))
    body = slide.get("body") if isinstance(slide.get("body"), dict) else {}
    for bullet in _strings(body.get("bullets")):
        lines.append(f"- {bullet}")
    design = slide.get("design") if isinstance(slide.get("design"), dict) else {}
    if design.get("layout"):
        lines.append(f"_Layout: {design['layout']}_")
    sources = _strings(slide.get("source_refs"))
    if sources:
        lines.append(f"_Sources: {', '.join(sources)}_")
    return "\n".join(lines)


def _header(tool: str, title: str, language: str) -> str:
    if tool == "notebooklm":
        return (f"# {title}\n\n"
                f"Using the attached sources, produce a briefing document and a slide outline in "
                f"{language}. Follow the structure below; each section is one slide. Keep the good "
                f"existing content, integrate the updates, and add the new slides marked [ADD]. Cite "
                f"the listed sources.")
    if tool == "gpt_pro":
        return (f"# {title}\n\n"
                f"You are an expert university lecturer. Generate a complete slide deck in Markdown in "
                f"{language}, following the per-slide specification below exactly. Keep slides marked "
                f"[KEEP], revise [UPDATE], and create the [ADD] slides at their position. Do not invent "
                f"unsupported facts; cite the listed sources.")
    return (f"# {title}\n\n"
            f"Create a presentation in {language}. One card per slide, in this exact order. Keep the "
            f"good content, apply the [UPDATE] changes and create the [ADD] cards. Use the layout hints "
            f"and cite the listed sources.")


def build_presentation_prompt(slide_design_or_ref, target_tool, *, base=None, provenance=None) -> dict:
    """Build a validated ``presentation_prompt@1`` draft for ``target_tool``."""
    design = _load_design(slide_design_or_ref, base=base)
    tool = target_tool if target_tool in ALLOWED_TARGET_TOOLS else DEFAULT_TARGET_TOOL
    language = str(design.get("output_language") or "English")
    title = str(design.get("deck_title") or design.get("task_id") or "Lecture")
    slides = [slide for slide in _as_list(design.get("slides")) if isinstance(slide, dict)]

    parts = [_header(tool, title, language), ""]
    for slide in slides:
        parts.append(_slide_block(slide))
        parts.append("")

    source_list: list[dict] = []
    seen: set[str] = set()
    for slide in slides:
        for source_ref in _strings(slide.get("source_refs")):
            if source_ref not in seen:
                seen.add(source_ref)
                source_list.append({"source_ref": source_ref})
    if source_list:
        parts.append("## Sources")
        parts.append("")
        for entry in source_list:
            parts.append(f"- {entry['source_ref']}")

    prompt = {
        "schema_version": OUTPUT_CONTRACT,
        "task_id": design["task_id"],
        "output_language": language,
        "target_tool": tool,
        "prompt_markdown": "\n".join(parts).rstrip() + "\n",
        "slide_count": len(slides),
        "source_list": source_list,
        "provenance": provenance if isinstance(provenance, dict) else {},
    }
    checked = contracts.validate(prompt, OUTPUT_CONTRACT)
    if not checked["ok"]:
        raise ValueError("invalid presentation_prompt@1: " + "; ".join(checked["errors"]))
    return prompt


def store_prompt(prompt_or_ref, *, base=None) -> str:
    """Persist the prompt's Markdown as a user-visible text artifact; return its ``artifact://`` ref."""
    prompt = _load_prompt(prompt_or_ref, base=base)
    task_id = _safe_task_id(prompt.get("task_id"))
    tool = prompt.get("target_tool") or DEFAULT_TARGET_TOOL
    return artifacts.store_text(f"g03/prompts/{task_id}.{tool}.md", prompt["prompt_markdown"], base=base)


def render_prompt(prompt_or_ref, *, base=None, persist: bool = False) -> dict:
    """Return the Markdown view of a ``presentation_prompt@1`` (optionally persisted as a .md file)."""
    prompt = _load_prompt(prompt_or_ref, base=base)
    rendered = {
        "format": "markdown",
        "markdown": prompt["prompt_markdown"],
        "target_tool": prompt.get("target_tool"),
        "slide_count": prompt.get("slide_count", 0),
    }
    if persist:
        rendered["ref"] = store_prompt(prompt, base=base)
    return rendered


def finalize_presentation_prompt_from_input(slide_design_or_ref, target_tool, *, base=None,
                                            provenance=None) -> dict:
    """Build and persist the presentation prompt through the official G03 finalize path."""
    prompt = build_presentation_prompt(slide_design_or_ref, target_tool, base=base, provenance=provenance)
    return solution.finalize_presentation_prompt(prompt["task_id"], prompt, base=base)
