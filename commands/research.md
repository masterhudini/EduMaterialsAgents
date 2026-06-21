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
(plan → domain/canonical/recent search → candidate index → *user source-selection gate* →
retrieval → paper review → claim verification → synthesis → *user research gate*).

It consumes only the typed boundary contract `research_graph_input@1` (compact cards +
`artifact://` refs), never raw slides or the full intake state.

{{HOST_ADAPTER}}