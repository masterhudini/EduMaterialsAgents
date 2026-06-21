# edu-materials-agents

Agent-stack plugin for **Claude Code** and **Codex** that improves educational / lecture
materials through reviewed agent graphs (intake → research → solution). First graph in scope:
the **Research Graph** (see `docs/research graph project.md`).

## Layout

```
plugin.manifest.json     # source of truth for metadata, components, host packaging
agents/                  # flat: one .md per agent, auto-discovered (e.g. research-planner.md)
skills/<name>/SKILL.md   # neutral skill plus adapters/claude* and adapters/codex.md
commands/<name>.md       # slash-command entry points (e.g. research.md)
shared/
  contracts/             # versioned JSON-Schema handoff artifacts (envelope@1 is here)
  graphs/                # *.graph.json manifests — SINGLE SOURCE OF TRUTH per graph
  scripts/
    core/                # reusable, stdlib-only runtime engine
    <graph>/             # per-graph flow + shape checks
    mcp/                 # stdlib MCP servers exposing deterministic seams
scripts/build-plugin.py  # composes dist/claude and dist/codex installable bundles
scripts/install_plugin.py # shared cross-platform installer implementation
install.sh / install.ps1 # POSIX and native Windows installer entry points
mocks/                   # hand-authored boundary contexts for testing graphs (dev-only)
tests/                   # pytest (dev-only, not shipped)
scripts/dev-setup.sh     # creates .venv for tests
docs/                    # design notes + component conventions
```

> Component dirs (`agents/`, `commands/`, `skills/`) hold **only** source components. Conventions live in
> `docs/02_Architektura_agentow_i_skilli.md`. Graphs are organised in `shared/graphs/` and
> `shared/scripts/<graph>/`; components are flat and namespaced by name (e.g. `research-*`).

## Packaging model

The repo is the **source of truth**, not the production plugin folder. `scripts/build-plugin.py`
generates host-specific bundles:

```
dist/claude/
  .claude-plugin/marketplace.json
  plugins/edu-materials-agents/
    .claude-plugin/plugin.json
    .mcp.json
    skills/ agents/ commands/ shared/

dist/codex/
  .agents/plugins/marketplace.json
  plugins/edu-materials-agents/
    .codex-plugin/plugin.json
    .mcp.json
    skills/ shared/
```

`dist/` is git-ignored and can be regenerated at any time:

```bash
python scripts/build-plugin.py --host all
```

This avoids maintaining duplicate manifests by hand and keeps Claude/Codex host-specific files
out of the repo root. In particular, root-level `.mcp.json` is intentionally not used as a source
file because Claude treats it as project MCP config when this repo is the current working directory.

## Runtime is dependency-free by design

Everything under `shared/scripts/**` is **pure stdlib**. At build time the MCP configuration is
bound to the absolute Python interpreter used by the installer, so both `python3` and `python`
environments are supported. If that interpreter path later changes (upgrade/relocation), rerun the
installer to rebind the MCP command. There is **no virtualenv in the installed plugin**. Anything needing third-party packages (network retrieval, PDF parsing)
goes into an isolated agent with its own tool, never into the deterministic core.

Runtime artifacts (drafts, logs, hydrated `artifact://` files) live in the **current project**
under `.emagents/` (override with `EMAGENTS_HOME`); the dir is git-ignored.

## Host-specific skill rendering

Skills are authored once and rendered per host at build time. A skill can keep shared workflow
instructions in `SKILL.md`, host-specific notes in `adapters/claude.md` and `adapters/codex.md`,
and host-specific frontmatter in `adapters/<host>.frontmatter.yaml`; `scripts/build-plugin.py`
injects the matching adapter into the generated `dist/*` bundle and does not ship the other
host's adapter.

## Install (Claude Code)

The installer builds `dist/claude` and registers that generated marketplace via the official
`claude` CLI — no hand-editing of Claude's registries.

```bash
bash install.sh --claude --dry-run   # preview the CLI commands
bash install.sh --claude             # claude plugin marketplace add + install
```

Native Windows PowerShell:

```powershell
.\install.ps1 --claude --dry-run
.\install.ps1 --claude
```

`--dry-run` builds and validates both host bundles in a temporary directory. It does not modify
`dist/`, plugin registries or an existing installation.

Then, in Claude Code:

```
/reload-plugins
/plugin                              # shows edu-materials-agents (marketplace: edu-materials)
```

Verify the component inventory (expect 10 agents + 18 skills, including orchestrate-research):

```bash
claude plugin details edu-materials-agents
```

After editing source files, rebuild/reinstall with `bash install.sh --claude` and then
`/reload-plugins`.

### Codex (experimental)

```bash
bash install.sh --codex              # builds dist/codex and installs under Local Plugins
```

On Windows use `.\install.ps1 --codex`. Replacement of an existing Codex plugin is staged and
the previous directory is retained as a timestamped backup after a successful installation.

Then start a new Codex thread. The plugin appears as `edu-materials-agents` in the default
`Local Plugins` marketplace. Codex receives the shared skills, runtime and MCP tools. The Codex
CLI plugin manifest does not currently register plugin `commands/` as slash commands, so
`/research` is Claude-only in current Codex CLI builds.

## Run

In Claude Code:

```text
/research mocks/research/research_graph_input.json
```

In Codex, start a new thread after install and ask in natural language, using an absolute JSON path
so plugin runtime does not depend on the MCP or worker process working directory:

```text
Zrób research dla /home/khudaszek/projects/EduMaterialsAgents/mocks/research/research_graph_input.json
```

or:

```text
Run the research graph for /home/khudaszek/projects/EduMaterialsAgents/mocks/research/research_graph_input.json
```

The `orchestrate-research` skill treats these as semantic entrypoints and uses the
`research_run_codex` MCP tool. The default Codex gate mode is pause/resume (`gates: "pause"`), so
human gates return a `resume_token` instead of reading interactive stdin from the MCP process.

Or use the runner directly:

```bash
python /home/khudaszek/.codex/plugins/edu-materials-agents/shared/scripts/research/research_flow.py run-codex /home/khudaszek/projects/EduMaterialsAgents/mocks/research/research_graph_input.json
```

Or run deterministically, without an LLM. This harness validates wiring and uses no-op producers,
automatic reviewer approvals and automatic user-gate approvals:

```bash
python shared/scripts/research/research_flow.py run mocks/research/research_graph_input.json
# inspect what one agent would receive:
python shared/scripts/research/research_flow.py inputs mocks/research/research_graph_input.json --node research-planner
```

Or drive the real graph through **Codex workers** (each node is an isolated `codex exec`, no API
key — Codex subscription login; terminal user gates). Local/dev only:

```bash
python shared/scripts/research/research_flow.py run-codex mocks/research/research_graph_input.json
# single isolated node (cheaper smoke):
python shared/scripts/research/runners/codex.py research-planner
```

The engine is host-agnostic; execution is the per-host runner (Claude Task subagents vs Codex
`codex exec`). Gates support auto / terminal (`--gates prompt`) / async pause-resume.

## Develop & test

```bash
bash scripts/dev-setup.sh     # one-time: .venv with pytest
.venv/bin/python -m pytest
```

Windows:

```powershell
.\scripts\dev-setup.ps1
.\.venv\Scripts\python.exe -m pytest
```
