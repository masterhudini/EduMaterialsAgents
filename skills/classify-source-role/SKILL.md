---
name: classify-source-role
description: Assign evidence-based functional roles to scholarly source candidates without conflating role, quality, access or stance. Use when canonical, recent or candidate-index agents must classify real SourceRecords for a ResearchPlan topic.
---

# Classify Source Role

## Contract

Consume a `SourceRecord`, topic requirements and available metadata or abstract. Produce one or
more role assignments from the approved vocabulary, each with signals, confidence, access basis
and mapped topics or claims.

## Workflow

1. Determine what information was actually observed: metadata, abstract, contents, preview or
   full text. Restrict classification strength accordingly.
2. Evaluate roles independently: canonical, foundational, current, rising, survey, didactic,
   methodological, claim-specific, qualifying or critical, optional.
3. Cite signals for each role, such as publication history, citation relation, work type, scope,
   recency or abstract content. Keep citation count as one signal.
4. Separate source role from scientific quality, stance and Open Access status.
5. Assign multiple compatible roles when supported and record confidence for each.
6. Leave a required role unassigned when evidence is insufficient; surface the coverage gap.

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
