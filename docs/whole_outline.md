Projekt systemu agentowego do odświeżania materiałów wykładowych

Wersja robocza: v6 — pełny projekt: 3 subgrafy, review-loopy, user gates, kontrakty wejścia

0. Cel systemu

System ma wspierać prowadzących akademickich w odświeżaniu prezentacji wykładowych.

Użytkownik wrzuca prezentację w PDF. System:

rozumie strukturę i sens istniejącego wykładu,
identyfikuje claimy, pojęcia, luki logiczne i problemy dydaktyczne,
prowadzi ukierunkowany research naukowy,
weryfikuje claimy i aktualność materiału,
projektuje nową wersję wykładu,
oznacza slajdy statusem zmiany,
przygotowuje paczkę gotową do użycia w Gamma, NotebookLM, GPT Pro albo innym generatorze slajdów.

System nie ma przebudowywać wszystkiego. Ma działać selektywnie.

1. Główna architektura

System składa się z trzech subgrafów:

flowchart TD
    A[PDF Upload] --> G1[Intake / Understanding Graph]
    G1 --> H1[User Intake Gate]

    H1 -->|approved handoff only| G2[Research Graph]
    H1 -->|needs correction| G1

    G2 --> H2[User Research Gate]

    H2 -->|approved handoff only| G3[Solution Design Graph]
    H2 -->|needs correction| G2

    G3 --> H3[User Change Plan Gate]
    H3 -->|approved| G3B[Detailed Slide Design]
    H3 -->|needs correction| G3

    G3B --> H4[Final User Review Gate]
    H4 -->|approved| OUT[Export Package]
    H4 -->|needs correction| G3B
1.1 Trzy subgrafy
Subgraf	Cel	Produkt
1. Intake / Understanding Graph	Zrozumieć istniejącą prezentację	UserApprovedIntakeBundle
2. Research Graph	Zweryfikować claimy i znaleźć aktualną literaturę	UserApprovedResearchBundle
3. Solution Design Graph	Zaprojektować nową wersję wykładu	FinalLecturePackage
2. Kluczowa zasada przepływu stanu

Z grafu do grafu nie przechodzi cały stan.

System działa przez:

central artifact store
        +
typed handoff bundles
        +
compact cards
        +
lazy hydration po referencjach

Czyli:

flowchart TD
    A[Raw PDF, slide images, OCR, full paper PDFs] --> STORE[Central Artifact Store]

    STORE --> B1[Intake Graph uses scoped views]
    STORE --> B2[Research Graph uses compact cards + refs]
    STORE --> B3[Solution Graph uses approved recommendations + refs]

    B1 --> C1[UserApprovedIntakeBundle]
    C1 --> B2

    B2 --> C2[UserApprovedResearchBundle]
    C2 --> B3
2.1 Co to oznacza praktycznie

Research Graph nie dostaje całej prezentacji. Dostaje tylko:

zatwierdzone domeny,
claimy do weryfikacji,
compact claim cards,
concept context cards,
selected flow issue cards,
locked sections,
artifact refs do ewentualnego dociągania szczegółów.

Solution Graph nie dostaje całego research corpus. Dostaje tylko:

zatwierdzone findings,
evidence cards,
slide impact map,
constraints od użytkownika,
inventory slajdów,
referencje do źródeł.
3. Standardowy model kontraktów
3.1 AgentDefinition

To jest stała definicja agenta. Nie jest stanem.

AgentDefinition:
  agent_id: "ExampleAgent"
  graph: "IntakeGraph"

  responsibility:
    - "What this agent owns"

  non_responsibilities:
    - "What this agent must not do"

  guardrails:
    - "Stable behavioral boundaries"

  input_contract: "ExampleInputBundle"
  output_contract: "ExampleState"

  revision_policy:
    retry_scope: "deck | section | per_slide | per_claim | artifact | handoff_bundle"
    complexity_class: "semantic_high_ambiguity"
    max_revision_attempts:
      low: 1
      medium: 2
      high: 3
      critical: 3
    escalation_after_exhaustion: "orchestrator_or_user_gate"
3.2 InputBundle

To jest dane wejściowe konkretnego uruchomienia.

InputBundle:
  task_id: "TASK_001"

  artifact_refs:
    some_ref: "artifact://..."

  hydrated_payload:
    small_context_slice: {}

  task_context:
    user_context: {}
    run_parameters: {}

  output_contract:
    artifact: "ExpectedArtifact"
3.3 ReviewResult

Reviewer nie przechowuje retry policy. Reviewer zgłasza problem, severity i scope poprawki.

ReviewResult:
  review_id: "REV_001"
  target_agent_id: "ExampleAgent"
  target_artifact: "ExampleState"

  verdict: "REVISE" # APPROVED | APPROVED_WITH_WARNINGS | REVISE | BLOCKED

  issues:
    - issue_id: "ISS_001"
      severity: "high"
      revision_scope:
        type: "per_slide"
        slide_id: 12
      problem: "..."
      required_fix: "..."

  routing:
    return_to_agent: "ExampleAgent"
3.4 OrchestratorRevisionDecision

Retry liczy orkiestrator na podstawie definicji agenta i historii prób.

OrchestratorRevisionDecision:
  target_agent_id: "ExampleAgent"
  issue_id: "ISS_001"
  severity: "high"
  retry_scope:
    type: "per_slide"
    slide_id: 12

  max_revision_attempts_for_scope: 2
  current_attempts_for_scope: 1

  decision: "RETRY_ALLOWED"
4. Ogólna retry matrix

Retry zależy od:

complexity_class agenta,
severity issue z review,
retry_scope.
Complexity class	Low	Medium	High	Critical	Przykład
deterministic_technical	0	1	2	3	PDF Intake, Export Integrity
bounded_structural	0	1	2	3	Slide Structure
bounded_interpretive	0	1	2	2	Slide Debt
semantic_high_ambiguity	1	2	3	3	Semantic Understanding
pedagogical_high_ambiguity	0	2	2	3	Difficulty
logic_high_ambiguity	1	2	3	3	Logical Flow
claim_high_impact	1	2	3	3	Claim Extraction
research_planning	0	2	3	3	G02-A01 Planner
evidence_high_impact	1	2	3	3	G02-A08 Claim Verification
synthesis_decision	0	1	2	3	Synthesizers
cross_artifact_reconciliation	0	2	3	3	Cross-Agent Reviewer
creative_design	0	2	3	3	New Slide Designer
structural_design	0	2	3	3	Merge/Split/Reorder
4.1 Interpretacja
low = 0 — zwykle nie cofamy do agenta, zapisujemy warning.
medium = 1–2 — cofamy, jeśli wpływa na jakość handoffu.
high = 2–3 — cofamy prawie zawsze.
critical = 3 — próbujemy naprawić, potem eskalacja.
5. Statusy slajdów

W Solution Design każdy slajd może dostać status:

Status	Znaczenie
KEEP	Slajd zostaje bez zmian.
UPDATE	Slajd zostaje, ale jego treść wymaga aktualizacji.
REMOVE	Slajd powinien zostać usunięty.
ADD	Należy dodać nowy slajd.
MERGE	Należy połączyć dwa lub więcej slajdów.
SPLIT	Jeden slajd należy rozbić na kilka prostszych slajdów.
REORDER	Slajd zostaje, ale powinien zmienić pozycję.
6. Subgraf 1: Intake / Understanding Graph
6.1 Cel

Zrozumieć istniejącą prezentację:

struktura,
sekcje,
pojęcia,
relacje,
claimy,
trudność,
flow logiczny,
problemy wizualne,
elementy wymagające decyzji człowieka.
6.2 Kontrakt wejścia do subgrafu
IntakeGraphInput:
  task_id: "INTAKE_001"

  upload:
    pdf_file_ref: "artifact://uploads/original.pdf"
    filename: "lecture.pdf"
    mime_type: "application/pdf"
    file_size_bytes: 12345678
    upload_id: "UPL_001"

  user_provided_context:
    title_hint: null
    course_hint: null
    audience_hint: null
    language_hint: null
    target_duration_hint: null

  ingestion_profile:
    extract_text: true
    render_slide_images: true
    extract_assets: true
    ocr_policy: "only_if_text_missing"
    keep_original_order: true

  output_contract:
    artifact: "UserApprovedIntakeBundle"
6.3 Czego Intake Graph nie dostaje
researchu,
poprzednich źródeł naukowych,
gotowego planu zmian,
sugestii, które slajdy naprawiać,
zewnętrznej literatury,
solution constraints poza tym, co podał użytkownik.
6.4 Graf Intake
flowchart TD
    A[IntakeGraphInput: PDF Upload] --> B[PDF Intake Agent]

    B --> R0[Extraction Integrity Reviewer]
    R0 -->|REVISE via PDFIntake policy| B
    R0 -->|BLOCKED| HT[Technical User / Orchestrator Gate]
    R0 -->|APPROVED| V0[Typed Slide Views]

    V0 --> C1[Slide Structure Agent]
    V0 --> C2[Semantic Understanding Agent]
    V0 --> C3[Visual / Slide Debt Agent]

    C1 --> R1[Structure Reviewer]
    C2 --> R2[Semantic Graph Reviewer]
    C3 --> R3[Slide Debt Reviewer]

    R1 -->|REVISE via Structure policy| C1
    R2 -->|REVISE via Semantic policy| C2
    R3 -->|REVISE via SlideDebt policy| C3

    R1 -->|APPROVED| W1[Reviewed Base Understanding]
    R2 -->|APPROVED| W1
    R3 -->|APPROVED| W1

    W1 --> C4[Pedagogical Difficulty Agent]
    W1 --> C5[Logical Flow Agent]
    W1 --> C6[Claim Extraction Agent]

    C4 --> R4[Difficulty Reviewer]
    C5 --> R5[Flow Reviewer]
    C6 --> R6[Claim Extraction Reviewer]

    R4 -->|REVISE via Difficulty policy| C4
    R5 -->|REVISE via Flow policy| C5
    R6 -->|REVISE via Claim policy| C6

    R4 -->|APPROVED| XR[Cross-Agent Reconciliation Reviewer]
    R5 -->|APPROVED| XR
    R6 -->|APPROVED| XR
    W1 --> XR

    XR -->|REVISE routed| C1
    XR -->|REVISE routed| C2
    XR -->|REVISE routed| C3
    XR -->|REVISE routed| C4
    XR -->|REVISE routed| C5
    XR -->|REVISE routed| C6

    XR -->|APPROVED| S[Intake Synthesizer Agent]

    S --> RS[Intake Synthesis Reviewer]
    RS -->|REVISE via Synthesizer policy| S
    RS -->|APPROVED| H1[User Intake Gate]

    H1 -->|APPROVED| O[UserApprovedIntakeBundle]
    H1 -->|NEEDS_CORRECTION| S
6.5 Typed Slide Views

Po PDF Intake system tworzy widoki robocze. Agenci nie dostają raw PDF ani całego manifestu, tylko odpowiednie view.

SlideOrderView
SlideOrderView:
  slide_count: 42
  slide_ids: [1, 2, 3, 4]
  source_order_preserved: true
SlideTextView
SlideTextView:
  slides:
    - slide_id: 1
      title_candidate: "Introduction"
      text_blocks:
        - block_id: "B1"
          text: "..."
          role_hint: "title"
        - block_id: "B2"
          text: "..."
          role_hint: "body"
      text_quality:
        ocr_used: false
        confidence: 0.94
SlideLayoutView
SlideLayoutView:
  slides:
    - slide_id: 1
      layout_type_hint: "title_and_content"
      block_count: 4
      bullet_count: 5
      has_table: false
      has_chart: true
      has_formula: false
SlideVisualView
SlideVisualView:
  slides:
    - slide_id: 1
      thumbnail_ref: "artifact://slides/001_thumb.png"
      image_ref: "artifact://slides/001.png"
      detected_visuals:
        - type: "chart"
          asset_ref: "artifact://assets/001_chart_01.png"
SlideSemanticView
SlideSemanticView:
  slides:
    - slide_id: 1
      title_candidate: "..."
      normalized_text: "..."
      visual_caption_candidates:
        - "Line chart comparing model accuracy over time"
      formula_text_candidates: []
6.6 Agenci Intake — definicje i wejścia
PDF Intake Agent
AgentDefinition
agent_definition:
  agent_id: "PDFIntakeAgent"
  graph: "IntakeGraph"
  complexity_class: "deterministic_technical"

  responsibility:
    - "Convert uploaded PDF into technical slide corpus"
    - "Extract slide images, text, layout and assets"
    - "Preserve original slide order"

  non_responsibilities:
    - "Do not interpret academic meaning"
    - "Do not classify domain"
    - "Do not judge slide quality"
    - "Do not propose changes"

  guardrails:
    - "Every slide must have stable slide_id"
    - "Every slide must have image_ref"
    - "Missing text must be explicitly marked for OCR"
    - "Original order must be preserved"

  revision_policy:
    retry_scope: "deck"
    max_revision_attempts:
      low: 0
      medium: 1
      high: 2
      critical: 3
    escalation_after_exhaustion: "technical_orchestrator_gate"

  input_contract: "PDFIntakeInputBundle"
  output_contract: "SlideCorpusManifest"
InputBundle
PDFIntakeInputBundle:
  task_id: "TASK_INTAKE_001"

  upload:
    pdf_file_ref: "artifact://uploads/original.pdf"
    filename: "lecture.pdf"
    mime_type: "application/pdf"
    file_size_bytes: 12345678
    upload_id: "UPL_001"

  user_provided_context:
    title_hint: null
    course_hint: null
    audience_hint: null
    language_hint: null

  ingestion_config:
    extract_text: true
    render_slide_images: true
    extract_assets: true
    ocr_policy: "only_if_text_missing"
    keep_original_order: true

  output_contract:
    artifact: "SlideCorpusManifest"
Slide Structure Agent
AgentDefinition
agent_definition:
  agent_id: "SlideStructureAgent"
  graph: "IntakeGraph"
  complexity_class: "bounded_structural"

  responsibility:
    - "Detect presentation sections"
    - "Assign slide types"
    - "Map slides to structural roles"

  non_responsibilities:
    - "Do not build concept graph"
    - "Do not extract claims"
    - "Do not verify factual correctness"
    - "Do not propose slide updates"

  guardrails:
    - "Every slide must be assigned to a section or explicitly marked as orphan"
    - "Every slide must receive slide_type"
    - "Section continuity must be preserved unless explicitly flagged"
    - "Do not infer domain from keywords only"

  revision_policy:
    retry_scope: "artifact"
    max_revision_attempts:
      low: 0
      medium: 1
      high: 2
      critical: 3
    escalation_after_exhaustion: "orchestrator_review"

  input_contract: "SlideStructureInputBundle"
  output_contract: "StructureState"
InputBundle
SlideStructureInputBundle:
  task_id: "TASK_STRUCTURE_001"

  artifact_refs:
    slide_order_view_ref: "artifact://views/slide_order.json"
    slide_text_view_ref: "artifact://views/slide_text.json"
    slide_layout_view_ref: "artifact://views/slide_layout.json"

  hydrated_payload:
    slide_index:
      - slide_id: 1
        title_candidate: "..."
        text_excerpt: "..."
        layout_type_hint: "title"
      - slide_id: 2
        title_candidate: "Agenda"
        text_excerpt: "..."

  task_context:
    user_title_hint: null
    course_hint: null

  output_contract:
    artifact: "StructureState"
Semantic Understanding Agent
AgentDefinition
agent_definition:
  agent_id: "SemanticUnderstandingAgent"
  graph: "IntakeGraph"
  complexity_class: "semantic_high_ambiguity"

  responsibility:
    - "Build concept graph"
    - "Detect central and supporting concepts"
    - "Infer domains from concepts and relations"
    - "Detect prerequisites and undefined concepts"

  non_responsibilities:
    - "Do not verify claims against literature"
    - "Do not rewrite slides"
    - "Do not produce change plan"
    - "Do not treat SlideStructureState as ground truth during first pass"

  guardrails:
    - "Every concept must have slide references"
    - "Every relation must have evidence references"
    - "Domain inference must be concept-based, not keyword-only"
    - "Mark uncertainty explicitly"
    - "Flag concepts used before explanation"

  revision_policy:
    retry_scope: "deck"
    max_revision_attempts:
      low: 1
      medium: 2
      high: 3
      critical: 3
    escalation_after_exhaustion: "orchestrator_or_user_semantic_gate"

  input_contract: "SemanticUnderstandingInputBundle"
  output_contract: "ConceptState"
InputBundle
SemanticUnderstandingInputBundle:
  task_id: "TASK_SEMANTIC_001"

  artifact_refs:
    slide_semantic_view_ref: "artifact://views/slide_semantic.json"
    slide_visual_view_ref: "artifact://views/slide_visual.json"

  hydrated_payload:
    slides:
      - slide_id: 1
        title_candidate: "..."
        normalized_text: "..."
        visual_caption_candidates: []
      - slide_id: 2
        title_candidate: "..."
        normalized_text: "..."

  task_context:
    user_course_hint: null
    user_audience_hint: null

  output_contract:
    artifact: "ConceptState"
Visual / Slide Debt Agent
AgentDefinition
agent_definition:
  agent_id: "SlideDebtAgent"
  graph: "IntakeGraph"
  complexity_class: "bounded_interpretive"

  responsibility:
    - "Evaluate visual and didactic debt"
    - "Detect text overload"
    - "Detect visual clarity problems"
    - "Identify student comprehension risks caused by slide form"

  non_responsibilities:
    - "Do not judge domain correctness"
    - "Do not verify claims"
    - "Do not propose research updates"
    - "Do not rewrite slide content"

  guardrails:
    - "Every issue must have slide_id"
    - "Every issue must have severity"
    - "Separate visual issue from content issue"
    - "Every issue should include likely_student_risk where possible"

  revision_policy:
    retry_scope: "per_slide"
    max_revision_attempts:
      low: 0
      medium: 1
      high: 2
      critical: 2
    escalation_after_exhaustion: "approve_with_warning_or_orchestrator"

  input_contract: "SlideDebtInputBundle"
  output_contract: "SlideDebtState"
InputBundle
SlideDebtInputBundle:
  task_id: "TASK_SLIDE_DEBT_001"

  artifact_refs:
    slide_visual_view_ref: "artifact://views/slide_visual.json"
    slide_layout_view_ref: "artifact://views/slide_layout.json"
    slide_text_view_ref: "artifact://views/slide_text.json"

  hydrated_payload:
    slides:
      - slide_id: 1
        thumbnail_ref: "artifact://slides/001_thumb.png"
        layout_type_hint: "title_and_content"
        bullet_count: 7
        block_count: 5
        has_chart: true
        has_table: false
        text_excerpt: "..."

  task_context:
    audience_hint: null
    delivery_mode_hint: "lecture"

  output_contract:
    artifact: "SlideDebtState"
Pedagogical Difficulty Agent
AgentDefinition
agent_definition:
  agent_id: "PedagogicalDifficultyAgent"
  graph: "IntakeGraph"
  complexity_class: "pedagogical_high_ambiguity"

  responsibility:
    - "Assess academic and didactic difficulty"
    - "Estimate concept density"
    - "Estimate prerequisite load"
    - "Identify difficulty jumps"
    - "Assign Bloom level where useful"

  non_responsibilities:
    - "Do not verify factual correctness"
    - "Do not search literature"
    - "Do not propose content updates"
    - "Do not reduce difficulty assessment to word count"

  guardrails:
    - "Difficulty must not be based on word count only"
    - "Use concept density and prerequisite load"
    - "Audience assumptions must be explicit"
    - "Every high-risk slide must have reasons"

  revision_policy:
    retry_scope: "per_section_or_slide"
    max_revision_attempts:
      low: 0
      medium: 2
      high: 2
      critical: 3
    escalation_after_exhaustion: "orchestrator_or_user_audience_gate"

  input_contract: "PedagogicalDifficultyInputBundle"
  output_contract: "DifficultyState"
InputBundle
PedagogicalDifficultyInputBundle:
  task_id: "TASK_DIFFICULTY_001"

  artifact_refs:
    concept_state_ref: "artifact://states/concept_state.approved.json"
    structure_state_ref: "artifact://states/structure_state.approved.json"
    slide_debt_state_ref: "artifact://states/slide_debt_state.approved.json"
    slide_semantic_view_ref: "artifact://views/slide_semantic.json"
    slide_layout_view_ref: "artifact://views/slide_layout.json"

  hydrated_payload:
    per_slide_summary:
      - slide_id: 8
        section_id: S2
        concepts_introduced: [C4, C5, C6]
        prerequisite_concepts: [C1, C2]
        formula_count: 2
        has_dense_visual: true
        text_density_hint: "high"

  task_context:
    audience_level: null
    assumed_level_if_missing: "undergraduate"
    assumption_confidence: "low"

  output_contract:
    artifact: "DifficultyState"
Logical Flow Agent
AgentDefinition
agent_definition:
  agent_id: "LogicalFlowAgent"
  graph: "IntakeGraph"
  complexity_class: "logic_high_ambiguity"

  responsibility:
    - "Assess internal logical flow"
    - "Detect missing definitions before use"
    - "Detect broken prerequisite order"
    - "Detect repetition and misplaced examples"
    - "Suggest structural fix hints"

  non_responsibilities:
    - "Do not use external literature"
    - "Do not rewrite slides"
    - "Do not produce final change plan"
    - "Do not verify factual correctness"

  guardrails:
    - "Evaluate internal logic only"
    - "Every flow issue must reference slide_ids"
    - "Fix hints must be structural, not full solution"
    - "Severity is required for every issue"

  revision_policy:
    retry_scope: "deck_or_section"
    max_revision_attempts:
      low: 1
      medium: 2
      high: 3
      critical: 3
    escalation_after_exhaustion: "orchestrator_or_user_logic_gate"

  input_contract: "LogicalFlowInputBundle"
  output_contract: "FlowState"
InputBundle
LogicalFlowInputBundle:
  task_id: "TASK_FLOW_001"

  artifact_refs:
    structure_state_ref: "artifact://states/structure_state.approved.json"
    concept_state_ref: "artifact://states/concept_state.approved.json"
    slide_order_view_ref: "artifact://views/slide_order.json"
    slide_semantic_view_ref: "artifact://views/slide_semantic.json"

  hydrated_payload:
    narrative_units:
      - slide_id: 5
        section_id: S2
        title: "Prior distribution"
        concepts: [C1]
        introduced_concepts: [C1]
        referenced_concepts: []
      - slide_id: 6
        section_id: S2
        title: "Posterior distribution"
        concepts: [C2]
        introduced_concepts: [C2]
        referenced_concepts: [C1]

  task_context:
    allowed_fix_hint_types:
      - "ADD_BRIDGE"
      - "REORDER"
      - "SPLIT"
      - "MERGE"
      - "CLARIFY"
      - "REMOVE_DUPLICATE"

  output_contract:
    artifact: "FlowState"
Claim Extraction Agent
AgentDefinition
agent_definition:
  agent_id: "ClaimExtractionAgent"
  graph: "IntakeGraph"
  complexity_class: "claim_high_impact"

  responsibility:
    - "Extract verifiable claims"
    - "Classify claim type"
    - "Assign verification need"
    - "Map claims to slide spans and concepts"

  non_responsibilities:
    - "Do not verify claims"
    - "Do not search literature"
    - "Do not rewrite claims"
    - "Do not produce research plan"

  guardrails:
    - "Every claim must have slide_id"
    - "Every claim must have source_span_id"
    - "Every claim must be specific"
    - "Every empirical/methodological/state-of-the-art claim must have verification_need"
    - "Do not extract plain headings as claims"

  revision_policy:
    retry_scope: "per_claim_or_slide"
    max_revision_attempts:
      low: 1
      medium: 2
      high: 3
      critical: 3
    escalation_after_exhaustion: "orchestrator_or_user_claim_gate"

  input_contract: "ClaimExtractionInputBundle"
  output_contract: "ClaimState"
InputBundle
ClaimExtractionInputBundle:
  task_id: "TASK_CLAIMS_001"

  artifact_refs:
    slide_semantic_view_ref: "artifact://views/slide_semantic.json"
    concept_state_ref: "artifact://states/concept_state.approved.json"
    structure_state_ref: "artifact://states/structure_state.approved.json"

  hydrated_payload:
    candidate_units:
      - slide_id: 12
        section_id: S3
        text_spans:
          - span_id: "S12_T1"
            text: "Bayesian methods are computationally expensive for large-scale problems."
        related_concepts: [C8, C9]
        structural_role: "limitation"

  extraction_profile:
    include:
      - "definition"
      - "empirical"
      - "methodological"
      - "historical"
      - "state_of_the_art"
      - "normative"
      - "statistical"
      - "tooling"
    exclude:
      - "plain_headings"
      - "agenda_items"
      - "decorative_text"
      - "speaker_navigation"

  output_contract:
    artifact: "ClaimState"
Cross-Agent Reconciliation Reviewer
AgentDefinition
agent_definition:
  agent_id: "CrossAgentReconciliationReviewer"
  graph: "IntakeGraph"
  complexity_class: "cross_artifact_reconciliation"

  responsibility:
    - "Detect conflicts between reviewed intake artifacts"
    - "Route revision to the correct owner agent"
    - "Prevent inconsistent handoff to synthesizer"

  non_responsibilities:
    - "Do not rewrite artifacts directly"
    - "Do not create synthesis report"
    - "Do not perform research"
    - "Do not decide final slide changes"

  guardrails:
    - "Every conflict must identify affected artifacts"
    - "Every conflict must have likely_owner"
    - "Every revision request must route to one agent"
    - "Do not send full state to downstream graph"

  revision_policy:
    retry_scope: "per_conflict"
    max_revision_attempts:
      low: 0
      medium: 2
      high: 3
      critical: 3
    escalation_after_exhaustion: "orchestrator_or_user_intake_gate"

  input_contract: "CrossAgentReconciliationInputBundle"
  output_contract: "ReconciliationResult"
InputBundle
CrossAgentReconciliationInputBundle:
  task_id: "TASK_RECONCILE_001"

  reviewed_artifact_refs:
    structure_state_ref: "artifact://states/structure_state.approved.json"
    concept_state_ref: "artifact://states/concept_state.approved.json"
    slide_debt_state_ref: "artifact://states/slide_debt_state.approved.json"
    difficulty_state_ref: "artifact://states/difficulty_state.approved.json"
    flow_state_ref: "artifact://states/flow_state.approved.json"
    claim_state_ref: "artifact://states/claim_state.approved.json"

  minimal_views:
    slide_order_view_ref: "artifact://views/slide_order.json"
    slide_semantic_view_ref: "artifact://views/slide_semantic.json"

  reconciliation_profile:
    detect_conflicts:
      - "concept_claim_mismatch"
      - "difficulty_concept_density_mismatch"
      - "flow_structure_mismatch"
      - "claim_without_concept"
      - "undefined_concept_used_in_claim"
      - "slide_debt_conflicts_with_narrative"

  output_contract:
    artifact: "ReconciliationResult"
Intake Synthesizer Agent
AgentDefinition
agent_definition:
  agent_id: "IntakeSynthesizerAgent"
  graph: "IntakeGraph"
  complexity_class: "synthesis_decision"

  responsibility:
    - "Synthesize reviewed intake artifacts"
    - "Create intake report"
    - "Create user validation packet"
    - "Create candidate handoff to Research Graph"

  non_responsibilities:
    - "Do not create research plan"
    - "Do not verify claims"
    - "Do not propose final slide changes"
    - "Do not pass full internal state to Research Graph"

  guardrails:
    - "Summarize, do not dump state"
    - "Expose uncertainties"
    - "Separate facts from assumptions"
    - "User packet must be decision-oriented"
    - "Research candidate must use compact cards, not full state"

  revision_policy:
    retry_scope: "handoff_bundle"
    max_revision_attempts:
      low: 0
      medium: 1
      high: 2
      critical: 3
    escalation_after_exhaustion: "orchestrator_or_user_intake_gate"

  input_contract: "IntakeSynthesizerInputBundle"
  output_contract:
    - "IntakeReport"
    - "UserValidationPacket"
    - "ResearchInputCandidate"
InputBundle
IntakeSynthesizerInputBundle:
  task_id: "TASK_SYNTH_INTAKE_001"

  approved_artifact_refs:
    structure_state_ref: "artifact://states/structure_state.approved.json"
    concept_state_ref: "artifact://states/concept_state.approved.json"
    slide_debt_state_ref: "artifact://states/slide_debt_state.approved.json"
    difficulty_state_ref: "artifact://states/difficulty_state.approved.json"
    flow_state_ref: "artifact://states/flow_state.approved.json"
    claim_state_ref: "artifact://states/claim_state.approved.json"

  reconciliation_result_ref: "artifact://reviews/reconciliation_result.approved.json"

  synthesis_request:
    produce:
      - "intake_report"
      - "user_validation_packet"
      - "research_input_candidate"

  output_contract:
    artifacts:
      - "IntakeReport"
      - "UserValidationPacket"
      - "ResearchInputCandidate"
7. User Intake Gate
7.1 Cel

Człowiek zatwierdza, czy system dobrze zrozumiał materiał.

7.2 Input do User Gate
UserIntakeGateInput:
  intake_report_ref: "artifact://reports/intake_report.md"

  validation_packet:
    slide_count: 42

    detected_structure_summary: "..."

    detected_domains:
      - label: "Bayesian statistics"
        confidence: 0.84
        evidence: "Detected central concepts: prior, posterior, likelihood"

    main_concepts:
      - "Prior distribution"
      - "Likelihood"
      - "Posterior distribution"

    potential_logic_issues:
      - issue_id: F_001
        severity: "high"
        summary: "Concept used before introduction"

    claims_requiring_research:
      high: 8
      medium: 12
      low: 5

  required_decisions:
    - decision_id: D1
      type: "confirm_audience"

    - decision_id: D2
      type: "confirm_domains"

    - decision_id: D3
      type: "approve_research_scope"

    - decision_id: D4
      type: "mark_locked_sections"

    - decision_id: D5
      type: "allow_logic_repairs"
7.3 Output z User Gate
UserApprovedIntakeBundle:
  approved_context:
    audience_level: "master"
    course_name: "Bayesian Statistics"
    target_duration_minutes: 90
    teaching_goal: "refresh and improve logical flow"

  approved_domains:
    - domain_id: D1
      label: "Bayesian statistics"
    - domain_id: D2
      label: "probabilistic programming"

  approved_research_scope:
    verify_claims:
      priority:
        - "high"
        - "medium"
    include_recent_developments: true
    include_canonical_sources: true
    include_didactic_examples: true

  locked_sections:
    - section_id: S1
      reason: "Author wants to keep opening narrative"

  allowed_repair_modes:
    update_content: true
    remove_slides: true
    add_slides: true
    merge_slides: true
    split_slides: true
    reorder_slides: true

  handoff_to_research:
    claim_cards:
      - claim_id: CLM_001
        slide_id: 12
        text: "Bayesian methods are computationally expensive for large-scale problems."
        type: "methodological"
        verification_need: "high"
        related_concepts:
          - "Bayesian inference"
          - "approximate inference"
        artifact_ref: "artifact://states/claim_state.approved.json#/claims/CLM_001"

    concept_context_cards:
      - concept_id: C1
        label: "Posterior distribution"
        role: "core_concept"
        related_claims: [CLM_001, CLM_003]
        artifact_ref: "artifact://states/concept_state.approved.json#/concepts/C1"

    flow_issue_cards:
      - issue_id: F_001
        severity: "high"
        summary: "Posterior is used before likelihood is explained"
        affected_slides: [6, 7]
        fix_hint: "REORDER_OR_ADD_BRIDGE"
        artifact_ref: "artifact://states/flow_state.approved.json#/issues/F_001"
8. Subgraf 2: Research Graph
8.1 Cel

Research Graph nie bada „tematu ogólnie”. Bada zatwierdzone claimy, domeny, luki i potrzeby aktualizacji.

8.2 Kontrakt wejścia do subgrafu
ResearchGraphInput:
  schema_version: "research_graph_input@1"
  task_id: "RESEARCH_001"

  user_approved_context:
    audience_level: "master"
    course_name: "Bayesian Statistics"
    target_duration_minutes: 90
    teaching_goal: "refresh and improve logical flow"

  approved_domains:
    - domain_id: D1
      label: "Bayesian statistics"
    - domain_id: D2
      label: "probabilistic programming"

  approved_research_scope:
    verify_claims:
      priority:
        - "high"
        - "medium"
    include_recent_developments: true
    include_canonical_sources: true
    include_didactic_examples: true

  research_drivers:
    - driver_id: DRV_001
      driver_type: "claim"
      priority: "high"
      purpose: "Qualify the approved computational-cost claim"
      related_claims: [CLM_001]
      related_concepts: [C1]
      related_flow_issues: []
      related_update_needs: []

  claim_cards:
    - claim_id: CLM_001
      slide_id: 12
      text: "Bayesian methods are computationally expensive for large-scale problems."
      type: "methodological"
      verification_need: "high"
      related_concepts:
        - "Bayesian inference"
        - "approximate inference"
      artifact_ref: "artifact://states/claim_state.approved.json#/claims/CLM_001"

  concept_context_cards:
    - concept_id: C1
      label: "Posterior distribution"
      role: "core_concept"
      related_claims: [CLM_001, CLM_003]
      artifact_ref: "artifact://states/concept_state.approved.json#/concepts/C1"

  selected_flow_issue_cards:
    - issue_id: F_001
      severity: "high"
      summary: "Posterior is used before likelihood is explained"
      affected_slides: [6, 7]
      fix_hint: "REORDER_OR_ADD_BRIDGE"
      artifact_ref: "artifact://states/flow_state.approved.json#/issues/F_001"

  selected_update_need_cards: []
  existing_source_cards: []

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
    open_access_preference: "preferred"

  locked_sections:
    - section_id: S1
      reason: "Author wants to keep opening narrative"

  artifact_refs_for_lazy_hydration:
    claim_state_ref: "artifact://states/claim_state.approved.json"
    concept_state_ref: "artifact://states/concept_state.approved.json"
    flow_state_ref: "artifact://states/flow_state.approved.json"

  output_language: "English"
8.3 Czego Research Graph nie dostaje
pełnego PDF,
pełnego tekstu wszystkich slajdów,
całego StructureState,
całego SlideDebtState,
całego DifficultyState,
całego FlowState,
całego ConceptState,
planu zmian slajdów.
8.4 Graf Research
flowchart TD
    A[ResearchGraphInput] --> RP[G02-A01 Planner Agent]

    RP --> RPR[Research Plan Reviewer]
    RPR -->|REVISE via ResearchPlanner policy| RP
    RPR -->|APPROVED| P[Parallel Research Work]

    P --> DR1[G02-A02 Domain Agents]
    P --> CV[G02-A08 Claim Verification Agent]
    P --> RD[G02-A04 Recent Developments Agent]
    P --> CS[G02-A03 Canonical Sources Agent]

    DR1 --> DSR[Domain Search Reviewer]
    DSR -->|REVISE routed| DR1

    CV --> CER[Claim Evidence Reviewer]
    CER -->|REVISE via ClaimVerification policy| CV

    RD --> RDR[G02-A10 Output Reviewer]
    RDR -->|REVISE via RecentDevelopments policy| RD

    CS --> CSR[G02-A10 Output Reviewer]
    CSR -->|REVISE via CanonicalSources policy| CS

    DSR -->|APPROVED| SS[Source Selection Agent]
    CER -->|APPROVED| SS
    RDR -->|APPROVED| SS
    CSR -->|APPROVED| SS

    SS --> SQR[Source Quality Reviewer]
    SQR -->|REVISE via SourceSelection policy| SS
    SQR -->|APPROVED| PR[G02-A06 Paper Retrieval Agent]

    PR --> PIR[Retrieval Integrity Reviewer]
    PIR -->|REVISE via Retrieval policy| PR
    PIR -->|APPROVED| PRA[G02-A07 Paper Review Agents]

    PRA --> PRQR[G02-A10 Output Reviewer]
    PRQR -->|REVISE via PaperReview policy| PRA
    PRQR -->|APPROVED| RS[G02-A09 Synthesizer Agent]

    RS --> RSR[Research Synthesis Reviewer]
    RSR -->|REVISE via Synthesizer policy| RS
    RSR -->|BLOCKED: bad plan| RP
    RSR -->|APPROVED| H2[User Research Gate]

    H2 -->|APPROVED| O[UserApprovedResearchBundle]
    H2 -->|NEEDS_CORRECTION| RS
8.5 Agenci Research — definicje i wejścia
G02-A01 Planner Agent
AgentDefinition
agent_definition:
  agent_id: "G02A01PlannerAgent"
  graph: "ResearchGraph"
  complexity_class: "research_planning"

  responsibility:
    - "Turn approved intake bundle into research plan"
    - "Group claims by topic and verification need"
    - "Define source strategy per topic"
    - "Limit scope to what is needed for lecture refresh"

  non_responsibilities:
    - "Do not verify claims"
    - "Do not summarize papers"
    - "Do not propose slide changes"
    - "Do not search broadly without link to approved scope"

  guardrails:
    - "Every research topic must link to claim, domain, flow issue or approved update need"
    - "Each topic must have purpose"
    - "Plan must distinguish canonical, recent and didactic sources"
    - "Do not expand beyond user-approved scope"

  revision_policy:
    retry_scope: "research_plan"
    max_revision_attempts:
      low: 0
      medium: 2
      high: 3
      critical: 3
    escalation_after_exhaustion: "user_research_scope_gate"

  input_contract: "research_planner_input@1"
  output_contract: "research_plan@1"
InputBundle
research_planner_input@1:
  schema_version: "research_planner_input@1"
  source_input_contract: "research_graph_input@1"
  task_id: "RESEARCH_001"

  user_approved_context:
    audience_level: "master"
    course_name: "Bayesian Statistics"
    teaching_goal: "refresh and improve logical flow"

  approved_domains:
    - domain_id: D1
      label: "Bayesian statistics"

  approved_research_scope:
    verify_claims:
      priority: ["high", "medium"]
    include_recent_developments: true
    include_canonical_sources: true
    include_didactic_examples: true

  research_drivers:
    - driver_id: DRV_001
      driver_type: "claim"
      priority: "high"
      purpose: "Qualify the computational-cost claim"
      related_claims: [CLM_001]
      related_concepts: [C1]
      related_flow_issues: []
      related_update_needs: []

  claim_cards:
    - claim_id: CLM_001
      text: "Bayesian methods are computationally expensive for large-scale problems."
      type: "methodological"
      verification_need: "high"
      related_concepts: ["Bayesian inference", "approximate inference"]

  concept_context_cards:
    - concept_id: C1
      label: "Posterior distribution"
      role: "core_concept"

  selected_flow_issue_cards:
    - issue_id: F_001
      summary: "Posterior is used before likelihood is explained"

  selected_update_need_cards: []
  existing_source_cards: []
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
    open_access_preference: "preferred"
  locked_sections: []
  artifact_refs_for_lazy_hydration: {}
  output_language: "English"
G02-A02 Domain Agents
AgentDefinition
agent_definition:
  agent_id: "G02A02DomainAgent"
  graph: "ResearchGraph"
  complexity_class: "research_search"

  responsibility:
    - "Search literature within assigned domain/topic"
    - "Collect candidate sources"
    - "Separate canonical, recent, survey and didactic sources"

  non_responsibilities:
    - "Do not verify specific claims unless assigned"
    - "Do not summarize full papers"
    - "Do not decide final source set"
    - "Do not propose slide changes"

  guardrails:
    - "Every candidate source must map to research topic"
    - "Every source must have metadata"
    - "Avoid keyword spam; iterate semantically"
    - "Track source role and relevance"

  revision_policy:
    retry_scope: "per_topic"
    max_revision_attempts:
      low: 0
      medium: 2
      high: 3
      critical: 3
    escalation_after_exhaustion: "research_orchestrator"

  input_contract: "DomainResearchInputBundle"
  output_contract: "CandidateSources"
InputBundle
DomainResearchInputBundle:
  task_id: "TASK_DOMAIN_RESEARCH_001"

  assigned_topic:
    topic_id: R1
    name: "Scalable Bayesian inference"
    purpose: "Verify claims about computational cost of Bayesian methods"
    related_claims: [CLM_001]

  source_strategy:
    require_recent_sources: true
    require_canonical_sources: true
    prefer_surveys: true
    include_didactic_sources: false

  approved_domains:
    - "Bayesian statistics"
    - "probabilistic programming"

  output_contract:
    artifact: "CandidateSources"
G02-A08 Claim Verification Agent
AgentDefinition
agent_definition:
  agent_id: "G02A08ClaimVerificationAgent"
  graph: "ResearchGraph"
  complexity_class: "evidence_high_impact"

  responsibility:
    - "Verify approved claims against sources"
    - "Classify claim status"
    - "Attach evidence and confidence"
    - "Identify implication for lecture"

  non_responsibilities:
    - "Do not rewrite slides"
    - "Do not create final change plan"
    - "Do not use unsupported sources"
    - "Do not ignore controversial evidence"

  guardrails:
    - "Every verification must have evidence"
    - "Every evidence source must support the conclusion"
    - "High confidence requires strong sources"
    - "Controversial claims need counter-sources or uncertainty"

  revision_policy:
    retry_scope: "per_claim"
    max_revision_attempts:
      low: 1
      medium: 2
      high: 3
      critical: 3
    escalation_after_exhaustion: "user_research_gate"

  input_contract: "ClaimVerificationInputBundle"
  output_contract: "ClaimVerificationState"
InputBundle
ClaimVerificationInputBundle:
  task_id: "TASK_VERIFY_CLAIMS_001"

  claim_cards:
    - claim_id: CLM_001
      slide_id: 12
      text: "Bayesian methods are computationally expensive for large-scale problems."
      type: "methodological"
      verification_need: "high"
      related_concepts:
        - "Bayesian inference"
        - "approximate inference"

  candidate_source_refs:
    - "artifact://g02/candidates/R1_sources.json"

  verification_profile:
    statuses:
      - "valid"
      - "needs_update"
      - "too_simplified"
      - "unsupported"
      - "controversial"
      - "obsolete"
      - "needs_context"

  output_contract:
    artifact: "ClaimVerificationState"
G02-A04 Recent Developments Agent
AgentDefinition
agent_definition:
  agent_id: "G02A04RecentDevelopmentsAgent"
  graph: "ResearchGraph"
  complexity_class: "research_search"

  responsibility:
    - "Find recent developments relevant to approved domains"
    - "Distinguish stable updates from temporary hype"
    - "Classify what belongs in lecture vs appendix"

  non_responsibilities:
    - "Do not replace canonical material"
    - "Do not create slide content"
    - "Do not expand beyond approved domains"

  guardrails:
    - "Every development must map to approved domain or claim"
    - "Mark maturity level"
    - "Separate core update from optional trend"

  revision_policy:
    retry_scope: "per_topic"
    max_revision_attempts:
      low: 0
      medium: 2
      high: 3
      critical: 3
    escalation_after_exhaustion: "research_orchestrator"

  input_contract: "RecentDevelopmentsInputBundle"
  output_contract: "RecentDevelopmentsState"
InputBundle
RecentDevelopmentsInputBundle:
  task_id: "TASK_RECENT_DEV_001"

  approved_domains:
    - "Bayesian statistics"
    - "probabilistic programming"

  approved_research_scope:
    include_recent_developments: true

  topic_cards:
    - topic_id: R1
      name: "Scalable Bayesian inference"
      related_claims: [CLM_001]

  recency_window:
    preferred_years: 5
    allow_older_if_canonical: true

  output_contract:
    artifact: "RecentDevelopmentsState"
G02-A03 Canonical Sources Agent
AgentDefinition
agent_definition:
  agent_id: "G02A03CanonicalSourcesAgent"
  graph: "ResearchGraph"
  complexity_class: "research_search"

  responsibility:
    - "Find canonical sources"
    - "Find surveys, textbooks and foundational papers"
    - "Assess suitability for teaching"

  non_responsibilities:
    - "Do not prioritize novelty over reliability"
    - "Do not generate slide content"
    - "Do not verify every claim in detail"

  guardrails:
    - "Every canonical source must map to concept or domain"
    - "Mark teaching suitability"
    - "Separate foundational source from advanced technical source"

  revision_policy:
    retry_scope: "per_domain"
    max_revision_attempts:
      low: 0
      medium: 2
      high: 3
      critical: 3
    escalation_after_exhaustion: "research_orchestrator"

  input_contract: "CanonicalSourcesInputBundle"
  output_contract: "CanonicalSourcesState"
InputBundle
CanonicalSourcesInputBundle:
  task_id: "TASK_CANONICAL_001"

  approved_domains:
    - "Bayesian statistics"

  concept_context_cards:
    - concept_id: C1
      label: "Posterior distribution"
      role: "core_concept"
    - concept_id: C2
      label: "Likelihood"
      role: "prerequisite"

  source_need:
    include_textbooks: true
    include_surveys: true
    include_foundational_papers: true

  output_contract:
    artifact: "CanonicalSourcesState"
Source Selection Agent
AgentDefinition
agent_definition:
  agent_id: "SourceSelectionAgent"
  graph: "ResearchGraph"
  complexity_class: "synthesis_decision"

  responsibility:
    - "Select final source set"
    - "Remove duplicates"
    - "Balance canonical, recent, survey and didactic sources"
    - "Limit corpus size"

  non_responsibilities:
    - "Do not summarize papers"
    - "Do not verify claims"
    - "Do not create slide plan"

  guardrails:
    - "Every selected source must have role"
    - "Every selected source must map to topic or claim"
    - "Avoid excessive corpus size"
    - "Do not select low-quality sources without justification"

  revision_policy:
    retry_scope: "source_set"
    max_revision_attempts:
      low: 0
      medium: 1
      high: 2
      critical: 3
    escalation_after_exhaustion: "research_orchestrator"

  input_contract: "SourceSelectionInputBundle"
  output_contract: "SelectedSources"
InputBundle
SourceSelectionInputBundle:
  task_id: "TASK_SOURCE_SELECTION_001"

  candidate_source_refs:
    domain_sources_ref: "artifact://g02/candidate_sources/domain.json"
    recent_sources_ref: "artifact://g02/candidate_sources/recent.json"
    canonical_sources_ref: "artifact://g02/candidate_sources/canonical.json"
    claim_evidence_candidates_ref: "artifact://g02/candidate_sources/claim_evidence.json"

  selection_profile:
    max_sources_per_topic: 12
    min_canonical_per_foundational_topic: 1
    min_recent_for_update_topic: 2
    prefer_surveys: true

  output_contract:
    artifact: "SelectedSources"
G02-A06 Paper Retrieval Agent
AgentDefinition
agent_definition:
  agent_id: "G02A06PaperRetrievalAgent"
  graph: "ResearchGraph"
  complexity_class: "deterministic_technical"

  responsibility:
    - "Download or register selected papers"
    - "Create topic folders"
    - "Store PDFs and metadata"
    - "Mark unavailable PDFs"

  non_responsibilities:
    - "Do not judge source quality"
    - "Do not summarize papers"
    - "Do not modify source selection"

  guardrails:
    - "Every file must map to source_id"
    - "Missing PDFs must be explicitly marked"
    - "Folder structure must be stable"

  revision_policy:
    retry_scope: "per_source"
    max_revision_attempts:
      low: 0
      medium: 1
      high: 2
      critical: 3
    escalation_after_exhaustion: "research_orchestrator"

  input_contract: "PaperRetrievalInputBundle"
  output_contract: "RetrievedCorpus"
InputBundle
PaperRetrievalInputBundle:
  task_id: "TASK_RETRIEVAL_001"

  selected_sources_ref: "artifact://g02/selected_sources.json"

  folder_policy:
    root: "research/"
    topic_folder_pattern: "{index}_{slugified_topic_name}"
    papers_subfolder: "papers"
    reviews_subfolder: "reviews"

  output_contract:
    artifact: "RetrievedCorpus"
G02-A07 Paper Review Agents
AgentDefinition
agent_definition:
  agent_id: "G02A07PaperReviewAgent"
  graph: "ResearchGraph"
  complexity_class: "evidence_high_impact"

  responsibility:
    - "Review assigned paper"
    - "Extract contribution, methods, findings and limitations"
    - "Assess relevance to lecture"
    - "Identify usable teaching elements"

  non_responsibilities:
    - "Do not decide final slide changes"
    - "Do not overstate paper conclusions"
    - "Do not ignore limitations"

  guardrails:
    - "Every review must include relevance_to_lecture"
    - "Every review must include limitations or warnings"
    - "Separate paper claims from lecture implications"

  revision_policy:
    retry_scope: "per_paper"
    max_revision_attempts:
      low: 0
      medium: 1
      high: 2
      critical: 3
    escalation_after_exhaustion: "research_orchestrator"

  input_contract: "PaperReviewInputBundle"
  output_contract: "PaperReview"
InputBundle
PaperReviewInputBundle:
  task_id: "TASK_PAPER_REVIEW_001"

  source:
    source_id: P_014
    metadata_ref: "artifact://g02/01_topic/papers/P_014_metadata.json"
    pdf_ref: "artifact://g02/01_topic/papers/P_014.pdf"

  review_context:
    related_claims: [CLM_001]
    related_topics: [R1]
    audience_level: "master"

  output_contract:
    artifact: "PaperReview"
G02-A09 Synthesizer Agent
AgentDefinition
agent_definition:
  agent_id: "G02A09SynthesizerAgent"
  graph: "ResearchGraph"
  complexity_class: "synthesis_decision"

  responsibility:
    - "Synthesize claim verification, source reviews and recent developments"
    - "Create ResearchState"
    - "Create evidence map"
    - "Create user research validation packet"
    - "Create candidate input for Solution Graph"

  non_responsibilities:
    - "Do not write final slides"
    - "Do not decide final change plan"
    - "Do not pass full paper corpus to Solution Graph"

  guardrails:
    - "Every recommendation must have evidence"
    - "Separate required updates from optional improvements"
    - "Do not include full research corpus in handoff"
    - "High-priority claims must be resolved or explicitly marked unresolved"

  revision_policy:
    retry_scope: "research_synthesis"
    max_revision_attempts:
      low: 0
      medium: 1
      high: 2
      critical: 3
    escalation_after_exhaustion: "user_research_gate"

  input_contract: "ResearchSynthesizerInputBundle"
  output_contract:
    - "ResearchState"
    - "EvidenceMap"
    - "UserResearchValidationPacket"
    - "SolutionInputCandidate"
InputBundle
ResearchSynthesizerInputBundle:
  task_id: "TASK_RESEARCH_SYNTH_001"

  approved_research_plan_ref: "artifact://g02/research_plan.approved.json"
  claim_verification_ref: "artifact://g02/claim_verification.approved.json"
  selected_sources_ref: "artifact://g02/selected_sources.approved.json"
  paper_reviews_index_ref: "artifact://g02/paper_reviews/index.json"
  recent_developments_ref: "artifact://g02/recent_developments.approved.json"
  canonical_sources_ref: "artifact://g02/canonical_sources.approved.json"

  synthesis_request:
    produce:
      - "evidence_map"
      - "research_summary"
      - "slide_impact_candidates"
      - "user_research_validation_packet"
      - "solution_input_candidate"

  output_contract:
    artifacts:
      - "ResearchState"
      - "EvidenceMap"
      - "UserResearchValidationPacket"
      - "SolutionInputCandidate"
9. User Research Gate
9.1 Cel

Człowiek zatwierdza, które wyniki researchu mają wpływać na nową wersję wykładu.

9.2 Input
UserResearchGateInput:
  research_summary_ref: "artifact://g02/research_summary.md"

  validation_packet:
    verified_claims:
      valid: 10
      needs_update: 6
      obsolete: 2
      controversial: 3
      unresolved: 1

    required_updates:
      - finding_id: RF_001
        related_claims: [CLM_001]
        summary: "Claim about computational cost needs qualification."
        evidence_count: 3
        recommended_impact: "UPDATE"

    optional_improvements:
      - finding_id: RF_014
        summary: "Modern probabilistic programming example could improve lecture."
        recommended_impact: "ADD_OPTIONAL"

    unresolved_questions:
      - claim_id: CLM_022
        reason: "Insufficient evidence in open-access sources."

  required_decisions:
    - decision_id: RD1
      type: "approve_required_updates"

    - decision_id: RD2
      type: "approve_optional_trends"

    - decision_id: RD3
      type: "choose_depth_of_recent_developments"

    - decision_id: RD4
      type: "confirm_unresolved_claim_handling"
9.3 Output
UserApprovedResearchBundle:
  approved_research_summary_ref: "artifact://g02/research_summary.approved.md"

  approved_update_findings:
    - finding_id: RF_001
      impact: "UPDATE"
      priority: "high"
      related_claims: [CLM_001]
      evidence_cards:
        - evidence_id: EV_001
          source_id: P_014
          summary: "Approximate inference reduces practical computational barriers."
          source_ref: "artifact://g02/01_topic/reviews/P_014_review.json"

  approved_optional_findings:
    - finding_id: RF_014
      impact: "ADD_OPTIONAL"
      priority: "medium"

  rejected_findings:
    - finding_id: RF_020
      reason: "Too advanced for this course"

  unresolved_claim_policy:
    action: "move_to_speaker_note_or_remove"
    require_user_confirmation_before_final: true

  solution_handoff:
    evidence_cards: []
    slide_impact_cards: []
    source_cards: []
    unresolved_claim_cards: []
10. Subgraf 3: Solution Design Graph
10.1 Cel

Zaprojektować nową wersję wykładu:

nie przebudować wszystkiego,
chronić KEEP,
oznaczyć UPDATE, REMOVE, ADD, MERGE, SPLIT, REORDER,
stworzyć nowe slajdy,
poprawić istniejące,
napisać notatki mówcy,
oszacować czas,
przygotować export package.
10.2 Kontrakt wejścia do subgrafu
SolutionDesignGraphInput:
  task_id: "SOLUTION_001"

  approved_context:
    audience_level: "master"
    course_name: "Bayesian Statistics"
    target_duration_minutes: 90
    teaching_goal: "refresh and improve logical flow"

  locked_sections:
    - section_id: S1
      reason: "Author wants to keep opening narrative"

  allowed_repair_modes:
    update_content: true
    remove_slides: true
    add_slides: true
    merge_slides: true
    split_slides: true
    reorder_slides: true

  deck_inventory_cards:
    - slide_id: 12
      section_id: S3
      title: "Limitations of Bayesian methods"
      current_role: "limitation"
      related_claims: [CLM_001]
      related_concepts: [C8, C9]
      artifact_ref: "artifact://views/slide_semantic.json#/slides/12"

  approved_update_findings:
    - finding_id: RF_001
      impact: "UPDATE"
      priority: "high"
      related_claims: [CLM_001]
      evidence_cards:
        - evidence_id: EV_001
          source_id: P_014
          summary: "Approximate inference reduces practical computational barriers."
          source_ref: "artifact://g02/01_topic/reviews/P_014_review.json"

  approved_optional_findings:
    - finding_id: RF_014
      impact: "ADD_OPTIONAL"
      priority: "medium"

  flow_issue_cards:
    - issue_id: F_001
      severity: "high"
      summary: "Posterior is used before likelihood is explained"
      affected_slides: [6, 7]
      fix_hint: "REORDER_OR_ADD_BRIDGE"

  unresolved_claim_policy:
    action: "move_to_speaker_note_or_remove"
    require_user_confirmation_before_final: true

  artifact_refs_for_lazy_hydration:
    slide_semantic_view_ref: "artifact://views/slide_semantic.json"
    structure_state_ref: "artifact://states/structure_state.approved.json"
    concept_state_ref: "artifact://states/concept_state.approved.json"
    evidence_map_ref: "artifact://g02/evidence_map.approved.json"

  output_contract:
    artifact: "FinalLecturePackage"
10.3 Czego Solution Graph nie dostaje
pełnego research corpus,
wszystkich PDF-ów,
pełnego raw PDF prezentacji,
całego Intake state,
niezatwierdzonych findings,
odrzuconych przez człowieka propozycji jako aktywnych zaleceń.
10.4 Graf Solution Design
flowchart TD
    A[SolutionDesignGraphInput] --> CP[Change Planner Agent]

    CP --> CPR[Change Plan Reviewer]
    CPR -->|REVISE via ChangePlanner policy| CP
    CPR -->|APPROVED| H3[User Change Plan Gate]

    H3 -->|NEEDS_CORRECTION| CP
    H3 -->|APPROVED| P[Parallel Design Work]

    P --> SE[Merge / Split / Reorder Agent]
    P --> ND[Lecture Narrative Designer]
    P --> SP[Slide Patch Agent]
    P --> NS[New Slide Designer]

    SE --> SER[Structural Edit Reviewer]
    ND --> NR[Narrative Reviewer]
    SP --> SPR[Slide Patch Reviewer]
    NS --> NSR[New Slide Reviewer]

    SER -->|REVISE via Structural policy| SE
    NR -->|REVISE via Narrative policy| ND
    SPR -->|REVISE via Patch policy| SP
    NSR -->|REVISE via NewSlide policy| NS

    SER -->|APPROVED| SN[Speaker Notes Agent]
    NR -->|APPROVED| SN
    SPR -->|APPROVED| SN
    NSR -->|APPROVED| SN

    SN --> SNR[Speaker Notes Reviewer]
    SNR -->|REVISE via Notes policy| SN
    SNR -->|APPROVED| T[Timing Agent]

    T --> TR[Timing Reviewer]
    TR -->|REVISE_NOTES| SN
    TR -->|REVISE_NARRATIVE| ND
    TR -->|REVISE_CHANGE_PLAN| CP
    TR -->|APPROVED| CR[Final Consistency Reviewer]

    CR -->|REVISE_PATCHES| SP
    CR -->|REVISE_NEW_SLIDES| NS
    CR -->|REVISE_NOTES| SN
    CR -->|REVISE_NARRATIVE| ND
    CR -->|REVISE_STRUCTURAL| SE
    CR -->|REVISE_CHANGE_PLAN| CP
    CR -->|APPROVED| H4[Final User Review Gate]

    H4 -->|NEEDS_CORRECTION| CR
    H4 -->|APPROVED| FB[Final Package Builder]

    FB --> ER[Export Integrity Reviewer]
    ER -->|REVISE via Export policy| FB
    ER -->|APPROVED| OUT[FinalLecturePackage]
10.5 Agenci Solution Design — definicje i wejścia
Change Planner Agent
AgentDefinition
agent_definition:
  agent_id: "ChangePlannerAgent"
  graph: "SolutionDesignGraph"
  complexity_class: "synthesis_decision"

  responsibility:
    - "Assign status to every slide or planned new slide"
    - "Protect locked sections"
    - "Translate evidence and flow issues into change decisions"
    - "Create ChangePlan"

  non_responsibilities:
    - "Do not write final slide text"
    - "Do not write speaker notes"
    - "Do not fetch new sources"
    - "Do not override user-approved constraints"

  guardrails:
    - "Every existing slide must receive status"
    - "Every change must have reason"
    - "Every research-based change must have evidence"
    - "Locked sections cannot be changed unless explicitly allowed"
    - "Allowed statuses: KEEP, UPDATE, REMOVE, ADD, MERGE, SPLIT, REORDER"

  revision_policy:
    retry_scope: "change_plan"
    max_revision_attempts:
      low: 0
      medium: 1
      high: 2
      critical: 3
    escalation_after_exhaustion: "user_change_plan_gate"

  input_contract: "ChangePlannerInputBundle"
  output_contract: "ChangePlan"
InputBundle
ChangePlannerInputBundle:
  task_id: "TASK_CHANGE_PLAN_001"

  deck_inventory_cards:
    - slide_id: 12
      section_id: S3
      title: "Limitations of Bayesian methods"
      current_role: "limitation"
      related_claims: [CLM_001]

  approved_update_findings:
    - finding_id: RF_001
      impact: "UPDATE"
      priority: "high"
      related_claims: [CLM_001]
      evidence_cards: [EV_001]

  approved_optional_findings:
    - finding_id: RF_014
      impact: "ADD_OPTIONAL"
      priority: "medium"

  flow_issue_cards:
    - issue_id: F_001
      severity: "high"
      affected_slides: [6, 7]
      fix_hint: "REORDER_OR_ADD_BRIDGE"

  locked_sections:
    - section_id: S1
      reason: "Author wants to keep opening narrative"

  allowed_repair_modes:
    update_content: true
    remove_slides: true
    add_slides: true
    merge_slides: true
    split_slides: true
    reorder_slides: true

  output_contract:
    artifact: "ChangePlan"
Merge / Split / Reorder Agent
AgentDefinition
agent_definition:
  agent_id: "StructuralEditAgent"
  graph: "SolutionDesignGraph"
  complexity_class: "structural_design"

  responsibility:
    - "Design MERGE operations"
    - "Design SPLIT operations"
    - "Design REORDER operations"
    - "Preserve content and speaker-note continuity"

  non_responsibilities:
    - "Do not update factual content"
    - "Do not create new research-based claims"
    - "Do not write full slide deck"

  guardrails:
    - "MERGE must preserve unique claims"
    - "SPLIT must reduce cognitive load"
    - "REORDER must not break prerequisites"
    - "Every structural edit must include content preservation plan"

  revision_policy:
    retry_scope: "per_operation"
    max_revision_attempts:
      low: 0
      medium: 2
      high: 3
      critical: 3
    escalation_after_exhaustion: "user_change_plan_gate"

  input_contract: "StructuralEditInputBundle"
  output_contract: "StructuralEditPlan"
InputBundle
StructuralEditInputBundle:
  task_id: "TASK_STRUCTURAL_EDIT_001"

  approved_change_plan_ref: "artifact://solution/change_plan.approved.json"

  structural_candidates:
    merge_candidates:
      - slide_ids: [14, 15]
        reason: "Duplicate example"
    split_candidates:
      - slide_id: 10
        reason: "Too many concepts on one slide"
    reorder_candidates:
      - slide_id: 18
        move_after_slide: 12
        reason: "Example should appear earlier"

  concept_order_refs:
    concept_state_ref: "artifact://states/concept_state.approved.json"
    flow_state_ref: "artifact://states/flow_state.approved.json"

  output_contract:
    artifact: "StructuralEditPlan"
Lecture Narrative Designer
AgentDefinition
agent_definition:
  agent_id: "LectureNarrativeDesigner"
  graph: "SolutionDesignGraph"
  complexity_class: "creative_design"

  responsibility:
    - "Design updated lecture narrative"
    - "Integrate approved changes into coherent flow"
    - "Maintain difficulty curve"
    - "Design section transitions"

  non_responsibilities:
    - "Do not verify claims"
    - "Do not fetch sources"
    - "Do not override ChangePlan"
    - "Do not write final slide details"

  guardrails:
    - "Narrative must respect approved ChangePlan"
    - "Difficulty curve must be explicit"
    - "New slides must be integrated, not appended randomly"
    - "Locked sections must be preserved"

  revision_policy:
    retry_scope: "deck"
    max_revision_attempts:
      low: 0
      medium: 2
      high: 3
      critical: 3
    escalation_after_exhaustion: "user_change_plan_gate"

  input_contract: "NarrativeDesignInputBundle"
  output_contract: "NarrativePlan"
InputBundle
NarrativeDesignInputBundle:
  task_id: "TASK_NARRATIVE_001"

  approved_change_plan_ref: "artifact://solution/change_plan.approved.json"
  structural_edit_plan_ref: "artifact://solution/structural_edit_plan.json"

  deck_inventory_cards: []
  concept_context_cards: []
  flow_issue_cards: []

  teaching_context:
    audience_level: "master"
    target_duration_minutes: 90
    teaching_goal: "refresh and improve logical flow"

  output_contract:
    artifact: "NarrativePlan"
Slide Patch Agent
AgentDefinition
agent_definition:
  agent_id: "SlidePatchAgent"
  graph: "SolutionDesignGraph"
  complexity_class: "creative_design"

  responsibility:
    - "Patch slides with UPDATE status"
    - "Use approved evidence for factual updates"
    - "Preserve original slide role where possible"

  non_responsibilities:
    - "Do not modify KEEP slides"
    - "Do not create ADD slides"
    - "Do not perform structural MERGE/SPLIT/REORDER"
    - "Do not introduce unsupported claims"

  guardrails:
    - "Every patch must map old content to new content"
    - "Every evidence-based update must cite evidence card"
    - "No unverified claims"
    - "Bullet density must remain manageable"

  revision_policy:
    retry_scope: "per_slide"
    max_revision_attempts:
      low: 0
      medium: 2
      high: 3
      critical: 3
    escalation_after_exhaustion: "solution_orchestrator"

  input_contract: "SlidePatchInputBundle"
  output_contract: "SlidePatches"
InputBundle
SlidePatchInputBundle:
  task_id: "TASK_PATCH_001"

  approved_change_plan_ref: "artifact://solution/change_plan.approved.json"

  slides_to_update:
    - slide_id: 12
      title: "Limitations of Bayesian methods"
      current_text_ref: "artifact://views/slide_semantic.json#/slides/12"
      related_claims: [CLM_001]
      approved_findings: [RF_001]
      evidence_cards: [EV_001]

  narrative_plan_ref: "artifact://solution/narrative_plan.json"

  output_contract:
    artifact: "SlidePatches"
New Slide Designer
AgentDefinition
agent_definition:
  agent_id: "NewSlideDesigner"
  graph: "SolutionDesignGraph"
  complexity_class: "creative_design"

  responsibility:
    - "Design ADD slides"
    - "Define learning goal for every new slide"
    - "Place each new slide in narrative"
    - "Attach evidence where new knowledge is introduced"

  non_responsibilities:
    - "Do not patch existing slides"
    - "Do not create unsupported content"
    - "Do not ignore target duration"

  guardrails:
    - "Every new slide must have insert position"
    - "Every new slide must have reason"
    - "Every research-based new slide must have evidence"
    - "Avoid too many new concepts per slide"

  revision_policy:
    retry_scope: "per_new_slide"
    max_revision_attempts:
      low: 0
      medium: 2
      high: 3
      critical: 3
    escalation_after_exhaustion: "solution_orchestrator"

  input_contract: "NewSlideInputBundle"
  output_contract: "NewSlides"
InputBundle
NewSlideInputBundle:
  task_id: "TASK_NEW_SLIDES_001"

  approved_change_plan_ref: "artifact://solution/change_plan.approved.json"
  narrative_plan_ref: "artifact://solution/narrative_plan.json"

  add_candidates:
    - new_slide_id: NEW_01
      insert_after_slide: 12
      reason: "Missing bridge between computational limitation and modern approximate inference"
      approved_findings: [RF_001]
      evidence_cards: [EV_001]

  teaching_context:
    audience_level: "master"
    target_duration_minutes: 90

  output_contract:
    artifact: "NewSlides"
Speaker Notes Agent
AgentDefinition
agent_definition:
  agent_id: "SpeakerNotesAgent"
  graph: "SolutionDesignGraph"
  complexity_class: "creative_design"

  responsibility:
    - "Write speaker notes"
    - "Create talk track"
    - "Add instructor cues and transitions"
    - "Support student comprehension"

  non_responsibilities:
    - "Do not change slide status"
    - "Do not add unsupported claims"
    - "Do not rewrite evidence"

  guardrails:
    - "Notes must not merely repeat bullets"
    - "Notes must include transitions where needed"
    - "Unverified claims are forbidden"
    - "Notes must be compatible with target timing"

  revision_policy:
    retry_scope: "per_slide"
    max_revision_attempts:
      low: 0
      medium: 2
      high: 3
      critical: 3
    escalation_after_exhaustion: "solution_orchestrator"

  input_contract: "SpeakerNotesInputBundle"
  output_contract: "SpeakerNotes"
InputBundle
SpeakerNotesInputBundle:
  task_id: "TASK_NOTES_001"

  narrative_plan_ref: "artifact://solution/narrative_plan.json"
  slide_patches_ref: "artifact://solution/slide_patches.approved.json"
  new_slides_ref: "artifact://solution/new_slides.approved.json"
  structural_edit_plan_ref: "artifact://solution/structural_edit_plan.approved.json"

  teaching_context:
    audience_level: "master"
    delivery_mode: "lecture"
    target_duration_minutes: 90

  output_contract:
    artifact: "SpeakerNotes"
Timing Agent
AgentDefinition
agent_definition:
  agent_id: "TimingAgent"
  graph: "SolutionDesignGraph"
  complexity_class: "bounded_interpretive"

  responsibility:
    - "Estimate timing per slide and section"
    - "Detect overloaded sections"
    - "Recommend optional/appendix slides"
    - "Route timing issues to correct owner"

  non_responsibilities:
    - "Do not rewrite slides directly"
    - "Do not remove slides directly"
    - "Do not override user target duration"

  guardrails:
    - "Every slide must have estimated time"
    - "Total time must include buffer"
    - "Timing issues must route to notes, narrative or change plan"

  revision_policy:
    retry_scope: "deck_or_section"
    max_revision_attempts:
      low: 0
      medium: 1
      high: 2
      critical: 3
    escalation_after_exhaustion: "user_final_review_gate"

  input_contract: "TimingInputBundle"
  output_contract: "TimingState"
InputBundle
TimingInputBundle:
  task_id: "TASK_TIMING_001"

  updated_slide_plan_refs:
    structural_edit_plan_ref: "artifact://solution/structural_edit_plan.approved.json"
    slide_patches_ref: "artifact://solution/slide_patches.approved.json"
    new_slides_ref: "artifact://solution/new_slides.approved.json"
    speaker_notes_ref: "artifact://solution/speaker_notes.approved.json"

  timing_config:
    target_duration_minutes: 90
    words_per_minute: 140
    include_transition_buffer: true
    include_questions_buffer: true

  output_contract:
    artifact: "TimingState"
Final Consistency Reviewer
AgentDefinition
agent_definition:
  agent_id: "FinalConsistencyReviewer"
  graph: "SolutionDesignGraph"
  complexity_class: "cross_artifact_reconciliation"

  responsibility:
    - "Review whole designed lecture package"
    - "Detect contradictions"
    - "Verify status constraints"
    - "Verify evidence coverage"
    - "Route revisions to owner agents"

  non_responsibilities:
    - "Do not rewrite final package directly"
    - "Do not fetch new sources"
    - "Do not override user decisions"

  guardrails:
    - "Every issue must route to one owner"
    - "No unverified claim may remain"
    - "KEEP slides must not be modified"
    - "Timing must fit target or be explicitly escalated"

  revision_policy:
    retry_scope: "per_issue"
    max_revision_attempts:
      low: 0
      medium: 2
      high: 3
      critical: 3
    escalation_after_exhaustion: "user_final_review_gate"

  input_contract: "FinalConsistencyReviewInputBundle"
  output_contract: "ConsistencyReviewResult"
InputBundle
FinalConsistencyReviewInputBundle:
  task_id: "TASK_FINAL_CONSISTENCY_001"

  artifacts:
    change_plan_ref: "artifact://solution/change_plan.approved.json"
    structural_edit_plan_ref: "artifact://solution/structural_edit_plan.approved.json"
    narrative_plan_ref: "artifact://solution/narrative_plan.approved.json"
    slide_patches_ref: "artifact://solution/slide_patches.approved.json"
    new_slides_ref: "artifact://solution/new_slides.approved.json"
    speaker_notes_ref: "artifact://solution/speaker_notes.approved.json"
    timing_state_ref: "artifact://solution/timing_state.approved.json"

  evidence_map_ref: "artifact://g02/evidence_map.approved.json"

  output_contract:
    artifact: "ConsistencyReviewResult"
Final Package Builder
AgentDefinition
agent_definition:
  agent_id: "FinalPackageBuilder"
  graph: "SolutionDesignGraph"
  complexity_class: "deterministic_technical"

  responsibility:
    - "Build final output package"
    - "Export Markdown/YAML"
    - "Create Gamma prompt"
    - "Create NotebookLM brief"
    - "Create GPT Pro generation prompt"
    - "Create change log and audit report"

  non_responsibilities:
    - "Do not change content decisions"
    - "Do not rewrite slides"
    - "Do not alter evidence"

  guardrails:
    - "Export must preserve slide statuses"
    - "Every source reference must remain available"
    - "YAML must validate"
    - "Output folder structure must match contract"

  revision_policy:
    retry_scope: "export_package"
    max_revision_attempts:
      low: 0
      medium: 1
      high: 2
      critical: 3
    escalation_after_exhaustion: "technical_orchestrator_gate"

  input_contract: "FinalPackageBuilderInputBundle"
  output_contract: "FinalLecturePackage"
InputBundle
FinalPackageBuilderInputBundle:
  task_id: "TASK_PACKAGE_001"

  approved_solution_artifacts:
    change_plan_ref: "artifact://solution/change_plan.approved.json"
    structural_edit_plan_ref: "artifact://solution/structural_edit_plan.approved.json"
    narrative_plan_ref: "artifact://solution/narrative_plan.approved.json"
    slide_patches_ref: "artifact://solution/slide_patches.approved.json"
    new_slides_ref: "artifact://solution/new_slides.approved.json"
    speaker_notes_ref: "artifact://solution/speaker_notes.approved.json"
    timing_state_ref: "artifact://solution/timing_state.approved.json"

  approved_research_artifacts:
    evidence_map_ref: "artifact://g02/evidence_map.approved.json"
    selected_sources_ref: "artifact://g02/selected_sources.approved.json"

  export_targets:
    - "updated_lecture.yaml"
    - "updated_lecture.md"
    - "gamma_prompt.md"
    - "notebooklm_brief.md"
    - "gpt_pro_generation_prompt.md"
    - "change_log.md"
    - "audit_report.md"

  output_contract:
    artifact: "FinalLecturePackage"
11. User Change Plan Gate
11.1 Cel

Użytkownik zatwierdza ingerencje w prezentację, zanim system zacznie pisać konkretne slajdy.

11.2 Input
UserChangePlanGateInput:
  change_plan_ref: "artifact://solution/change_plan.reviewed.json"

  summary:
    keep_count: 20
    update_count: 8
    remove_count: 2
    add_count: 5
    merge_count: 2
    split_count: 3
    reorder_count: 4

  high_impact_changes:
    - slide_id: 12
      status: "UPDATE"
      reason: "Outdated methodological claim"
      evidence: [EV_001]

    - slide_id: 10
      status: "SPLIT"
      reason: "Too many concepts introduced at once"

    - slide_ids: [14, 15]
      status: "MERGE"
      reason: "Duplicate example"

  required_decisions:
    - decision_id: CD1
      type: "approve_statuses"

    - decision_id: CD2
      type: "approve_removals"

    - decision_id: CD3
      type: "approve_structural_changes"

    - decision_id: CD4
      type: "approve_new_slides"
11.3 Output
UserApprovedChangePlan:
  approved_change_plan_ref: "artifact://solution/change_plan.approved.json"

  user_overrides:
    - slide_id: 9
      original_status: "REMOVE"
      new_status: "KEEP"
      reason: "Author wants this example preserved"

  approved_statuses:
    keep: true
    update: true
    remove: true
    add: true
    merge: true
    split: true
    reorder: true
12. User Final Review Gate
12.1 Cel

Użytkownik sprawdza finalny projekt przed exportem.

12.2 Input
UserFinalReviewGateInput:
  final_preview_ref: "artifact://solution/final_preview.md"

  summary:
    total_slides_after_changes: 48
    estimated_duration_minutes: 88
    target_duration_minutes: 90
    high_risk_items_remaining: 0
    unresolved_claims:
      count: 1
      policy: "move_to_speaker_note_or_remove"

  review_sections:
    - "change_summary"
    - "new_slides_preview"
    - "updated_slides_preview"
    - "speaker_notes_sample"
    - "timing_summary"
    - "source_summary"

  required_decisions:
    - decision_id: FD1
      type: "approve_final_package"

    - decision_id: FD2
      type: "resolve_remaining_unresolved_claims"
12.3 Output
UserApprovedFinalPackage:
  approved_for_export: true
  final_adjustments:
    - type: "minor_note"
      slide_id: 23
      instruction: "Make example more practical"
13. Final output package
13.1 Struktura katalogów
output/
  updated_lecture.yaml
  updated_lecture.md
  gamma_prompt.md
  notebooklm_brief.md
  gpt_pro_generation_prompt.md
  change_log.md
  audit_report.md

research/
  01_bayesian_inference/
    papers/
    reviews/

  02_scalable_inference/
    papers/
    reviews/
13.2 Przykładowy updated_lecture.yaml
lecture:
  title: "Bayesian Statistics"
  audience: "master"
  duration_minutes: 90

slides:
  - id: 1
    status: KEEP
    title: "Introduction"
    bullets: []
    speaker_notes: "..."
    estimated_time_minutes: 2

  - id: 10
    status: SPLIT
    reason: "Too many concepts introduced at once"
    split_into:
      - id: "10a"
        title: "Prior distribution – intuition"
        bullets: []
        speaker_notes: "..."
      - id: "10b"
        title: "Likelihood – evidence model"
        bullets: []
        speaker_notes: "..."

  - id: 12
    status: UPDATE
    title: "Scalability of Bayesian methods"
    bullets:
      - "Exact inference can be costly in high-dimensional settings"
      - "Approximate methods reduce computational barriers"
      - "Modern probabilistic programming makes Bayesian workflows more accessible"
    sources: [P_014, P_022]
    speaker_notes: "..."
    estimated_time_minutes: 4

  - id: NEW_01
    status: ADD
    insert_after_slide: 12
    title: "Modern approximate inference"
    bullets: []
    speaker_notes: "..."
    sources: [P_014, P_022]
14. Granice między subgrafami
14.1 Intake → Research

Przechodzi:

UserApprovedIntakeBundle:
  approved_context: {}
  approved_domains: []
  approved_research_scope: {}
  locked_sections: []
  allowed_repair_modes: {}
  claim_cards: []
  concept_context_cards: []
  flow_issue_cards: []
  artifact_refs_for_lazy_hydration: []

Nie przechodzi:

cały PDF,
wszystkie slajdy,
pełny ConceptState,
pełny FlowState,
pełny DifficultyState,
pełny SlideDebtState.
14.2 Research → Solution

Przechodzi:

UserApprovedResearchBundle:
  approved_update_findings: []
  approved_optional_findings: []
  rejected_findings: []
  evidence_cards: []
  slide_impact_cards: []
  source_cards: []
  unresolved_claim_policy: {}
  artifact_refs_for_lazy_hydration: []

Nie przechodzi:

cały research corpus,
wszystkie PDF-y,
wszystkie paper reviews,
niezatwierdzone trendy,
odrzucone przez człowieka findings jako aktywne rekomendacje.
14.3 Solution → Export

Przechodzi:

FinalPackageBuilderInputBundle:
  approved_solution_artifacts:
    change_plan_ref: "..."
    structural_edit_plan_ref: "..."
    narrative_plan_ref: "..."
    slide_patches_ref: "..."
    new_slides_ref: "..."
    speaker_notes_ref: "..."
    timing_state_ref: "..."

  approved_research_artifacts:
    evidence_map_ref: "..."
    selected_sources_ref: "..."

  export_targets: []

Nie przechodzi:

niezatwierdzony change plan,
robocze wersje slajdów,
rejected findings,
pełne źródła bez potrzeby.
15. Minimalne review-loopy obowiązkowe
Intake
Extraction Integrity Review.
Structure Review.
Semantic Graph Review.
Claim Extraction Review.
Cross-Agent Reconciliation Review.
Intake Synthesis Review.
User Intake Gate.
Research
Research Plan Review.
Domain Search Review.
Claim Evidence Review.
Source Quality Review.
Retrieval Integrity Review.
Paper Review Quality Review.
Research Synthesis Review.
User Research Gate.
Solution
Change Plan Review.
User Change Plan Gate.
Structural Edit Review.
Narrative Review.
Slide Patch Review.
New Slide Review.
Speaker Notes Review.
Timing Review.
Final Consistency Review.
User Final Review Gate.
Export Integrity Review.
16. Podsumowanie architektury

System powinien działać jako zespół agentów, a nie jeden duży agent.

Najważniejsze zasady:

Trzy subgrafy:
Intake / Understanding,
Research,
Solution Design.
Nie przekazujemy pełnego stanu między grafami.
Przekazujemy typed handoff bundles, compact cards i artifact refs.
Stałe ograniczenia są w AgentDefinition, nie w stanie.
Retry policy jest w AgentDefinition / orchestrator config, nie w input bundle.
Reviewer nie poprawia artefaktu.
Reviewer wskazuje problem, severity, scope i route. Poprawia agent właściciel.
User Gates są strategiczne.
Człowiek zatwierdza:
rozumienie prezentacji,
zakres researchu,
wyniki researchu,
plan zmian,
finalny pakiet.
Solution Design działa selektywnie.
Slajdy dostają status:
KEEP,
UPDATE,
REMOVE,
ADD,
MERGE,
SPLIT,
REORDER.
Produktem końcowym jest paczka projektowa.
Nie musi to być od razu PPTX. Najlepszym outputem jest strukturalny Markdown/YAML + prompty do Gamma, NotebookLM i GPT Pro.
