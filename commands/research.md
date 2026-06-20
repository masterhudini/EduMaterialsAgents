---
description: Run the Research Graph over an approved research-input bundle (thin/stub stage).
argument-hint: "[path or artifact:// ref to a research_graph_input bundle]"
---

# /research

## Usage

```
/research <path-or-artifact-ref-to-research_graph_input>
```

## What it does

Routes into the `orchestrate-research` skill, which runs the **Research Graph**: turn an
approved research-input bundle into a verified, evidence-backed `UserApprovedResearchBundle`
(plan → domain/canonical/recent search → candidate index → *user source-selection gate* →
retrieval → paper review → claim verification → synthesis → *user research gate*).

It consumes only the typed boundary contract `research_graph_input@1` (compact cards +
`artifact://` refs), never raw slides or the full intake state.

> **Thin stub stage:** every node is a no-op; the graph still loads, sequences and emits a valid
> bundle so the spine is runnable end-to-end. Deterministic entry (no LLM):
> `python3 shared/scripts/research/research_flow.py run tests/fixtures/research_graph_input.example.json`
