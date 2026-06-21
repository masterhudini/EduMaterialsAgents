## Host Adapter: Claude Code

- Run inside the `g02-a10-output-reviewer` node invoked by the orchestrator.
- Prepare the task through `research_review_prepare`; read only the artifact returned by that
  deterministic operation.
- Submit the structured decision through `research_review_finalize`; do not invoke another agent
  or the user.
