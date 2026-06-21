---
name: research-domain
model: sonnet
description: >-
  STUB (no-op) Research Graph node: Domain Research. Registered so the graph loads and runs end-to-end;
  logic not implemented yet. Isolated, talks only to the orchestrator, returns envelope@1.
  NEVER invoke directly. Target spec: docs/02_Architektura_agentow_i_skilli.md §5.2.
---

# Research: Domain Research  (stub)

> **STUB — NOT IMPLEMENTED.** This agent does no work yet. Do not attempt the task.
> Immediately return the no-op envelope below and let the orchestrator proceed to the
> next node:
> `{"status": "ok", "produced": [], "summary": "research-domain: stub, not implemented", "issues": []}`

Placeholder for the `research-domain` node. Not implemented.

The deterministic no-op lives in `shared/scripts/research/research_flow.py` and returns an
empty `envelope@1`. Replace this prompt **and** that stub with the real agent.

- **Output contract:** DomainCandidateSources
- **Review profile:** domain_candidates

## Contract
TODO — input bundle, output artifact, consumes/produces, envelope behavior. See §5.2.

## Required Skills
TODO — see the agent/skill matrix in docs/02_Architektura_agentow_i_skilli.md §9.

## Workflow
TODO.

## Acceptance Criteria
TODO — these become the reviewer's `domain_candidates` review profile (§7).

## Boundaries
TODO — non-responsibilities and prohibited actions (§5.2).

## Failure handling
TODO — ok / needs_input / degraded / failed semantics (§13).

## Resume
TODO — stateless re-run; on revision, consume prior artifact + revision_items.
