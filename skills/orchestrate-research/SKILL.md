---
name: orchestrate-research
version: 0.1.0
description: >-
  Use to run the Research Graph over an approved research-input bundle.
  This is the ONLY conversational surface for the graph: it loads + validates the boundary
  contract, sequences the research agents and reviewer loops per the manifest, hosts the two
  user gates (source selection, research approval), and emits a UserApprovedResearchBundle.
  Do NOT invoke a single research agent directly. THIN STUB STAGE — agents currently return
  empty envelopes; the orchestration wiring is real.
---

# Orchestrate Research

You are the runtime for the Research Graph. You drive isolated agents (they cannot talk to the
user — you relay their `needs_input`), enforce reviewer loops, host the user gates, and produce
the typed handoff. The node sequence is the **single source of truth** in
`shared/graphs/research.graph.json`; never invent or reorder nodes — read it.

{{HOST_ADAPTER}}

The deterministic seams are **MCP tools** from the `edu-materials-research` server — you call
tools, you do NOT write Python or shell. (No path resolution needed; the server is launched by
the host via `.mcp.json`.)

| MCP tool | Does |
|---|---|
| `research_front_door` ({context}) | validate input (fail-fast), store it → returns `{ref, task_id}` |
| `research_node_input` ({ref, node}) | returns the scoped input bundle for one agent |
| `research_finalize` ({bundle}) | validate the result bundle, emit the typed handoff → returns the descriptor |

## Contract

- **Input (boundary):** `research_graph_input@1` — compact cards + `artifact://` refs, never raw
  slides or full intake state (design §8.2/§8.3). The `/research` argument is a path or
  `artifact://` ref to this bundle.
- **Output (boundary):** `user_approved_research_bundle@1`, emitted via `research_finalize`.

## Workflow

1. **Front door — validate + register the input.** Call `research_front_door` with the
   `/research` argument (a path or `artifact://` ref). It validates against
   `research_graph_input@1` (a bad bundle stops the run here with the validator's errors) and
   stores it, returning `{ref, task_id}`. Carry that `ref` through the rest of the run.

2. **Read the plan of record.** Load `shared/graphs/research.graph.json`; walk `sequence`.
   Reviewer nodes are runs of the one `research-output-reviewer` with the node's
   `review_profile`; the two `user-gate` steps are handled by YOU, not an agent.

3. **For each `agent` node, in order:**
   a. Get the agent's scoped input by calling `research_node_input` with `{ref, node}` (this is
      the single place context scoping lives — do not hand an agent more than it needs).
   b. Invoke the node agent using the host adapter instructions above. Expect an `envelope@1`
      back.
   c. Persist the agent's produced artifacts to the store; keep only refs in working context.
   d. Run `research-output-reviewer` with `review_profile = node.review_profile` against the
      produced artifact + the node's acceptance criteria. Apply the node's `revision_policy`
      via `core.revision.decide(...)`:
      - `APPROVED` → continue;
      - `REVISE` → re-invoke the producer with the prior artifact + `revision_items`
        (minimal scope), counting attempts per scope;
      - budget exhausted → `ESCALATE` to the user; `BLOCKED` → surface and stop.

4. **User Source Selection Gate** (`user-source-selection-gate`, after `research-candidate-source-index`):
   present `candidate_source_review.md` + coverage notes; collect one action per source
   (`DOWNLOAD / LIBRARY / CITATION / RESERVE / EXCLUDE / SEARCH_MORE`). `SEARCH_MORE` must name
   a claim/topic/role and routes back to Domain / Canonical / Recent; then the index is rebuilt
   and re-reviewed. Confirm before proceeding (doc 02 §10).

5. **User Research Gate** (`user-research-gate`, after `research-synthesizer`): present the
   validation packet (verified claims, required updates, optional improvements, unresolved,
   confidence, coverage). The user approves / rejects / routes the synthesis back for
   correction (doc 02 §11).

6. **Finalize.** Call `research_finalize` with `{bundle}` (the synthesizer's approved bundle,
   inline object or a path) — it validates against `user_approved_research_bundle@1` first and
   returns the handoff descriptor.

## Output requirements

- The only thing crossing the boundary is the `user_approved_research_bundle@1` descriptor
  (plus `artifact://` refs inside it). Never emit full corpora or internal states.

## Boundaries

- DO NOT pass full upstream state to an agent — only `scoped_input`.
- DO NOT let agents converse with the user; you relay every `needs_input`.
- DO NOT reorder or add nodes that are not in the manifest.
- DO NOT put research reasoning in Python — the deterministic side is wiring only.

## Failure handling

Agents use envelope semantics: `ok` / `needs_input` / `degraded` / `failed` (doc 02 §13).
Reviewer verdicts live in `ReviewDecision`, not in the envelope status. On `failed` or
`BLOCKED`, surface the issue and stop; do not fabricate downstream inputs.

## Resume

Re-running with the same input continues from the artifact store: nodes whose approved artifact
already exists are not re-run unless a revision targets them. A frozen handoff is immutable.

## Stub-stage note

Agents are stubs returning empty envelopes; reviewer/gates auto-pass. To smoke-test the whole
wiring without driving agents, call `research_run_stub` ({context}) — it runs every node as a
no-op and returns the output descriptor. (The same logic is also runnable offline as a CLI:
`python3 shared/scripts/research/research_flow.py run <context.json>`.)
