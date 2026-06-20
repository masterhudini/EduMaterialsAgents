---
name: claim-verification
model: sonnet
description: >-
  STUB (no-op) Research Graph node: Claim Verification. Registered so the graph loads and runs end-to-end;
  logic not implemented yet. Isolated, talks only to the orchestrator, returns envelope@1.
  NEVER invoke directly. Target spec: docs/02_Architektura_agentow_i_skilli.md §5.8.
---

# Research: Claim Verification  (stub)

Placeholder for the `claim-verification` node. Not implemented.

The deterministic no-op lives in `shared/scripts/research/research_flow.py` and returns an
empty `envelope@1`. Replace this prompt **and** that stub with the real agent.

- **Output contract:** ClaimAssessmentState
- **Review profile:** claim_assessment

## Contract
TODO — input bundle, output artifact, consumes/produces, envelope behavior. See §5.8.

## Required Skills
TODO — see the agent/skill matrix in docs/02_Architektura_agentow_i_skilli.md §9.

## Workflow
TODO.

## Acceptance Criteria
TODO — these become the reviewer's `claim_assessment` review profile (§7).

## Boundaries
TODO — non-responsibilities and prohibited actions (§5.8).

## Failure handling
TODO — ok / needs_input / degraded / failed semantics (§13).

## Resume
TODO — stateless re-run; on revision, consume prior artifact + revision_items.
