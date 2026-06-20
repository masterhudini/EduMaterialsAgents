---
name: orchestrate-research
version: 0.1.0
model: opus
description: >-
  Use to run the Research Graph over an approved research-input bundle (the /research command).
  Hosts the run: loads + validates the boundary contract, sequences the research nodes and
  reviewer loops, presents the two user gates (source selection, research approval), and
  freezes a HumanApprovedResearchBundle. THIN STUB STAGE — nodes are no-ops. Do NOT invoke a
  single research agent directly; this orchestrator is the only conversational surface.
---

# Orchestrate Research (thin stub)

Hosts one run of the Research Graph. The node sequence is the single source of truth in
`shared/graphs/research.graph.json`; this prompt and `shared/scripts/research/research_flow.py`
must agree with it (`core/graph_check.py` verifies registration).

## Contract

- **Input (boundary):** `research_graph_input@1` — compact cards + `artifact://` refs, never raw
  material (design §8.2/§8.3). Loaded via `handoff.load_handoff(ref, contract_ref=...)`, which
  re-validates on entry.
- **Output (boundary):** `human_approved_research_bundle@1` — emitted via `handoff.emit_handoff`.

## Workflow (current: stub)

The deterministic spine lives in `research_flow.run()`:
load+validate input → walk stub nodes (each a no-op `envelope@1`) → freeze stub bundle →
emit handoff. Reviewers are runs of the one `research-output-reviewer` with a per-node profile;
the two `user-gate` steps auto-approve in stub mode.

To run the spine without an LLM:
`python3 shared/scripts/research/research_flow.py tests/fixtures/research_graph_input.example.json`

## Boundaries

- DO NOT pass full upstream state across the boundary — only the bundle + refs.
- DO NOT let agents talk to the user; relay their `needs_input` yourself.

## Failure handling / Resume

Stub stage: not yet implemented. Target semantics: `ok / needs_input / degraded / failed`
(§13); reviewer verdicts live in `ReviewDecision`, not in the envelope status.
