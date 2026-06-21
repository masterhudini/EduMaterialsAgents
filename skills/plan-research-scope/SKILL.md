---
name: plan-research-scope
description: Convert an approved Research Graph input bundle into bounded research topics, source strategies, coverage requirements and stop rules. Use when the research planner must produce or revise ResearchPlan without searching for literature.
---

# Plan Research Scope

## Contract

Consume approved context, scope, research drivers, claim and concept cards, flow or update-need
cards, constraints and source-selection limits. Produce `ResearchPlan` with topic IDs, purpose,
priority, linked drivers, required source roles, search strategy, coverage requirements and stop
rules.

## Workflow

1. Validate that every requested investigation has a human-approved driver. Report missing or
   contradictory drivers instead of inventing them.
2. Group tightly related claims and needs into topics. Split topics when their terminology,
   evidence standard or source strategy differs materially.
3. State one operational purpose per topic and link all originating IDs.
4. Assign source roles required for the purpose: canonical, current, survey, didactic and
   qualifying or critical evidence.
5. Define core terms, allowed expansion areas, exclusions, date windows, languages, work types
   and approved seed sources. Keep these as strategy, not fabricated search results.
6. Define observable coverage units and a stop rule using configured limits. Require at least
   one complementary search route before stopping for saturation.
7. Check that every high-priority driver is covered and no topic exceeds approved scope.

## Output requirements

- Use stable `TOPIC_*` IDs and preserve upstream IDs exactly.
- Every topic contains purpose, priority, linked drivers, required roles, coverage and stop rule.
- Record unresolved input gaps explicitly.
- Produce no bibliographic record or claim verdict.

## Boundaries

- Do not call literature APIs, select papers or evaluate claims.
- Do not broaden the approved domains, teaching goal or locked sections.
- Do not treat an interesting subject as a research driver.

## Failure handling

Return `needs_input` through the calling agent when required drivers, scope or constraints are
missing. Return a degraded plan only when useful topics can be formed and every omitted area is
listed with its consequence.

## Resume

On revision, preserve unaffected topic IDs and modify only topics named by revision items.
