# agents — isolated subagent definitions

One Markdown file per graph node that does reviewed reasoning. Agents are **isolated**: they
cannot talk to the user, they receive an input bundle and return the universal
`envelope@1`. Grouped by graph: `agents/<graph>/<node>.md`.

## File convention (see inspiration/agents/.../collector-domain.md)

Frontmatter:
```yaml
---
name: research-planner
model: sonnet          # or opus for high-impact synthesis/evidence nodes
tools: ["Read", "Bash"]
description: >-
  One paragraph: what it produces, when it runs, that it is isolated and NEVER invoked
  directly (only by the orchestrator).
---
```

Body sections: `# Title` → `## Contract` (input/output, consumes/produces) →
`## Workflow` (steps; call the shape check inline before returning) → `## Boundaries`
(non-responsibilities / guardrails) → `## Failure handling` (degrade-don't-punt) → `## Resume`.

## To create: agents/research/ (from docs §8.5)

`research-planner`, `research-plan-reviewer`, `domain-research`, `domain-search-reviewer`,
`claim-verification`, `claim-evidence-reviewer`, `recent-developments`,
`recent-developments-reviewer`, `canonical-sources`, `canonical-sources-reviewer`,
`source-selection`, `source-quality-reviewer`, `paper-retrieval`, `retrieval-integrity-reviewer`,
`paper-review`, `paper-review-quality-reviewer`, `research-synthesizer`,
`research-synthesis-reviewer`.

Each agent definition carries: `responsibility`, `non_responsibilities`, `guardrails`,
`revision_policy` (retry_scope, max_revision_attempts by severity, escalation), `complexity_class`,
`input_contract`, `output_contract`. Agents are auto-discovered from `agents/` — no
`plugin.json` array needed; just drop the `.md` file in.
