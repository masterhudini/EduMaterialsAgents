# edu-materials-agents

Agent-stack plugin for **Claude Code** and **Codex** that improves educational / lecture
materials through reviewed agent graphs (`g01` intake → `g02` research → `g03` solution). First graph in scope:
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
bound to the Python interpreter used by the installer, so both `python3` and `python` environments
are supported. There is **no virtualenv in the installed plugin**. Provider HTTP clients use the
standard library. Work requiring third-party packages, such as PDF parsing, stays outside the
deterministic core until its owning agent defines an isolated tool boundary.

Runtime artifacts (drafts, logs, hydrated `artifact://` files) live in the **current project**
under `.emagents/` (override with `EMAGENTS_HOME`); the dir is git-ignored.

The implemented deterministic Research Graph seams currently cover the boundary front door,
G02-A01 Planner, G02-A02 Domain, provider configuration and metadata search, the universal reviewer
and the final handoff. OpenAlex, Semantic Scholar and arXiv adapters apply bounded requests, retry,
rate limits, cache, normalization and raw-response provenance. The MCP server exposes fifteen
operations at version `0.4.0`. A11 Market Cases and its two skills are shipped as a design scaffold;
the Tavily search and post-gate extraction operations remain scheduled with the A11 runtime slice.
Remaining operations are added with their owning agents.

Before the first G02-A02 run, copy `shared/config/g02.providers.example.json` to
`.emagents/config/g02-providers.json`, set `EMAGENTS_RESEARCH_CONTACT_EMAIL` and provide the
required `OPENALEX_API_KEY`. `SEMANTIC_SCHOLAR_API_KEY` remains optional but is recommended for an
individual rate limit. See `shared/config/README.md`; never place credentials in the JSON file.

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

Verify the component inventory (expect 11 agents + 20 skills, including the A11 scaffold and
g02-orchestrate-research):

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
<<<<<<< Updated upstream
<<<<<<< Updated upstream
`Local Plugins` marketplace. Codex receives the shared skill/runtime and MCP tools; Codex-specific
subagent orchestration is a separate adapter layer from Claude's agent `.md` files.
=======
`Local Plugins` marketplace. Codex receives the shared agents, skills, runtime and MCP tools. The Codex
CLI plugin manifest does not currently register plugin `commands/` as slash commands, so
`/research` is Claude-only in current Codex CLI builds.
>>>>>>> Stashed changes
=======
`Local Plugins` marketplace. Codex receives the shared agents, skills, runtime and MCP tools. The
Codex runner reads the same agent `.md` definitions as Claude and invokes each node through an
isolated `codex exec`; only the host execution adapter differs.
>>>>>>> Stashed changes

## Run

```
/research mocks/g02/research_graph_input.json
```

Or deterministically, without an LLM. This harness validates wiring and uses no-op producers,
automatic reviewer approvals and automatic user-gate approvals:

```bash
python shared/scripts/g02/g02_flow.py run mocks/g02/research_graph_input.json
# inspect what one agent would receive:
python shared/scripts/g02/g02_flow.py inputs mocks/g02/research_graph_input.json --node g02-a01-planner
```

<<<<<<< Updated upstream
=======
Or drive the real graph through **Codex workers** (each node is an isolated `codex exec`, no API
key — Codex subscription login; terminal user gates). Local/dev only:

```bash
python shared/scripts/g02/g02_flow.py run-codex mocks/g02/research_graph_input.json
# single isolated node (cheaper smoke):
python shared/scripts/g02/runners/codex.py g02-a01-planner mocks/g02/research_graph_input.json
```

The engine is host-agnostic; execution is the per-host runner (Claude Task subagents vs Codex
`codex exec`). Gates support auto / terminal (`--gates prompt`) / async pause-resume.

>>>>>>> Stashed changes
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
