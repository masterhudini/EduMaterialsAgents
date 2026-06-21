---
name: resolve-open-access
description: Resolve legal Open Access locations and document versions for human-approved sources through configured deterministic providers. Use before retrieval to produce auditable location candidates without bypassing paywalls or claiming access that was not verified.
---

# Resolve Open Access

## Contract

Consume one human-approved `SourceRecord`, its requested action and provider configuration. Produce
`OpenAccessResolution` with checked routes, candidate URLs, version type, host, license, identity
signals, access status and issues.

## Workflow

1. Require stable source identity and action `DOWNLOAD`; route `LIBRARY` and `CITATION` without
   automated retrieval.
2. Query configured deterministic resolvers in the approved semantic order, ordinarily Unpaywall,
   OpenAlex OA locations, arXiv, CORE and DOAB or OAPEN where applicable.
3. Preserve every checked route and result. Prefer a lawful stable full-text location whose work
   identity and version can be established.
4. Record version of record, accepted manuscript, submitted manuscript, preprint or unknown; do not
   equate versions silently.
5. Record license only when returned by a provider or trusted host metadata.
6. Return `unavailable` or `library_required` when no authorized OA location is verified.

## Output requirements

- Include source ID, provider, landing and file URL, version, license, checked time and identity basis.
- Keep resolver metadata separate from successful file validation.
- Preserve redirects or host changes for retrieval validation.

## Boundaries

- Do not bypass authentication, paywalls, robots controls or institutional access.
- Do not guess licenses or infer work identity from a similar title alone.

## Failure handling

Return unavailable after all configured routes complete without a valid location. Return degraded
when some routes fail but another provides a defensible candidate. Distinguish provider failure.

## Resume

Reuse a recent valid resolution according to configured freshness; otherwise rerun all required routes.
