# edu-materials-agents

Agent-stack plugin for **Claude Code** and **Codex** that improves educational / lecture
materials through agent graphs (`g01` intake → `g02` research → `g03` solution). First graph in scope:
the **Research Graph** (see `docs/research graph project.md`).

## Layout

```
plugin.manifest.json     # source of truth for metadata, components, host packaging
agents/                  # flat: one .md per agent, auto-discovered (e.g. g02-a01-planner.md)
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
> `shared/scripts/<graph>/`; components are flat and namespaced by stable graph and agent codes
> (for example `g02-*` and `g02-a01-*`).

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
    skills/ agents/ shared/
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
installer to rebind the MCP command. There is **no virtualenv in the installed plugin**. Provider
HTTP clients use the standard library. Work requiring third-party packages, such as PDF parsing,
stays outside the deterministic core until its owning agent defines an isolated tool boundary.

Runtime artifacts (drafts, logs, hydrated `artifact://` files) live in the **current project**
under `.emagents/` (override with `EMAGENTS_HOME`); the dir is git-ignored.

The active Research Graph path covers the boundary front door, G02-A01 Planner, deterministic
Scout fanout, G02-A07 light source review, obligatory G02-A09 synthesis and the Human Research
Gate. Scout persists machine artifacts (plan, requests, manifests, per-topic corpora and
cross-topic index) under `.emagents/artifacts/g02/scout/runs/`, while human-inspectable PDF copies
live under `knowledge/g02/<task_id>/<topic-name>/`.
A07 reads only bounded Scout windows and compact intake context. A09 consumes aggregated A07
reviews plus bounded deep-dive windows, records whether the model pass succeeded, materializes
`research_state@1`, `evidence_map@1`, `research_summary@1`, the human validation packet and
`solution_input_candidate@1`, then pauses for human approval before emitting
`user_approved_research_bundle@1`.

The current MCP public surface exposes the active Scout/A07/A09 operations. Retired A02-A06,
A08, A11, source-selection and `research_run_*` flow surfaces are not listed for new runs. The
old modules remain in the repo as legacy implementation/test material until removed fully.

For Scout runs, the agent collects optional provider credentials from the user through
`research_provider_setup`. Ambient shell credentials are ignored by the active G02 runtime unless
they were marked by that setup step and inherited only as process transport; credentials never
belong in JSON, prompts, artifacts, cache or logs.

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

Verify the component inventory (expect the active g01/g02/g03 agents and skills, including A07
light review, obligatory A09 synthesis and g02-orchestrate-research):

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
`Local Plugins` marketplace. Codex receives the shared agents, skills, runtime and MCP tools. The
Codex runner reads the same agent `.md` definitions as Claude and invokes each node through an
isolated `codex exec`; only the host execution adapter differs.

## Run

In Claude Code:

```text
/research mocks/g02/research_graph_input.json
```

In Codex, start a new thread after install and ask in natural language, using an absolute JSON path
so plugin runtime does not depend on the MCP or worker process working directory:

```text
Zrób research dla /home/khudaszek/projects/EduMaterialsAgents/mocks/g02/research_graph_input.json
```

or:

```text
Run the research graph for /home/khudaszek/projects/EduMaterialsAgents/mocks/g02/research_graph_input.json
```

The `g02-orchestrate-research` skill treats these as semantic entrypoints and uses the
`research-scout-e2e` MCP prompt. The prompt drives A01 planning, Scout fanout, A07 light review,
A09 synthesis and the Human Research Gate without A10 review. After approval it creates a compact
`user_approved_research_bundle@1` for Graph03. Fast/scout mode explicitly states that A08 Claim
Verification was skipped.

For a no-LLM wiring inspection, the legacy `g02_flow.py inputs` command can still show what the A01
planner receives:

```bash
python shared/scripts/g02/g02_flow.py inputs mocks/g02/research_graph_input.json --node g02-a01-planner
```

The engine is host-agnostic; execution is the per-host orchestrator plus MCP tools. Human gates are
presented by the host and require explicit approval. Deprecated runner and review tools remain in
source for migration, but the MCP runtime returns `deprecated_tool` for those names.

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
