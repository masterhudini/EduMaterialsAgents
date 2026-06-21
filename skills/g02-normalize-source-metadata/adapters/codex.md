## Host Adapter: Codex

- Call the configured MCP normalization operation with provider records and provenance refs.
- Consume the returned SourceRecords without dropping conflicts or warnings.
- If the operation is unavailable, return `external_dependency_blocked` instead of rewriting records ad hoc.
