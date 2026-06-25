---
name: g02-a11-author-web-queries
description: Author a small bounded set of web search queries for one analysed topic from its core_terms and purpose, before the host web search runs. Use inside g02-a11-market-cases to cover applied-case, failure-case and current-event angles without calling any provider. Preserves approved scope — no topic broadening, no fabricated constraints.
---

# Author Web Queries

## Contract

Consume one `a11_market_case_task@1` topic (`topic_id`, `name`, `purpose`, `claim_ids`,
`core_terms`, `allowed_expansion_areas`) and the `output_language`. Produce a short list of concrete
web search query strings for the host's native search. This skill calls no provider and fetches
nothing — it only shapes the queries `g02-a11-find-market-cases` will run.

## Workflow

1. Anchor every query in the topic `core_terms`; you may add terms only from
   `allowed_expansion_areas`. Do not broaden the topic.
2. Cover three angles, a couple of queries each:
   - **applied case** — notable real-world uses / adopters of the topic;
   - **failure / incident** — well-documented failures, outages, recalls, lawsuits;
   - **current event / fresh data** — recent developments, reports or statistics.
3. Write queries in the task `output_language` and add an English variant where it widens reputable
   results. Keep each query short and specific (include an institution, year or "case study" hint
   when useful).
4. Keep the set small (roughly 4–8 queries per topic) so discovery stays bounded.

## Output requirements

- Every query traces back to the topic's approved `core_terms` (plus allowed expansions only).
- The set spans applied-case, failure-case and current-event angles.
- No query invents a date range, domain filter or scope the task did not approve.

## Boundaries

- Do not call any search provider or fetch any page here; only author the query strings.
- Do not broaden the topic beyond `core_terms` + `allowed_expansion_areas`.
- Do not embed credentials, operators or endpoints — these are plain user-facing search queries.
