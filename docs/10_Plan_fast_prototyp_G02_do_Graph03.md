# Plan fast prototypu G02 do Graph03

Status: aktywne zrodlo prawdy. P0-P8 i audyt gotowosci przed P9 wdrozone 2026-06-23 bez
lokalnego uruchamiania testow; testy sa przygotowane i czekaja na osobne srodowisko TEST.
P9 pozostaje niewykonany.

Data: 2026-06-23.

Cel: doprowadzic G02 do szybkiego, oszczednego i sprawnego przeplywu, ktory startuje z
`research_graph_input@1`, znajduje i pobiera mala liczbe zrodel, wydobywa z nich uzyteczne
evidence, a na koncu tworzy artefakt syntezy i handoff dla Graph03. Tryb `fast` ma dawac pierwszy
dzialajacy prototyp, z mniejsza szerokoscia discovery i mniejsza rygorystycznoscia review, ale bez
utraty koncowego celu systemu.

## 1. Decyzje obowiazujace

Ten plan integruje obecny stan repo i decyzje z ostatniego przegladu:

1. `fast` nie moze konczyc sie na A06. A09 pozostaje ostatnim producentem w linii i tworzy finalny
   plik syntezy dla Graph03.
2. A08 Claim Verification jest wylaczony w trybie `fast`, ale zostaje w repo jako etap dla
   pozniejszego trybu `balanced` albo `strict`.
3. Dodajemy deterministyczne generowanie szybkiego `query_plan@1`, ale nie zastepujemy calego A02
   pelnym deterministycznym executorem.
4. A05 ma umiec pracowac w `fast` z dostepnymi reviewed streamami i jawnymi lukami, bez wymuszania
   calego kompletu A03/A04/A11 w kazdym przebiegu.
5. Obnizamy realne limity providerow, indeksu i retrieval dla `fast`.
6. Nie kompresujemy teraz promptow runnera i nie przebudowujemy sposobu ladowania skilli przez
   `codex_node_runner`.
7. Nie niszczymy dotychczas zaimplementowanych pionowych wycinkow. Dalsze zmiany maja byc
   profilowane przez `execution_profiles`, polityki fast i dodatkowe seamy MCP.

## 2. Docelowy przeplyw fast

Minimalny dzialajacy przeplyw:

```text
A01 Planner
  -> A10 review research_plan
  -> A02 Domain per selected topic
  -> optional A03/A04/A11 only when required or cheap enough
  -> A05 Candidate Source Index
  -> A10 review candidate_index
  -> Human Source Selection Gate
  -> A06 Paper Retrieval
  -> A10 review retrieved_corpus
  -> A07 Paper Review fast, one run per downloaded document or accepted market case
  -> A09 Synthesizer fast, without A08
  -> A10 review research_synthesis
  -> Human Research Gate z trzema jawnymi decyzjami
  -> user_approved_research_bundle@1 / SolutionInputCandidate for Graph03
```

Fast output is not a final slide deck. It is a compact, evidence-linked research package for
Graph03. It must contain enough information to create a new presentation: suggested updates,
optional improvements, unresolved issues, source refs, evidence cards, limitations and confidence
labels. It must not pass full PDFs or verbose paper reviews downstream.

## 3. Current state in repo

### Implemented or mostly implemented

- `shared/graphs/g02.graph.json` has `default_execution_profile: fast` and current model bindings.
- A01 through A06 deterministic seams exist in `shared/scripts/g02/` and MCP exposure exists in
  `shared/scripts/mcp/research_server.py`.
- A02, A03, A04, A11, A05 and A06 have contracts, agents, skills and runtime modules.
- A05 already performs deterministic deduplication, ranking, coverage and Markdown generation in
  `shared/scripts/g02/candidate_index.py`.
- A06 already prepares, resolves, downloads, validates and finalizes retrieved corpus artifacts in
  `shared/scripts/g02/retrieval.py` and `shared/scripts/g02/oa_retrieval.py`.
- A10 has `review_task@1`, `review_decision@1`, deterministic prepare/finalize and one-review
  semantics in `shared/scripts/g02/review.py`.
- `reviewed_flow.py` runs the implemented fast frontier through reviewed A09, pauses at Human
  Research Gate, and supports fast-track review for clean discovery stages.

### Implemented runtime after P6-P8

- A07 has agent and skill definitions, `paper_review@1`, runtime module, MCP operations, text
  index/window seams and source-scoped reviewed scheduler integration.
- A09 has agent and skill definitions, `research_state@1`, bundle contracts, runtime module, MCP
  operations, fast synthesis input, finalization and reviewed scheduler integration.
- A08 has agent, skill and `claim_assessment@1`, but its model is explicitly not frozen. It stays
  disabled in `fast`.

### Known fast blockers or inefficiencies

Po audycie gotowosci przed P9 nie pozostaje znany statyczny blocker implementacyjny. Wynik wymaga
potwierdzenia w osobnym srodowisku TEST. W audycie domknieto:

- osobne handlery terminalowe dla Human Source Selection Gate i Human Research Gate;
- kompletne CLI pause/resume przez `--resume-token` i decyzje JSON;
- walidacje wszystkich trzech decyzji koncowej bramki i filtrowanie opcjonalnych oraz
  nierozstrzygnietych pozycji w zatwierdzonym handoffie;
- nowa wersje i nowy ref dla jedynej poprawki po `REVISE`, bez drugiego review;
- fail-closed A05 `REVISE`, gdy bez zmiany upstreamu lub profilu powstalby identyczny indeks;
- provenance review A07 wymagane przez domyslny profil `fast` przed A09;
- synteze A09 z jawnymi retrieval gaps takze wtedy, gdy A06 nie pobral zadnego dokumentu;
- deterministyczne pominiecie A03, gdy approved scope lub role topicu nie wymagaja canonical stream;
- konserwatywna, niezalezna od kolejnosci agregacje statusow evidence;
- kontrakty czterech pomocniczych artefaktow A09 oraz scislejsze kontrakty A07, A09 i bundle;
- limit czterech bounded windows na zrodlo A07 i sekcyjne lokacje fallbackowego parsera PDF.

- A02 uses a deterministic fast query generator before model adjustment.
- A05 applies `available_streams` in fast and preserves optional-stream warnings.
- Provider, candidate-index and retrieval limits are capped by the active fast profile.
- A10 receives a deterministic preflight summary and fast blocker/major guidance.
- P6-P8 tests are prepared but not executed locally. P9 remains the separate TEST pass for the
  proper environment.

## 4. Implementation plan

### P0. Freeze this plan as the active roadmap

Files:

- `docs/10_Plan_fast_prototyp_G02_do_Graph03.md`
- `docs/00_README.md`
- later, cross-links from `docs/07_Rejestr_DEV_TEST_1b1.md` and `docs/09_Optymalizacja_kosztu_i_czasu.md`

Tasks:

- [x] Add this file to the documentation index.
- [x] Treat this plan as the execution checklist for the remaining fast prototype work.
- [x] Keep `06_Plan_finalizacji_1b1.md` as the broader 1b1 plan, while this file governs the
      fast G02 to Graph03 prototype.

Definition of done:

- The repo has one clear fast-prototype plan that includes A07 and A09, disables A08 in fast and
  preserves existing implemented work.

### P1. Extend graph profile semantics

Files:

- `shared/graphs/g02.graph.json`
- `shared/scripts/g02/reviewed_flow.py`
- `shared/scripts/mcp/research_server.py`
- `tests/test_g02_reviewed_flow.py`
- `tests/test_plugin_build.py`

Tasks:

- [x] Add `execution_profiles.fast.terminal_stage: g02-a09-synthesizer`.
- [x] Add `execution_profiles.fast.skip_nodes: ["g02-a08-claim-verification"]`.
- [x] Add `execution_profiles.fast.synthesis_mode: "evidence_without_claim_assessment"`.
- [x] Extend review policy so `fast` requires A10 for A01, A05, A06 and A09.
- [x] Make A07 review conditional in fast:
  - run A10 for A07 when paper review is `degraded`, has missing locations, conflicting evidence,
    prompt-injection flags, or the document is marked central;
  - allow deterministic fast-track for clean, limited A07 outputs only if validation is strong.
- [x] Keep A02, A03, A04 and A11 fast-track when finalizer returns clean `ok`.
- [x] Keep the activation guard explicit: update `research_run_codex` default `through` from A06
      to A09 only in P8, once P6 and P7 add the required A07/A09 seams.

Definition of done:

- The profile and implemented runner use reviewed A09 as the terminal producer.
- A08 is skipped by policy, not deleted.
- A09 is reviewed before a Graph03 handoff is emitted.

### P2. Add deterministic fast query-plan generation

Files:

- `shared/scripts/g02/query_planning.py`
- `shared/scripts/mcp/research_server.py`
- `agents/g02-a02-domain.md`
- `skills/g02-expand-research-query/SKILL.md`
- `mocks/g02/query_plan.json`
- `mocks/g02/recent_query_plan.json`
- tests around query planning and metadata search

Tasks:

- [x] Add `generate_fast_query_plan(discovery_input, profile)` in `query_planning.py`.
- [x] Expose MCP tool `research_query_plan_generate_fast`.
- [x] Generate at most three flat routes:
  - `core`;
  - `complementary` when stop rule requires it;
  - `qualifying_or_critical` only when the role is required.
- [x] Use one ready provider per scholarly route, default `openalex`.
- [x] Preserve exclusions, filters, coverage units, limits and approved origin terms exactly.
- [x] Validate generated output through existing `validate_query_plan`.
- [x] Update A02 instructions: in fast, call the query-plan generator first and only ask the model
      to adjust if the generator reports a structured gap.

Non-goal:

- Do not implement a full deterministic A02 executor now. A02 remains the agent responsible for
  interpreting provider results and building `domain_candidate_sources@1`.

Definition of done:

- A02 no longer needs to invent the query plan structure in the common fast path.
- A bad query plan is caught before any provider call.

### P3. Make A05 tolerant of fast available-stream policy

Files:

- `shared/scripts/g02/candidate_index.py`
- `shared/graphs/g02.graph.json`
- `agents/g02-a05-candidate-source-index.md`
- `skills/g02-orchestrate-research/SKILL.md`
- candidate index tests and mocks

Tasks:

- [x] Add profile option `required_stream_policy`.
- [x] Use strict current behavior outside fast.
- [x] In `fast`, require A02 domain for every selected topic.
- [x] Treat A03, A04 and A11 as available optional streams unless the plan or user explicitly
      marks them as mandatory for this run.
- [x] Preserve missing stream warnings in `coverage_matrix`, `search_summary` and
      `candidate_source_review.md`.
- [x] Keep A05 review mandatory, because A05 is the human gate artifact.

Definition of done:

- A05 can build a useful fast index from A02 plus any available A03/A04/A11 outputs.
- Missing optional streams are visible to the user and to A09, but do not block the prototype.

### P4. Lower fast limits

Files:

- `shared/graphs/g02.graph.json`
- `shared/config/g02.providers.example.json`
- `shared/scripts/g02/provider_config.py`
- `shared/scripts/g02/candidate_index.py`
- `shared/scripts/g02/retrieval.py`
- mocks and tests using limits

Target fast limits:

- Planner:
  - max topics: 2
  - candidate limit per topic: 12
  - candidate pool target per topic: 8
- Scholarly providers:
  - per page: 8 or 10
  - max pages per call: 1
  - max records per query: 8
- Web:
  - max queries per task: 3 or 4
  - max Tavily queries per task: 2 or 3
  - max results per query: 5
  - max extractions per task: 3
- A05:
  - display limit: 8
  - reserve limit: 4
  - per topic limit: 4
- A06:
  - max documents per task: 3 to 5

Tasks:

- [x] Move fast limits into `execution_profiles.fast` where possible.
- [x] Let deterministic modules read profile overrides with safe fallback to current config.
- [x] Keep example provider config conservative, but not destructive for existing non-fast use.
- [x] Update tests to assert fast limit application. Tests are prepared for the separate TEST
      environment and were not run in this implementation session.

Definition of done:

- A normal fast run cannot silently fan out into a large search or retrieval job.
- Strict or future balanced mode can still raise limits without rewriting code.

### P5. Optimize A10 for fast review

Files:

- `agents/g02-a10-output-reviewer.md`
- `skills/g02-review-research-output/SKILL.md`
- `shared/scripts/g02/review.py`
- `shared/scripts/g02/reviewed_flow.py`
- review tests

Tasks:

- [x] Add deterministic review preflight summary:
  - contract validation status;
  - artifact identity and version;
  - acceptance criteria list;
  - evidence requirement checklist;
  - deterministic issues;
  - small semantic sample or summary when available.
- [x] Add fast review mode in review task or review context.
- [x] In fast, require A10 to focus on blocker and major defects only.
- [x] Move minor wording or style concerns into `advisories`.
- [x] Keep one review per producer run and one correction without re-review.
- [x] Keep fast-track approval for clean A02/A03/A04/A11.
- [x] Require A10 for A09 before Graph03 handoff.
- [x] Retain `sonnet/medium`; consider `sonnet/low` only after real fast tests prove it useful.

Definition of done:

- A10 stops causing repeated correction loops.
- A10 protects the key gates, A01, A05, A06 and A09, without reviewing every clean discovery artifact.

### P6. Implement A07 fast paper review

Files to add or modify:

- `shared/scripts/g02/paper_review.py`
- `shared/scripts/mcp/research_server.py`
- `shared/contracts/paper_review.schema.json`
- `agents/g02-a07-paper-review.md`
- `skills/g02-a07-extract-paper-evidence/SKILL.md`
- `skills/g02-a11-extract-case-evidence/SKILL.md`
- `shared/scripts/g02/reviewed_flow.py`
- mocks and tests for one PDF and one market case

Required MCP tools:

- `research_paper_review_prepare`
- `research_document_text_index`
- `research_document_text_window`
- `research_paper_review_finalize`
- `research_paper_review_task`

Fast behavior:

- [x] Run one A07 instance per downloaded document or accepted market-case bundle.
- [x] Read only targeted text windows, not full PDFs.
- [x] Use source title, abstract, section map, methods/results/conclusion windows and assigned
      topic/claim terms.
- [x] Produce compact `paper_review@1` with evidence cards, locations, method context,
      limitations and confidence.
- [x] For market cases, use A06 bundled Markdown and JSON plus reviewed A11 annotation, with no
      new web extraction.
- [x] Mark insufficient or partial text explicitly instead of guessing.

Minimum viable output:

- source ID;
- reviewed document ref;
- related topic IDs and claim IDs where available;
- contribution;
- method or source basis;
- findings as evidence cards;
- limitations;
- page or section locations;
- `evidence_access_level`;
- `review_profile_ref: paper_evidence`.

Definition of done:

- A07 can create evidence cards from a small downloaded corpus without loading full documents into
  one context.
- A09 can consume A07 output without A08.

### P7. Implement A09 fast synthesis without A08

Files to add or modify:

- `shared/scripts/g02/synthesis.py`
- `shared/scripts/mcp/research_server.py`
- `shared/contracts/research_state.schema.json`
- `shared/contracts/user_approved_research_bundle.schema.json`
- `agents/g02-a09-synthesizer.md`
- `skills/g02-a09-synthesize-research-findings/SKILL.md`
- `shared/scripts/g02/reviewed_flow.py`
- tests and mocks for A07 to A09

Required MCP tools:

- `research_synthesis_prepare`
- `research_synthesis_finalize`
- `research_synthesis_review_task`
- optionally `research_bundle_finalize` if current `research_finalize` is not enough for the
  post-human-gate bundle.

Fast behavior:

- [x] Accept reviewed A07 paper reviews and retrieved corpus refs.
- [x] Accept A05 candidate index and source selection refs.
- [x] Do not require A08 claim assessments in `fast`.
- [x] Produce evidence-linked findings with conservative status labels:
  - `supported_by_reviewed_source`;
  - `needs_human_check`;
  - `insufficient_evidence`;
  - `context_only`;
  - `market_case_signal`.
- [x] Avoid final truth labels such as fully verified claim when A08 is skipped.
- [x] Produce:
  - `research_state@1`;
  - evidence map or evidence map ref;
  - human validation packet;
  - `SolutionInputCandidate`;
  - final `user_approved_research_bundle@1` after gate or explicit fast approval mode.
- [x] Keep full PDFs, full extracted text and verbose paper reviews out of Graph03 handoff.

Definition of done:

- A09 is the last producer in `fast`.
- Graph03 receives compact, traceable presentation-building input.
- Missing A08 is visible as a fast-mode limitation, not hidden as a completed claim verification.

### P8. Update orchestrator and reviewed flow through A09

Files:

- `shared/scripts/g02/reviewed_flow.py`
- `shared/scripts/mcp/research_server.py`
- `skills/g02-orchestrate-research/SKILL.md`
- `commands/adapters/research.codex.md`
- `commands/adapters/research.claude.md`
- `shared/graphs/README.md`

Tasks:

- [x] Extend `STAGES` beyond A06 to A07 and A09 for fast.
- [x] Implement skip logic for A08 in fast.
- [x] Add preparation and review-task routing for A07 and A09.
- [x] Add A09 output ref to `research_run_report@1`.
- [x] Decide whether Human Research Gate is required in every fast run or can be represented by a
      paused final approval step.
- [x] Keep source selection gate before A06 unchanged.
- [x] Update command docs so `/research` and `research_run_codex` describe A09 as the fast target.

Definition of done:

- One command can run from input to A09 synthesis, pausing only at human gates.

### P9. Tests in the proper environment

Do not spend time here on full live tests until the runtime pieces exist. The test plan should be
ready, but execution belongs in the target test environment.

Required targeted tests:

- [ ] Query generator produces valid flat `query_plan@1`.
- [ ] A02 with generated fast query plan reaches `domain_candidate_sources@1`.
- [ ] A05 builds index from A02-only plus optional stream gaps in fast.
- [ ] A06 retrieves or marks unavailable a small approved set.
- [ ] A07 creates paper review from one PDF fixture.
- [ ] A09 creates synthesis without A08 and marks claim verification limitation.
- [ ] A09 finalizer blocks missing or unbound evidence refs before A10; A10 reviews the valid
      synthesis semantically exactly once.
- [ ] End-to-end fast run reaches A09 and emits Graph03 handoff candidate.
- [ ] Terminal `--gates prompt` obsluguje osobno source gate i finalny research gate bez wyjatku.
- [ ] Jedyna korekta po `REVISE` tworzy nowy ref i podnosi patch `artifact_version`; A10 nie jest
      wywolywany drugi raz.
- [ ] A09 odrzuca brak provenance review A07 w domyslnym `fast`.
- [ ] A09 tworzy unresolved retrieval gaps i dochodzi do Human Research Gate, gdy A06 nie pobral
      zadnego PDF.
- [ ] Odrzucenie optional improvements lub unresolved items jest odzwierciedlone w zatwierdzonym
      research summary i bundle dla Graph03.

## 5. Non-goals for this fast prototype

These items stay out of the immediate fast implementation:

- Full A08 claim verification.
- Full deterministic A02 executor replacing the A02 agent.
- Prompt compression in `codex_node_runner`.
- Broad fan-out/fan-in scheduler for wall-clock optimization.
- Strict review for every clean discovery artifact.
- Full semantic proof that every claim is verified.
- Final slide writing inside G02.

## 6. Definition of done for the fast prototype

The fast prototype is done when:

- `research_run_codex` can run to A09 by default, with explicit pauses at human gates.
- A08 is skipped by policy in fast and remains available for future modes.
- A01 creates at most two priority-selected topics.
- A02 uses a valid fast query plan without schema iteration.
- A05 can build a compact human source review from available fast streams.
- A06 downloads or records unavailability for a small approved set.
- A07 extracts compact evidence from downloaded PDFs or approved market-case bundles.
- A09 creates a compact, evidence-linked synthesis and `SolutionInputCandidate`.
- A10 protects A01, A05, A06 and A09, and handles A07 conditionally.
- Graph03 receives refs, evidence cards, update recommendations and limitations, not full PDFs.
- Existing strict-capable architecture remains intact.

## 7. Suggested implementation order

1. P0, add and index this plan.
2. P1, extend fast profile semantics.
3. P2, deterministic fast query-plan generation.
4. P3 and P4, A05 policy and fast limits.
5. P5, A10 fast review packet and A09 mandatory review.
6. P6, A07 runtime and MCP.
7. P7, A09 runtime and MCP without A08.
8. P8, reviewed flow and command integration through A09.
9. P9, targeted tests in the proper test environment.

This sequence gets a working prototype before broader quality work. It keeps the current A01-A06
frontier useful, adds the missing evidence and synthesis tail, and leaves A08 for the later
quality profile.
