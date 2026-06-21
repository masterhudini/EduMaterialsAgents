## Host Adapter: Codex

- Invoke the configured MCP document-validation operation and preserve all check results.
- Do not inspect or execute the file through arbitrary shell tools before validation.
- If validation MCP is missing, return `external_dependency_blocked` and do not accept the document.
