# edu-materials-agents

Agent-stack plugin for **Claude Code** and **Codex** that improves educational / lecture
materials through reviewed agent graphs (intake → research → solution). First graph in scope:
the **Research Graph** (see `docs/research graph project.md`).

## Layout

```
.claude-plugin/          # plugin.json (manifest) + marketplace.json (local marketplace)
agents/                  # flat: one .md per agent, auto-discovered (e.g. research-planner.md)
skills/<name>/SKILL.md   # one level per skill (e.g. orchestrate-research) — the only surface
commands/<name>.md       # slash-command entry points (e.g. research.md)
shared/
  contracts/             # versioned JSON-Schema handoff artifacts (envelope@1 is here)
  graphs/                # *.graph.json manifests — SINGLE SOURCE OF TRUTH per graph
  scripts/
    core/                # reusable, stdlib-only runtime engine
    <graph>/             # per-graph flow + shape checks
install.sh               # installer (--claude | --codex | --all, --dry-run)
mocks/                   # hand-authored boundary contexts for testing graphs (dev-only)
tests/                   # pytest (dev-only, not shipped)
scripts/dev-setup.sh     # creates .venv for tests
docs/                    # design notes + component conventions
```

> Component dirs (`agents/`, `commands/`, `skills/`) hold **only** components — Claude Code
> auto-discovers every `.md` there, so no `README.md` inside them. Conventions live in
> `docs/02_Architektura_agentow_i_skilli.md`. Graphs are organised in `shared/graphs/` and
> `shared/scripts/<graph>/`; components are flat and namespaced by name (e.g. `research-*`).

## Runtime is dependency-free by design

Everything under `shared/scripts/**` is **pure stdlib**. At runtime the agents call the system
`python3` with `$CLAUDE_PLUGIN_ROOT/shared/scripts` on the path — there is **no virtualenv in
the installed plugin**. Anything needing third-party packages (network retrieval, PDF parsing)
goes into an isolated agent with its own tool, never into the deterministic core.

Runtime artifacts (drafts, logs, hydrated `artifact://` files) live in the **current project**
under `.emagents/` (override with `EMAGENTS_HOME`); the dir is git-ignored.

## Install (Claude Code)

The repo doubles as its own local **marketplace** (`.claude-plugin/marketplace.json`). The
installer registers it via the official `claude` CLI — no hand-editing of Claude's registries.

```bash
bash install.sh --claude --dry-run   # preview the CLI commands
bash install.sh --claude             # claude plugin marketplace add + install
```

Then, in Claude Code:

```
/reload-plugins
/plugin                              # shows edu-materials-agents (marketplace: edu-materials)
```

Verify the component inventory (expect 10 agents + the orchestrate-research skill):

```bash
claude plugin details edu-materials-agents
```

The marketplace source is the repo itself (`source: directory`), so after editing files you
only need `/reload-plugins` — no reinstall.

**Dev without installing:** `claude --plugin-dir "$PWD"`

### Codex (experimental)

```bash
bash install.sh --codex              # copies into ~/.codex and registers in Codex marketplaces
```

## Run

```
/research mocks/research/research_graph_input.json
```

Or deterministically, without an LLM (stub nodes):

```bash
python3 shared/scripts/research/research_flow.py run mocks/research/research_graph_input.json
# inspect what one agent would receive:
python3 shared/scripts/research/research_flow.py inputs mocks/research/research_graph_input.json --node research-planner
```

## Develop & test

```bash
bash scripts/dev-setup.sh     # one-time: .venv with pytest
.venv/bin/pytest
```
