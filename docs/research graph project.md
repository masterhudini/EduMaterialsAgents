8. Subgraf 2: Research Graph
8.1 Cel
Research Graph nie bada „tematu ogólnie”. Bada zatwierdzone claimy, domeny, luki i potrzeby aktualizacji.
8.2 Kontrakt wejścia do subgrafu
ResearchGraphInput:
  task_id: "RESEARCH_001"
  human_approved_context:
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
      related_claims: [CLM_001, CLM_003]      artifact_ref: "artifact://states/concept_state.approved.json#/concepts/C1"
  selected_flow_issue_cards:
    - issue_id: F_001
      severity: "high"
      summary: "Posterior is used before likelihood is explained"
      affected_slides: [6, 7]      fix_hint: "REORDER_OR_ADD_BRIDGE"
      artifact_ref: "artifact://states/flow_state.approved.json#/issues/F_001"
  locked_sections:
    - section_id: S1
      reason: "Author wants to keep opening narrative"
  artifact_refs_for_lazy_hydration:
    claim_state_ref: "artifact://states/claim_state.approved.json"
    concept_state_ref: "artifact://states/concept_state.approved.json"
    flow_state_ref: "artifact://states/flow_state.approved.json"
  output_contract:
    artifact: "HumanApprovedResearchBundle"
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
    RP --> RPR[Research Plan Reviewer]    RPR -->|REVISE via ResearchPlanner policy| RP
    RPR -->|APPROVED| P[Parallel Research Work]
    P --> DR1[G02-A02 Domain Agents]    P --> CV[G02-A08 Claim Verification Agent]    P --> RD[G02-A04 Recent Developments Agent]    P --> CS[G02-A03 Canonical Sources Agent]
    DR1 --> DSR[Domain Search Reviewer]    DSR -->|REVISE routed| DR1
    CV --> CER[Claim Evidence Reviewer]    CER -->|REVISE via ClaimVerification policy| CV
    RD --> RDR[G02-A10 Output Reviewer]    RDR -->|REVISE via RecentDevelopments policy| RD
    CS --> CSR[G02-A10 Output Reviewer]    CSR -->|REVISE via CanonicalSources policy| CS
    DSR -->|APPROVED| SS[Source Selection Agent]    CER -->|APPROVED| SS
    RDR -->|APPROVED| SS
    CSR -->|APPROVED| SS
    SS --> SQR[Source Quality Reviewer]    SQR -->|REVISE via SourceSelection policy| SS
    SQR -->|APPROVED| PR[G02-A06 Paper Retrieval Agent]
    PR --> PIR[Retrieval Integrity Reviewer]    PIR -->|REVISE via Retrieval policy| PR
    PIR -->|APPROVED| PRA[G02-A07 Paper Review Agents]
    PRA --> PRQR[G02-A10 Output Reviewer]    PRQR -->|REVISE via PaperReview policy| PRA
    PRQR -->|APPROVED| RS[G02-A09 Synthesizer Agent]
    RS --> RSR[Research Synthesis Reviewer]    RSR -->|REVISE via Synthesizer policy| RS
    RSR -->|BLOCKED: bad plan| RP
    RSR -->|APPROVED| H2[Human Research Gate]
    H2 -->|APPROVED| O[HumanApprovedResearchBundle]    H2 -->|NEEDS_CORRECTION| RS
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
    escalation_after_exhaustion: "human_research_scope_gate"
  input_contract: "ResearchPlannerInputBundle"
  output_contract: "ResearchPlan"
InputBundle
ResearchPlannerInputBundle:
  task_id: "TASK_RESEARCH_PLAN_001"
  human_approved_context:
    audience_level: "master"
    course_name: "Bayesian Statistics"
    teaching_goal: "refresh and improve logical flow"
  approved_research_scope:
    verify_claims:
      priority: ["high", "medium"]    include_recent_developments: true
    include_canonical_sources: true
    include_didactic_examples: true
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
  flow_issue_cards:
    - issue_id: F_001
      summary: "Posterior is used before likelihood is explained"
  output_contract:
    artifact: "ResearchPlan"
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
    escalation_after_exhaustion: "human_research_gate"
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
    related_claims: [CLM_001]    related_topics: [R1]    audience_level: "master"
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
    - "Create human research validation packet"
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
    escalation_after_exhaustion: "human_research_gate"
  input_contract: "ResearchSynthesizerInputBundle"
  output_contract:
    - "ResearchState"
    - "EvidenceMap"
    - "HumanResearchValidationPacket"
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
      - "human_research_validation_packet"
      - "solution_input_candidate"
  output_contract:
    artifacts:
      - "ResearchState"
      - "EvidenceMap"
      - "HumanResearchValidationPacket"
      - "SolutionInputCandidate"
9. Human Research Gate
9.1 Cel
Człowiek zatwierdza, które wyniki researchu mają wpływać na nową wersję wykładu.
9.2 Input
HumanResearchGateInput:
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
        related_claims: [CLM_001]        summary: "Claim about computational cost needs qualification."
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
HumanApprovedResearchBundle:
  approved_research_summary_ref: "artifact://g02/research_summary.approved.md"
  approved_update_findings:
    - finding_id: RF_001
      impact: "UPDATE"
      priority: "high"
      related_claims: [CLM_001]      evidence_cards:
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
 
agent: Collector: Domain
Isolated intake collector. Establishes the product's domains — the units the produced plugin will route between. Wrong domains here mis-shape the whole product, so this node extracts facts faithfully and refuses to guess: a domain it can't ground in the input is a question for the user, not an invention.
Contract
Input: {build_mode, description?, extend_target?}. Output (via the universal envelope): either
status: ok, producing domains: [{name, intent, signals}] (status confirmed for new, inferred for extend until the user confirms), or
status: needs_input, with a question (e.g. description too thin to derive any scope).
consumes: {build_mode, description?, extend_target?}
produces: domains[]{name, intent, signals} (FLAT — no faculty)
Workflow
Source by build_mode:
new → derive domains from the user's description.
extend → call plugin-searcher with focus: "domains" on extend_target; treat everything it returns as inferred (to be user-confirmed).
Sense check (this is validate_field_sense for domains): is there enough signal to name a real scope? If the description is empty, generic ("make something useful"), or otherwise gives no derivable scope → return needs_input asking for concrete purpose/tasks (local clarify ≤3 rounds; then escalate). NEVER fabricate a domain from nothing (§9.1).
For each domain, write:
name — a slug [a-z0-9-] (normalise via slugify).
intent — a BROAD, stable scope definition: which questions belong to this domain, phrased at the discipline's purpose level, NOT a list of features. State the boundary against the nearest sibling domain in one clause.
signals — 6–12 illustrative trigger phrases GENERATED from the intent (anchors, not match rules; do not ask the user for these).
Keep the list FLAT. Do not group into faculties — that decision belongs to the architect.
Validate shape before returning:
 
Fix any structural errors before returning.
Boundaries
DO NOT group domains into faculties or design routing — architect's job.
DO NOT invent a domain to fill an empty description — return needs_input.
DO NOT ask the user for signals; generate them from intent.
DO NOT write files or call the network (plugin-searcher excepted, via the Agent tool).
Failure handling
Degrade-don't-punt: in extend, if plugin-searcher returns format: unknown with no domain signal, fall back to asking the user from scratch (as in new) rather than guessing.
Resume
Stateless; re-run refines from the same input. On re-run after user confirmation, mark previously-inferred domains confirmed.
python3 -c "import sys; sys.path.insert(0,'$CLAUDE_PLUGIN_ROOT/shared/scripts'); \  from intake.domain_shape import check_domains; import json,sys; \  print(check_domains(json.load(sys.stdin)))" <<< '<domains-json>'
 
skill: 
---
name: stack-architect-intake
version: 1.0.0
model: opus
description: >-
  Use when the user wants to BUILD or EXTEND an agent-stack / plugin for any domain — triggers
  like "build a plugin for", "create an agent stack", "zbuduj plugin", "stwórz stack agentów",
  "extend my plugin", or the /build-stack command. The intake phase of stack-architect:
  orchestrates the intake nodes (build-mode-prober, collectors, stack-auditor, understand-check),
  owns the conversation with the user (intake nodes are isolated and return needs_input), and
  runs the final GATE that freezes a complete, coherent draft into target_stack_spec@2. Covers
  ONLY intake; the design phase (graph building) is out of scope. Do NOT use to run a built
  plugin's own logic — only to build/extend one. Entry point for the meta-factory.
---
# Stack Architect — Intake Phase
The factory's front door. Collects the facts needed to build a plugin and freezes them into a
`target_stack_spec@2`. It does NOT design the graph here — that is the later (out-of-scope)
phase. Intake is about FACTS; design is about structure.
**Role:** orchestrator + host of the user conversation. The intake nodes are isolated and
cannot talk to the user; when one returns `needs_input`, THIS skill relays the question and
feeds the answer back. It sequences the nodes, maintains `draft.json`, and runs the GATE.
## Contract
**Input:** `{request, plugin_name, description?}` from the user.
**Output:** a frozen `target_stack_spec@2` (or a `blocked`/`cancelled` draft).
- consumes: user request
- produces: `target_stack_spec@2`
## Workflow (intake)
> The canonical node sequence and edges live in `shared/graphs/g01.graph.json` (single
> source of truth). This Workflow must agree with it; `graph_check.py` verifies the two,
> plus `plugin.json`, never drift apart.
1. **Probe basics** — `build-mode-prober` reads the full installed plugin and skill inventory
   with descriptions, plus routing/similarity signals, and returns either explicit
   `build_mode`/`align_with_installed` or `build_mode: undecided`. Do not ask extend-vs-new
   yet when the request is ambiguous; first collect enough domain signal.
2. **Collect domain** — run `collector-domain` from the user's basic request/description.
   This gives the scan a concrete domain target.
3. **Scan installed plugins/skills** — always run `plugin-scanner` after `collector-domain`.
   Present its domain-aware report to the user together with the prober's full plugin/skill
   inventory and collision/similarity signals. Then ask whether to build a new stack, extend
   an existing one, and whether the new stack should align with installed boundaries
   (`align_with_installed`).
4. **Audit (extend only)** — `stack-auditor` on `extend_target`. Present the report; on
   "repair", apply the extend->new promotion (build_mode flips, `mode_switched_from=extend`,
   re-check scheduled).
5. **Collect remaining facts** — run `collector-process`, `collector-quality`, and
   `boundary-extractor` only when `align_with_installed`. After each, run `validate_field_type`
   locally; on failure or `needs_input`, relay to the user (clarify ≤3) and route back to that
   collector.
6. **Global understand-check** — `understand-check` over the full draft. On conflict, relay to
   the user; if unresolved after the guard, the draft is `blocked` — STOP, do not GATE. Re-run
   this check after any extend->new promotion.
7. **GATE + FREEZE** — run `gate_status`; if not ok, route each reason back to its
   `route_back_to` collector and loop. Never force a freeze. If ok, `pass_gate_and_freeze`
   → `target_stack_spec@2` (product-card filter: no process/meta keys, no `skills/meta` paths).
## Boundaries
- DO NOT design the graph, faculties, data_artifacts, or orchestration here — that is the
  (out-of-scope) design phase. Intake stops at the frozen spec.
- DO NOT freeze a `blocked` or incomplete draft — route back and clarify instead.
- DO NOT let intake nodes talk to the user directly; you are the only conversational surface.
## Failure handling
Degrade-don't-punt: if the user cancels, mark the draft `abandoned` (kept for audit, not
auto-resumed). If a node fails irrecoverably, surface its issues; never emit a partial spec.
## Resume
`draft.json` is resumable via `resume_token`; re-entry continues from the first unfilled or
unconfirmed field. A frozen spec is immutable — changes require a new intake.
 
 
state: 
{
  "plugin_name": "research-agents",
  "description": "Extension of research-agents for end-to-end English finance Data Science PhD research, from topic and literature through modeling, validation, publications, and dissertation traceability.",
  "build_mode": "extend",
  "align_with_installed": true,
  "extend_target": "/home/khudaszek/.codex/plugins/research-agents",
  "domains": [
    {
      "name": "doctoral-research-management",
      "intent": "Manage an English-language finance Data Science PhD as a coherent multi-year research program, preserving traceability from thesis topic through contribution, research questions, hypotheses, methods, evidence, papers, chapters, and review feedback.",
      "signals": [
        "phd",
        "doctorate",
        "doctoral thesis",
        "dissertation",
        "research roadmap",
        "contribution",
        "research questions",
        "hypotheses",
        "traceability",
        "chapter plan",
        "supervisor feedback"
      ]
    },
    {
      "name": "empirical-finance-modeling",
      "intent": "Support empirical finance and econometric modeling decisions, including time-series design, causal and predictive modeling, diagnostics, robustness checks, backtesting, and interpretation against finance theory.",
      "signals": [
        "empirical finance",
        "econometrics",
        "time series",
        "asset pricing",
        "volatility",
        "risk",
        "VAR",
        "Granger",
        "cointegration",
        "robustness",
        "backtesting"
      ]
    },
    {
      "name": "data-science-modeling",
      "intent": "Support Data Science and machine-learning modeling for financial research, including feature engineering, leakage-safe validation, model comparison, explainability, reproducibility, and computational experiment tracking.",
      "signals": [
        "machine learning",
        "Data Science",
        "feature engineering",
        "cross-validation",
        "data leakage",
        "SHAP",
        "model comparison",
        "forecasting",
        "classification",
        "regression",
        "experiment tracking"
      ]
    },
    {
      "name": "research-data-pipeline",
      "intent": "Design and govern research data pipelines for finance Data Science, including data sourcing, ingestion, cleaning, schema design, versioning, quality checks, reproducible notebooks, and analysis-ready datasets.",
      "signals": [
        "data pipeline",
        "dataset",
        "data quality",
        "schema",
        "preprocessing",
        "ETL",
        "ELT",
        "versioning",
        "notebook",
        "reproducibility",
        "BigQuery"
      ]
    },
    {
      "name": "scholarly-literature-synthesis",
      "intent": "Produce structured scholarly literature reviews, methodology comparisons, citation evidence, gap maps, and publication-ready literature sections for finance and Data Science research.",
      "signals": [
        "literature review",
        "state of the art",
        "Scopus",
        "WoS",
        "citations",
        "gap map",
        "methodology review",
        "BibTeX",
        "related work",
        "theoretical contribution"
      ]
    },
    {
      "name": "thesis-and-paper-writing",
      "intent": "Draft, validate, and revise English academic manuscripts and thesis chapters, ensuring each claim is supported by traceable results, literature, tables, figures, and methodological justification.",
      "signals": [
        "write paper",
        "manuscript",
        "thesis chapter",
        "abstract",
        "introduction",
        "methods",
        "results",
        "discussion",
        "journal",
        "reviewer response",
        "academic English"
      ]
    },
    {
      "name": "publication-quality-governance",
      "intent": "Enforce a publication-grade quality standard suitable for a Scopus-oriented finance/Data Science PhD reviewed by supervisors, doctoral committee members, external reviewers, and journal reviewers.",
      "signals": [
        "quality check",
        "Scopus",
        "reviewer",
        "supervisor",
        "committee",
        "replication",
        "robustness",
        "audit trail",
        "standards",
        "evidence",
        "publication quality"
      ]
    }
  ],
  "process_current": "- Route broad or multi-step research questions through research-orchestrator, while direct single-domain requests go to the relevant specialist skill.\n- Run structured literature reviews through literature-review, producing plans, shortlists, evidence files, BibTeX, and Quarto reports.\n- Use data-engineering, EDA, econometrics, ML forecasting, NLP, and reporting skills for pipeline-specific research artifacts.\n- Use paper-writing and section-specific paper skills to draft article sections with traceability between claims, artifacts, and citations.\n- Delegate heavy retrieval, compute, batch inference, and paragraph validation to isolated subagents where appropriate.",
  "process_target": "- Define the PhD topic, expected scientific contribution, finance/Data Science scope, and publication strategy in English.\n- Build and maintain a doctoral research map linking topic, contribution, research questions, hypotheses, methods, datasets, artifacts, papers, thesis chapters, and review feedback.\n- Conduct structured literature reviews and gap mapping for empirical finance, econometrics, machine learning, and financial Data Science.\n- Formulate research questions, hypotheses, identification or modeling strategies, and validation plans before running analysis.\n- Design research data pipelines covering sources, ingestion, cleaning, schema, versioning, data quality checks, and reproducible analysis-ready datasets.\n- Run EDA, preprocessing, feature engineering, econometric analysis, machine-learning experiments, and optional NLP/LLM components when the research question requires them.\n- Validate results through leakage checks, time-aware validation, backtesting, robustness checks, diagnostics, sensitivity analysis, and model comparison.\n- Interpret findings against finance theory, Data Science methodology, and the reviewed literature, explicitly separating causal, predictive, and descriptive claims.\n- Draft and revise English papers and thesis chapters with claim-level traceability to literature, data, methods, results, tables, figures, and appendices.\n- Prepare supervisor, committee, journal-review, and Scopus-oriented quality checks before treating an artifact as publication-ready.",
  "output_types": [
    "doctoral_research_map",
    "literature_review_report",
    "gap_map",
    "rq_hypothesis_register",
    "methodology_decision_memo",
    "data_pipeline_spec",
    "analysis_notebook",
    "model_experiment_report",
    "robustness_validation_report",
    "manuscript_section",
    "thesis_chapter",
    "publication_quality_checklist"
  ],
  "quality_profile": {
    "name": "Scopus-grade English finance Data Science PhD standard",
    "context_description": "The stack supports an English-language PhD at the intersection of informatics/Data Science and economics/finance. Outputs are expected to survive supervisor review, doctoral committee scrutiny, external review, and Scopus-oriented journal peer review. Poor output can create false empirical claims, invalid financial modeling conclusions, irreproducible experiments, weak publications, or a fragile dissertation argument.",
    "required_artifacts": [
      "A traceability record linking each research question and hypothesis to data, methods, tests, results, tables or figures, manuscript sections, and thesis chapters.",
      "A literature evidence trail with search strategy, inclusion/exclusion logic, shortlisted papers, citation metadata, BibTeX, and gap synthesis.",
      "A methodology justification that distinguishes descriptive, predictive, causal, and econometric claims and states why each method is appropriate.",
      "A reproducible data lineage artifact covering data sources, transformations, schema, quality checks, versioning, and analysis-ready datasets.",
      "A validation package covering leakage checks, time-aware validation, diagnostics, robustness checks, sensitivity analysis, backtesting where applicable, and model comparison.",
      "An interpretation note connecting results to finance theory, Data Science methodology, and prior literature without overstating causality or external validity.",
      "A publication-readiness checklist for English academic style, Scopus/journal fit, figures/tables, references, limitations, ethical or compliance issues, and reviewer-facing evidence.",
      "A decision log recording major modeling, data, literature, and writing choices with rationale and reviewer/supervisor feedback resolution."
    ],
    "reference": null
  },
  "existing_boundary_rules": [
    {
      "from_plugin": "research-agents",
      "rule": "research-orchestrator is the entry point for cross-domain planning and routing; unambiguous single-domain work should route directly to the matching specialist skill.",
      "rationale": "The existing orchestrator explicitly separates multi-step orchestration from domain execution to avoid duplicating specialist logic."
    },
    {
      "from_plugin": "research-agents",
      "rule": "literature-review owns structured retrieval, screening, synthesis, BibTeX, and literature-report artifacts; it does not own empirical modeling or manuscript drafting.",
      "rationale": "The literature skill has a gated review workflow and hands methodology decisions or citation artifacts to downstream research and writing components."
    },
    {
      "from_plugin": "research-agents",
      "rule": "data-engineering, eda, econometrics, ml-forecasting, and nlp-text own their respective analytical artifacts; paper-writing consumes those artifacts rather than recomputing them.",
      "rationale": "Existing skills define clear handoffs from analysis artifacts to reporting and writing."
    },
    {
      "from_plugin": "research-agents",
      "rule": "paper-writing owns interactive manuscript drafting, claim validation, traceability, and section coherence; project issues discovered during writing route back to analytical or literature skills.",
      "rationale": "The paper-writing workflow explicitly validates paragraphs against artifacts and routes missing evidence to the responsible research skill."
    },
    {
      "from_plugin": "research-agents",
      "rule": "heavy retrieval, compute, batch inference, and paragraph validation should be delegated to isolated subagents rather than kept in the main conversation context.",
      "rationale": "The plugin already protects the main context from verbose or expensive operations through dedicated subagents."
    }
  ]
}
