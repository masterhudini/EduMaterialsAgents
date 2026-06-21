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
    RV2 -->|APPROVED| EXP["Parallel expansion"]

    EXP --> CS["G02-A03 Canonical Sources Agents"]
    EXP --> RD["G02-A04 Recent Developments Agents"]
    CS --> RV3["G02-A10 Output Reviewer\nprofile: canonical_sources"]
    RD --> RV4["G02-A10 Output Reviewer\nprofile: recent_developments"]
    RV3 -->|REVISE| CS
    RV4 -->|REVISE| RD

    RV3 -->|APPROVED| IDX["G02-A05 Candidate Source Index Agent"]
    RV4 -->|APPROVED| IDX
    RV2 -->|APPROVED| IDX

    IDX --> RV5["G02-A10 Output Reviewer\nprofile: candidate_index"]
    RV5 -->|REVISE| IDX
    RV5 -->|APPROVED| HG1["Human Source Selection Gate"]
    HG1 -->|SEARCH_MORE| DR
    HG1 -->|APPROVED| PR["G02-A06 Paper Retrieval Agent"]

    PR --> RV6["G02-A10 Output Reviewer\nprofile: retrieved_corpus"]
    RV6 -->|REVISE| PR
    RV6 -->|APPROVED| PRA["G02-A07 Paper Review Agents\none per document"]

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

Moduł zawiera dziesięć plików agentów, płasko w `agents/` dla auto-discovery. Każdy techniczny
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

Kody `a01`–`a10` są niezmienne i nie zależą od kolejności wykonania. Usuniętego kodu nie wolno
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
powierzchnię MCP lub równoważny adapter Codex. `scripts/render_skill_adapters.py` tworzy wariant
instalacyjny bez modyfikacji źródła i bez dołączania instrukcji drugiego hosta.

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

Uruchamiany po bazowym G02-A02 Domain, osobno dla topic lub domeny.

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

**Wyjście:** `CanonicalCandidateSources`.

### 5.4. G02-A04 Recent Developments Agent

Uruchamiany równolegle z G02-A03 Canonical Sources po G02-A02 Domain.

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

**Wyjście:** `RecentCandidateSources`.

### 5.5. G02-A05 Candidate Source Index Agent

**Cel:** przygotować wiarygodny i czytelny indeks do decyzji człowieka.

**Odpowiedzialności:**

- agregować trzy strumienie kandydatów,
- normalizować metadane,
- deduplikować rekordy,
- przypisywać role źródeł,
- tworzyć osobne sygnały canonical i rising,
- sprawdzać candidate coverage,
- wybierać pulę prezentowaną i rezerwową,
- generować opisy LLM wyłącznie z dostępnych abstraktów,
- tworzyć `candidate_source_index.json` i `candidate_source_review.md`.

**Granice:**

- nie podejmuje ostatecznej decyzji o pobraniu,
- nie przedstawia opisu abstraktowego jako pełnej weryfikacji,
- nie tworzy metadanych bibliograficznych przez LLM,
- nie usuwa zamkniętych źródeł tylko z powodu braku OA.

**Wyjście:** `CandidateSourceIndex` i human-readable review document.

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

**Wyjście:** `RetrievedCorpus`.

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
| `candidate_index` | Deduplikacja, role, ranking, pokrycie, opisy oparte na abstraktach, dokument dla człowieka. |
| `retrieved_corpus` | Tylko zatwierdzone źródła, stabilne ID, integralne pliki, jawne błędy i unavailable. |
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
| `g02-classify-source-role` | Canonical, recent, survey, didactic, claim-specific, optional. |
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
| `g02-review-research-output` | Uniwersalna procedura review względem profile. |
| `g02-orchestrate-research` | Rozmowa, routing, reviewer loops i human gates. |

## 9. Macierz agentów i skilli

| Agent | Wymagane skille | Opcjonalne skille |
|---|---|---|
| G02-A01 Planner | `g02-a01-plan-research-scope` | `g02-expand-research-query` do planu terminów, bez wyszukiwania |
| G02-A02 Domain | `g02-expand-research-query`, `g02-search-scholarly-metadata` | `g02-expand-citation-graph` |
| G02-A03 Canonical Sources | `g02-expand-citation-graph`, `g02-classify-source-role`, `g02-search-scholarly-metadata` | `g02-normalize-source-metadata` |
| G02-A04 Recent Developments | `g02-expand-research-query`, `g02-search-scholarly-metadata`, `g02-classify-source-role` | `g02-expand-citation-graph` |
| G02-A05 Candidate Source Index | `g02-normalize-source-metadata`, `g02-a05-deduplicate-source-records`, `g02-classify-source-role`, `g02-a05-rank-source-candidates`, `g02-a05-annotate-source-candidates`, `g02-assess-source-coverage` | brak na start |
| G02-A06 Paper Retrieval | `g02-a06-resolve-open-access`, `g02-a06-retrieve-open-access-document`, `g02-a06-validate-retrieved-document` | brak na start |
| G02-A07 Paper Review | `g02-a07-extract-paper-evidence` | ukierunkowane ponowne wydobycie |
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

Orkiestrator parsuje odpowiedź, pokazuje podsumowanie i prosi o finalne potwierdzenie.

### 10.3. Powrót do wyszukiwania

`SEARCH_MORE` musi zawierać claim, topic albo brakującą rolę. Orkiestrator kieruje żądanie do
G02-A02 Domain, G02-A03 Canonical Sources lub G02-A04 Recent Developments zgodnie z typem luki.
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

- G02-A02 Domain działa równolegle per topic.
- Canonical i Recent działają równolegle po zatwierdzeniu bazowej puli.
- G02-A07 Paper Review działa równolegle per dokument.
- G02-A08 Claim Verification może działać równolegle per niezależny claim lub ciasny claim group.
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

