---
name: research-planner
model: sonnet
description: >-
  STUB (no-op) Research Graph node: Research Planner. Registered so the graph loads and runs end-to-end;
  logic not implemented yet. Isolated, talks only to the orchestrator, returns envelope@1.
  NEVER invoke directly. Target spec: docs/02_Architektura_agentow_i_skilli.md §5.1.
---

# Research: Research Planner  (stub)

Placeholder for the `research-planner` node. Not implemented.

The deterministic no-op lives in `shared/scripts/research/research_flow.py` and returns an
empty `envelope@1`. Replace this prompt **and** that stub with the real agent.

- **Output contract:** ResearchPlan
- **Review profile:** research_plan

## Contract
TODO — input bundle, output artifact, consumes/produces, envelope behavior. See §5.1.

## Required Skills
TODO — see the agent/skill matrix in docs/02_Architektura_agentow_i_skilli.md §9.

## Workflow
TODO.

## Acceptance Criteria
TODO — these become the reviewer's `research_plan` review profile (§7).

## Boundaries
TODO — non-responsibilities and prohibited actions (§5.1).

## Failure handling
TODO — ok / needs_input / degraded / failed semantics (§13).

## Resume
TODO — stateless re-run; on revision, consume prior artifact + revision_items.
