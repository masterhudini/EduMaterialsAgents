## Host Adapter: Claude Code

- Run inside `g02-a09-synthesizer` and hydrate only reviewed assessment, evidence and coverage refs.
- Write human-readable packet content in `output_language` and keep identifiers in English.
- For Graph03 handoff updates, emit evidence as `evidence_refs` objects with `source_id`,
  `location` and `quote`. Do not emit `evidence_refs` as strings.
- Required updates must carry enough material for the solution producer to improve the deck:
  a concrete finding, rationale versus the current presentation, compact cited evidence,
  source metadata and bounded `ready_to_apply_text`.
- Do not create placeholder optional improvements with empty finding, rationale or slide text.
- Return artifact descriptors to the orchestrator; do not open the final user gate directly.
