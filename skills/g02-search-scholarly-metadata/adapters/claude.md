## Host Adapter: Claude Code

- Call `research_provider_status` during startup and `research_metadata_search` per approved route.
- Pass only structured QueryPlan data and consume normalized records plus artifact provenance.
- Never parse ad hoc web results or put credentials in the agent context.
- Preserve unavailable and zero-result operations in the Domain query log.
