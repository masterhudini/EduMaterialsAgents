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
bound to the absolute Python interpreter used by the installer, so both `python3` and `python`
environments are supported. If that interpreter path later changes (upgrade/relocation), rerun the
installer to rebind the MCP command. There is **no virtualenv in the installed plugin**. Provider
HTTP clients use the standard library. Work requiring third-party packages, such as PDF parsing,
stays outside the deterministic core until its owning agent defines an isolated tool boundary.

Runtime artifacts (drafts, logs, hydrated `artifact://` files) live in the **current project**
under `.emagents/` (override with `EMAGENTS_HOME`); the dir is git-ignored.

The implemented deterministic Research Graph seams cover the boundary front door, G02-A01
Planner, G02-A02 Domain, G02-A03 Canonical Sources, G02-A04 Recent Developments, G02-A11 Market
Cases, G02-A05 Candidate Source Index, G02-A06 Paper Retrieval, source-scoped G02-A07 Paper Review,
G02-A09 fast Synthesis, the universal reviewer and the final handoff. OpenAlex,
Semantic Scholar and arXiv adapters apply bounded metadata and citation requests. Crossref verifies
available DOIs through persisted registry metadata, field comparisons and raw provenance; provider
metadata is never overwritten on conflict. A11 uses Tavily as the default web provider, with strict
query budgets, redirect checks, cache, timeout, rate limits, source tiers and provenance. SearXNG
remains disabled and no public-instance endpoint catalog is installed. Full-page Tavily extraction requires a
persisted final `human_source_selection@1`; discovery cannot invoke it. A05 accepts only upstream
artifacts bound either to `APPROVED` A10 decisions or to one corrected `REVISE` decision with a
validated `revision_completion@1` receipt. It creates a deduplicated index and a readable source
choice document whose scholarly descriptions are labelled as abstract-based or metadata-only and
whose market-case descriptions use reviewed A11 facts and didactic mechanisms. A two-step source
gate freezes `human_approved_source_set@1`. A06 resolves scholarly DOWNLOAD sources through approved
record links, Unpaywall, optional CORE and DOAB/OAPEN, validates PDF identity and integrity, and
places validated PDFs plus gated A11 market-case bundles in one `corpus://` run folder described
by `retrieval_directory@1`. Each bundle includes a readable Markdown document containing
the reviewed A11 fact, didactic mechanism, source assessment and bounded post-gate page content;
the JSON remains the machine-readable audit artifact. The human fixes the exact DOWNLOAD count at the gate; A06 enforces the
administrator's `max_documents_per_task` and cannot add sources. A07 reads only deterministic
bounded text windows from accepted PDFs or A06 market-case bundles. In `fast`, A08 remains skipped
by graph policy, and A09 produces `research_state@1`, a compact evidence map, a human validation
packet and a SolutionInputCandidate before pausing at the Human Research Gate. The MCP server
exposes 52 operations at version `0.13.0`, including the dedicated pre-A07
`research_scout_fanout` operation.

Before the first G02-A02 or A11 run, copy `shared/config/g02.providers.example.json` to
`.emagents/config/g02-providers.json`, set `EMAGENTS_RESEARCH_CONTACT_EMAIL` and provide the
required `OPENALEX_API_KEY`. The same contact email enables polite Crossref requests. Set
`TAVILY_API_KEY` for A11. `SEMANTIC_SCHOLAR_API_KEY` remains optional. The supplied configuration
keeps SearXNG disabled; the runtime never selects a public instance. See `shared/config/README.md`; credentials never belong
in JSON, prompts, artifacts, cache or logs.

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

Verify the component inventory (expect 11 agents + 21 skills, including DOI verification, A11 and
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
`research_run_codex` MCP tool. The default Codex gate mode is pause/resume (`gates: "pause"`), so
human gates return a `resume_token` instead of reading interactive stdin from the MCP process.
The reviewed runner covers the implemented fast frontier through reviewed A09 and returns a typed
`research_run_report@1`. It pauses at the Human Source Selection Gate and again at the Human
Research Gate; after approval it creates a compact `user_approved_research_bundle@1` for Graph03.
Fast mode explicitly states that A08 Claim Verification was skipped.

Or use the runner directly:

```bash
python /home/khudaszek/.codex/plugins/edu-materials-agents/shared/scripts/g02/g02_flow.py run-codex /home/khudaszek/projects/EduMaterialsAgents/mocks/g02/research_graph_input.json
```

Or run deterministically, without an LLM. This harness validates wiring and uses no-op producers,
automatic reviewer approvals and automatic user-gate approvals:

```bash
python shared/scripts/g02/g02_flow.py run mocks/g02/research_graph_input.json
# inspect what one agent would receive:
python shared/scripts/g02/g02_flow.py inputs mocks/g02/research_graph_input.json --node g02-a01-planner
```

Or drive the real graph through **Codex workers** (each node is an isolated `codex exec`, no API
key — Codex subscription login; terminal user gates). Local/dev only:

```bash
python shared/scripts/g02/g02_flow.py run-codex mocks/g02/research_graph_input.json
# bounded forward smoke for one topic, stopping before A05 requires the complete plan:
python shared/scripts/g02/g02_flow.py run-codex mocks/g02/research_graph_input.json \
  --through g02-a02-domain --topic-id TOPIC_BAYESIAN_COMPUTATION
# single isolated node (cheaper smoke):
python shared/scripts/g02/runners/codex.py g02-a01-planner mocks/g02/research_graph_input.json
```

The engine is host-agnostic; execution is the per-host runner (Claude Task subagents vs Codex
`codex exec`). Real Codex gates show numbered source cards, accept numbers or stable source IDs,
and require a separate terminal confirmation (`--gates prompt`) or
pause/resume (`--gates pause`). Automatic synthetic gates exist only in the no-op stub harness.
Every real producer envelope and stored artifact is validated before A10 runs. A10 runs at most
once per producer execution. `APPROVED` continues immediately, `BLOCKED` stops the process, and
`REVISE` permits one targeted producer correction that is deterministically finalized and recorded
without a second review.

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
