# shared/graphs - graph manifests (single source of truth)

One `*.graph.json` file defines each graph. The manifest is the authority for node order,
contracts, execution profiles and MCP operation names. Flow code, orchestrator skills and plugin
packaging must agree with this file. `core/graph_check.py` checks that declared contracts and
physical agent files exist.

## Manifest Shape

```jsonc
{
  "graph_id": "g02",
  "orchestrator": "g02-orchestrate-research",
  "reviewer": null,
  "default_execution_profile": "scout_e2e",
  "entry_node": "g02-a01-planner",
  "exit_artifact": "user_approved_research_bundle@1",
  "nodes": [
    {
      "name": "g02-a01-planner",
      "kind": "agent",
      "input_contract": "research_planner_input@1",
      "output_contract": "research_plan@1",
      "operations": {
        "prepare": "research_planner_prepare",
        "finalize": "research_planner_finalize"
      }
    },
    {
      "name": "research-scout-fanout",
      "kind": "script",
      "operations": {
        "provider_setup": "research_provider_setup",
        "run": "research_scout_fanout"
      }
    },
    {
      "name": "user-research-gate",
      "kind": "user-gate",
      "operations": {
        "prepare": "research_human_gate_prepare",
        "finalize": "research_bundle_finalize",
        "trace": "research_trace"
      }
    }
  ],
  "sequence": ["..."]
}
```

## G02 Active Status

`g02.graph.json` defines the active Research Graph as Scout E2E. The default execution profile is
`scout_e2e`; it does not run A10 review.

The active path is:

```text
A01 -> deterministic Scout fanout -> A07 bounded source-window agents
-> A09 synthesizer -> Human Research Gate -> user_approved_research_bundle@1
```

A07 runs once per prepared Scout topic/source work item. It uses bounded selected windows and
compact intake context, never full PDFs. A09 consumes aggregated `a07_reviews@1`, may use bounded
deep-dive windows, materializes `research_state@1`, `evidence_map@1`, `research_summary@1`, a human
validation packet and `solution_input_candidate@1`. The Graph03 bundle is created only after the
Human Research Gate approves.

Legacy A02-A06/A08/A11/source-selection and A10 review code remains in source for migration and
module-level tests, but the current MCP runtime returns `deprecated_tool` for those tool names.
