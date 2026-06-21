# Research Graph, plan finalizacji agentów i skilli 1b1

## 1. Cel i status

Ten dokument jest wykonawczym planem finalizacji Research Graph. Uzupełnia backlog z
`04_Backlog_i_podzial_pracy.md` o ścisłą kolejność pracy, granice pionowych wycinków i bramkę
pozwalającą zamknąć jeden zestaw przed rozpoczęciem następnego.

Aktualny etap: repozytoryjna migracja namespace przed zestawem 2. Implementacja i retest
reviewera są zakończone; migracja nazw `g02` jest zakończona dewelopersko i oczekuje na osobny
TEST 1E oraz decyzję o commicie.

Aktualny podetap: `1E. Namespace g02`, zakończony dewelopersko.

Kolejny etap nie rozpoczyna się przed ukończeniem implementacji bieżącego zestawu, przeglądem
zmian i zatwierdzeniem przez właściciela repozytorium.

## 2. Tryb pracy i rozdzielenie testów

Finalizacja komponentów oraz ich testowanie są prowadzone w dwóch osobnych fazach.

W bieżącej fazie deweloperskiej:

- modyfikowane są definicje agentów i skilli,
- zamrażane są kontrakty i identyfikatory artefaktów,
- implementowane są deterministyczne narzędzia i konfiguracja,
- aktualizowane są manifesty i dokumentacja,
- zapisywana jest lista scenariuszy wymagających późniejszej weryfikacji,
- nie są tworzone ani uruchamiane testy.

Testy powstaną później w osobnym katalogu i osobnym środowisku. Faza testowa obejmie testy
jednostkowe, kontraktowe, integracyjne, mocki providerów, forward tests agentów, failure paths,
resume oraz pełny przebieg end-to-end.

Status implementacji i odłożone scenariusze są prowadzone w `07_Rejestr_DEV_TEST_1b1.md`.

## 3. Stały cykl pojedynczego zestawu

Każdy zestaw agent, skille, kontrakty, narzędzia i testy przechodzi ten sam cykl:

1. Audyt celu, odpowiedzialności, wejść, wyjść i granic.
2. Zamrożenie wersjonowanych kontraktów i identyfikatorów artefaktów.
3. Finalizacja definicji agenta i wszystkich wymaganych skilli.
4. Implementacja deterministycznych narzędzi i konfiguracji wymaganych przez ten zestaw.
5. Zapisanie jawnych failure paths, zasad resume i scenariuszy do późniejszego testowania.
6. Aktualizacja dokumentacji, manifestu i rejestracji, jeśli zestaw ich dotyczy.
7. Przegląd zmian implementacyjnych i potwierdzenie kompletności zakresu.
8. Raport zamykający z listą zmian, ograniczeń i odłożonych scenariuszy testowych.
9. Zatwierdzenie właściciela repozytorium przed przejściem do następnego zestawu.

Pierwszy zestaw reviewera jest przypadkiem bootstrapowym. Przechodzi niezależny przegląd według
jawnej checklisty, ponieważ jego własna decyzja nie może być jedynym dowodem poprawności.

## 4. Kolejność pionowych wycinków

### 4.1. G02-A10 Output Reviewer

Komponenty:

- `agents/g02-a10-output-reviewer.md`,
- `skills/g02-review-research-output/`,
- `review_task@1`,
- `review_decision@1`,
- walidatory shape i integracyjny seam reviewera,
- mapowanie severity i podstawowa obsługa rewizji.

Testy obejmują `APPROVED`, `REVISE`, `BLOCKED`, brak lub sprzeczność profilu, stabilne finding
IDs, read-only review, prompt injection, nieprawidłowy artefakt i wyczerpanie limitu prób.

### 4.2. G02-A01 Planner

Komponenty:

- `agents/g02-a01-planner.md`,
- `skills/g02-a01-plan-research-scope/`,
- `research_plan@1`,
- scoped planner input,
- shape check planu,
- profil `research_plan`.

Plan musi zawierać bounded topics, research drivers, source roles, coverage units i stop rules.

### 4.3. G02-A02 Domain

Komponenty:

- `agents/g02-a02-domain.md`,
- `skills/g02-expand-research-query/`,
- `skills/g02-search-scholarly-metadata/`,
- `domain_candidate_sources@1`,
- `source_record@1`,
- `literature_tool_result@1`.

W tym etapie powstaje wspólny setup providerów: konfiguracja usług, zmienne środowiskowe dla
sekretów i adresów e-mail, katalogi cache, corpus, artifacts i logs, timeouty, retry, paginacja,
rate limiting oraz walidacja konfiguracji przy starcie. Implementowane są pierwsze klienty
OpenAlex, Semantic Scholar, arXiv i wymaganych usług uzupełniających wraz z mockami API.

### 4.4. G02-A03 Canonical Sources

Komponenty:

- `agents/g02-a03-canonical-sources.md`,
- `skills/g02-expand-citation-graph/`,
- `skills/g02-classify-source-role/`,
- `canonical_candidate_sources@1`,
- deterministyczne rozszerzanie references i citations.

Wynik zachowuje podstawę kanoniczności, proweniencję i jawne ograniczenia dostępu.

### 4.5. G02-A04 Recent Developments

Komponenty:

- `agents/g02-a04-recent-developments.md`,
- współdzielone skille query, metadata discovery, source role i citation expansion,
- `recent_candidate_sources@1`,
- reguły okna czasowego, maturity i recency.

### 4.6. G02-A05 Candidate Source Index

Komponenty:

- `agents/g02-a05-candidate-source-index.md`,
- `skills/g02-normalize-source-metadata/`,
- `skills/g02-a05-deduplicate-source-records/`,
- `skills/g02-classify-source-role/`,
- `skills/g02-a05-rank-source-candidates/`,
- `skills/g02-a05-annotate-source-candidates/`,
- `skills/g02-assess-source-coverage/`,
- `candidate_source_index@1`,
- `human_source_selection@1`,
- `human_approved_source_set@1`.

Etap obejmuje generator `candidate_source_review.md`, parser decyzji, final confirmation,
`SEARCH_MORE`, coverage exceptions i Human Source Selection Gate.

### 4.7. G02-A06 Paper Retrieval

Komponenty:

- `agents/g02-a06-paper-retrieval.md`,
- `skills/g02-a06-resolve-open-access/`,
- `skills/g02-a06-retrieve-open-access-document/`,
- `skills/g02-a06-validate-retrieved-document/`,
- `retrieved_corpus@1`.

Łańcuch OA obejmuje Unpaywall, OpenAlex OA, arXiv, CORE i DOAB/OAPEN. Implementacja zawiera
bezpieczny downloader, kontrolę redirectów i rozmiaru, sygnaturę pliku, checksum, wykrywanie
duplikatów, zgodność dokumentu ze źródłem oraz zakaz pobierania bez decyzji `DOWNLOAD`.

### 4.8. G02-A07 Paper Review

Komponenty:

- `agents/g02-a07-paper-review.md`,
- `skills/g02-a07-extract-paper-evidence/`,
- `paper_review@1`,
- `paper_evidence_card@1`,
- przygotowanie tekstu PDF,
- indeks stron i sekcji,
- targeted retrieval i targeted second pass.

Testy obejmują długie dokumenty, monografie, brak OCR, błędny PDF, dokument nieistotny dla
claimu, prompt injection i dokładność evidence locations.

### 4.9. G02-A08 Claim Verification

Komponenty:

- `agents/g02-a08-claim-verification.md`,
- `skills/g02-a08-assess-claim-evidence/`,
- `skills/g02-assess-source-coverage/`,
- `claim_assessment_state@1`.

Przed zamrożeniem kontraktu należy zamknąć z TK
`[TK-DECISION: CLAIM-ASSESSMENT-MODEL]`. Testy obejmują dowody wspierające, mieszane,
przestarzałe, kontrowersyjne i niewystarczające oraz źródła bez dostępnej treści.

### 4.10. G02-A09 Synthesizer

Komponenty:

- `agents/g02-a09-synthesizer.md`,
- `skills/g02-a09-synthesize-research-findings/`,
- `research_state@1`,
- `evidence_map@1`,
- `human_research_validation_packet@1`,
- `solution_input_candidate@1`,
- finalizacja `user_approved_research_bundle@1`.

Etap obejmuje Human Research Gate, obsługę odrzuconych findings, unresolved claim policy,
potwierdzenie decyzji człowieka i immutable freeze.

### 4.11. G02 Orchestrator

Komponenty:

- `skills/g02-orchestrate-research/`,
- `commands/research.md`,
- scoped input bundles,
- producer i reviewer loops,
- fan-out i fan-in,
- revision routing,
- oba human gates,
- state persistence, atomowy zapis i resume,
- event log i zamrażanie zaakceptowanych artefaktów.

Orkiestrator jest finalizowany po zamrożeniu kontraktów wszystkich producentów.

### 4.12. Ponowny przegląd G02-A10 Output Reviewera

Reviewer przechodzi regresję na wszystkich profilach: `research_plan`, `domain_candidates`,
`canonical_sources`, `recent_developments`, `candidate_index`, `retrieved_corpus`,
`paper_evidence`, `claim_assessment` i `research_synthesis`.

Kontrola potwierdza, że reviewer nie przejął odpowiedzialności producentów, zachowuje granice
kryteriów i poprawnie klasyfikuje root causes po wdrożeniu wszystkich kontraktów.

### 4.13. Integracja końcowa i osobna faza testowa

Zakres:

- pełne testy `pytest`,
- build i packaging Claude oraz Codex,
- testy mockowanych providerów i kontrolowane smoke tests,
- pełny przebieg Research Graph end-to-end,
- failure paths, przerwanie i resume,
- zamknięcie `[KH-TODO: CODEX-RESEARCH-RUNTIME-ADAPTER]`,
- aktualizacja starszych dokumentów,
- końcowy consistency check repozytorium.

## 5. Bramka ukończenia implementacji pojedynczego zestawu

Zestaw może zostać przekazany do commita, gdy:

- odpowiedzialność agenta i skilli jest jednoznaczna,
- wszystkie używane kontrakty istnieją i przechodzą walidację,
- potrzebne narzędzia deterministyczne są zaimplementowane,
- operacje zewnętrzne mają timeout, retry, proweniencję i kontrolowane błędy,
- jawne failure paths i resume są opisane w implementacji,
- scenariusze późniejszych testów zostały zapisane,
- dokumentacja i manifest nie przeczą implementacji,
- raport zamykający wymienia zmiany, odłożone testy oraz pozostałe zależności zewnętrzne.

Zatwierdzony zestaw nie może zawierać rozpoczętej implementacji następnego agenta.
