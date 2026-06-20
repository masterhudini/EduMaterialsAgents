"""Typed handoff bundles — the seam between subgraphs.

A subgraph ends by freezing its state into a product dict (``state.freeze``). ``emit_handoff``
validates that dict against its declared contract, stores it in the artifact store, and returns
a typed descriptor ``{type, schema_version, ref}``. The next subgraph loads it with
``load_handoff``, which re-validates on the way in.

This descriptor (plus the ``artifact://`` refs the bundle carries internally for lazy
hydration) is the ONLY thing that crosses a subgraph boundary — never the full upstream state
(design §2). Pure stdlib.
"""
from __future__ import annotations

from pathlib import Path

from . import artifacts, contracts

HANDOFF_SUBDIR = "handoffs"


def _full_ref(contract_ref: str) -> tuple[str, int]:
    name, major = contracts.parse_ref(contract_ref)
    if major is None:
        major = int(contracts.load_schema(contract_ref).get("x-major", 1))
    return name, major


def emit_handoff(bundle: dict, contract_ref: str, *, name: str,
                 base: str | Path | None = None) -> dict:
    """Validate ``bundle`` against ``contract_ref``, store it, return a typed descriptor.

    Raises ``ValueError`` if the bundle does not satisfy its contract — a subgraph never hands
    off a shape the next graph cannot consume.
    """
    res = contracts.validate(bundle, contract_ref)
    if not res["ok"]:
        raise ValueError(f"handoff {name!r} fails {contract_ref}: " + "; ".join(res["errors"]))
    type_, major = _full_ref(contract_ref)
    ref = artifacts.store(f"{HANDOFF_SUBDIR}/{name}.json", bundle, base=base)
    return {"type": type_, "schema_version": f"{type_}@{major}", "ref": ref}


def load_handoff(ref_or_descriptor, *, contract_ref: str | None = None,
                 base: str | Path | None = None) -> dict:
    """Hydrate a handoff bundle from a ref or a descriptor; re-validate if ``contract_ref`` given."""
    ref = ref_or_descriptor["ref"] if isinstance(ref_or_descriptor, dict) else ref_or_descriptor
    bundle = artifacts.hydrate(ref, base=base)
    if contract_ref:
        res = contracts.validate(bundle, contract_ref)
        if not res["ok"]:
            raise ValueError(f"incoming handoff fails {contract_ref}: " + "; ".join(res["errors"]))
    return bundle
