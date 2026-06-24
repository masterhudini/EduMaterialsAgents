## Host Adapter: Codex

- Use this only when a `scout_a07_model_task@1` has already been prepared.
- Inspect the task JSON, not the full PDF.
- Produce the raw A07 output JSON and pass it to `research_scout_a07_partial_finalize`.
- If evidence is weak or irrelevant, return `review_status: "insufficient"` or `"irrelevant"`.
