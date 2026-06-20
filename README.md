# edu-materials-agents

Agent-stack plugin for **Claude Code** and **Codex** that improves educational / lecture
materials through reviewed agent graphs (intake → research → solution). First graph in scope:
the **Research Graph** (see `docs/research graph project.md`).

## Layout

```
plugin.json              # manifest: skills[], agents[], commands[] (filled as nodes land)
install.sh               # installer for Claude Code + Codex (--all|--claude|--codex, --dry-run)
commands/                # slash-command entry points (thin → orchestrator skill)
agents/<graph>/          # isolated subagents, one .md per node; return envelope@1
skills/<graph>/          # interactive orchestrators (the only surface that talks to the user)
shared/
  contracts/             # versioned JSON-Schema handoff artifacts (envelope@1 is here)
  graphs/                # *.graph.json manifests — SINGLE SOURCE OF TRUTH per graph
  scripts/
    core/                # reusable, stdlib-only runtime engine
    <graph>/             # per-graph flow + shape checks
tests/                   # pytest (dev-only, not shipped)
scripts/dev-setup.sh     # creates .venv for tests
docs/                    # design (research graph project.md)
inspiration/             # reference meta-factory plugin (NOT shipped, NOT installed)
```

Each directory has a `README.md` describing its convention and what to implement.

## Runtime is dependency-free by design

Everything under `shared/scripts/**` is **pure stdlib**. At runtime the agents call the system
`python3` with `$CLAUDE_PLUGIN_ROOT/shared/scripts` on the path — there is **no virtualenv in
the installed plugin**. Anything needing third-party packages (network retrieval, PDF parsing)
goes into an isolated agent with its own tool, never into the deterministic core.

Runtime artifacts (drafts, logs, hydrated `artifact://` files) live project-locally under
`.emagents/` (override with `EMAGENTS_HOME`); the dir is git-ignored.

## Install

```bash
bash install.sh --dry-run     # preview
bash install.sh               # install into Claude Code + Codex
```

Restart Claude Code / Codex after installing.

## Develop & test

```bash
bash scripts/dev-setup.sh     # one-time: .venv with pytest
.venv/bin/pytest
```
