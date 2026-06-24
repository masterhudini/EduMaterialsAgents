---
name: g02-a01-plan-research-scope
description: Convert research_planner_input@1 into bounded topics, source-role strategies, observable coverage units and stop rules for research_plan@1. Use only inside G02-A01 Planner after deterministic input preparation, without searching for or inventing literature.
---

# Plan Research Scope

## Contract

Consume one validated `research_planner_input@1`. Produce the structured content of one
`research_plan@1` while preserving task identity, approved scope, all upstream IDs, constraints and
output language. Use the `plan_output_template` returned by preparation as the immutable structural
base. The calling agent performs deterministic finalization and artifact storage.

## Workflow

1. Build a driver table with `driver_id`, priority, purpose and all linked claim, concept,
   flow-issue and update-need IDs. Stop when a driver has no approved upstream link.
2. Score drivers before grouping. Give strongest weight to high-priority claim drivers, high-
   severity flow issues, drivers linked to multiple approved upstream cards, central concepts used
   by more than one claim and drivers that unblock later evidence or retrieval. Medium-priority
   drivers may be absorbed into a stronger group when they support the same investigation.
3. In the default fast profile, respect the scoped `constraints.max_topics` limit, normally two.
   When that scoped limit is six (the `scout` profile), choose 4–6 groups based on actual intake
   coverage rather than filling a quota mechanically. Select the highest-value groups by the score
   above. Do not select the first groups merely because they appear first in the input.
4. Group drivers only when they support one operational investigation and require compatible
   terminology, evidence standards, source roles and time windows. Split mixed groups when any of
   these differ materially, unless a lower-priority driver can be represented as a coverage unit
   inside one of the selected high-value topics without broadening scope.
5. If an approved driver cannot fit into the selected fast-profile topics, place it in
   `uncovered_driver_ids` and add an `input_issues` entry with severity `minor` or `major`,
   depending on downstream consequence. Do not create a third topic to avoid an explicit tradeoff.
6. Assign a stable `TOPIC_*` ID, concise name and one bounded purpose to each group. The name must
   be an established research field, method family or technical problem usable directly in an
   academic search. Ground it in the linked drivers and their approved claim, concept, update-need,
   flow-issue and teaching-context wording; reject generic planning labels. Set topic priority to
   the highest priority among its linked drivers.
7. Copy all related upstream IDs from the grouped drivers. Use only domain IDs present in
   `approved_domains`; do not infer an adjacent domain.
8. Select source roles according to the approved need:
   - use `canonical` for foundations, definitions or historically established methods;
   - use `current` for explicit update needs, recency questions or state-of-the-art claims;
   - use `survey` when the task needs landscape coverage or method comparison;
   - use `didactic` for approved conceptual or flow needs requiring teachable exposition;
   - use `qualifying_or_critical` for claims that require limitations, counterevidence or boundary
     conditions.
9. Form a provider-neutral search strategy. Core terms come from approved card wording and domain
   labels. Allowed expansions name bounded concepts rather than provider syntax and are specific
   enough to serve as the declared basis of later generated terms. Include separate areas for
   qualifying or critical terminology when that route is required. Exclusions prevent known
   ambiguity. Dates, languages and work types remain within global constraints. Seed sources use
   only approved `existing_source_cards.source_id` values.
   In the Scout profile, write 3–6 core terms and keep at least one technical intake/domain anchor
   in the topic name and term set. Put teaching intent in `purpose`. Never use `tutorial`,
   `overview`, `foundations`, `introduction`, `applications` or `recent developments` as a short
   primary query. Reframe didactic needs as domain-specific research phenomena such as conceptual
   understanding, misconceptions or instructional sequencing.
10. Create one or more observable `COV_*` units per topic. Each unit states what must be covered,
   acceptable source roles, a positive minimum source count and whether it is mandatory. Avoid
   vague units such as "enough evidence".
11. Copy configured saturation behavior into each stop rule. Keep `candidate_limit` within the
   approved maximum and require a complementary route before declaring saturation.
12. Reconcile all drivers. Put an unplannable driver in `uncovered_driver_ids` and link it to an
   `input_issues` entry that states the missing decision and consequence. A blocker prevents output.
13. Copy approved constraints to `global_constraints`, preserve `output_language`, set
    `review_profile_ref: research_plan` and perform the output checks below.

## Output requirements

- Copy `plan_output_template` and preserve every key exactly. Never rename canonical fields to
  plausible aliases. In particular use `linked_driver_ids`, `related_claims`,
  `source_roles_required`, `coverage_requirements[].source_roles`,
  `coverage_requirements[].mandatory` and `stop_rule`.

- Use unique stable `TOPIC_[A-Z0-9_]+` and `COV_[A-Z0-9_]+` identifiers.
- Every topic has a non-empty purpose, priority, driver links, approved domain, required source
  role, search strategy, coverage unit and stop rule.
- Every driver is covered by at least one topic or is explicitly declared uncovered with an input
  issue. Covered and uncovered sets cannot overlap.
- Search terms are plans only. Do not include authors, titles, DOI values, citations or claimed
  search results.
- Global constraints and output language match the scoped input exactly.
- On revision, advance `artifact_version` and preserve unaffected topics byte-for-byte at the
  structured-data level when findings name specific topic IDs.

## Boundaries

- Do not call scholarly APIs, inspect publications, retrieve files or evaluate source quality.
- Do not verify claims or infer verdicts from their wording.
- Do not broaden approved domains, research drivers, teaching goals, source policy or date limits.
- Do not convert a locked section or an interesting adjacent subject into a new driver.
- Do not propose slide edits, speaker notes or final teaching solutions.

## Failure handling

Return control to the calling agent with a precise missing-input issue when drivers, domains,
constraints or approved links are absent or contradictory. A useful partial plan may be degraded
only when all omissions are declared. Invalid IDs, scope expansion, fabricated literature or a
blocking input issue prevent artifact creation.

## Resume

Use the previous plan and concrete reviewer findings as the revision boundary. Preserve unrelated
topic IDs, ordering and content. Apply only corrections needed to close named findings, then repeat
driver reconciliation and all output checks.
