# skills — interactive orchestrators

`skills/<graph>/<name>/SKILL.md`. Skills are the **conversational surface**: they host the
user dialogue and sequence the isolated agents (which cannot talk to the user). Typically one
orchestrator skill per graph, plus any interactive collectors.

## File convention (see inspiration/skills/.../collector-process/SKILL.md)

Frontmatter:
```yaml
---
name: research-orchestrator
version: 1.0.0
model: opus
description: >-
  Use when ... (trigger phrases, EN + PL). What it orchestrates, what is out of scope,
  and that it must not be used to run a single agent directly.
---
```

Body: `## Contract` → `## Workflow` (the node sequence; must agree with the graph manifest) →
`## Boundaries` → `## Failure handling` → `## Resume`.

## To create: skills/research/

- `research-orchestrator/SKILL.md` — hosts the Research Graph run: relays each agent's
  `needs_input` to the user, drives reviewer loops, presents the User Research Gate
  decisions (§9), and freezes the `UserApprovedResearchBundle` via `core/gate.py`.

Skills are auto-discovered from `skills/` (each dir with a `SKILL.md`) — no `plugin.json` array
needed. The Codex installer mirrors each `SKILL.md` dir into `~/.codex/skills/<dirname>`, so
skill dir names must be unique.
