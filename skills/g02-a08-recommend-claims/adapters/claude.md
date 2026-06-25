## Host Adapter: Claude Code

- Bind only the two supplied streams (A09 `scholarly_synthesis` + A11 `web_cases`); use no web search.
- Group by `topic_id`; recommend interesting, well-documented claims worth featuring.
- Set `support_basis` (`literature`/`web`/`both`) to match the refs you cite; `both` only when a
  scholarly finding and a web case reinforce the same claim.
- Recommend additions; never critique current slides, draft slide text or pick placement.
- Call `research_a08_finalize`; omit `output` to record the deterministic fallback.
