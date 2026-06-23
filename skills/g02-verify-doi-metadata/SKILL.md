---
name: g02-verify-doi-metadata
description: Verify a scholarly SourceRecord DOI and depositor metadata through the deterministic Crossref operation. Use in G02 discovery, candidate indexing and retrieval identity checks when a real provider record carries a DOI or needs an auditable Crossref conflict assessment.
---

# Verify DOI Metadata

## Contract

Consume one provider-backed `source_record@1` or a bounded array of records. Call
`research_doi_verify` or `research_doi_verify_batch`. Preserve every returned
`doi_verification_result@1` reference and status.

## Workflow

1. Verify only unchanged provider records. Never construct a DOI from title or model knowledge.
2. Reuse a prior result for the same normalized DOI when it belongs to the current artifact chain.
3. Treat `confirmed_crossref` as bibliographic identity evidence, not evidence of scientific
   quality, peer review or claim truth.
4. Preserve `not_found_crossref`, `unavailable`, malformed DOI and field-conflict outcomes.
5. Use the suggested overlay only for a missing field and retain Crossref as its provenance.
   Never overwrite a conflicting provider value.
6. Keep DOI-bearing records with unavailable verification visibly degraded. Escalate a critical
   title, author or year conflict before deduplication or retrieval identity acceptance.

## Output requirements

- Preserve operation ID, result ref, normalized DOI, registry status, match status and raw response
  provenance.
- Keep `not_found_crossref` distinct from an invalid DOI because another registration agency may
  own the DOI.
- Do not copy Crossref metadata into factual summaries of publication contents.

## Boundaries

- Do not call Crossref through direct HTTP, shell or generic web tools.
- Do not claim that a Crossref match validates methods, conclusions or access rights.
- Do not silently replace provider metadata or merge records solely because titles resemble.

## Failure handling

Return the structured provider outcome. Allow the owning agent to continue in degraded mode when
Crossref is unavailable and the original provider identity remains usable. Treat a critical
bibliographic conflict as unresolved identity.
