## Host Adapter: Codex

- Call MCP `research_planner_prepare` before starting the isolated planner node.
- Give the node only the returned `planner_input`, plus validated revision context when present.
- Do not expose web, scholarly-search or retrieval tools to the planner node.
- Call MCP `research_planner_finalize` with the proposed plan and return its envelope unchanged.
- The orchestrator calls `research_plan_review_task`, then the universal reviewer tools.
- If isolated execution is unavailable, return the deterministic failed envelope with
  `planner_executor_unavailable`.
