"""Handoff-contract registry: load and validate typed artifacts exchanged between graph
components (skills / agents).

Contracts are versioned JSON-Schema files under ``shared/contracts/<type>.schema.json``.
A reference is ``"<type>@<major>"`` (e.g. ``"envelope@1"``); the bare ``"<type>"`` matches the
current major. A minimal validator (a small JSON-Schema subset: type, required, properties,
items, enum) keeps the registry dependency-free and offline-deterministic.

Domain-agnostic: this registry enforces only the SHAPE of the factory's own handoff artifacts,
never any product-domain meaning. Pure stdlib.
"""
from __future__ import annotations

import json
from pathlib import Path

# core/contracts.py -> core -> scripts -> shared ; schemas live in shared/contracts.
SCHEMA_DIR = Path(__file__).resolve().parents[2] / "contracts"


def parse_ref(ref: str) -> tuple[str, int | None]:
    """Split ``"type@major"`` into ``(type, major)``; bare ``"type"`` -> major ``None``."""
    if "@" in ref:
        name, ver = ref.split("@", 1)
        try:
            major = int(str(ver).split(".", 1)[0])
        except ValueError as exc:
            raise ValueError(f"bad version in ref {ref!r}") from exc
        return name, major
    return ref, None


def schema_path(name: str) -> Path:
    return SCHEMA_DIR / f"{name}.schema.json"


def load_schema(ref: str) -> dict:
    """Load the schema for ``ref``. Raises ``KeyError`` if the type is unknown and
    ``ValueError`` if the requested major does not match the registered schema."""
    name, major = parse_ref(ref)
    path = schema_path(name)
    if not path.exists():
        raise KeyError(f"unknown contract type {name!r} (no {path.name})")
    schema = json.loads(path.read_text())
    registered = int(schema.get("x-major", 1))
    if major is not None and registered != major:
        raise ValueError(f"contract {name!r} is major {registered}, requested @{major}")
    return schema


def _type_ok(value: object, t: str) -> bool:
    # bool is a subclass of int — keep numeric/integer checks honest.
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "boolean":
        return isinstance(value, bool)
    return {
        "object": lambda v: isinstance(v, dict),
        "array": lambda v: isinstance(v, list),
        "string": lambda v: isinstance(v, str),
        "null": lambda v: v is None,
    }.get(t, lambda v: False)(value)


def _validate(value: object, schema: dict, path: str, errors: list[str]) -> None:
    here = path or "$"
    declared = schema.get("type")
    if declared is not None:
        types = declared if isinstance(declared, list) else [declared]
        if not any(_type_ok(value, t) for t in types):
            errors.append(f"{here}: expected type {declared}, got {type(value).__name__}")
            return  # wrong container type — deeper checks would be noise
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{here}: {value!r} not in enum {schema['enum']}")
    if isinstance(value, dict):
        for req in schema.get("required", []):
            if req not in value:
                errors.append(f"{here}: missing required '{req}'")
        for key, subschema in schema.get("properties", {}).items():
            if key in value:
                _validate(value[key], subschema, f"{path}.{key}" if path else key, errors)
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            _validate(item, schema["items"], f"{here}[{i}]", errors)


def validate(payload: object, ref: str) -> dict:
    """Validate ``payload`` against contract ``ref`` -> ``{"ok": bool, "errors": [...]}``."""
    schema = load_schema(ref)
    errors: list[str] = []
    _validate(payload, schema, "", errors)
    return {"ok": not errors, "errors": errors}


def validate_envelope(payload: object) -> dict:
    """Validate a universal subagent return envelope (``envelope@1``)."""
    return validate(payload, "envelope@1")


def list_types() -> list[str]:
    suffix = ".schema.json"
    return sorted(p.name[: -len(suffix)] for p in SCHEMA_DIR.glob(f"*{suffix}"))
