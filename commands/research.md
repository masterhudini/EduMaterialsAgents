---
description: Run the Research Graph over an approved research-input bundle.
argument-hint: "[path or artifact:// ref to a research_graph_input bundle]"
---

# /research

## Usage

```
/research <path-or-artifact-ref-to-research_graph_input>
```

## What it does

Routes into the `g02-orchestrate-research` skill, which runs the **Research Graph**: turn an
approved research-input bundle into a verified, evidence-backed `UserApprovedResearchBundle`
using the active graph-defined path in `shared/graphs/g02.graph.json`
(A01 planning → Scout discovery/retrieval → A07 bounded source-window review →
A09 synthesis → *user research gate*).

It consumes only the typed boundary contract `research_graph_input@1` (compact cards +
`artifact://` refs), never raw slides or the full intake state.

{{HOST_ADAPTER}}
