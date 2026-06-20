---
name: research-synthesizer
model: sonnet
description: >-
  STUB (no-op) Research Graph node: Research Synthesizer. Registered so the graph loads and runs end-to-end;
  logic not implemented yet. Isolated, talks only to the orchestrator, returns envelope@1.
  NEVER invoke directly. Target spec: docs/02_Architektura_agentow_i_skilli.md §5.9.
---

# Research: Research Synthesizer  (stub)

Placeholder for the `research-synthesizer` node. Not implemented.

The deterministic no-op lives in `shared/scripts/research/research_flow.py` and returns an
empty `envelope@1`. Replace this prompt **and** that stub with the real agent.

- **Output contract:** ResearchState, EvidenceMap, HumanResearchValidationPacket, SolutionInputCandidate
- **Review profile:** research_synthesis

## Contract
TODO — input bundle, output artifact, consumes/produces, envelope behavior. See §5.9.

## Required Skills
TODO — see the agent/skill matrix in docs/02_Architektura_agentow_i_skilli.md §9.

## Workflow
TODO.

## Acceptance Criteria
TODO — these become the reviewer's `research_synthesis` review profile (§7).

## Boundaries
TODO — non-responsibilities and prohibited actions (§5.9).

## Failure handling
TODO — ok / needs_input / degraded / failed semantics (§13).

## Resume
TODO — stateless re-run; on revision, consume prior artifact + revision_items.
