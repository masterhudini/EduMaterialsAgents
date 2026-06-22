# Research Graph, architektura agentów i skilli

## 1. Architektura logiczna

```mermaid
flowchart TD
    IN["ResearchGraphInput"] --> RP["G02-A01 Planner Agent"]
    RP --> RV1["G02-A10 Output Reviewer\nprofile: research_plan"]
    RV1 -->|REVISE| RP
    RV1 -->|APPROVED| DR["G02-A02 Domain Agents\none per topic"]

    DR --> RV2["G02-A10 Output Reviewer\nprofile: domain_candidates"]
    RV2 -->|REVISE| DR
    RV2 -->|APPROVED| EXP["Discovery expansion\nlogical fan-out"]

    EXP --> CS["G02-A03 Canonical Sources Agents"]
    EXP --> RD["G02-A04 Recent Developments Agents"]
    EXP --> MC["G02-A11 Market Cases Agent\nTavily + controlled SearXNG"]
    CS --> RV3["G02-A10 Output Reviewer\nprofile: canonical_sources"]
    RD --> RV4["G02-A10 Output Reviewer\nprofile: recent_developments"]
    MC --> RVMC["G02-A10 Output Reviewer\nprofile: market_cases"]
    RV3 -->|REVISE| CS
    RV4 -->|REVISE| RD
    RVMC -->|REVISE| MC

    RV3 -->|APPROVED| IDX["G02-A05 Candidate Source Index Agent"]
    RV4 -->|APPROVED| IDX
    RVMC -->|APPROVED| IDX
    RV2 -->|APPROVED| IDX

    IDX --> RV5["G02-A10 Output Reviewer\nprofile: candidate_index"]
    RV5 -->|REVISE| IDX
    RV5 -->|APPROVED| HG1["Human Source Selection Gate"]
    HG1 -->|SEARCH_MORE| DR
    HG1 -->|APPROVED DOCUMENT| PR["G02-A06 Paper Retrieval Agent"]
    HG1 -->|APPROVED MARKET CASE| WEX["Deterministic Tavily extraction\nfinal selection required"]

    PR --> RV6["G02-A10 Output Reviewer\nprofile: retrieved_corpus"]
    RV6 -->|REVISE| PR
    RV6 -->|APPROVED| PRA["G02-A07 Paper Review Agents\none per document"]
    WEX --> PR

    PRA --> RV7["G02-A10 Output Reviewer\nprofile: paper_evidence"]
    RV7 -->|REVISE| PRA
    RV7 -->|APPROVED| CV["G02-A08 Claim Verification Agents\none per claim or tight claim group"]

    CV --> RV8["G02-A10 Output Reviewer\nprofile: claim_assessment"]
    RV8 -->|REVISE| CV
    RV8 -->|APPROVED| RS["G02-A09 Synthesizer Agent"]

    RS --> RV9["G02-A10 Output Reviewer\nprofile: research_synthesis"]
    RV9 -->|REVISE| RS
    RV9 -->|UPSTREAM_ERROR| RP
    RV9 -->|APPROVED| HG2["Human Research Gate"]

    HG2 -->|NEEDS_CORRECTION| RS
    HG2 -->|APPROVED| OUT["UserApprovedResearchBundle"]
```

Wszystkie pola oznaczone jako `G02-A10 Output Reviewer` są uruchomieniami tej samej
fizycznej definicji agenta.

## 2. Fizyczne definicje agentów

Moduł zawiera jedenaście plików agentów, płasko w `agents/` dla auto-discovery. Każdy techniczny
identyfikator składa się z kodu grafu `g02`, stałego kodu fizycznego agenta i krótkiej roli:

1. `g02-a01-planner.md`
2. `g02-a02-domain.md`
3. `g02-a03-canonical-sources.md`
4. `g02-a04-recent-developments.md`
5. `g02-a05-candidate-source-index.md`
6. `g02-a06-paper-retrieval.md`
7. `g02-a07-paper-review.md`
8. `g02-a08-claim-verification.md`
9. `g02-a09-synthesizer.md`
10. `g02-a10-output-reviewer.md`
11. `g02-a11-market-cases.md`

Kody `a01`–`a11` są niezmienne i nie zależą od kolejności wykonania. Usuniętego kodu nie wolno
przydzielać ponownie. Para `gNN-aNN` jest globalnie jednoznaczna, a numeracja agentów może
rozpoczynać się od `a01` osobno w każdym grafie.

`User Source Selection Gate` i `User Research Gate` są krokami orkiestratora. Nie wymagają
osobnych agentów.

## 3. Standard pliku agenta

Docelowe pliki są po angielsku i zachowują następującą strukturę:

```markdown
---
name: gNN-aNN-agent-role
description: Short description of the isolated responsibility and its boundary.
---

# GNN-ANN Agent Role

Short description of the isolated responsibility and why its boundary matters.

## Contract

Input, output, consumes, produces, required artifact refs and envelope behavior.

## Required Skills

Mandatory skills, optional skills and allowed execution order.

## Workflow

Numbered execution procedure.

## Acceptance Criteria

Criteria later passed to the universal reviewer as a review profile.

## Boundaries

Non-responsibilities, prohibited actions and scope constraints.

## Failure handling

Degraded results, needs_input, blocked dependencies and escalation data.

## Resume

Stateless re-run behavior and handling of revision items.
```

Każdy agent:

- jest izolowany,
- nie rozmawia bezpośrednio z użytkownikiem,
- otrzymuje ograniczony input bundle,
- korzysta tylko z wymienionych skilli,
- zwraca `envelope@1`,
- zapisuje wyniki jako artefakty,
- nie wykonuje odpowiedzialności następnego etapu,
- przy rewizji otrzymuje poprzedni artefakt i konkretne `revision_items`.

## 4. Standard skilla

Każdy skill znajduje się w `skills/<skill-name>/SKILL.md` (jeden poziom — Claude Code nie
wykrywa zagnieżdżenia `skills/<graph>/<name>/`). Każdy katalog skilla zawiera również wymagany
folder `adapters/`. Dodatkowe zasoby powstają tylko wtedy, gdy są potrzebne do deterministycznego
i powtarzalnego wykonania procedury.

```markdown
---
name: skill-name
description: What the skill does, when an authorized research agent must use it, and its scope.
---

# Skill Name

## Contract
## Workflow
## Output requirements
## Boundaries
## Failure handling
## Resume
```

Opis musi jednoznacznie wskazywać, czy skill jest interaktywnym orkiestratorem, czy procedurą
wykonawczą uruchamianą przez agenta. Skille wykonawcze nie prowadzą rozmowy z użytkownikiem.

### Frontmatter i adaptery (ograniczenia buildu)

`scripts/build-plugin.py` parsuje frontmatter **mini-podzbiorem YAML** (`key: scalar`, jedna
linia na klucz). Stąd zasady, których autor skilla musi przestrzegać:

- **Neutralny `SKILL.md`** ma we frontmatterze **wyłącznie `name` i `description`** — każde jako
  pojedyncza linia (bez bloków `>-`/`|`, bez list/map). Cudzysłowy `"..."`/`'...'` są dozwolone.
  `name` musi równać się nazwie folderu.
- **Frontmatter zależny od hosta** (np. `model: opus`) idzie do
  `adapters/<host>.frontmatter.yaml` — build nakłada go na neutralny frontmatter. Overlay
  **nie może** zmienić `name`.
- **Treść zależna od hosta** idzie do `adapters/<host>.md` (nie może być pusta). Build wstawia ją
  w miejsce `{{HOST_ADAPTER}}` w ciele `SKILL.md`, a gdy placeholdera brak — **dokleja na końcu**.
- W zbudowanym bundlu folder `adapters/` **jest usuwany** (host dostaje tylko swój wariant).
- Wymagane pliki na skill: `adapters/claude.md`, `adapters/codex.md`, `adapters/claude.frontmatter.yaml`.

Struktura host adapters:

```text
skills/<skill-name>/
├── SKILL.md
└── adapters/
    ├── claude.frontmatter.yaml
    ├── claude.md
    └── codex.md
```

`SKILL.md` zawiera wyłącznie wspólną semantykę. `claude.frontmatter.yaml` wybiera model Claude
dla danego skilla, `claude.md` opisuje Task/Agent i narzędzia Claude Code, a `codex.md` opisuje
powierzchnię MCP lub równoważny adapter Codex. Renderowanie wykonuje krok buildu
`scripts/build-plugin.py` (funkcja `render_skill_adapters`): nakłada `<host>.frontmatter.yaml` na
neutralny frontmatter, wstawia treść `<host>.md` w miejsce `{{HOST_ADAPTER}}` (albo dokleja na
końcu) i **usuwa katalog `adapters/`** z bundla — wariant instalacyjny powstaje bez modyfikacji
źródła i bez instrukcji drugiego hosta.

### 4.1. Deterministyczne narzędzia skilli

Skille wyszukiwania, indeksowania, Open Access i pobierania korzystają z narzędzi Research
Graph zamiast samodzielnie konstruować requesty w kontekście LLM. Narzędzie przyjmuje JSON,
zwraca JSON i nie podejmuje decyzji semantycznych należących do agenta.

Wspólny wynik operacji narzędzia zawiera co najmniej:

- `operation_id`, `provider`, `status` i czas wykonania,
- znormalizowane `records` albo deskryptory pobranych plików,
- `query_log`, proweniencję oraz identyfikatory dostawcy,
- informacje o paginacji, limitach i częściowych brakach,
- strukturalne `issues` bez ukrywania degradacji.

Provider adapters G02-A02 obejmują OpenAlex, Semantic Scholar i arXiv. Unpaywall, Crossref, CORE,
DOAB i OAPEN zostaną dołączone przy pierwszym agencie, który wymaga ich funkcji. Agent wybiera
strategię, a adapter wykonuje zapytanie, normalizuje odpowiedź i zachowuje jej pochodzenie.
Narzędzia są wystawione hostowi przez MCP, lecz komunikację z API, retry, cache i limity realizuje
lokalny kod deterministyczny.

## 5. Agenci wykonawczy

### 5.1. G02-A01 Planner Agent

**Cel:** zamienić zatwierdzony input na ograniczony plan badań.

**Odpowiedzialności:**

- pogrupować research drivers w topics,
- określić cel każdego topic,
- wskazać powiązane claimy, koncepty i potrzeby aktualizacji,
- zdefiniować role źródeł i coverage requirements,
- przygotować strategię wyszukiwania,
- ustalić priorytety, limity i warunki zakończenia.

**Granice:**

- nie wyszukuje publikacji,
- nie ocenia claimów,
- nie proponuje zmian slajdów,
- nie rozszerza zatwierdzonego zakresu.

**Wejście:** ograniczony `research_planner_input@1`, przygotowany z zatwierdzonego
`research_graph_input@1`.

**Wyjście:** `research_plan@1` w `envelope@1`.

Deterministyczny moduł `shared/scripts/g02/planner.py` odpowiada za scoping wejścia, walidację
semantycznej kompletności, shape check planu, zapis artefaktu, minimalność rewizji i zbudowanie
profilu `research_plan`. Planner nie otrzymuje narzędzi wyszukiwawczych.

### 5.2. G02-A02 Domain Agent

Uruchamiany osobno dla każdego topic.

**Cel:** zbudować bazową pulę kandydatów powiązanych z topic i jego research needs.

**Odpowiedzialności:**

- rozwinąć zapytanie w zatwierdzonych granicach,
- przeszukać główny indeks metadanych,
- zebrać rekordy i ślad zapytań,
- mapować kandydatów do coverage units,
- zachować źródła wspierające, kwalifikujące i potencjalnie krytyczne.

**Granice:**

- nie potwierdza claimów,
- nie tworzy finalnego rankingu,
- nie pobiera PDF,
- nie decyduje o kanoniczności poza wstępnym sygnałem.

**Wejście:** `domain_research_input@1`, czyli jeden zatwierdzony topic z `research_plan@1`, ref
planu i jawne, pozbawione sekretów capabilities providerów.

**Wyjście:** `domain_candidate_sources@1` w `envelope@1`.

Agent tworzy provider-neutral `query_plan@1`. Każdy termin wygenerowany przez AI wskazuje w
`generated_term_bases` zatwierdzony origin term, expansion area i typ relacji. Każda trasa jest wykonywana przez
`research_metadata_search`, który zwraca zapisany `literature_tool_result@1` zawierający
znormalizowane `source_record@1`. Moduły `provider_config.py`, `query_planning.py`, `providers.py`
oraz `domain.py` odpowiadają za granice konfiguracji, wykonanie API, proweniencję, walidację,
zapis i profil review. Agent nie wykonuje surowych requestów HTTP i nie modyfikuje metadanych
zwróconych przez providerów.

### 5.3. G02-A03 Canonical Sources Agent

Uruchamiany po zatwierdzonym G02-A02 Domain, osobno dla jednego topicu.

**Cel:** uzupełnić pulę o źródła fundamentalne, monografie, podręczniki, przeglądy i ważne
prace metodologiczne.

**Odpowiedzialności:**

- analizować sygnały cytowań i centralności,
- rozszerzać graf wstecz i wokół kluczowych źródeł,
- oddzielać canonical anchor od dostępnego dowodu,
- rejestrować źródła zamknięte,
- wskazywać źródła dostępne, które mogą uzupełnić zamkniętą monografię.

**Granice:**

- nie przypisuje treści niedostępnej książce,
- nie traktuje liczby cytowań jako jakości naukowej,
- nie pobiera dokumentów,
- nie wykonuje pełnego review.

**Wejście:** `canonical_research_input@1` utworzone przez `research_canonical_prepare`. Scoped input
zawiera zatwierdzony topic, reviewed `domain_candidate_sources@1`, wyłącznie zweryfikowane seedy
providerów, nierozwiązane seedy planu, role, coverage, limit jednego hopu i pozbawione sekretów
capabilities providerów.

**Wyjście:** `candidate_sources@1` z `stream: canonical`, zapisane przez
`research_canonical_finalize` i przekazane do review przez `research_canonical_review_task`.

Ekspansja grafu jest wykonywana wyłącznie przez `research_citation_expand`: OpenAlex obsługuje
`cited_by`, Semantic Scholar `references`, `cited_by` oraz `recommendations`, a arXiv pozostaje
providerem wyszukiwania metadanych. Wyszukiwanie uzupełniające korzysta ze wspólnego
`research_metadata_search`. Rekordy providerów są kopiowane bez zmian, natomiast role,
canonicality basis, relacje cytowań, access statement i coverage trafiają do osobnych
`canonical_annotations`. Każdy `literature_tool_result@1` zawiera `request.scope`; finalizacja
akceptuje wynik tylko wtedy, gdy task, topic, ResearchPlan i reviewed A02 ref dokładnie odpowiadają
wejściu A03. Profil review zamraża kryteria `CS-01` do `CS-06`.

### 5.4. G02-A04 Recent Developments Agent

Logicznie niezależny od G02-A03 Canonical Sources po G02-A02 Domain. Docelowy scheduler może
uruchamiać oba węzły równolegle; bieżący `g02_flow.py` zachowuje kolejność manifestu.

**Cel:** znaleźć aktualne, dojrzałe zmiany istotne dla zatwierdzonego topic lub claimu.

**Odpowiedzialności:**

- korzystać z recency window,
- analizować dynamikę cytowań i powiązania grafowe,
- odróżniać core update od optional trend,
- oznaczać maturity level,
- rejestrować preprinty jako odrębną kategorię.

**Granice:**

- nie zastępuje materiału kanonicznego,
- nie uznaje nowości za jakość,
- nie generuje treści slajdów,
- nie pobiera dokumentów.

**Wejście:** `recent_research_input@1` z `research_recent_prepare`. Okno kalendarzowe jest
deterministycznie wyliczane z kopii intake `approved_research_scope.recency_window_years` w
`research_plan@1` i ograniczane zatwierdzonymi datami topicu. Input zawiera reviewed A02,
zweryfikowane seedy, role, coverage, limity i pozbawione sekretów capabilities.

**Wyjście:** recent variant `candidate_sources@1`, zapisane przez `research_recent_finalize` i
przekazane do review przez `research_recent_review_task`.

Wszystkie trasy metadanych używają wspólnego `research_metadata_search` i dokładnie zamrożonego
okna. Opcjonalny `research_citation_expand` zachowuje jeden hop i oznacza wyniki jako
`recent_expansion`. Rekordy providerów pozostają niezmienione; `recent_annotations` rozdzielają
role, recency basis, konserwatywny publication status, maturity, update class, relacje, coverage i
`quality_status: not_assessed`. Wyniki narzędzi są związane przez `request.scope` z dokładnym task,
topic, ResearchPlan i reviewed A02 ref. Profil review zamraża `RD-01` do `RD-06`.

### 5.5. G02-A05 Candidate Source Index Agent

**Cel:** przygotować wiarygodny i czytelny indeks do decyzji człowieka.

**Odpowiedzialności:**

- agregować reviewed A02 oraz strumienie A03, A04 i A11,
- normalizować metadane,
- deduplikować rekordy,
- przypisywać role źródeł,
- tworzyć osobne sygnały canonical i rising,
- sprawdzać candidate coverage,
- wybierać pulę prezentowaną i rezerwową,
- generować krótkie opisy publikacji z dostępnych abstraktów, a przy braku abstraktu jawnie
  ograniczać kartę do metadanych,
- opisywać market case przez reviewed fakt rynkowy i mechanizm dydaktyczny A11, bez ekstrakcji
  strony przed bramką,
- tworzyć `candidate_source_index.json` i `candidate_source_review.md`.

**Granice:**

- nie podejmuje ostatecznej decyzji o pobraniu,
- nie przedstawia opisu abstraktowego jako pełnej weryfikacji,
- nie tworzy metadanych bibliograficznych przez LLM,
- nie usuwa zamkniętych źródeł tylko z powodu braku OA.

**Wejście wykonawcze:** `candidate_index_input@1`, przygotowane wyłącznie z artefaktów związanych
z decyzjami A10 `APPROVED` dla dokładnego tasku, planu, ref i wersji.

**Wyjście:** `candidate_source_index@1` i `candidate_source_review.md`. Każda karta pokazuje
`description_basis`, skrót treści, związek z topic/coverage, ograniczenia dostępu i rekomendowaną
akcję, pozostawiając decyzję człowiekowi.

### 5.6. G02-A06 Paper Retrieval Agent

**Cel:** pobrać lub zarejestrować wyłącznie źródła zatwierdzone przez człowieka.

**Odpowiedzialności:**

- rozwiązać dostęp OA zgodnie z zatwierdzonym łańcuchem,
- pobierać wyłącznie legalne, dostępne wersje,
- sprawdzać typ i integralność dokumentu,
- tworzyć stabilne powiązanie `source_id` z plikiem,
- rejestrować unavailable, failed i library access,
- nie pobierać ponownie posiadanych plików, jeżeli runtime dostarcza manifest.

**Granice:**

- nie ocenia jakości naukowej,
- nie zmienia wyboru człowieka,
- nie analizuje treści,
- nie automatyzuje dostępu instytucjonalnego.

**Wyjście:** `RetrievedCorpus` oraz typed `retrieval_directory@1`. Deskryptor katalogu wskazuje
manifest, katalog zwalidowanych PDF i katalog zatwierdzonych market-case bundles przez `corpus://`.
Każdy bundle zawiera przyjazny dla człowieka Markdown renderowany z reviewed adnotacji A11 i
ograniczonej ekstrakcji po bramce oraz osobny JSON przeznaczony do audytu maszynowego. Manifest
przechowuje oddzielne refs i SHA-256 obu plików.
A06 próbuje dokładnie source IDs oznaczone przez człowieka jako `DOWNLOAD`; przekroczenie
administracyjnego `max_documents_per_task` zatrzymuje przygotowanie przed requestem.

### 5.7. G02-A07 Paper Review Agent

Uruchamiany osobno dla jednego dokumentu.

**Cel:** wydobyć z dokumentu dowody potrzebne downstream bez przekazywania pełnego PDF.

**Odpowiedzialności:**

- zlokalizować sekcje związane z przypisanymi claimami i topics,
- wydobyć contribution, method, findings i limitations,
- zapisać lokalizację dowodu,
- oddzielić twierdzenia publikacji od interpretacji dla wykładu,
- wskazać dowody wspierające, sprzeczne i kontekstualizujące,
- określić evidence access level.

**Granice:**

- nie czyta całego dokumentu bez potrzeby,
- nie wykonuje ostatecznej oceny claimu,
- nie proponuje finalnych zmian slajdów,
- nie ignoruje ograniczeń publikacji.

**Wyjście:** `PaperReview` oraz `PaperEvidenceCards`.

### 5.8. G02-A08 Claim Verification Agent

Uruchamiany po zaakceptowanych wynikach G02-A07 Paper Review, osobno dla claimu lub ściśle
powiązanego pakietu.

**Cel:** ocenić claim w wielu wymiarach na podstawie zatwierdzonych evidence cards.

**Odpowiedzialności:**

- ocenić wsparcie dowodowe,
- ocenić aktualność,
- ocenić adekwatność dydaktyczną,
- rozpoznać kontrowersyjność,
- przypisać confidence z uzasadnieniem,
- wskazać rekomendowaną akcję,
- oznaczyć niewystarczające dowody,
- poprosić o ukierunkowany drugi odczyt, jeśli brakuje konkretnego fragmentu.

**Granice:**

- nie korzysta bezpośrednio z pełnego korpusu,
- nie zmienia claimu bez zachowania oryginalnej treści,
- nie tworzy finalnego planu zmian,
- nie ukrywa sprzecznych dowodów.

**Wyjście:** `ClaimAssessmentState`.

### 5.9. G02-A09 Synthesizer Agent

**Cel:** utworzyć kompaktowy, dowodowy pakiet dla człowieka i Solution Graph.

**Odpowiedzialności:**

- połączyć claim assessments, paper evidence, źródła kanoniczne i recent developments,
- utworzyć `ResearchState`,
- utworzyć `EvidenceMap`,
- rozdzielić required updates i optional improvements,
- wskazać unresolved claims,
- przygotować `UserResearchValidationPacket`,
- przygotować `SolutionInputCandidate` bez pełnego korpusu.

**Granice:**

- nie pisze slajdów,
- nie tworzy finalnego planu zmian,
- nie dodaje nowych dowodów podczas syntezy,
- nie przekazuje pełnych PDF-ów do Solution Graph.

## 6. Uniwersalny reviewer

### 6.1. G02-A10 Output Reviewer Agent

**Cel:** sprawdzić, czy konkretny agent wykonał przydzielone zadanie zgodnie z kontraktem i
profilem etapu.

**Wejście:** `ReviewTask` (`review_task@1`) zawierający:

- oryginalne zadanie producenta,
- ograniczony input producenta,
- artefakt wynikowy,
- expected output contract,
- acceptance criteria,
- evidence requirements,
- prohibited behaviors,
- severity rules,
- poprzednie findings i numer próby.

**Wyjście:** `ReviewDecision` (`review_decision@1`) w `envelope@1`.

**Decyzje:**

- `APPROVED`,
- `REVISE`,
- `BLOCKED`.

**Root cause:**

- `producer_error`,
- `insufficient_evidence`,
- `invalid_or_incomplete_input`,
- `upstream_plan_error`,
- `review_profile_error`,
- `external_dependency_blocked`.

**Zasady:**

- reviewer nie poprawia artefaktu,
- reviewer nie rozszerza kryteriów poza review profile,
- każde finding wskazuje criterion, location, severity i required correction,
- rewizja ma minimalny zakres,
- brak lub sprzeczność kryteriów prowadzi do `BLOCKED`,
- reviewer otrzymuje artefakt i kontrakt, bez prywatnego toku rozumowania producenta,
- osobne artefakty są oceniane w osobnych wywołaniach.

## 7. Profile review

| Profile | Najważniejsze kryteria |
|---|---|
| `research_plan` | Każdy topic ma stabilne ID, purpose, research drivers, zatwierdzone domeny, role źródeł, coverage i stop rule; wszystkie drivery są rozliczone, a zakres i ograniczenia zachowane. |
| `domain_candidates` | Kandydaci mapują się do topic, zapytania są w zakresie, metadane pochodzą z indeksów. |
| `canonical_sources` | Kanoniczność ma podstawę, access level jest jawny, zamknięta treść nie jest interpretowana. |
| `recent_developments` | Recency i maturity są jawne, hype jest oddzielony od dojrzałej aktualizacji. |
| `market_cases` | Instytucja lub zdarzenie, data, tier źródła, mapowanie do claimu/topic, rozdzielenie faktu od interpretacji i jawne ograniczenia reżimu. |
| `candidate_index` | Deduplikacja, role, ranking, pokrycie, opisy oparte na abstraktach, dokument dla człowieka. |
| `retrieved_corpus` | Tylko zatwierdzone źródła, stabilne ID, integralne PDF oraz market-case Markdown + JSON, jawne błędy i unavailable. |
| `paper_evidence` | Evidence location, metoda, findings, ograniczenia, relacja z claimem i access level. |
| `claim_assessment` | Wszystkie wymiary oceny, dowody przeciwne, confidence i coverage. |
| `research_synthesis` | Każda rekomendacja ma evidence refs, unresolved są jawne, handoff jest kompaktowy. |

## 8. Katalog skilli G02

Nazwy są technicznymi identyfikatorami. Skill jednego agenta używa postaci
`g02-aNN-<dotychczasowa-nazwa-skilla>`. Skill współdzielony przez kilka agentów, wiele logicznych
węzłów albo cały graf używa postaci `g02-<dotychczasowa-nazwa-skilla>`. Część opisowa skilla nie
otrzymuje numeru i zachowuje dotychczasową nazwę.

| Skill | Główna funkcja |
|---|---|
| `g02-a01-plan-research-scope` | Topics, research needs, source strategy, coverage i stop rules. |
| `g02-expand-research-query` | Kontrolowane synonimy, terms, topics i wyłączenia. |
| `g02-search-scholarly-metadata` | Wyszukiwanie realnych rekordów bibliograficznych. |
| `g02-expand-citation-graph` | Rozszerzenie od seed sources i relacji cytowań. |
| `g02-classify-source-role` | Canonical, recent, survey, didactic, claim-specific, applied_case, optional. |
| `g02-normalize-source-metadata` | Ujednolicenie DOI, autorów, roku, typu i identyfikatorów. |
| `g02-a05-deduplicate-source-records` | Łączenie rekordów z wielu indeksów. |
| `g02-a05-rank-source-candidates` | Osobne sygnały canonical i rising oraz priorytet coverage. |
| `g02-a05-annotate-source-candidates` | Krótkie, ugruntowane w abstrakcie opisy dla człowieka. |
| `g02-assess-source-coverage` | Candidate, selection i evidence coverage. |
| `g02-a06-resolve-open-access` | Ustalenie legalnej dostępnej wersji dokumentu. |
| `g02-a06-retrieve-open-access-document` | Pobranie zatwierdzonego dokumentu. |
| `g02-a06-validate-retrieved-document` | Integralność, typ, zgodność source ID i status. |
| `g02-a07-extract-paper-evidence` | Ukierunkowane wydobycie evidence cards z dokumentu. |
| `g02-a08-assess-claim-evidence` | Wielowymiarowa ocena claimu. |
| `g02-a09-synthesize-research-findings` | ResearchState, EvidenceMap i handoff. |
| `g02-a11-find-market-cases` | Web discovery realnych, datowanych case'ów przez kontrolowany seam Tavily/SearXNG. |
| `g02-a11-extract-case-evidence` | Ekstrakcja kompaktowej evidence card z case'a zatwierdzonego przez człowieka. |
| `g02-review-research-output` | Uniwersalna procedura review względem profile. |
| `g02-orchestrate-research` | Rozmowa, routing, reviewer loops i human gates. |

## 9. Macierz agentów i skilli

| Agent | Wymagane skille | Opcjonalne skille |
|---|---|---|
| G02-A01 Planner | `g02-a01-plan-research-scope` | `g02-expand-research-query` do planu terminów, bez wyszukiwania |
| G02-A02 Domain | `g02-expand-research-query`, `g02-search-scholarly-metadata` | `g02-expand-citation-graph` |
| G02-A03 Canonical Sources | `g02-expand-citation-graph`, `g02-classify-source-role`, `g02-search-scholarly-metadata` | `g02-normalize-source-metadata` |
| G02-A04 Recent Developments | `g02-expand-research-query`, `g02-search-scholarly-metadata`, `g02-classify-source-role` | `g02-expand-citation-graph` |
| G02-A11 Market Cases | `g02-expand-research-query`, `g02-a11-find-market-cases`, `g02-classify-source-role` | brak; ekstrakcja należy warunkowo do A07 po bramce człowieka |
| G02-A05 Candidate Source Index | `g02-normalize-source-metadata`, `g02-a05-deduplicate-source-records`, `g02-classify-source-role`, `g02-a05-rank-source-candidates`, `g02-a05-annotate-source-candidates`, `g02-assess-source-coverage` | brak na start |
| G02-A06 Paper Retrieval | `g02-a06-resolve-open-access`, `g02-a06-retrieve-open-access-document`, `g02-a06-validate-retrieved-document` | brak na start |
| G02-A07 Paper Review | `g02-a07-extract-paper-evidence`; `g02-a11-extract-case-evidence` warunkowo dla zatwierdzonego market case | ukierunkowane ponowne wydobycie |
| G02-A08 Claim Verification | `g02-a08-assess-claim-evidence`, `g02-assess-source-coverage` | brak na start |
| G02-A09 Synthesizer | `g02-a09-synthesize-research-findings`, `g02-assess-source-coverage` | brak na start |
| G02-A10 Output Reviewer | `g02-review-research-output` | read-only użycie odpowiedniego skilla sprawdzającego, jeśli review profile tego wymaga |

## 10. Human Source Selection Gate

### 10.1. Co człowiek otrzymuje

- krótkie podsumowanie w rozmowie,
- ścieżkę lub link do `candidate_source_review.md`,
- liczbę kandydatów i wykryte luki,
- instrukcję decyzji,
- gotowy szablon odpowiedzi.

### 10.2. Instrukcja

Orkiestrator generuje instrukcję w `output_language` przy każdym wejściu do bramki:

```text
A candidate source review is ready.

1. Open: <artifact path>
2. Review the short descriptions and coverage notes.
3. Assign one action to each source you want to keep or reject.

DOWNLOAD      Retrieve an available Open Access document.
LIBRARY       Keep it and request institutional or library access.
CITATION      Keep it as contextual citation without retrieval.
RESERVE       Keep it available as a replacement.
EXCLUDE       Remove it from this research run.
SEARCH_MORE   Ask for more candidates for a topic, claim or missing source role.

Reply using the copyable template below. Natural language is also accepted.

DOWNLOAD: SRC_...
LIBRARY: SRC_...
CITATION: SRC_...
RESERVE: SRC_...
EXCLUDE: SRC_..., reason: ...
SEARCH_MORE: CLM_... or TOPIC_..., need: ...
```

Orkiestrator parsuje odpowiedź, pokazuje dokładną liczbę `DOWNLOAD` oraz osobno liczbę PDF
scholarly i plików market case, po czym prosi o finalne potwierdzenie. Człowiek podejmuje decyzję.
A05 wyłącznie rekomenduje, a A06 nie może zwiększyć ani zmienić zatwierdzonego zbioru.

### 10.3. Powrót do wyszukiwania

`SEARCH_MORE` musi zawierać claim, topic albo brakującą rolę. Orkiestrator kieruje żądanie do
G02-A02 Domain, G02-A03 Canonical Sources, G02-A04 Recent Developments albo G02-A11 Market Cases
zgodnie z typem luki. A11 korzysta wyłącznie z kontrolowanych operacji Tavily/SearXNG.
Po rozszerzeniu G02-A05 Candidate Source Index jest
budowany ponownie, reviewer ocenia nową wersję, a człowiek otrzymuje zaktualizowany dokument.

## 11. Human Research Gate

Człowiek otrzymuje:

- podsumowanie zweryfikowanych claimów,
- required updates,
- optional improvements,
- unresolved claims,
- poziomy confidence,
- evidence coverage,
- źródła i ograniczenia,
- decyzje wymagane przed przekazaniem do Solution Graph.

Człowiek zatwierdza, odrzuca lub kieruje syntezę do korekty. Finalny pakiet zawiera również
świadomie zaakceptowane wyjątki i politykę obsługi nierozstrzygniętych claimów.

## 12. Współbieżność

`g02_flow.py` wykonuje obecnie `sequence` z manifestu sekwencyjnie. Architektura wskazuje poniższe
grupy jako logicznie niezależne i kwalifikujące się do przyszłego fan-out/fan-in po dodaniu jawnych
zależności oraz schedulera:

- G02-A02 Domain per topic.
- Canonical, Recent i Market Cases po zatwierdzeniu bazowej puli.
- G02-A07 Paper Review per dokument lub zatwierdzony market case.
- G02-A08 Claim Verification per niezależny claim lub ciasny claim group.
- Reviewer ocenia każdy artefakt oddzielnie.
- Fan-in następuje dopiero po zatwierdzeniu wszystkich wymaganych wyników albo oznaczeniu
  jawnych wyjątków.

## 13. Failure handling

Agenci używają wspólnej semantyki envelope:

- `ok`, artefakt gotowy do review,
- `needs_input`, potrzebna decyzja użytkownika przekazana przez orkiestratora,
- `degraded`, użyteczny wynik z jawnymi brakami,
- `failed`, brak użytecznego artefaktu.

Decyzje reviewera są zapisane w `ReviewDecision`, nie w statusie envelope.

Przykładowe sytuacje degraded:

- brak abstraktu dla części źródeł,
- niedostępny pełny tekst,
- częściowe pokrycie topic,
- niedostępność jednego indeksu przy działającym źródle głównym.

Przykładowe sytuacje blocked:

- brak wymaganych research drivers,
- sprzeczny review profile,
- wszystkie wymagane źródła zewnętrzne niedostępne,
- potrzeba decyzji człowieka, której agent nie może bezpiecznie założyć.

## 14. Model wykonania i parytet hostów

Wykonanie jest **per host**, rdzeń pozostaje agnostyczny:

- **Claude:** orkiestrator-skill prowadzi izolowanych subagentów przez Task tool (model „w cenie"
  subskrypcji); deterministyczne szwy przez MCP.
- **Codex:** silnik `g02_flow.run` prowadzi graf, a każdy węzeł to izolowany `codex exec`
  (`shared/scripts/g02/g02_flow.py run-codex`), na loginie ChatGPT (bez API key).

Ujednolicenie do jednej ścieżki odrzucono: Task nie jest wołalny z Pythona, a wołanie API LLM
dla Claude wymagałoby klucza i kosztu poza subskrypcją.

**Parytet utrzymujemy przez jedno źródło prawdy — manifest grafu** (`shared/graphs/<graph>.graph.json`):
sekwencja węzłów, `review_profile`, `retry_matrix`, `complexity_class`, `model_bindings`,
`required_decisions`. Obie ścieżki z niego czerpią; żadna nie hardkoduje polityki. `graph_check`
wymusza, że skill-orkiestrator odwołuje się do manifestu (łapie rozjazd, gdy ktoś skopiuje
przepływ do promptu).

## 15. G02-A11 Market Cases (web case studies, zaimplementowany pionowy wycinek)

G02-A11 ma zamrożony scoped input, wariant wyjścia `candidate_sources@1`, walidację semantyczną,
operacje Tavily i SearXNG, profil review, mocki oraz testy do wykonania w osobnym środowisku.
Ekstrakcja pełnej strony jest odrębną operacją po Human Source Selection Gate. Bieżący runner nadal
wykonuje logiczny fan-out sekwencyjnie.

### 15.1. Cel i miejsce w grafie

`g02-a11-market-cases` to logicznie niezależny strumień discovery po zatwierdzonej puli bazowej
G02-A02, obok G02-A03 Canonical Sources i G02-A04 Recent Developments. Bieżący runner wykonuje te
węzły sekwencyjnie; docelowy scheduler może uruchomić je jako fan-out. Zamiast
indeksów bibliograficznych przeszukuje web pod realne, datowane przypadki rynkowe ilustrujące
zatwierdzony claim lub topic (zastosowania, konstrukcje opcyjne i głośne porażki w praktyce
instytucji). Kod `a11` jest niezmienny i nie recyklowany. Wynik `MarketCaseCandidateSources`
wpływa do G02-A05 Candidate Source Index i przechodzi tę samą bramkę Human Source Selection Gate,
co kandydaci z API. Case'y nie są osobną, nieaudytowalną klasą dowodów.

To rozszerza listę fizycznych agentów z par. 2 o jedenasty plik `agents/g02-a11-market-cases.md`.

### 15.2. Deterministyczny seam web i provider

Skille discovery i ekstrakcji nie wołają web bezpośrednio. Operacje MCP `research_web_case_search`
i `research_web_case_extract` (moduł `shared/scripts/g02/web_cases.py` według wzorca `providers.py`)
wykonują request, normalizują odpowiedź do `source_record@1` z `record_type: market_case`,
przypisują `source_tier` z domeny wyniku i zachowują surową odpowiedź oraz provenance. Provider
jest abstrakcją z Tavily jako pierwszym i domyślnym adapterem (`tavily_search`, `tavily_extract`).
Klucz API i parametry pochodzą ze zmiennych środowiskowych, nigdy z kontekstu LLM. Ekstrakcja
pełnej treści następuje dopiero po bramce człowieka, na zatwierdzonych case'ach, co oszczędza
kredyty Tavily i jest spójne z zasadą braku ciężkiego poboru przed bramką (A06).

Drugim adapterem discovery jest kontrolowana, samodzielnie utrzymywana instancja SearXNG przez
jej API JSON. Zapewnia ona ścieżkę bez klucza i opłat per request, lecz wymaga własnej instancji lub
zaufanej instancji administracyjnej oraz ponosi koszt infrastruktury. System nie wybiera losowych
publicznych instancji i nie przekazuje agentowi ogólnej przeglądarki. Konfiguracja dopuszcza tryby
`tavily`, `searxng` i `auto_budgeted`. W `auto_budgeted` SearXNG wykonuje ograniczone discovery, a
Tavily uzupełnia braki wysokiego priorytetu i obsługuje ekstrakcję po bramce. Oba adaptery zwracają
ten sam provider-neutral wynik z query, czasem, pozycją, URL, snippetem, providerem i provenance.

Instancja SearXNG jest ustalana przez administratora przy instalacji, a nie przez intake lub model.
Endpoint musi używać HTTPS, z wyjątkiem jawnie skonfigurowanego loopback podczas DEV. Runtime
blokuje credentials w URL, zmianę origin przez redirect, adresy prywatne poza dozwolonym
loopbackiem, nieobsługiwany content type i nadmierną odpowiedź. Obowiązują wspólny budżet per task
i per provider, rate limit, cache, timeout, allowlista kategorii, tier policy oraz pełny zapis
provenance. Cache hit nie zużywa drugiego zapytania.

`research_market_cases_prepare` materializuje `market_case_research_input@1` z zatwierdzonego
ResearchPlan i dokładnego reviewed ref A02. Wejście zawiera topic, identyfikatory claimów,
deterministycznie wyprowadzone market-case needs, coverage, limity, tier policy, provider mode i
zredagowane capabilities. Nie zawiera całego intake, rekordów naukowych A02, sekretów ani endpointu
SearXNG. `research_web_case_search` zwraca `web_case_tool_result@1`, a finalizacja wiąże każdą
operację z taskiem, topikiem, planem i A02 ref.

Konfiguracja produkcyjna wymaga wspólnego kroku pierwszego uruchomienia. W tym samym formularzu
system prosi o kontaktowy e-mail, `OPENALEX_API_KEY` i `TAVILY_API_KEY`. Klucz
`SEMANTIC_SCHOLAR_API_KEY` jest prezentowany jako opcjonalny i użytkownik może jawnie go pominąć;
arXiv nie wymaga klucza. Tavily jest konfigurowany od razu, także wtedy, gdy operacje A11 nie są
jeszcze aktywne. Sekrety zapisuje magazyn poświadczeń hosta. Nie trafiają one do intake grafu,
konfiguracji JSON, kontekstu LLM, artefaktów, cache ani logów. Obecny ręczny setup zmiennych
środowiskowych pozostaje wyłącznie ścieżką DEV/TEST do czasu implementacji tego onboardingu.

### 15.3. Tiering źródeł i próg materialności

Hierarchia wiarygodności jest kodowana jako preferencja domen i kryterium rankingu, bez
wykluczania niższych poziomów. Tier 1: regulatorzy i nadzór (SEC, CFTC, FCA, ESMA, KNF), raporty
śledcze, dokumenty sądowe, raporty roczne. Tier 2: uznane media finansowe i branżowe. Tier 3:
blogi i materiały marketingowe, wyłącznie jako sygnał z flagą `weakly_sourced`. Próg materialności
(skala zdarzenia, realna konsekwencja, potwierdzenie w źródle wyższego tieru) odsiewa anegdoty i
ciekawostki, zanim case wejdzie do prezentowanej puli.

### 15.4. Weryfikacja i synteza

Case'y zatwierdzone przez człowieka przechodzą lekki wariant G02-A07 Paper Review przez skill
`g02-a11-extract-case-evidence`: ekstrakcja strony do evidence card (co się stało, mechanizm,
źródło, tier), z oddzieleniem faktu rynkowego od interpretacji dydaktycznej. Dalej karty trafiają
do G02-A08 i pełnej syntezy G02-A09 jak inne dowody, co zachowuje identyfikowalność
need, claim, market_case, evidence card, rekomendacja. Operacja ekstrakcji wymaga zapisanego
`human_source_selection@1` o statusie `approved`, `final_confirmation: true` oraz source ID w
`approved_for_download`. Runtime hydratuje również wskazany CandidateSourceIndex i wymaga dokładnie
jednego wpisu dla source ID. Zwraca `web_case_extract_result@1` z refem ograniczonego artefaktu
`untrusted_external_research`, hashem treści, flagami prompt injection i zakazem przekazywania
pełnej strony downstream.

### 15.5. Spójność tabel i komponentów

Profil `market_cases` w par. 7 stosuje kryteria MC-01 do MC-06 (instytucja,
zdarzenie, data, źródło wyższego tieru lub flaga `weakly_sourced`; mapowanie do claimu lub topic z
mechanizmem dydaktycznym; fakt oddzielony od interpretacji; udokumentowane zdarzenie kontra
anegdota; jawny kontekst rynkowy i reżim; brak metadanych tworzonych przez LLM).

Katalog w par. 8 zawiera `g02-a11-find-market-cases` (web discovery realnych, datowanych
case'ów przez `research_web_case_search`) i `g02-a11-extract-case-evidence` (lekka ekstrakcja
evidence card z zatwierdzonego case'a, wariant A07). `g02-classify-source-role` zyskuje rolę
`applied_case`.

Macierz w par. 9 zawiera G02-A11 Market Cases z wymaganymi skillami
`g02-expand-research-query`, `g02-a11-find-market-cases`, `g02-classify-source-role` i bez skilli opcjonalnych na start.
