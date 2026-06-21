---
name: retrieve-open-access-document
description: Download a document only from a verified OpenAccessResolution for a human-approved DOWNLOAD source. Use deterministic retrieval tools with bounded redirects, size and retry controls, producing a temporary file descriptor for validation.
---

# Retrieve Open Access Document

## Contract

Consume an approved source action, verified OA resolution and retrieval policy. Produce
`RetrievedFileCandidate` with temporary ref, response metadata, byte count, checksum, final URL,
attempt log and source identity. This result is not accepted into the corpus before validation.

## Workflow

1. Verify that source ID is in `HumanApprovedSourceSet.approved_sources` with action `DOWNLOAD`.
2. Use the resolved file location through the configured deterministic downloader.
3. Enforce timeout, bounded redirects, maximum size, allowed scheme and host policy. Never send
   credentials to an unapproved redirect target.
4. Stream to a temporary artifact, calculate checksum and preserve response content type and URL chain.
5. Retry only transient failures within provider policy. Do not retry permanent access denial as if transient.
6. Pass the candidate to document validation before promoting it to the corpus.

## Output requirements

- Record every attempt, status, final URL, content type, bytes and checksum.
- Use collision-safe local names based on source ID, not remote path input.
- Leave partial or invalid downloads outside the accepted corpus.

## Boundaries

- Do not download unapproved, LIBRARY, CITATION, RESERVE or EXCLUDE sources.
- Do not automate institutional login or execute downloaded content.
- Do not infer validity from an HTTP success code.

## Failure handling

Return unavailable for permanent access conditions and failed for exhausted transient or storage
errors. Keep attempts auditable and remove or quarantine partial data according to policy.

## Resume

Reuse only a previously validated checksum. Otherwise start a fresh temporary retrieval operation.
