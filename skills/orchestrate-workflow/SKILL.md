---
name: orchestrate-workflow
description: Run the complete educational-materials workflow end to end — Intake (g01) then Research (g02) then Solution (g03) — from a lecture PDF to an approved solution_blueprint@1, chaining each graph's approved boundary output into the next. Trigger when the user asks to "odswiez wyklad" / "odśwież wykład" / "odswiez materialy edukacyjne" / "odśwież materiały edukacyjne" / "refresh lecture" / "refresh educational materials" with a path. Use as the single conversational surface for the whole pipeline; it delegates to each graph's orchestrator and never does producer work itself.
---

# Orchestrate Workflow (g01 → g02 → g03)

Run the three graphs in sequence and carry the approved boundary artifacts between them. Do NOT do
any producer/reviewer work here — each graph has its own orchestrator, isolated agents, reviewer and
human gates. This skill only sequences them and threads the refs. Every human gate inside each graph
still fires; never skip or auto-approve them.

## The chain (boundaries are contracts, carried as `artifact://` refs)

```
g01 ──research_graph_input@1───────────────────────────────► g02
g01 ──lecture_baseline@1────────────────┐
g02 ──user_approved_research_bundle@1───┴── solution_graph_input@1 ──► g03 ──► solution_blueprint@1
```

g01 has TWO exits: `research_graph_input@1` (its handoff, straight into g02) and `lecture_baseline@1`
(the lecture skeleton g02 never carries — g03 needs it to map findings onto slides). Capture BOTH.

## Workflow

1. **Intake (g01)** — run the `g01-orchestrate-intake` loop from the lecture PDF. On completion you
   have the `research_graph_input@1` handoff. ALSO capture the **`lecture_baseline@1` ref** produced
   by `g01-a04-lecture-baseline` (its finalize op returns it during the run) — you will need it for
   g03. The user intake gate runs here.
2. **Research (g02)** — run the `g02-orchestrate-research` loop with the `research_graph_input@1` from
   step 1. On completion the report's `output_ref` is the approved `user_approved_research_bundle@1`.
   The two-step source-selection gate and the Human Research Gate run here.
3. **Solution (g03)** — run the `g03-orchestrate-solution` loop with both refs from steps 1–2:
   `{lecture_baseline_ref, research_bundle_ref}`. On completion you have the approved
   `solution_blueprint@1`. The user solution gate runs here.
4. Report the final `solution_blueprint@1` and the boundary refs of each stage.

## Output requirements

- Only the typed boundary artifacts cross between graphs (plus `artifact://` refs inside them). Never
  copy a graph's full internal state into the next graph or into orchestration context.
- Default human-readable output to English when `output_language` is absent.

## Boundaries

- Do not perform intake, research or solution producer work — delegate to each graph's orchestrator.
- Do not skip, reorder or auto-approve any graph's human gate.
- Do not invent a boundary artifact; if a stage did not complete, stop and report where.

## Failure handling

If any graph returns `failed`/`blocked` or an unresolved `BLOCKED`, stop the chain and report which
graph and node failed; do not fabricate the downstream input. Resume each graph from its own
resume token.

## Resume

Each graph resumes independently from its own token. A frozen boundary artifact is immutable; a later
change starts a new task or version.

{{HOST_ADAPTER}}
