# Research Graph, backlog i sugerowany podział pracy

## 1. Cel backlogu

Backlog prowadzi od aktualnego szkieletu repozytorium do działającego Research Graph. Kolejność
wynika z zależności między kontraktami, agentami, skillami, reviewerem i bramkami człowieka.

Oznaczenia odpowiedzialności:

- `CONTENT`, treść agentów, skilli, kryteriów i komunikatów,
- `KH`, zgodność między modułami oraz warstwa systemowa i orkiestracyjna,
- `JOINT`, wspólna decyzja lub test integracyjny.

Oznaczenia nie są ostatecznym przydziałem osób. Mają ułatwić późniejszy podział pracy.

## 2. Decyzje wejściowe

### Zamknięte

- Jeden fizyczny `ResearchOutputReviewerAgent`.
- Claim Verification działa po Paper Review.
- Domain Research tworzy pulę bazową.
- Canonical Sources i Recent Developments rozszerzają pulę równolegle.
- Candidate Source Index przygotowuje rekomendacje, a człowiek zatwierdza źródła.
- Human Source Selection Gate występuje przed pobraniem.
- Człowiek otrzymuje Markdown i jasną instrukcję odpowiedzi.
- Skille mają relację wiele do wielu z agentami.
- Agent i skill są przenośnym Markdownem dla Codex i Claude Code.
- Definicje operacyjne są po angielsku.
- Human-readable output domyślnie jest po angielsku i respektuje `output_language`.
- Źródła zamknięte pozostają w indeksie i mogą trafić do kolejki bibliotecznej.
- Limity domyślne: 30 widocznych kandydatów, 12 miękko i 20 twardo dla pobierania.
- Candidate coverage i evidence coverage korzystają ze wspólnej macierzy.

### Do kontroli KH

1. `[KH-DECISION: RESEARCH-GRAPH-INPUT-CONTRACT]`
2. `[KH-DECISION: CLAIM-ASSESSMENT-MODEL]`

Kontrola KH może zmienić nazwy i serializację pól. Zmiana znaczenia wymaga wspólnej decyzji i
aktualizacji dokumentacji.

## 3. Faza A, wyrównanie repozytorium

### A1. Zatwierdzić dokumentację projektową

**Owner:** JOINT

**Działania:**

- przejrzeć cztery dokumenty,
- zatwierdzić dwie flagi KH,
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

- `agents/README.md`, lista dziesięciu agentów,
- `skills/README.md`, orchestrator i nieinteraktywne skille wykonawcze,
- `shared/graphs/README.md`, logical node oraz physical `agent_ref`,
- `shared/contracts/README.md`, nowe artifact types,
- `shared/scripts/research/README.md`, nowe shape checks i kolejność,
- `docs/research graph project.md`, nowa specyfikacja,
- `plugin.json`, rejestracja komponentów.

### A4. Dostosować manifest do jednego reviewera

**Owner:** KH

Manifest powinien umożliwiać wiele logicznych review nodes wskazujących
`research-output-reviewer`. Należy rozróżnić:

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

Skill powinien być krótki, proceduralny i pozbawiony kodu adapterów API. Nie tworzyć
`references/`, `scripts/` i `assets/` bez rzeczywistej potrzeby.

### B3. Zamrozić standard acceptance criteria

**Owner:** CONTENT

Każdy agent producent zawiera kryteria przekazywane reviewerowi. Kryteria muszą być:

- obserwowalne w artefakcie,
- ograniczone do odpowiedzialności producenta,
- powiązane z konkretnym polem lub wymaganiem,
- możliwe do zamiany na `revision_items`.

### B4. Uzgodnić severity mapping

**Owner:** JOINT

Runtime używa `low`, `medium`, `high`, `critical` dla revision policy, a envelope używa
`minor`, `major`, `blocker`. Należy zdefiniować mapowanie albo utrzymać skale w oddzielnych
warstwach z jasną regułą użycia.

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

### D1. Skill `review-research-output`

**Owner:** CONTENT

Skill definiuje:

- porównanie artefaktu z review profile,
- klasyfikację findings,
- minimalny revision scope,
- root cause,
- decyzje APPROVED, REVISE i BLOCKED,
- zakaz samodzielnej naprawy artefaktu.

### D2. Agent `research-output-reviewer`

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

### D4. Test pionowy

**Owner:** JOINT

Użyć prostego artefaktu ResearchPlan:

- poprawny wynik powinien przejść,
- brak coverage powinien prowadzić do REVISE,
- brak review profile powinien prowadzić do BLOCKED,
- wyczerpany limit prób powinien eskalować przez runtime.

## 7. Faza E, Planner

### E1. Skill `plan-research-scope`

**Owner:** CONTENT

Uwzględnić research drivers, source roles, coverage units, search strategy, stop rules,
constraints i output language.

### E2. Agent `research-planner`

**Owner:** CONTENT

Zdefiniować pełny kontrakt i acceptance criteria. Planner nie wyszukuje publikacji.

### E3. Integracja planner-reviewer

**Owner:** JOINT

Sprawdzić revision loop i route back przy brakującym albo zbyt szerokim planie.

## 8. Faza F, wyszukiwanie bazowe

### F1. Skill `expand-research-query`

**Owner:** CONTENT

Skill przyjmuje zatwierdzony topic i zwraca kontrolowane terminy. Każdy termin ma origin,
purpose i mapowanie do topic. Rozszerzenie nie może zmienić research scope.

### F2. Skill `search-scholarly-metadata`

**Owner:** CONTENT

Opisać wyszukiwanie realnych rekordów z indeksów, minimalne metadane, query log, provenance,
obsługę braków i neutralność stanowiskową.

Szczegóły wywołań API pozostają w adapterach technicznych.

### F3. Opcjonalny skill `expand-citation-graph`

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

### G1. Skill `classify-source-role`

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

## 10. Faza H, Candidate Source Index i bramka człowieka

### H1. Skille metadanych

**Owner:** CONTENT

Utworzyć:

- `normalize-source-metadata`,
- `deduplicate-source-records`,
- `rank-source-candidates`,
- `annotate-source-candidates`,
- `assess-source-coverage`.

### H2. Agent `candidate-source-index`

**Owner:** CONTENT

Agent tworzy indeks maszynowy i dokument dla człowieka. LLM używa wyłącznie dostępnego
abstraktu do summary i relevance reason. Brak abstraktu jest jawny.

### H3. Generator `candidate_source_review.md`

**Owner:** KH z treścią od CONTENT

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

### I1. Skill `resolve-open-access`

**Owner:** CONTENT

Opisać semantyczną kolejność źródeł OA, wymagane pola wyniku, wersję dokumentu, licencję i
obsługę zamkniętych źródeł.

### I2. Skill `retrieve-open-access-document`

**Owner:** CONTENT

Opisać pobieranie wyłącznie źródeł zatwierdzonych, poszanowanie limitów, retry i brak
automatyzacji institutional access.

### I3. Skill `validate-retrieved-document`

**Owner:** CONTENT

Kontrola content type, nagłówka PDF, source ID, duplikatu i jawnego statusu błędu.

### I4. Agent `paper-retrieval`

**Owner:** CONTENT

Agent łączy trzy skille, nie ocenia jakości naukowej i zwraca RetrievedCorpus.

### I5. Adaptery API i downloader

**Owner:** KH lub programista integracyjny

Zweryfikować bieżące zasady OpenAlex, Crossref, Semantic Scholar, Unpaywall, arXiv, CORE oraz
DOAB/OAPEN. Nie opierać implementacji wyłącznie na historycznych limitach z dokumentu LitPipe.

## 12. Faza J, Paper Review

### J1. Skill `extract-paper-evidence`

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

## 13. Faza K, Claim Verification

### K1. Skill `assess-claim-evidence`

**Owner:** CONTENT

Zaimplementować semantykę evidence, currency, pedagogical i controversy status, confidence,
recommended action oraz unresolved questions.

### K2. Agent `claim-verification`

**Owner:** CONTENT

Agent używa zaakceptowanych EvidenceCards. Może poprosić o targeted second pass, ale nie
otrzymuje całego korpusu automatycznie.

### K3. Kontrola modelu przez KH

**Owner:** KH

Zamknąć `[KH-DECISION: CLAIM-ASSESSMENT-MODEL]` przed zamrożeniem kontraktu.

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

### L1. Skill `synthesize-research-findings`

**Owner:** CONTENT

Tworzy evidence map, required updates, optional improvements, unresolved questions i kompaktowy
handoff. Nie dodaje nowych faktów.

### L2. Agent `research-synthesizer`

**Owner:** CONTENT

Przyjmuje wyłącznie zatwierdzone upstream artifacts. Każda rekomendacja wskazuje evidence refs.

### L3. Human Research Gate

**Owner:** JOINT

Przygotować komunikaty, decyzje użytkownika, obsługę odrzuconych findings i unresolved claim
policy. Użytkownik widzi podsumowanie, confidence, coverage i ograniczenia.

### L4. HumanApprovedResearchBundle

**Owner:** KH

Zamrozić zatwierdzony pakiet i przekazać do Solution Graph bez pełnego korpusu.

## 15. Faza M, orchestrator

### M1. Skill `orchestrate-research-graph`

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
5. Candidate Source Index,
6. decyzja człowieka,
7. jeden dostępny PDF i jedno źródło library,
8. Paper Review,
9. Claim Verification,
10. Synthesis,
11. Human Research Gate,
12. zamrożony HumanApprovedResearchBundle.

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
- Candidate Source Index pokazuje coverage i access status,
- reviewer loops działają na jednym fizycznym reviewerze,
- Paper Review działa per dokument,
- Claim Verification działa na EvidenceCards,
- unresolved claims pozostają jawne,
- Solution Graph otrzymuje kompaktowy pakiet,
- state można wznowić,
- graph manifest, plugin registration i dokumentacja są spójne,
- podstawowy przebieg oraz kluczowe failure paths są zweryfikowane.

## 20. Sugerowana kolejność pierwszych prac

Po zatwierdzeniu dokumentacji:

1. Zamknąć dwie flagi KH.
2. Dostosować konwencje repo i manifest do jednego reviewera.
3. Zamrozić szablony agenta i skilla.
4. Zbudować uniwersalnego reviewera oraz jego skill.
5. Zbudować Research Planner i `plan-research-scope`.
6. Zbudować Domain Research wraz ze skillami wyszukiwania.
7. Dodać Canonical i Recent.
8. Zbudować Candidate Source Index i Human Source Selection Gate.
9. Dodać Retrieval.
10. Dodać Paper Review.
11. Dodać Claim Verification.
12. Dodać Synthesizer i Human Research Gate.
13. Spiąć orchestrator, kontrakty, shape checks i manifest.
14. Wykonać test end-to-end i failure-path tests.

