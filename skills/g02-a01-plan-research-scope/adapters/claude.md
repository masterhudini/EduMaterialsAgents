## Host Adapter: Claude Code

- Run only inside `g02-a01-planner` after `research_planner_prepare` reports `ready: true`.
- Use `planner_input`, plus `previous_plan` and `revision_items` only when supplied by preparation.
- Do not enable WebSearch, WebFetch or literature-provider tools for this node.
- Submit the structured plan to `research_planner_finalize` and return its envelope unchanged.
- Leave `research_plan_review_task` and reviewer invocation to the orchestrator.
