## Host Adapter: Codex

- Run only in a reviewer node created by the Codex node-agent adapter.
- Use `research_review_prepare` to resolve the authorized artifact and
  `research_review_finalize` to validate and persist the decision.
- If node isolation or artifact resolution is unavailable, return `external_dependency_blocked`.
