---
name: g03-a04-prompt-notebooklm
description: Assemble the final Graph03 generator prompt tailored to NotebookLM — a source-grounded briefing plus a slide outline (one section per slide) built from the approved slide_design_set@1, producing presentation_prompt@1 with target_tool=notebooklm. Executable procedure run by g03-a04; not interactive.
---

# Prompt Builder — NotebookLM

## Contract

Consume the approved `slide_design_set@1` and `target_tool=notebooklm`. Produce a
`presentation_prompt@1` whose `prompt_markdown` is a NotebookLM-shaped brief, persisted through
`solution_prompt_finalize`. Format the existing design; do not change content or add evidence.

## Workflow

1. Start from the `solution_prompt_build` draft for `notebooklm`.
2. Shape the Markdown to NotebookLM's idiom: an instruction to use the attached/added sources to
   produce a briefing document and a slide outline in the lecture language, then one section per slide.
   For each slide give the title, the 6-10 sentence narrative, the key bullets, the layout hint and its
   sources; mark `[KEEP]` / `[UPDATE]` / `[ADD]`. End with the consolidated source list and an explicit
   instruction to ground every claim in those sources.
3. Fill `source_list` and `provenance`; persist with `solution_prompt_finalize`; optionally call
   `solution_prompt_render` to write the user-readable `.md`.

## Output requirements

A validated `presentation_prompt@1` with `target_tool="notebooklm"`, complete `prompt_markdown`,
`slide_count`, `source_list` and `provenance`. In the lecture language.

## Boundaries

Do not change slide content, statuses or design; no new evidence; no calls to G01/G02; do not emit a
prompt for another tool.

## Failure handling

`needs_input` on an absent/invalid design set or tool choice.

## Resume

Stateless; regenerate the NotebookLM prompt from the approved design set on revision.

{{HOST_ADAPTER}}
