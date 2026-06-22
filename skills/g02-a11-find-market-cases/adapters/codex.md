## Host Adapter: Codex

- Call MCP `research_provider_status`, then `research_web_case_search` for each approved web route.
- Treat the typed web-case operation result as the provider boundary and preserve its artifact ref,
  operation ID, cursor, cache status, observed source tier and issues. Its concrete result contract
  is added with the A11 runtime seam; do not reuse `literature_tool_result@1` implicitly.
- If MCP is unavailable, return `external_dependency_blocked`; do not browse as a substitute.
- Do not invoke extraction during discovery; extraction is deferred to the post-gate G02-A07 step.
