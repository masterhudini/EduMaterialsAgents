# shared/graphs - graph manifests (single source of truth)

One `*.graph.json` file defines each graph. The manifest is the authority for node order, contract
refs, review profiles and execution profiles. Flow code, orchestrator skills and plugin packaging
must agree with this file. `core/graph_check.py` checks that the declared contracts and physical
agent files exist.

## Manifest Shape

```jsonc
{
  "graph_id": "g02",
  "orchestrator": "g02-orchestrate-research",
  "reviewer": "g02-a10-output-reviewer",
  "entry_node": "g02-a01-planner",
  "exit_artifact": "user_approved_research_bundle@1",
  "nodes": [
    {
      "name": "g02-a01-planner",
      "kind": "agent",
      "input_contract": "research_planner_input@1",
      "output_contract": "research_plan@1",
      "review_profile": "research_plan"
    },
    {"name": "user-source-selection-gate", "kind": "user-gate"}
  ],
  "sequence": ["..."]
}
```

## G02 Fast Status

`g02.graph.json` defines the Research Graph from A01 through A11, A10 and the two human gates. The
default execution profile is `fast`.

The implemented fast path is:

```text
A01 -> A02/A03/A04/A11 discovery -> A05 -> Human Source Selection Gate
-> A06 -> source-scoped A07 -> skip A08 -> A09 -> Human Research Gate
-> user_approved_research_bundle@1
```

A07 runs once per accepted scholarly document or accepted market-case bundle. It uses bounded
deterministic text windows and produces compact `paper_review@1` artifacts. A08 remains in the
manifest and repo for future profiles, but `fast.skip_nodes` disables it. A09 is the last producer
in fast mode and creates `research_state@1`, a compact evidence map, a human validation packet and a
SolutionInputCandidate. The Graph03 bundle is created only after the Human Research Gate approves
reviewed A09 output.

Fast review policy:

- A10 is mandatory for A01, A05, A06 and A09.
- A07 uses conditional A10 when output is degraded, locations are missing, evidence conflicts are
  present, prompt-injection flags are present or the document is central.
- Clean A02, A03, A04 and A11 outputs may receive deterministic fast-track approval.

The runner remains intentionally serial for discovery and A07. Broad fan-out/fan-in scheduling is a
future optimization, not part of the fast prototype.
