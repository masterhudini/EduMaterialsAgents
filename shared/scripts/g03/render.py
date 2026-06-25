"""User-readable rendering for ``solution_blueprint@1``.

The blueprint remains the typed G03 deliverable. This module adds the user-facing view: a compact
Markdown plan and a short console summary that can be shown at the solution gate or after approval.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys as _sys

_sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> shared/scripts

from core import artifacts, contracts  # noqa: E402

OUTPUT_CONTRACT = "solution_blueprint@1"


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _text(value: object, default: str = "") -> str:
    text = str(value).strip() if value is not None else ""
    return text or default


def _is_polish(language: object) -> bool:
    value = str(language or "").casefold()
    return value.startswith("pl") or "polish" in value or "polski" in value


def _code(value: object) -> str:
    return "`" + _text(value, "n/a").replace("`", "'") + "`"


def _csv(values: object, *, empty: str) -> str:
    items = [_code(item) for item in _as_list(values) if _text(item)]
    return ", ".join(items) if items else empty


def _safe_task_id(task_id: object) -> str:
    value = _text(task_id, "solution").strip()
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
    return safe.strip("._") or "solution"


def _load_json_path(path: str | Path) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def load_blueprint(path_or_ref, *, base=None) -> dict:
    """Load and validate a ``solution_blueprint@1`` from an object, descriptor, path or ref."""
    if isinstance(path_or_ref, dict):
        if path_or_ref.get("schema_version") == OUTPUT_CONTRACT and "lecture_outline" in path_or_ref:
            blueprint = path_or_ref
        elif isinstance(path_or_ref.get("ref"), str):
            blueprint = artifacts.hydrate(path_or_ref["ref"], base=base)
        else:
            raise ValueError("blueprint object must be solution_blueprint@1 or a descriptor with ref")
    else:
        text = str(path_or_ref)
        if text.startswith(artifacts.SCHEME):
            blueprint = artifacts.hydrate(text, base=base)
        else:
            loaded = _load_json_path(text)
            blueprint = artifacts.hydrate(loaded["ref"], base=base) if isinstance(loaded.get("ref"), str) else loaded

    checked = contracts.validate(blueprint, OUTPUT_CONTRACT)
    if not checked["ok"]:
        raise ValueError("invalid solution_blueprint@1: " + "; ".join(checked["errors"]))
    return blueprint


def _labels(polish: bool) -> dict[str, str]:
    if polish:
        return {
            "title": "Nowy plan prezentacji z poprawkami",
            "task": "Zadanie",
            "language": "Język",
            "summary": "Podsumowanie",
            "sections": "Sekcje",
            "applied": "Zastosowane poprawki",
            "deferred": "Odroczone elementy",
            "sources": "Źródła",
            "plan": "Plan prezentacji",
            "slides": "Slajdy",
            "no_slides": "brak wskazanych slajdów",
            "change": "Zmiana",
            "section": "Sekcja",
            "trace": "Ślad",
            "source_list": "Atrybucja źródeł",
            "used_for": "Użyte dla",
            "reason": "Powód",
            "related_claim": "Powiązane twierdzenie",
        }
    return {
        "title": "Updated presentation plan with changes",
        "task": "Task",
        "language": "Language",
        "summary": "Summary",
        "sections": "Sections",
        "applied": "Applied updates",
        "deferred": "Deferred items",
        "sources": "Sources",
        "plan": "Presentation plan",
        "slides": "Slides",
        "no_slides": "no slide ids",
        "change": "Change",
        "section": "Section",
        "trace": "Trace",
        "source_list": "Source attribution",
        "used_for": "Used for",
        "reason": "Reason",
        "related_claim": "Related claim",
    }


def metrics(blueprint: dict) -> dict:
    """Return counts used by the inline and Markdown summaries."""
    return {
        "sections": len(_as_list(blueprint.get("lecture_outline"))),
        "applied_updates": len(_as_list(blueprint.get("applied_updates"))),
        "deferred_items": len(_as_list(blueprint.get("deferred_items"))),
        "source_attribution": len(_as_list(blueprint.get("source_attribution"))),
    }


def _pl_count(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def inline_summary(blueprint_or_ref, *, base=None) -> str:
    """A one-line console summary for the rendered solution plan."""
    blueprint = load_blueprint(blueprint_or_ref, base=base)
    counts = metrics(blueprint)
    task = _text(blueprint.get("task_id"), "SOLUTION")
    if _is_polish(blueprint.get("output_language")):
        return (
            f"solution_blueprint@1 {task}: "
            f"{_pl_count(counts['sections'], 'sekcja', 'sekcje')}, "
            f"{_pl_count(counts['applied_updates'], 'zastosowana poprawka', 'zastosowane poprawki')}, "
            f"{_pl_count(counts['deferred_items'], 'odroczony element', 'odroczone elementy')}, "
            f"{_pl_count(counts['source_attribution'], 'źródło', 'źródła')}."
        )
    return (
        f"solution_blueprint@1 {task}: {counts['sections']} sections, "
        f"{counts['applied_updates']} applied updates, "
        f"{counts['deferred_items']} deferred items, "
        f"{counts['source_attribution']} sources."
    )


def render_markdown(blueprint_or_ref, *, base=None) -> str:
    """Render ``solution_blueprint@1`` as a user-readable Markdown plan."""
    blueprint = load_blueprint(blueprint_or_ref, base=base)
    polish = _is_polish(blueprint.get("output_language"))
    labels = _labels(polish)
    counts = metrics(blueprint)
    empty = labels["no_slides"]
    lines: list[str] = [
        f"# {labels['title']}",
        "",
        f"- {labels['task']}: {_code(blueprint.get('task_id'))}",
        f"- {labels['language']}: {_text(blueprint.get('output_language'), 'English')}",
        "",
        f"## {labels['summary']}",
        "",
        f"- {labels['sections']}: {counts['sections']}",
        f"- {labels['applied']}: {counts['applied_updates']}",
        f"- {labels['deferred']}: {counts['deferred_items']}",
        f"- {labels['sources']}: {counts['source_attribution']}",
        "",
        f"## {labels['plan']}",
        "",
    ]

    for index, section in enumerate(_as_list(blueprint.get("lecture_outline")), start=1):
        if not isinstance(section, dict):
            continue
        title = _text(section.get("title"), "Untitled section")
        lines.append(f"{index}. **{title}** ({_code(section.get('section_id'))})")
        summary = _text(section.get("summary"))
        if summary:
            lines.append(f"   - {summary}")
        lines.append(f"   - {labels['slides']}: {_csv(section.get('slide_ids'), empty=empty)}")
    if not _as_list(blueprint.get("lecture_outline")):
        lines.append("- n/a")

    lines.extend(["", f"## {labels['applied']}", ""])
    for update in _as_list(blueprint.get("applied_updates")):
        if not isinstance(update, dict):
            continue
        lines.append(f"### {_text(update.get('update_id'), 'update')}")
        target_slides = update.get("target_slide_ids")
        if _as_list(target_slides):
            lines.append(f"- {labels['slides']}: {_csv(target_slides, empty=empty)}")
        if _text(update.get("target_section_id")):
            lines.append(f"- {labels['section']}: {_code(update.get('target_section_id'))}")
        lines.append(f"- {labels['change']}: {_text(update.get('change_summary'), 'n/a')}")
        if _text(update.get("finding_ref")):
            lines.append(f"- {labels['trace']}: {_code(update.get('finding_ref'))}")
        if _as_list(update.get("source_refs")):
            lines.append(f"- {labels['sources']}: {_csv(update.get('source_refs'), empty='n/a')}")
        lines.append("")
    if not _as_list(blueprint.get("applied_updates")):
        lines.append("- n/a")
    elif lines and lines[-1] == "":
        lines.pop()

    lines.extend(["", f"## {labels['deferred']}", ""])
    for item in _as_list(blueprint.get("deferred_items")):
        if not isinstance(item, dict):
            continue
        lines.append(f"- **{_text(item.get('item_id'), 'deferred')}**")
        lines.append(f"  - {labels['reason']}: {_text(item.get('reason'), 'n/a')}")
        if _text(item.get("related_claim_ref")):
            lines.append(f"  - {labels['related_claim']}: {_code(item.get('related_claim_ref'))}")
    if not _as_list(blueprint.get("deferred_items")):
        lines.append("- n/a")

    lines.extend(["", f"## {labels['source_list']}", ""])
    for item in _as_list(blueprint.get("source_attribution")):
        if not isinstance(item, dict):
            continue
        used_for = _csv(item.get("used_for"), empty="n/a")
        lines.append(f"- {_code(item.get('source_ref'))}: {labels['used_for']} {used_for}")
    if not _as_list(blueprint.get("source_attribution")):
        lines.append("- n/a")

    return "\n".join(lines).rstrip() + "\n"


def render_blueprint(path_or_ref, *, base=None, persist: bool = False) -> dict:
    """Return Markdown, inline summary and metrics for a ``solution_blueprint@1``."""
    blueprint = load_blueprint(path_or_ref, base=base)
    rendered = {
        "format": "markdown",
        "markdown": render_markdown(blueprint),
        "inline_summary": inline_summary(blueprint),
        "metrics": metrics(blueprint),
    }
    if persist:
        rendered["ref"] = store_markdown(blueprint, rendered["markdown"], base=base)
    return rendered


def store_markdown(blueprint_or_ref, markdown: str | None = None, *, base=None) -> str:
    """Persist the Markdown view as a text artifact and return its ``artifact://`` ref."""
    blueprint = load_blueprint(blueprint_or_ref, base=base)
    content = markdown if markdown is not None else render_markdown(blueprint)
    task_id = _safe_task_id(blueprint.get("task_id"))
    return artifacts.store_text(f"g03/render/{task_id}.solution-plan.md", content, base=base)
