---
name: g02-classify-source-role
description: Assign evidence-based functional roles to scholarly source candidates without conflating role, quality, access or stance. Use when canonical, recent or candidate-index agents must classify real SourceRecords for a ResearchPlan topic.
---

# Classify Source Role

## Contract

Consume an unchanged `source_record@1`, topic requirements and available metadata or abstract.
Produce one or more separate role assignments from the approved vocabulary, each with signals,
confidence, access basis and mapped topics, claims or coverage units.

## Workflow

1. Determine what information was actually observed: metadata, abstract, contents, preview or
   full text. Restrict classification strength accordingly.
2. Evaluate roles independently: canonical, foundational, current, rising, survey, didactic,
   methodological, claim-specific, qualifying or critical, applied_case, optional. Assign
   `applied_case` to a real, dated market case (a documented institutional event, applied use or
   failure) that illustrates a claim or topic; keep its source tier and evidence type separate from
   scientific quality.
3. Cite signals for each role, such as publication history, citation relation, work type, scope,
   recency or abstract content. Keep citation count as one signal.
4. Separate source role from scientific quality, stance and Open Access status.
5. Assign multiple compatible roles when supported and record confidence for each.
6. Leave a required role unassigned when evidence is insufficient; surface the coverage gap.
7. For G02-A03, write assignments only into `canonical_annotations`; never place inferred roles in
   the provider record's `classification.source_roles`.
8. For G02-A04, write assignments only into `recent_annotations`. Keep recency, maturity,
   `core_update`/`optional_trend`/`watch` and `quality_status` as separate fields.
9. For G02-A11, write assignments only into `market_case_annotations`. Keep role, source tier,
   evidence type, materiality, documentation status and scientific quality separate.

## Output requirements

- Each assignment contains role, topic or claim IDs, observed signals, confidence and access level.
- Closed or metadata-only sources may be canonical anchors but cannot receive semantic claim roles
  based on unseen content.
- Preserve uncertainty and conflicting signals.

## Boundaries

- Do not fabricate canonical consensus, impact or content.
- Do not use venue prestige as a complete quality assessment.
- Do not change bibliographic metadata or source-selection decisions.

## Failure handling

Return an empty assignment with explicit insufficiency when no role is supportable. Do not force a
classification merely to fill coverage.

## Resume

Reclassify only when metadata, accessible content, topic requirements or review findings changed.
