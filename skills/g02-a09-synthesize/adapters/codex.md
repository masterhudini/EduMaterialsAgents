## Host Adapter: Codex

- Call `research_a09_task_prepare` and use this skill exactly once for its
  `a09_synthesis_task@1`.
- Inspect the task JSON (baseline, A07 candidates, deep-dive windows), not full PDFs.
- Produce the raw A09 output JSON and pass it as `output` to `research_a09_synthesis_finalize`.
- Pass the `deep_dive` package returned beside the task to the same finalizer.
- Drop unsupported updates, convert usable deep-dive windows into ready slide updates, and leave the
  rest as coverage gaps. Never hand Graph03 a bare lookup pointer.
