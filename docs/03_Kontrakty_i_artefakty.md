# Research Graph, projekty kontraktów i artefaktów

## 1. Status dokumentu

Poniższe struktury są kontraktami semantycznymi. KH i programista warstwy integracyjnej mogą
dostosować szczegóły serializacji, wersjonowania i artifact paths, zachowując znaczenie pól i
granice odpowiedzialności.

Każdy izolowany agent zwraca uniwersalny `envelope@1`. Artefakty opisane poniżej znajdują się
w `produced[]` koperty.

## 2. Wejście całego modułu

### `[KH-DECISION: RESEARCH-GRAPH-INPUT-CONTRACT]`

KH powinien potwierdzić, czy wcześniejsze moduły mogą wytworzyć ten pakiet oraz czy nazwy
stanów i artifact refs są spójne z resztą systemu.

```yaml
ResearchGraphInput:
  schema_version: research_graph_input@1
  task_id: RESEARCH_001

  human_approved_context:
    course_name: Bayesian Statistics
    lecture_title: Scalable Bayesian Inference
    audience_level: master
    target_duration_minutes: 90
    teaching_goal: refresh_and_improve_logical_flow
    output_language: English

  approved_research_scope:
    domains:
      - domain_id: D1
        label: Bayesian statistics
      - domain_id: D2
        label: probabilistic programming

    verify_claim_priorities:
      - high
      - medium

    include_recent_developments: true
    include_canonical_sources: true
    include_didactic_examples: true
    recency_window_years: 5

    access_policy:
      index_open_and_closed: true
      download_open_access_only: true
      automate_institutional_access: false

  research_drivers:
    claim_cards:
      - claim_id: CLM_001
        slide_id: 12
        text: Bayesian methods are computationally expensive for large-scale problems.
        type: methodological
        verification_priority: high
        related_concepts:
          - Bayesian inference
          - approximate inference
        artifact_ref: artifact://states/claim_state.approved.json#/claims/CLM_001

    concept_cards:
      - concept_id: C1
        label: Posterior distribution
        role: core_concept
        related_claims:
          - CLM_001
        artifact_ref: artifact://states/concept_state.approved.json#/concepts/C1

    flow_issue_cards:
      - issue_id: F_001
        severity: high
        summary: Posterior is used before likelihood is explained.
        affected_slides:
          - 6
          - 7
        artifact_ref: artifact://states/flow_state.approved.json#/issues/F_001

    update_need_cards:
      - update_id: UPD_001
        summary: Check whether computational limitations need qualification.
        priority: high
        related_domains:
          - D1

    existing_source_cards:
      - source_id: EXISTING_001
        citation: null
        doi: null
        related_slides:
          - 12
        current_role: claim_support
        verification_need: high

  constraints:
    locked_sections:
      - section_id: S1
        reason: Author wants to keep the opening narrative.
    excluded_topics: []

  selection_profile:
    max_displayed_candidates: 30
    candidate_pool_factor: 2
    soft_retrieval_limit: 12
    hard_retrieval_limit: 20
    max_sources_per_topic: 12
    min_candidate_sources_high_claim: 3
    min_candidate_sources_medium_claim: 2
    min_recent_per_update_topic: 2
    require_counterevidence_search_for_high_claims: true

  artifact_refs_for_lazy_hydration:
    claim_state_ref: artifact://states/claim_state.approved.json
    concept_state_ref: artifact://states/concept_state.approved.json
    flow_state_ref: artifact://states/flow_state.approved.json

  output_contract:
    artifact: human_approved_research_bundle@1
```

### 2.1. Walidacja sensu wejścia

Research Graph może rozpocząć pracę, gdy:

- kontekst wykładu jest zatwierdzony,
- istnieje przynajmniej jedna zatwierdzona domena,
- istnieje co najmniej jeden research driver,
- priorytety i access policy są znane,
- output language jest określony lub może przyjąć `English`,
- zablokowane sekcje są jawne, nawet jeśli lista jest pusta.

Brak claimów nie blokuje modułu, jeśli istnieje zatwierdzona potrzeba aktualizacji, problem
pojęciowy albo flow issue. Ogólny opis dziedziny bez research driver prowadzi do `needs_input`.

## 3. ResearchPlan

```yaml
ResearchPlan:
  schema_version: research_plan@1
  task_id:
  topics:
    - topic_id: TOPIC_001
      name:
      purpose:
      priority:
      related_claims: []
      related_concepts: []
      related_flow_issues: []
      related_update_needs: []
      approved_domains: []

      source_roles_required:
        canonical: true
        current: true
        survey: true
        didactic: false
        qualifying_or_critical: true

      search_strategy:
        core_terms: []
        allowed_expansion_areas: []
        excluded_terms: []
        year_from: null
        year_to: null
        languages: []
        work_types: []
        seed_sources: []

      coverage_requirements: []
      stop_rule:
        candidate_limit:
        no_new_coverage_passes: 2
        complementary_search_route_required: true

  global_constraints:
  review_profile_ref:
```

Każdy topic musi być powiązany z zatwierdzonym research driver. Planner nie może tworzyć
topic wyłącznie dlatego, że wydaje się interesujący.

## 4. Rekord źródła

```yaml
SourceRecord:
  source_id: SRC_001

  identifiers:
    doi: null
    openalex_id: null
    semantic_scholar_id: null
    arxiv_id: null
    isbn: null

  bibliographic:
    title:
    authors: []
    year:
    venue: null
    publisher: null
    language: null
    work_type: article

  content_available:
    abstract: null
    abstract_source: null
    table_of_contents_available: false

  classification:
    related_topics: []
    related_claims: []
    source_roles: []
    category: null

  signals:
    cited_by_count: null
    citation_percentile: null
    recent_citation_velocity: null
    internal_graph_centrality: null
    recommendation_signal: null
    canonical_score: null
    rising_score: null

  access:
    oa_status: unknown
    access_level: metadata_only
    candidate_pdf_urls: []
    publisher_url: null
    library_access_required: false

  provenance:
    source_apis: []
    retrieved_at: null
    query_ids: []
    merged_from_records: []

  inclusion:
    reason_included: []
    coverage_units: []
    pool: displayed
```

### 4.1. Access level

Dozwolone wartości:

- `metadata_only`,
- `abstract`,
- `table_of_contents`,
- `preview`,
- `partial_text`,
- `full_text`.

Access level opisuje, co agent rzeczywiście widział. Nie jest równoznaczny z OA status.

### 4.2. Role źródła

Rekord może mieć więcej niż jedną rolę:

- `canonical`,
- `foundational`,
- `current`,
- `rising`,
- `survey`,
- `didactic`,
- `methodological`,
- `claim_specific`,
- `qualifying_or_critical`,
- `optional`.

## 5. CandidateSourceIndex

```yaml
CandidateSourceIndex:
  schema_version: candidate_source_index@1
  task_id:
  research_plan_ref:

  candidates: []
  reserve_candidates: []

  coverage_matrix: []

  search_summary:
    queries_run: []
    sources_queried: []
    raw_records_found:
    records_after_deduplication:
    displayed_candidates:
    reserve_candidates:
    unresolved_search_gaps: []

  annotation_policy:
    descriptions_generated_from:
      - abstract
    bibliographic_metadata_from_llm: false

  human_review_document_ref:
  reviewer_profile: candidate_index
```

## 6. Dokument dla człowieka

`candidate_source_review.md` jest generowanym artefaktem runtime. Nie jest częścią kodu
repozytorium.

### 6.1. Układ dokumentu

```markdown
# Candidate Source Review

## What you need to do

Plain-language instructions and decision codes.

## Coverage overview

Table: research need, required roles, found, currently selected, gap.

## Topic: <name>

### SRC_001, <short title>

- Citation:
- Source role:
- Related claims:
- Why it may be relevant:
- LLM summary:
- Summary basis: abstract
- Canonical signals:
- Recency signals:
- Access: Open Access / closed / unknown
- Limitations:
- Suggested action:

## Sources requiring library access
## Reserve candidates
## Known gaps
## Copyable response template
```

### 6.2. Zasady komunikatu

Komunikat orkiestratora musi:

- używać `output_language`,
- wyjaśnić cel bramki,
- wskazać dokładną ścieżkę lub link do dokumentu,
- opisać wszystkie decyzje prostym językiem,
- podać gotowy do skopiowania wzór odpowiedzi,
- poinformować, że zwykły język jest akceptowany,
- ostrzec o wykrytych lukach,
- po sparsowaniu pokazać podsumowanie przed finalnym zatwierdzeniem.

## 7. HumanSourceSelection

```yaml
HumanSourceSelection:
  schema_version: human_source_selection@1
  task_id:
  candidate_source_index_ref:

  status: approved

  approved_for_download: []
  keep_citation_only: []
  request_library_access: []
  keep_in_reserve: []

  excluded:
    - source_id:
      reason: null

  requested_search_extensions:
    - related_claim: null
      related_topic: null
      missing_source_role: null
      need:

  coverage_exceptions:
    - coverage_unit_id:
      accepted_by_human: true
      reason:

  human_notes: null
  final_confirmation: true
```

Statusy:

- `approved`,
- `needs_more_search`,
- `cancelled`.

## 8. HumanApprovedSourceSet

```yaml
HumanApprovedSourceSet:
  schema_version: human_approved_source_set@1
  task_id:
  source_selection_ref:
  approved_sources:
    - source_id:
      action: DOWNLOAD
      related_topics: []
      related_claims: []
      source_roles: []
  library_queue: []
  citation_only: []
  reserve: []
  excluded: []
  coverage_at_approval: []
  accepted_coverage_exceptions: []
```

Paper Retrieval przyjmuje ten artefakt. Nie przyjmuje surowego Candidate Source Index.

## 9. RetrievedCorpus

```yaml
RetrievedCorpus:
  schema_version: retrieved_corpus@1
  task_id:
  approved_source_set_ref:

  documents:
    - source_id:
      status: done
      local_ref:
      metadata_ref:
      resolved_from: unpaywall
      version_type: accepted_manuscript
      license: null
      content_type_valid: true
      pdf_header_valid: true

  unavailable:
    - source_id:
      status: unavailable
      reason:
      library_access_required: true

  failed:
    - source_id:
      status: failed
      reason:
      attempts:

  retrieval_summary:
```

Dozwolone źródła rozwiązania OA są konfigurowalne. Domyślna kolejność semantyczna:

1. Unpaywall,
2. OpenAlex OA locations,
3. arXiv,
4. CORE,
5. DOAB/OAPEN.

## 10. Paper Review i evidence cards

```yaml
PaperReview:
  schema_version: paper_review@1
  task_id:
  source_id:
  document_ref:

  review_scope:
    related_claims: []
    related_topics: []
    audience_level:

  contribution:
  methods:
  data_or_sample:
  findings:
  limitations:
  relevance_to_lecture:
  teaching_elements: []

  evidence_cards:
    - evidence_id: EV_001
      source_id:
      related_claims: []
      relation: supports
      evidence_summary:
      evidence_location:
        page: null
        section: null
        paragraph_or_table: null
      access_level: full_text
      method_context:
      limitations:
      extraction_confidence: high

  additional_targeted_review_needed: false
  targeted_review_request: null
```

Relacje dowodowe:

- `supports`,
- `contradicts`,
- `qualifies`,
- `contextualizes`,
- `method_only`,
- `unclear`.

Evidence summary jest parafrazą. Krótkie cytaty mogą być przechowywane tylko wtedy, gdy są
potrzebne i zgodne z ograniczeniami prawnoautorskimi.

## 11. Macierz pokrycia

Pokrycie jest procedurą kontrolną, a nie gwarancją kompletności całej literatury.

```yaml
CoverageRecord:
  coverage_unit_id: COV_CLM_001
  research_need_type: claim
  research_need_id: CLM_001
  priority: high

  required_source_roles:
    - foundational
    - current
    - qualifying_or_critical

  candidate_requirements:
    minimum_candidates: 3
    minimum_independent_author_groups: 2
    counterevidence_search_required: true

  candidates_found: []
  sources_selected: []
  evidence_verified: []

  status:
    candidate_coverage: complete
    selection_coverage: complete
    evidence_coverage: incomplete

  search_attempts: []
  gaps: []
  human_exception: null
```

### 11.1. Domyślne candidate coverage

| Research need | Minimum |
|---|---|
| Claim high | 3 kandydatów, co najmniej 2 niezależne grupy autorów |
| Claim medium | 2 kandydatów |
| Temat fundamentalny | 1 canonical anchor oraz 1 dostępny survey lub synthesis |
| Recent development | 2 źródła z zatwierdzonego recency window |
| Didactic example | 1 wiarygodne źródło dydaktyczne lub udokumentowany przykład |
| Claim kontrowersyjny | kandydaci reprezentujący konkurujące stanowiska |
| Flow issue | 1 źródło pojęciowe lub dydaktyczne |

Jedno źródło może wypełniać kilka coverage units. Zamknięty canonical anchor nie wypełnia
wymogu bezpośredniego dowodu pełnotekstowego.

### 11.2. Stop rule

Wyszukiwanie może zakończyć się, gdy:

- wszystkie obowiązkowe coverage units są complete albo jawnie unresolved,
- dla kluczowych komórek istnieje rezerwa, jeśli źródła są dostępne,
- dwa kolejne rozszerzenia nie dostarczyły nowego źródła wypełniającego lukę,
- użyto głównego indeksu i przynajmniej jednej drogi uzupełniającej,
- osiągnięto zatwierdzony limit kandydatów lub kosztu,
- reviewer nie wykrywa pominiętej luki dla claimu high.

Niespełniony wymóg jest dokumentowany wraz z zapytaniami. Agent nie deklaruje fałszywego
pokrycia.

### 11.3. Evidence coverage

Dla claimu high domyślnie wymagane są:

- co najmniej jeden bezpośredni dowód z odpowiedniego fragmentu tekstu,
- niezależne źródło uzupełniające, jeśli jest dostępne,
- próba znalezienia dowodu krytycznego lub kwalifikującego,
- jawne limitations i access level.

Claim kontrowersyjny wymaga przedstawienia konkurujących stanowisk. Brak wystarczających
dowodów prowadzi do `insufficient_evidence` lub `unresolved`.

## 12. ClaimAssessmentState

### `[KH-DECISION: CLAIM-ASSESSMENT-MODEL]`

KH powinien zatwierdzić zgodność poniższego modelu z kontraktami innych modułów.

```yaml
ClaimAssessment:
  claim_id: CLM_001
  original_text:

  evidence_status:
    value: supported
    allowed:
      - supported
      - mixed
      - unsupported
      - insufficient_evidence
    rationale:
    supporting_evidence: []
    contrary_evidence: []

  currency_status:
    value: needs_update
    allowed:
      - current
      - needs_update
      - obsolete
      - not_applicable
    rationale:

  pedagogical_status:
    value: needs_context
    allowed:
      - adequate
      - oversimplified
      - needs_context
      - misleading
      - not_applicable
    rationale:

  controversy_status:
    value: contested
    allowed:
      - settled
      - contested
      - unclear
    rationale:

  confidence:
    value: medium
    allowed:
      - high
      - medium
      - low
    rationale:

  recommended_action:
    value: qualify
    allowed:
      - retain
      - qualify
      - update
      - replace
      - remove
      - escalate
    rationale:

  evidence_coverage_ref:
  unresolved_questions: []
  lecture_implication:
```

Dotychczasowe pojedyncze statusy, takie jak `valid`, `obsolete` lub `too_simplified`, mogą być
wyliczane jako etykiety kompatybilności. Nie powinny zastępować wymiarów źródłowych.

## 13. ReviewDecision

```yaml
ReviewDecision:
  schema_version: review_decision@1
  review_id:
  task_id:
  logical_review_node:
  reviewer_agent: research-output-reviewer
  producer_agent:
  artifact_ref:
  review_profile:

  decision: APPROVED

  findings:
    - criterion_id:
      severity: medium
      location:
      explanation:
      required_correction:

  revision_scope: null

  root_cause: null
  allowed_root_causes:
    - producer_error
    - insufficient_evidence
    - invalid_or_incomplete_input
    - upstream_plan_error
    - review_profile_error
    - external_dependency_blocked

  confidence: high
  attempt:
```

Reviewer decision jest artefaktem w `produced[]`. Status envelope pozostaje jednym z `ok`,
`needs_input`, `degraded` lub `failed`.

## 14. Synteza

Research Synthesizer tworzy:

- `ResearchState`,
- `EvidenceMap`,
- `HumanResearchValidationPacket`,
- `SolutionInputCandidate`.

### 14.1. EvidenceMap

```yaml
EvidenceMap:
  schema_version: evidence_map@1
  claims:
    - claim_id:
      assessment_ref:
      evidence_cards: []
      source_ids: []
      evidence_coverage_ref:
      unresolved: false
```

### 14.2. HumanResearchValidationPacket

```yaml
HumanResearchValidationPacket:
  schema_version: human_research_validation_packet@1
  research_summary_ref:

  claim_summary:
    supported:
    mixed:
    unsupported:
    insufficient_evidence:
    needs_update:
    obsolete:
    unresolved:

  required_updates: []
  optional_improvements: []
  unresolved_questions: []
  accepted_source_coverage_exceptions: []

  required_human_decisions: []
```

## 15. HumanApprovedResearchBundle

```yaml
HumanApprovedResearchBundle:
  schema_version: human_approved_research_bundle@1
  approved_research_summary_ref:

  approved_update_findings:
    - finding_id:
      impact: UPDATE
      priority: high
      related_claims: []
      evidence_cards: []

  approved_optional_findings: []
  rejected_findings: []

  unresolved_claim_policy:
    action:
    require_user_confirmation_before_final: true

  solution_handoff:
    evidence_cards: []
    slide_impact_cards: []
    source_cards: []
    unresolved_claim_cards: []
```

Solution Graph otrzymuje kompaktowe karty. Pełny corpus, pełne PDF-y i verbose paper reviews
pozostają w artefaktach Research Graph.

## 16. Identyfikatory i wersjonowanie

Sugerowane prefiksy:

- `TOPIC_`,
- `SRC_`,
- `QUERY_`,
- `COV_`,
- `EV_`,
- `REV_`,
- `RF_`,
- `RD_` dla decyzji człowieka.

Kontrakty powinny używać major-version refs, na przykład `paper_review@1`. Zatwierdzone
artefakty są niezmienne. Korekta tworzy nową rewizję artefaktu, zachowując lineage.

## 17. Język pól i treści

- Nazwy pól, statusy, enumy i identyfikatory są po angielsku.
- Summary, rationale, explanation i komunikaty dla człowieka używają `output_language`.
- Domyślny `output_language` to `English`.
- Cytowania prezentowane człowiekowi mogą używać APA 7, ale identyfikatory DOI i metadane
  strukturalne są źródłem prawdy.

