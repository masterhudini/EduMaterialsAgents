---
name: g03-a04-prompt-gpt-pro
description: Assemble the final Graph03 generator prompt tailored to GPT Pro — a full generation instruction (role, task, per-slide specification and constraints) built from the approved slide_design_set@1, producing presentation_prompt@1 with target_tool=gpt_pro. Executable procedure run by g03-a04; not interactive.
---

# Prompt Builder — GPT Pro

## Contract

Consume the approved `slide_design_set@1` and `target_tool=gpt_pro`. Produce a `presentation_prompt@1`
whose `prompt_markdown` is a complete GPT Pro generation instruction, persisted through
`solution_prompt_finalize`. Format the existing design; do not change content or add evidence.

## Workflow

1. Start from the `solution_prompt_build` draft for `gpt_pro`.
2. Shape the Markdown to a self-contained generation prompt: a role line (expert lecturer), the task
   (generate the full deck in Markdown in the lecture language), then a per-slide specification —
   for each slide the title, the 6-10 sentence narrative, the bullets, the layout/visual and the
   sources, marked `[KEEP]` / `[UPDATE]` / `[ADD]`. Add explicit constraints: keep good slides,
   integrate the updates, create the new slides at their position, cite the listed sources, invent no
   unsupported facts. End with the source list.
3. Fill `source_list` and `provenance`; persist with `solution_prompt_finalize`; optionally call
   `solution_prompt_render` to write the user-readable `.md`.

## Output requirements

A validated `presentation_prompt@1` with `target_tool="gpt_pro"`, complete `prompt_markdown`,
`slide_count`, `source_list` and `provenance`. In the lecture language.

## Boundaries

Do not change slide content, statuses or design; no new evidence; no calls to G01/G02; do not emit a
prompt for another tool.

## Failure handling

`needs_input` on an absent/invalid design set or tool choice.

## Resume

Stateless; regenerate the GPT Pro prompt from the approved design set on revision.

{{HOST_ADAPTER}}
