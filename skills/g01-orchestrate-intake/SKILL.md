---
name: g01-orchestrate-intake
description: Run the Intake / Understanding Graph from an uploaded lecture PDF through isolated producer agents, one universal reviewer and the user intake gate, emitting the approved research_graph_input@1 handoff for the Research Graph. Use as the graph's only conversational surface and final handoff coordinator.
---

# Orchestrate Intake

Drive the Intake Graph without performing producer work. Read `shared/graphs/g01.graph.json` as the
node and contract source of truth. Agents never address the user; relay their questions and explain
every required human action.

## Contract

- Consume a path or artifact reference satisfying `intake_graph_input@1` (the uploaded PDF + ingestion
  profile).
- Produce TWO validated boundary outputs after the user intake gate (both depend on the gate decisions):
  - `research_graph_input@1` — the approved handoff the Research Graph (g01 -> g02) consumes (from a03).
  - `lecture_baseline@1` — the lecture skeleton the Solution Graph (g01 -> g03) consumes (from a04);
    declared as the manifest `secondary_exits`. Capture and surface BOTH refs.
- Persist intermediate artifacts and carry refs instead of full documents in orchestration context.
- Use `envelope@1` for execution status and `review_decision@1` for reviewer verdicts.

## Workflow

1. Validate and register the input through the deterministic front door; stop on contract failure.
2. Run `g01-a01-pdf-intake` to produce `SlideViews` through `intake_slide_views`. Its deterministic
   first step may be `intake_pdf_extract`, which emits `pdf_extract_result@1` when the local host has
   a PDF text backend such as `pypdf`; if the backend is missing, keep the dependency-missing state
   explicit and do not invent slide text. Then run `g01-a02-understanding` to produce
   `IntakeUnderstanding`; persist each artifact and carry its ref.
3. After every producer artifact, invoke `g01-a10-output-reviewer` with exactly one artifact, the
   node's review profile, the output contract, acceptance criteria and revision history. Handle
   `APPROVED` / `REVISE` / `BLOCKED` per the manifest revision policy.
4. Run the **User Intake Gate** (it sits BETWEEN a02 and a03/a04 — its decisions are inputs to both
   producers, so it must run first): present the understanding (slide count, detected domains, main
   concepts, potential logic issues, claims requiring research) and collect: confirm audience,
   confirm domains, approve research scope, mark locked sections. These are persisted as
   `intake_gate_decisions@1` and threaded to a03/a04.
5. Run `g01-a03-intake-synthesizer` to project the approved understanding + gate decisions into
   `research_graph_input@1` (compact cards + refs), review it, then validate, freeze and emit the handoff.
6. Run `g01-a04-lecture-baseline` to project SlideViews + IntakeUnderstanding + the gate's locked
   sections into `lecture_baseline@1` (the lecture skeleton + claim_id/concept_id join keys g03 needs),
   review it, then capture its ref as the second boundary output (`secondary_exits`).

## Output requirements

- Two typed artifacts cross the boundary: `research_graph_input@1` (-> g02) and `lecture_baseline@1`
  (-> g03), plus `artifact://` refs inside them. Never emit raw PDF text or full intake states.
- Default human-readable output to English when `output_language` is absent.

## Boundaries

- Do not verify claims, search literature, design a change plan or rewrite slides — that is later graphs.
- Do not let a producer self-approve or bypass the user intake gate.
- Do not change graph order or boundary contracts in prompt logic.

## Failure handling

Relay `needs_input` with an exact response request. Continue from `degraded` only when omissions are
explicit and the manifest permits. Stop on `failed`, unresolved `BLOCKED` or invalid human authorization.

## Resume

Resume from the latest approved artifact per node. A frozen intake handoff is immutable; a later change
creates a new task or version.

{{HOST_ADAPTER}}
