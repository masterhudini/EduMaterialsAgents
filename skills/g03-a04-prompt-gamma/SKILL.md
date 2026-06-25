---
name: g03-a04-prompt-gamma
description: Assemble the final Graph03 generator prompt tailored to Gamma — a clean card outline (one card per slide) with style and layout directives built from the approved slide_design_set@1, producing presentation_prompt@1 with target_tool=gamma. Executable procedure run by g03-a04; not interactive.
---

# Prompt Builder — Gamma

## Contract

Consume the approved `slide_design_set@1` and `target_tool=gamma`. Produce a `presentation_prompt@1`
whose `prompt_markdown` is a Gamma-shaped card outline, persisted through `solution_prompt_finalize`.
Format the existing design; do not change content or add evidence.

## Workflow

1. Start from the `solution_prompt_build` draft for `gamma`.
2. Shape the Markdown to Gamma's idiom: a short instruction to generate a presentation in the lecture
   language with ONE card per slide in the given order, then one heading per slide. Under each heading
   put the title, a concise version of the narrative, the bullets and a layout/visual directive; mark
   `[KEEP]` / `[UPDATE]` / `[ADD]`. Add overall style notes (tone, density, audience). End with the
   source list to cite where relevant. Keep cards scannable — Gamma expands terse outlines.
3. Fill `source_list` and `provenance`; persist with `solution_prompt_finalize`; optionally call
   `solution_prompt_render` to write the user-readable `.md`.

## Output requirements

A validated `presentation_prompt@1` with `target_tool="gamma"`, complete `prompt_markdown`,
`slide_count`, `source_list` and `provenance`. In the lecture language.

## Boundaries

Do not change slide content, statuses or design; no new evidence; no calls to G01/G02; do not emit a
prompt for another tool.

## Failure handling

`needs_input` on an absent/invalid design set or tool choice.

## Resume

Stateless; regenerate the Gamma prompt from the approved design set on revision.

{{HOST_ADAPTER}}
