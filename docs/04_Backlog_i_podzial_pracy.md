# Research Graph, backlog i sugerowany podział pracy

## 1. Cel backlogu

Backlog prowadzi od aktualnego szkieletu repozytorium do działającego Research Graph. Kolejność
wynika z zależności między kontraktami, agentami, skillami, reviewerem i bramkami człowieka.

Oznaczenia odpowiedzialności:

- `CONTENT`, treść agentów, skilli, kryteriów i komunikatów,
- `TOOLS`, deterministyczne narzędzia Research Graph, adaptery API, indeksowanie, downloader i
  przygotowanie dokumentów,
- `KH`, zgodność między modułami oraz warstwa systemowa i orkiestracyjna,
- `JOINT`, wspólna decyzja lub test integracyjny.

Oznaczenia nie są ostatecznym przydziałem osób. Mają ułatwić późniejszy podział pracy.

## 2. Decyzje wejściowe

### Zamknięte

- Jeden fizyczny `G02A10OutputReviewerAgent`.
- G02-A08 Claim Verification działa po G02-A07 Paper Review.
- G02-A02 Domain tworzy pulę bazową.
- G02-A03 Canonical Sources i G02-A04 Recent Developments rozszerzają pulę równolegle.
- G02-A05 Candidate Source Index przygotowuje rekomendacje, a człowiek zatwierdza źródła.
- Human Source Selection Gate występuje przed pobraniem.
- Człowiek otrzymuje Markdown i jasną instrukcję odpowiedzi.
- Skille mają relację wiele do wielu z agentami.
- Agent i skill są przenośnym Markdownem dla Codex i Claude Code.
- Definicje operacyjne są po angielsku.
- Human-readable output domyślnie jest po angielsku i respektuje `output_language`.
- Źródła zamknięte pozostają w indeksie i mogą trafić do kolejki bibliotecznej.
- Limity domyślne: 30 widocznych kandydatów, 12 miękko i 20 twardo dla pobierania.
- Candidate coverage i evidence coverage korzystają ze wspólnej macierzy.

### Status decyzji i integracji

1. `[RESOLVED: RESEARCH-GRAPH-INPUT-CONTRACT]`, zatwierdzone i wdrożone.
2. `[TK-DECISION: CLAIM-ASSESSMENT-MODEL]`, do podjęcia podczas przeglądu 1b1 G02-A08 Claim Verification.
3. `[KH-TODO: CODEX-RESEARCH-RUNTIME-ADAPTER]`, do implementacji w warstwie systemowej.

## 3. Faza A, wyrównanie repozytorium

### A1. Zatwierdzić dokumentację projektową

**Owner:** JOINT

**Działania:**

- przejrzeć cztery dokumenty,
- potwierdzić status rozwiązanych i otwartych flag,
- potwierdzić lokalizację dokumentacji w repo,
- rozstrzygnąć nazwy kontraktów i artifact refs,
- zamrozić wersję `Research Graph design v1`.

**Definition of done:** nie istnieje nierozstrzygnięta sprzeczność wpływająca na listę agentów,
kolejność grafu albo odpowiedzialność human gates.

### A2. Zaktualizować dokument główny Research Graph

**Owner:** JOINT

**Działania:**

- usunąć starą listę dziewięciu fizycznych reviewerów,
- opisać jeden reviewer z review profiles,
- przenieść Claim Verification,
- zastąpić Source Selection przez Candidate Source Index,
- dodać Human Source Selection Gate,
- opisać input, coverage i źródła OA,
- usunąć dołączone przykłady agent, skill i state z właściwej specyfikacji albo przenieść je do
  wyraźnie oznaczonego appendix.

### A3. Zmienić konwencje repozytorium

**Owner:** KH

**Pliki wymagające późniejszej aktualizacji:**

- `shared/contracts/`, docelowe boundary i intermediate schemas,
- `shared/scripts/g02/g02_flow.py`, realne scoping, agent invocation i fan-out/fan-in,
- `tests/test_research_graph.py`, testy ograniczonych input bundles, loops i gates,
- `docs/whole_outline.md`, wyrównanie starszego systemowego opisu Research Graph,
- konfiguracja instalatora, jeśli realne narzędzia literaturowe wymagają dodatkowego sposobu dystrybucji.

### A4. Dostosować manifest do jednego reviewera

**Owner:** KH

Manifest powinien umożliwiać wiele logicznych review nodes wskazujących
`g02-a10-output-reviewer`. Należy rozróżnić:

- logical node name,
- physical agent reference,
- review profile,
- reviewed producer,
- revision policy.

`graph_check.py` powinien sprawdzać także physical references, jeżeli zostaną dodane.

## 4. Faza B, wspólne standardy

### B1. Zamrozić szablon agenta

**Owner:** CONTENT

Sekcje:

- role description,
- Contract,
- Required Skills,
- Workflow,
- Acceptance Criteria,
- Boundaries,
- Failure handling,
- Resume.

Szablon musi opisywać `envelope@1`, brak bezpośredniej rozmowy z użytkownikiem i zachowanie
przy rewizji.

### B2. Zamrozić szablon skilla

**Owner:** CONTENT

Minimalny frontmatter `name` i `description`. Body: Contract, Workflow, Output requirements,
Boundaries, Failure handling, Resume.

Skill powinien być krótki i proceduralny. Nie umieszcza kodu adapterów API bezpośrednio w
Markdownie, lecz wskazuje deterministyczne narzędzie oraz jego kontrakt. Nie tworzyć
`references/`, `scripts/` i `assets/` bez rzeczywistej potrzeby.

Każdy skill ma obowiązkowe host adapters: `claude.frontmatter.yaml`, `claude.md` i `codex.md`.
Renderer scala wyłącznie właściwy wariant hosta. Testy muszą potwierdzać brak przecieku instrukcji
Claude do Codex i odwrotnie oraz brak mutacji neutralnego `SKILL.md`.

### B3. Zamrozić standard acceptance criteria

**Owner:** CONTENT

Każdy agent producent zawiera kryteria przekazywane reviewerowi. Kryteria muszą być:

- obserwowalne w artefakcie,
- ograniczone do odpowiedzialności producenta,
- powiązane z konkretnym polem lub wymaganiem,
- możliwe do zamiany na `revision_items`.

### B4. Severity mapping

**Status:** zamknięte

`ReviewDecision.findings[].severity` używa `minor`, `major`, `blocker`. `minor` i `major`
prowadzą do poprawki producenta, jeśli problem leży w jego zakresie. `blocker` prowadzi do
`BLOCKED`. Jeśli istniejący revision engine wymaga `low`, `medium`, `high`, `critical`, warstwa
integracyjna mapuje `low` na `minor`, `medium` i `high` na `major`, a `critical` na `blocker`.
Mapowanie w drugą stronę używa `minor` jako `low`, `major` jako `high` i `blocker` jako
`critical`.

## 5. Faza C, kontrakty i mechanika integracyjna

### C1. Zaimplementować ResearchGraphInput

**Owner:** KH po kontroli flagi input contract

Wymagane elementy:

- zatwierdzony kontekst wykładu,
- domeny i research scope,
- research drivers,
- existing source cards,
- constraints,
- selection profile,
- artifact refs,
- output language.

### C2. Utworzyć kontrakty agentów

**Owner:** KH z konsultacją CONTENT

Minimalne artifact types:

- `research_plan@1`,
- `domain_candidate_sources@1`,
- `canonical_candidate_sources@1`,
- `recent_candidate_sources@1`,
- `candidate_source_index@1`,
- `human_source_selection@1`,
- `human_approved_source_set@1`,
- `retrieved_corpus@1`,
- `paper_review@1`,
- `paper_evidence_card@1`,
- `claim_assessment_state@1`,
- `review_task@1`,
- `review_decision@1`,
- `research_state@1`,
- `evidence_map@1`,
- `human_research_validation_packet@1`,
- `human_approved_research_bundle@1`.

### C3. Zaimplementować shape checks

**Owner:** KH

Każdy agent wywołuje deterministyczny shape check przed zwróceniem artefaktu. Shape checks
kontrolują strukturę. Ocena sensu pozostaje po stronie agenta i reviewera.

### C4. Zaimplementować research graph manifest

**Owner:** KH

Manifest musi odzwierciedlać diagram z dokumentu architektury, fan-out i fan-in, dwa human
gates, reviewer loops oraz route back do planera przy upstream plan error.

## 6. Faza D, uniwersalny reviewer jako pierwszy pionowy wycinek

**Status implementacji:** kontrakty `review_task@1` i `review_decision@1`, agent, skill,
deterministyczne przygotowanie i finalizacja oraz operacje MCP są zaimplementowane. Testy są
odłożone do osobnego środowiska zgodnie z `07_Rejestr_DEV_TEST_1b1.md`.

### D1. Skill `g02-review-research-output`

**Owner:** CONTENT

Skill definiuje:

- porównanie artefaktu z review profile,
- klasyfikację findings,
- minimalny revision scope,
- root cause,
- decyzje APPROVED, REVISE i BLOCKED,
- zakaz samodzielnej naprawy artefaktu.

### D2. Agent `g02-a10-output-reviewer`

**Owner:** CONTENT

Agent przyjmuje dowolny artefakt Research Graph wraz ze specyficznym profilem. Nie zawiera
wszystkich kryteriów etapów w swoim głównym promptcie. Kryteria są przekazywane w wejściu.

### D3. Profile review

**Owner:** CONTENT

Przygotować profile:

- research plan,
- domain candidates,
- canonical sources,
- recent developments,
- candidate index,
- retrieved corpus,
- paper evidence,
- claim assessment,
- research synthesis.

Profile mogą być częścią input bundle generowanego na podstawie Acceptance Criteria agenta.
Identyfikatory i minimalne concerns są wspólne, natomiast pełne kryteria każdego profilu są
zamrażane razem z właściwym producentem. Reviewer nie utrzymuje osobnego, statycznego rejestru
kryteriów producentów.

### D4. Test pionowy

**Owner:** JOINT

Użyć prostego artefaktu ResearchPlan:

- poprawny wynik powinien przejść,
- brak coverage powinien prowadzić do REVISE,
- brak review profile powinien prowadzić do BLOCKED,
- wyczerpany limit prób powinien eskalować przez runtime.

## 7. Faza E, Planner

### E1. Skill `g02-a01-plan-research-scope`

**Owner:** CONTENT

Uwzględnić research drivers, source roles, coverage units, search strategy, stop rules,
constraints i output language.

### E2. Agent `g02-a01-planner`

**Owner:** CONTENT

Zdefiniować pełny kontrakt i acceptance criteria. Planner nie wyszukuje publikacji.

### E3. Integracja planner-reviewer

**Owner:** JOINT

Sprawdzić revision loop i route back przy brakującym albo zbyt szerokim planie.

## 8. Faza F, wyszukiwanie bazowe

### F1. Skill `g02-expand-research-query`

**Owner:** CONTENT

Skill przyjmuje zatwierdzony topic i zwraca kontrolowane terminy. Każdy termin ma origin,
purpose i mapowanie do topic. Rozszerzenie nie może zmienić research scope.

### F2. Skill `g02-search-scholarly-metadata`

**Owner:** CONTENT

Opisać wyszukiwanie realnych rekordów z indeksów, minimalne metadane, query log, provenance,
obsługę braków i neutralność stanowiskową.

Szczegóły wywołań API pozostają w adapterach technicznych.

### F2a. Adaptery discovery i wspólny kontrakt wyszukiwania

**Owner:** TOOLS

Zaimplementować wspólne wejście i wyjście JSON oraz adaptery OpenAlex, Semantic Scholar i
arXiv. Zapewnić paginację, retry dostawcy, provenance, jawne częściowe błędy i mapowanie do
wspólnego `CandidateSourceRecord`. Crossref może uzupełniać DOI i brakujące metadane.

### F3. Opcjonalny skill `g02-expand-citation-graph`

**Owner:** CONTENT

Może być współdzielony przez Domain i Canonical. Powinien używać zatwierdzonych seed sources i
zwracać powód dodania każdego rekordu.

### F4. Agent `domain-research`

**Owner:** CONTENT

Uruchamiany per topic. Zwraca bazową pulę, search log i wstępne mapowanie do coverage units.

### F5. Testy scenariuszy

**Owner:** JOINT

- topic z poprawnym zakresem,
- topic ze zbyt szerokim zapytaniem,
- brak abstraktów,
- częściowa awaria indeksu,
- wyniki wspierające i krytyczne,
- brak wystarczającego pokrycia.

## 9. Faza G, rozszerzenia canonical i recent

### G1. Skill `g02-classify-source-role`

**Owner:** CONTENT

Rozdzielić role source od jakości i access status. Każde przypisanie ma evidence signal i
confidence.

### G2. Agent `canonical-sources`

**Owner:** CONTENT

Uwzględnić monografie zamknięte, canonicality basis, access limitations, dostępne surrogates i
zakaz interpretowania niedostępnej treści.

### G3. Agent `recent-developments`

**Owner:** CONTENT

Uwzględnić recency window, maturity, peer-review status, preprint flag oraz core update versus
optional trend.

### G4. Integracja równoległa

**Owner:** KH

Canonical i Recent otrzymują zatwierdzoną pulę Domain i działają równolegle. Fan-in oczekuje
obu wyników albo jawnego degraded result.

## 10. Faza H, G02-A05 Candidate Source Index i bramka człowieka

### H1. Skille metadanych

**Owner:** CONTENT

Utworzyć:

- `g02-normalize-source-metadata`,
- `g02-a05-deduplicate-source-records`,
- `g02-a05-rank-source-candidates`,
- `g02-a05-annotate-source-candidates`,
- `g02-assess-source-coverage`.

### H2. Agent `candidate-source-index`

**Owner:** CONTENT

Agent tworzy indeks maszynowy i dokument dla człowieka. LLM używa wyłącznie dostępnego
abstraktu do summary i relevance reason. Brak abstraktu jest jawny.

### H3. Generator `candidate_source_review.md`

**Owner:** CONTENT z implementacją TOOLS

Dokument grupuje źródła według topic i roli, pokazuje coverage, zamknięte źródła, rezerwę i
znane luki.

### H4. Komunikaty Human Source Selection Gate

**Owner:** CONTENT

Przygotować komunikaty w języku wynikowym, definicje DOWNLOAD, LIBRARY, CITATION, RESERVE,
EXCLUDE i SEARCH_MORE oraz copyable response template.

### H5. Parser decyzji i final confirmation

**Owner:** KH

Orkiestrator akceptuje format strukturalny i zwykły język, pokazuje wynik parsowania oraz
wymaga finalnego potwierdzenia.

### H6. Coverage warnings

**Owner:** JOINT

Jeśli wybór człowieka narusza mandatory coverage, orkiestrator wyjaśnia skutek. Człowiek może
wybrać SEARCH_MORE albo jawnie zatwierdzić coverage exception.

## 11. Faza I, pobieranie

### I1. Skill `g02-a06-resolve-open-access`

**Owner:** CONTENT

Opisać semantyczną kolejność źródeł OA, wymagane pola wyniku, wersję dokumentu, licencję i
obsługę zamkniętych źródeł.

### I2. Skill `g02-a06-retrieve-open-access-document`

**Owner:** CONTENT

Opisać pobieranie wyłącznie źródeł zatwierdzonych, poszanowanie limitów, retry i brak
automatyzacji institutional access.

### I3. Skill `g02-a06-validate-retrieved-document`

**Owner:** CONTENT

Kontrola content type, nagłówka PDF, source ID, duplikatu i jawnego statusu błędu.

### I4. Agent `paper-retrieval`

**Owner:** CONTENT

Agent łączy trzy skille, nie ocenia jakości naukowej i zwraca RetrievedCorpus.

### I5. Adaptery API i downloader

**Owner:** TOOLS

Zweryfikować bieżące zasady OpenAlex, Crossref, Semantic Scholar, Unpaywall, arXiv, CORE oraz
DOAB/OAPEN. Zaimplementować provider adapters, kontrolę redirectów i content type, bezpieczny
zapis, checksum, deduplikację plików oraz jawne statusy niedostępności. Nie opierać implementacji
wyłącznie na historycznych limitach z dokumentu LitPipe.

## 12. Faza J, G02-A07 Paper Review

### J0. Przygotowanie pełnego tekstu

**Owner:** TOOLS

Zaimplementować ekstrakcję tekstu i indeks sekcji lub stron dla zatwierdzonego PDF. Narzędzie
ma umożliwiać wyszukanie relewantnych fragmentów i odczyt ograniczonych zakresów zamiast
umieszczania całego dokumentu w jednym kontekście. Zachować numery stron i lokalizacje dowodów.

### J1. Skill `g02-a07-extract-paper-evidence`

**Owner:** CONTENT

Procedura ukierunkowanego odczytu:

- przypisane claimy i topics,
- wyszukanie relewantnych sekcji,
- metoda, findings i limitations,
- dokładna evidence location,
- relation do claimu,
- access level i confidence,
- możliwość targeted second pass.

### J2. Agent `paper-review`

**Owner:** CONTENT

Jedna instancja na dokument. Agent zwraca PaperReview i EvidenceCards, bez pełnego tekstu w
handoff.

### J3. Token i context tests

**Owner:** JOINT

Sprawdzić krótki artykuł, długi artykuł, monografię z wybranym rozdziałem, brak OCR, artykuł
niezwiązany z przypisanym claimem oraz dokument zawierający instrukcje prompt injection.

## 13. Faza K, G02-A08 Claim Verification

### K1. Skill `g02-a08-assess-claim-evidence`

**Owner:** CONTENT

Zaimplementować semantykę evidence, currency, pedagogical i controversy status, confidence,
recommended action oraz unresolved questions.

### K2. Agent `claim-verification`

**Owner:** CONTENT

Agent używa zaakceptowanych EvidenceCards. Może poprosić o targeted second pass, ale nie
otrzymuje całego korpusu automatycznie.

### K3. Kontrola modelu przez KH

**Owner:** KH

Zamknąć `[TK-DECISION: CLAIM-ASSESSMENT-MODEL]` z TK podczas przeglądu 1b1 przed zamrożeniem
kontraktu.

### K4. Testy oceny

**Owner:** JOINT

- supported i current,
- supported, ale needs update,
- mixed evidence,
- oversimplified teaching claim,
- contested claim,
- insufficient evidence,
- obsolete claim,
- closed canonical source bez dostępu do tekstu.

## 14. Faza L, synteza i finalna bramka

### L1. Skill `g02-a09-synthesize-research-findings`

**Owner:** CONTENT

Tworzy evidence map, required updates, optional improvements, unresolved questions i kompaktowy
handoff. Nie dodaje nowych faktów.

### L2. Agent `g02-a09-synthesizer`

**Owner:** CONTENT

Przyjmuje wyłącznie zatwierdzone upstream artifacts. Każda rekomendacja wskazuje evidence refs.

### L3. Human Research Gate

**Owner:** JOINT

Przygotować komunikaty, decyzje użytkownika, obsługę odrzuconych findings i unresolved claim
policy. Użytkownik widzi podsumowanie, confidence, coverage i ograniczenia.

### L4. UserApprovedResearchBundle

**Owner:** KH

Zamrozić zatwierdzony pakiet i przekazać do Solution Graph bez pełnego korpusu.

## 15. Faza M, orchestrator

### M1. Skill `g02-orchestrate-research`

**Owner:** CONTENT z integracją KH

Skill:

- jest jedyną powierzchnią rozmowy,
- waliduje input,
- sekwencjonuje agentów,
- prowadzi fan-out i fan-in,
- uruchamia uniwersalnego reviewera,
- przekazuje revision items,
- obsługuje dwa human gates,
- zapisuje i wznawia state,
- nie przejmuje odpowiedzialności agentów wykonawczych.

### M2. Resume

**Owner:** KH

Wznowienie rozpoczyna się od pierwszego nieukończonego lub niezatwierdzonego etapu. Zamrożone
artefakty pozostają niezmienne. Human gate oczekujący na odpowiedź musi być resumable.

### M3. Polecenie wejściowe

**Owner:** KH

Utworzyć cienkie polecenie, na przykład `/research`, które kieruje do orchestrator skill i nie
duplikuje workflow.

## 16. Faza N, weryfikacja całości

### N1. Consistency checks

**Owner:** JOINT

Sprawdzić zgodność:

- graph manifest,
- plugin registration,
- agent names,
- skill names,
- contract refs,
- artifact names,
- orchestrator sequence,
- reviewer profiles,
- documentation.

### N2. Forward tests agentów i skilli

**Owner:** CONTENT

Testy powinny używać realistycznych, surowych input bundles. Agent testujący nie powinien
otrzymywać oczekiwanego rozwiązania ani diagnozy błędu.

### N3. End-to-end test

**Owner:** JOINT

Minimalny przebieg:

1. jeden topic,
2. jeden claim high,
3. pula Domain,
4. rozszerzenie Canonical i Recent,
5. G02-A05 Candidate Source Index,
6. decyzja człowieka,
7. jeden dostępny PDF i jedno źródło library,
8. G02-A07 Paper Review,
9. G02-A08 Claim Verification,
10. Synthesis,
11. Human Research Gate,
12. zamrożony UserApprovedResearchBundle.

### N4. Failure-path tests

**Owner:** JOINT

- brak input driver,
- awaria API,
- brak abstraktu,
- brak OA,
- niepoprawny PDF,
- reviewer REVISE,
- limit rewizji,
- SEARCH_MORE,
- coverage exception,
- unresolved claim,
- przerwanie i resume.

## 17. Definition of done dla pojedynczego agenta

Agent jest ukończony, gdy:

- plik zachowuje uzgodnioną strukturę,
- odpowiedzialność i granice nie nakładają się na sąsiadów,
- wejście i wyjście wskazują versioned contracts,
- Required Skills są kompletne,
- Workflow jest wykonalny i ograniczony,
- Acceptance Criteria są obserwowalne,
- Failure handling rozróżnia needs_input, degraded i failed,
- Resume opisuje rewizję i ponowne uruchomienie,
- agent zwraca envelope,
- agent przechodzi co najmniej jeden test poprawny i dwa testy trudne,
- uniwersalny reviewer potrafi ocenić jego artefakt z właściwym profilem.

## 18. Definition of done dla pojedynczego skilla

Skill jest ukończony, gdy:

- ma przenośny frontmatter,
- description jasno określa, kiedy autoryzowany agent ma go użyć,
- body jest krótkie i proceduralne,
- wejście i wyjście są jednoznaczne,
- stop conditions i failure handling są jawne,
- nie duplikuje odpowiedzialności innego skilla,
- nie zawiera niepotrzebnych plików,
- został sprawdzony na realistycznym zadaniu,
- jego wynik może zostać wykorzystany przez co najmniej jednego wskazanego agenta.

## 19. Definition of done dla Research Graph

Moduł jest ukończony, gdy:

- ResearchGraphInput przechodzi walidację,
- istnieje dziewięciu agentów wykonawczych i jeden reviewer,
- wszystkie agenty używają jawnych skilli,
- graf posiada dwa human gates,
- żaden PDF nie jest pobierany przed decyzją człowieka,
- G02-A05 Candidate Source Index pokazuje coverage i access status,
- reviewer loops działają na jednym fizycznym reviewerze,
- G02-A07 Paper Review działa per dokument,
- G02-A08 Claim Verification działa na EvidenceCards,
- unresolved claims pozostają jawne,
- Solution Graph otrzymuje kompaktowy pakiet,
- state można wznowić,
- graph manifest, plugin registration i dokumentacja są spójne,
- podstawowy przebieg oraz kluczowe failure paths są zweryfikowane.

## 20. Sugerowana kolejność przeglądu 1b1

Definicje agentów i skilli istnieją. Dalsza praca przebiega pionowymi wycinkami:

1. G02-A10 Output Reviewer i `g02-review-research-output`.
2. G02-A01 Planner i `g02-a01-plan-research-scope`.
3. G02-A02 Domain oraz query i metadata discovery.
4. G02-A03 Canonical Sources i citation expansion.
5. G02-A04 Recent Developments.
6. G02-A05 Candidate Source Index, ranking, coverage i Human Source Selection Gate.
7. G02-A06 Paper Retrieval oraz deterministyczne OA resolution, download i validation.
8. G02-A07 Paper Review oraz deterministyczny indeks tekstu PDF.
9. G02-A08 Claim Verification i `g02-a08-assess-claim-evidence`; w tym kroku zamknąć
   `[TK-DECISION: CLAIM-ASSESSMENT-MODEL]`.
10. G02-A09 Synthesizer i Human Research Gate.
11. Orchestrator, scoped inputs, revision loops i resume.
12. KH implementuje `[KH-TODO: CODEX-RESEARCH-RUNTIME-ADAPTER]` i wykonywany jest pełny test
    end-to-end bez no-op node runnera.

