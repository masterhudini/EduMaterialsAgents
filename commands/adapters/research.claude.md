## Host Adapter: Claude Code

Use the `orchestrate-research` skill as the conversational runtime. Start by calling the
plugin-provided MCP front door with the command argument, then drive producer agents through the
Task/Agent tool and use MCP seams for deterministic validation, scoped input and final handoff.

For a deterministic wiring check without producer agents, call `research_run_stub` with the same
context argument.

The default execution profile is `fast`. Use the review-task MCP builders unchanged; do not
hand-build `review_task@1`. A01 plans at most two priority-selected topics, discovery uses bounded
provider calls, A07 reviews each accepted source, A08 is skipped with an explicit limitation, and
A09 is the default reviewed terminal producer. A10 is mandatory for A01, A05, A06 and A09; A07 is
reviewed conditionally. After reviewed A09, pause at the Human Research Gate and call
`research_bundle_finalize` only after human approval.
