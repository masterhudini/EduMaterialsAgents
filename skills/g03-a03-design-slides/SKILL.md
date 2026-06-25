---
name: g03-a03-design-slides
description: Design every slide of the Graph03 new deck from the approved slide_plan@1 — title, content, layout, design and a 6-10 sentence narrative of what each slide should say, plus speaker notes — producing slide_design_set@1. Executable procedure run by g03-a03; not interactive.
---

# Design Slides

## Contract

Consume the approved `slide_plan@1` from g03-a02. Produce a `slide_design_set@1` with one design entry
per non-`REMOVE` slot, persisted through `solution_slide_design_finalize`. Realize the plan; do not
change its statuses, ordering or new-slide set, and add no evidence.

## Workflow

1. Start from the `solution_slide_design_build` deterministic draft (one entry per slot, seeded bullets,
   stub narrative, default layout).
2. For every slot author: a clear `title`; a tight `body` (manageable `bullets` + one `key_takeaway`);
   a **6-10 sentence `narrative`** stating exactly what the slide should say and why it matters here;
   `speaker_notes` that add delivery cues beyond the bullets; and a `design` with a fitting `layout`
   (`title+bullets`, `two-column`, `diagram`, `comparison`, `quote`, `section-break`) and a
   `visual_suggestion` where a figure helps.
3. Preserve `source_refs` on every research-based / `is_new_information` slide. Keep the lecture
   language and didactic register.
4. Set `estimated_minutes` per slide; fill `deck_metrics` and sanity-check the total against
   `target_minutes` when present (flag, do not silently cut).
5. Persist with `solution_slide_design_finalize` and return its envelope.

## Output requirements

A validated `slide_design_set@1`: `slides[]` (each with `title`, `body`, a 6-10 sentence `narrative`,
`speaker_notes`, `design`, `estimated_minutes`, `source_refs`, `is_new_information`) and `deck_metrics`.
In the lecture language.

## Boundaries

Do not change the plan (statuses, ordering, new-slide set); no prompt building; no evidence or sources
beyond the plan; no calls to G01/G02; no PDF reading.

## Failure handling

`needs_input` on an absent/invalid plan. Never drop a non-`REMOVE` slot or emit a partial set.

## Resume

Stateless; regenerate only the affected slides on revision.

{{HOST_ADAPTER}}
