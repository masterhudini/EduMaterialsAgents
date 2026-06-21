# Research Graph, projekty kontraktów i artefaktów

## 1. Status dokumentu

Poniższe struktury są kontraktami semantycznymi. KH i programista warstwy integracyjnej mogą
dostosować szczegóły serializacji, wersjonowania i artifact paths, zachowując znaczenie pól i
granice odpowiedzialności.

Każdy izolowany agent zwraca uniwersalny `envelope@1`. Artefakty opisane poniżej znajdują się
w `produced[]` koperty.

## 2. Wejście całego modułu

### `[RESOLVED: RESEARCH-GRAPH-INPUT-CONTRACT]`

Kontrakt został zatwierdzony i wdrożony. Wykonywalnym źródłem prawdy jest
`shared/contracts/research_graph_input.schema.json`; poniższy zapis opisuje semantyczny zakres
danych konsumowanych przez Research Graph.

```yaml
ResearchGraphInput:
  schema_version: research_graph_input@1
  task_id: RESEARCH_001

  user_approved_context:
    course_name: Bayesian Statistics
    audience_level: master
    target_duration_minutes: 90
    teaching_goal: refresh and improve logical flow

  approved_domains:
    - domain_id: D1
      label: Bayesian statistics
    - domain_id: D2
      label: probabilistic programming

  approved_research_scope:
    verify_claims:
      priority: [high, medium]
    include_recent_developments: true
    include_canonical_sources: true
    include_didactic_examples: true
    recency_window_years: 5

  research_drivers:
    - driver_id: DRV_001
      driver_type: claim
      priority: high
      purpose: Qualify the computational-cost claim.
      related_claims: [CLM_001]
      related_concepts: [C1]
      related_flow_issues: []
      related_update_needs: []

  claim_cards:
    - claim_id: CLM_001
      text: Bayesian methods are computationally expensive for large-scale problems.
      type: methodological
      verification_need: high
      artifact_ref: artifact://states/claim_state.approved.json#/claims/CLM_001

  concept_context_cards:
    - concept_id: C1
      label: Posterior distribution
      role: core_concept

  selected_flow_issue_cards:
    - issue_id: F_001
      severity: high
      summary: Posterior is used before likelihood is explained.

  selected_update_need_cards: []
  existing_source_cards:
    - source_id: EXISTING_001
      label: Existing course textbook
      artifact_ref: null

  constraints:
    max_topics: 6
    candidate_limit_per_topic: 24
    no_new_coverage_passes: 2
    allowed_languages: [en]
    allowed_work_types: [article, review, book, chapter, preprint]
    year_from: null
    year_to: null

  selection_profile:
    candidate_pool_target_per_topic: 16
    minimum_sources_per_required_role: 1
    open_access_preference: preferred

  locked_sections:
    - section_id: S1
      reason: Author wants to keep the opening narrative.

  artifact_refs_for_lazy_hydration:
    claim_state_ref: artifact://states/claim_state.approved.json
    concept_state_ref: artifact://states/concept_state.approved.json
    flow_state_ref: artifact://states/flow_state.approved.json

  output_language: English
```

### 2.1. Walidacja sensu wejścia

Research Graph może rozpocząć pracę, gdy:

- kontekst wykładu jest zatwierdzony,
- istnieje przynajmniej jedna zatwierdzona domena,
- istnieje co najmniej jeden research driver,
- priorytety i access policy są znane,
- output language jest określony; upstream materializuje `English`, jeżeli użytkownik nie wybrał
  innego języka,
- zablokowane sekcje są jawne, nawet jeśli lista jest pusta.

Brak claimów nie blokuje modułu, jeśli istnieje zatwierdzona potrzeba aktualizacji, problem
pojęciowy albo flow issue. Ogólny opis dziedziny bez research driver prowadzi do `needs_input`.

## 3. ResearchPlan

Wykonywalnym źródłem prawdy jest `shared/contracts/research_plan.schema.json`. Planner otrzymuje
wyłącznie `research_planner_input@1`, przygotowane deterministycznie z kontraktu granicznego.

```yaml
ResearchPlan:
  schema_version: research_plan@1
  artifact_version: 1.0.0
  task_id: RESEARCH_001
  topics:
    - topic_id: TOPIC_001
      name:
      purpose:
      priority:
      linked_driver_ids: []
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

      coverage_requirements:
        - coverage_id: COV_001
          description:
          source_roles: []
          minimum_sources: 1
          mandatory: true
      stop_rule:
        candidate_limit:
        no_new_coverage_passes: 2
        complementary_search_route_required: true

  uncovered_driver_ids: []
  input_issues: []
  global_constraints: {}
  output_language: English
  review_profile_ref: research_plan
```

Każdy topic musi być powiązany z zatwierdzonym research driver. Wszystkie drivery muszą znaleźć
się w topicach albo w jawnej liście `uncovered_driver_ids` wraz z `input_issues`. Planner nie może
tworzyć topic wyłącznie dlatego, że wydaje się interesujący. Moduł
`shared/scripts/g02/planner.py` sprawdza strukturę, proweniencję ID, limity, zachowanie zakresu i
minimalność rewizji, zapisuje artefakt oraz buduje profil `research_plan` dla reviewera.

### 3.1. Wejście i wyjście G02-A02

Wykonywalnymi źródłami prawdy są `shared/contracts/domain_research_input.schema.json` oraz
`shared/contracts/domain_candidate_sources.schema.json`. Jedno uruchomienie Domain dotyczy
wyłącznie jednego zatwierdzonego topic.

```yaml
DomainResearchInput:
  schema_version: domain_research_input@1
  task_id:
  research_plan_ref:
  research_plan_artifact_version:
  topic: {}
  provider_capabilities:
    - provider: openalex | semantic_scholar | arxiv
      enabled: true
      ready: true
      authentication: none | optional_key | required_key_missing | configured_key
  output_language:

DomainCandidateSources:
  schema_version: domain_candidate_sources@1
  artifact_version:
  task_id:
  topic_id:
  research_plan_ref:
  query_plan: {}
  candidates: []
  query_log: []
  coverage_map: []
  stop_reason: completed | candidate_limit | saturation | provider_unavailable | partial_coverage
  remaining_coverage_units: []
  provider_issues:
    - operation_id:
      provider:
      status: partial | unavailable | failed
      issues: []
  review_profile_ref: domain_candidates
```

`query_log` przechowuje `artifact://` ref do każdego `literature_tool_result@1`. Finalizator
sprawdza zgodność identity, planu zapytań, logu, rekordów providerów, coverage i stop reason.
Kandydat musi być identyczny z rekordem z deterministycznego narzędzia. Semantyczne mapowanie do
coverage pozostaje osobnym polem i może opierać się wyłącznie na metadata, title lub abstract.
Coverage unit pozostaje na liście braków do chwili osiągnięcia `minimum_sources`. `provider_issues`
jest dokładną projekcją wszystkich wyników narzędzi o statusie innym niż `ok`.

### 3.2. QueryPlan

`query_plan@1` oddziela decyzję agenta od wykonania providerów. Każda trasa zachowuje zatwierdzone
terminy źródłowe, jawnie oznacza terminy wygenerowane, mapuje coverage oraz ogranicza listę
providerów, filtry i limit. Każdy termin wygenerowany ma dokładnie jeden wpis
`generated_term_bases`, który wskazuje terminy źródłowe użyte w trasie, dokładną zatwierdzoną
`allowed_expansion_areas` i relację semantyczną. Walidator odrzuca brakującą, nadmiarową,
zduplikowaną albo wykraczającą poza zatwierdzony topic podstawę. Wymagane są trasy core,
complementary, a przy odpowiedniej roli także qualifying_or_critical. Wykonywalnym źródłem prawdy jest
`shared/contracts/query_plan.schema.json` wraz z `shared/scripts/g02/query_planning.py`.

## 4. Rekord źródła

```yaml
SourceRecord:
  schema_version: source_record@1
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
    provider_record_ids: {}
    retrieved_at: null
    query_ids: []
    raw_response_refs: []
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

### 4.3. Kontrakt deterministycznej operacji literaturowej

Agenci i skille nie konsumują bezpośrednio różnych formatów OpenAlex, Semantic Scholar, arXiv,
Unpaywall ani pozostałych dostawców. Adapter mapuje je do wspólnej odpowiedzi:

```yaml
LiteratureToolResult:
  schema_version: literature_tool_result@1
  operation_id:
  operation_type: metadata_search | citation_expand | oa_resolve | retrieve | validate | text_index
  provider:
  status: ok | partial | unavailable | failed
  started_at:
  completed_at:

  request:
    route_id:
    query_id: null
    canonical_query: null
    filters: {}
    cursor: null
    limit:

  records: []
  file_descriptors: []

  pagination:
    next_cursor: null
    exhausted: false
    pages_processed: 0

  provenance:
    raw_response_refs: []
    provider_request_ids: []
    cache_hit: false
    config_profile:

  issues:
    - code:
      retryable: false
      message:
```

Wynik `partial` oznacza użyteczny rezultat z jawnym brakiem, na przykład niedostępnością jednej
strony wyników, jednego dostawcy albo brakiem możliwości zagwarantowania filtra języka przez dany
indeks. Adapter nie tworzy brakujących rekordów, nie ocenia
relewantności i nie podejmuje decyzji wyboru źródeł. Te czynności należą do agentów.

Klucze API i dane uwierzytelniające nie występują w artefakcie. Warstwa narzędzi odczytuje je z
konfiguracji runtime, a do logu trafia wyłącznie nazwa użytego profilu konfiguracji.
Wykonywalnymi źródłami prawdy są `shared/contracts/source_record.schema.json`,
`shared/contracts/literature_tool_result.schema.json` oraz `shared/scripts/g02/providers.py`.

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

### `[TK-DECISION: CLAIM-ASSESSMENT-MODEL]`

TK powinien zatwierdzić poniższy model podczas przeglądu 1b1 G02-A08 Claim Verification Agent i
`g02-a08-assess-claim-evidence`.

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

## 13. ReviewTask i ReviewDecision

### 13.1. ReviewTask

Każde wywołanie uniwersalnego reviewera otrzymuje jeden `review_task@1`. Kontrakt zawiera:

- identyfikatory review, zadania, logical review node i producenta,
- numer próby i identyfikator profilu,
- oryginalne zadanie oraz ograniczony input autoryzowany dla producenta,
- dokładnie jeden deskryptor artefaktu z `type`, `ref`, `schema_version` i
  `artifact_version`,
- expected output contract, obserwowalne acceptance criteria, evidence requirements,
  prohibited behaviors i severity rules,
- opcjonalny `previous_decision_ref` i odpowiedź producenta na poprzednie findings.

Kryterium acceptance ma `criterion_id`, opis i flagę `mandatory`. Evidence requirement ma
analogiczny stabilny identyfikator, opis i flagę `mandatory`. Severity rules jawnie definiują
znaczenie `minor`, `major` i `blocker` dla danego wywołania.

Reviewer nie przyjmuje tablicy artefaktów. Niezależne artefakty wymagają niezależnych zadań.
`review_id` pozostaje stabilny w jednym strumieniu review, a `attempt` zwiększa się przy każdej
kolejnej ocenie poprawionego artefaktu. `previous_decision_ref` wskazuje bezpośrednio poprzednią
próbę. Finding z poprzedniej decyzji musi zachować ID albo pojawić się w
`closed_finding_ids`.

### 13.2. ReviewDecision

```yaml
ReviewDecision:
  schema_version: review_decision@1
  review_id:
  task_id:
  logical_review_node:
  reviewer_agent: g02-a10-output-reviewer
  producer_agent:
  artifact_ref:
  artifact_version:
  review_profile:

  decision: APPROVED

  findings:
    - finding_id:
      criterion_id:
      severity: major
      location:
      observed:
      required_correction:
      evidence_refs: []

  closed_finding_ids: []

  revision_scope:
    target_agent:
    finding_ids: []
    notes:

  root_cause: null
  confidence: high
  attempt:
  summary:
```

Dozwolone root causes to `producer_error`, `insufficient_evidence`,
`invalid_or_incomplete_input`, `upstream_plan_error`, `review_profile_error` i
`external_dependency_blocked`.

Reguły spójności:

- `APPROVED` ma pustą listę findings oraz null w `root_cause` i `revision_scope`,
- `REVISE` ma findings `minor` lub `major`, root cause `producer_error` albo
  `insufficient_evidence` oraz revision scope należący do producenta,
- `BLOCKED` ma co najmniej jeden finding `blocker` oraz root cause
  `invalid_or_incomplete_input`, `upstream_plan_error`, `review_profile_error` albo
  `external_dependency_blocked`,
- findings dotyczące artefaktu wskazują kryterium przekazane w `ReviewTask`,
- błędy samego review używają wyłącznie zarezerwowanych criterion IDs `REVIEW_BASIS`,
  `ARTIFACT_ACCESS` i `EXTERNAL_DEPENDENCY`.

Reviewer decision jest artefaktem w `envelope@1.produced[]`. Pole `path` deskryptora zawiera
URI `artifact://`, a `schema_version` ma wartość `review_decision@1`. Status envelope pozostaje
jednym z `ok`, `needs_input`, `degraded` lub `failed`. Zakończone wykonanie reviewera zwraca
envelope `ok` również dla decyzji `REVISE` i `BLOCKED`.

## 14. Synteza

G02-A09 Synthesizer tworzy:

- `ResearchState`,
- `EvidenceMap`,
- `UserResearchValidationPacket`,
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

### 14.2. UserResearchValidationPacket

```yaml
UserResearchValidationPacket:
  schema_version: user_research_validation_packet@1
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

## 15. UserApprovedResearchBundle

```yaml
UserApprovedResearchBundle:
  schema_version: user_approved_research_bundle@1
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

