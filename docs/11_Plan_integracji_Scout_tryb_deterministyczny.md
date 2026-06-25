# 11. Plan integracji Scout/Radar jako tryb deterministyczny G02

Status: aktywne źródło prawdy dla integracji. Plan przygotowany 2026-06-24 na podstawie
analizy repo EduMaterials oraz źródła `llmwiki_radar` (folder „LLMWiki scout source code").
Postęp: Faza A (standalone Scout w repo EduMaterials) UKOŃCZONA, łącznie z live smoke z siecią,
pobraniem PDF i manifestem (PASS 2026-06-24, szczegóły w sekcji 14). Bramka przed Fazą B zaliczona,
Faza B = GO.

Data: 2026-06-24. Ostatnia aktualizacja progresu: 2026-06-24.

## 0. Cel i zasada nadrzędna

Cel: doprowadzić G02 do działającego, deterministycznego przepływu, który startuje z planu
wyprodukowanego przez działający węzeł A01, wyszukuje i pobiera literaturę silnikiem Scouta
(`llmwiki_radar`), a następnie oddaje wynik jako typowany kontrakt na wejście istniejącego A09,
który produkuje `SolutionInputCandidate` dla Graph03.

Zasada nadrzędna: integracja jest w pełni addytywna. Nie usuwamy ani nie modyfikujemy
zachowania istniejących agentów G02 (A02–A07), ich kontraktów, skilli, runnerów Codex/Claude
ani seamów MCP. Nowy przepływ wchodzi jako osobny tryb wykonania obok dotychczasowych.
Stare, niedziałające agenty zostają na miejscu do czasu, aż tryb deterministyczny zostanie
potwierdzony jako działający end-to-end. Decyzja o ich usunięciu jest świadomie odłożona.

Druga zasada: pliki Scouta przenosimy bez zmiany ich logiki. Dopracowujemy wyłącznie szew
wejścia (plan A01 → zapytanie Scouta) i szew wyjścia (`RunResult` → kontrakty A09). Sam
`run_student` i jego zależności pozostają nietknięte, żeby zachować przetestowane zachowanie
i własne testy Scouta.

## 1. Decyzje zablokowane (z rozmowy roboczej)

1. Najprostszy przypadek napędu: jedno wywołanie `run_student` na zbiorczym zapytaniu
   złożonym z planu A01 (temat główny plus słowa kluczowe i intencja jako `intent`). Bez
   pętli per temat i bez scalania wielu przebiegów w pierwszej wersji.
2. Selekcja źródeł: automatyczny `apply_selection` top N, jak w domyślnym zachowaniu Scouta.
   Bez interaktywnej bramki człowieka w pierwszej wersji.
3. Warstwa LLM Scouta zostaje na OpenRouter (ekspansja zapytania, werdykt trafności,
   streszczenie), z twardym limitem kosztu i trybem fail-open. Nie przepinamy tego na model
   hosta. Streszczenia Scouta służą potem jako findings dla A09, więc nie ma drugiego
   wywołania LLM po stronie A09.
4. Recenzja artefaktów do A09 idzie deterministycznym fast-track z `reviewed_flow`, bez
   uruchamiania agenta A10.
5. A09 musi zostać użyte, bo to ono produkuje kontrakt wejściowy Graph03
   (`SolutionInputCandidate` / `user_approved_research_bundle@1`).

## 2. Co implementujemy

Trzy nowe elementy plus jeden punkt konfiguracji. Wszystko nowe, nic nadpisanego.

Silnik Scouta w repo. Vendoring rdzenia `llmwiki_radar` do `shared/scripts/g02/scout/`.
Cały rdzeń jest czysto stdlib (`urllib`, `sqlite3`, `json`, `xml`, `email`), więc mieści się
w zasadzie dependency-free rdzenia EduMaterials bez wprowadzania zależności. SHA-256 dla
`retrieved_corpus@1` dolicza dopiero adapter, przez stdlib `hashlib` (Scout sam hashy nie liczy).

Adapter wyniku. Nowy moduł `shared/scripts/g02/scout_adapter.py`, który mapuje `RunResult`
na typowane kontrakty EduMaterials wymagane przez A09 (sekcja 6). Adapter dolicza SHA-256 per
pobrany plik, bo Scout go nie liczy, a `retrieved_corpus@1` tego wymaga.

Sterownik trybu deterministycznego. Nowy moduł `shared/scripts/g02/deterministic_flow.py`,
który spina: odczyt planu A01 → zbudowanie jednego zapytania → `run_student` →
`apply_selection` → adapter → fast-track review → `research_synthesis_prepare` →
`research_synthesis_finalize`. Sterownik reużywa istniejących seamów `reviewed_flow` i
`synthesis`, nie tworzy własnej logiki recenzji ani syntezy.

Punkt wpięcia trybu. Nowa podkomenda `run-deterministic` w `shared/scripts/g02/g02_flow.py`
obok istniejących `run` (stub) i `run-codex` (agenci LLM), plus wpis profilu `deterministic`
w `execution_profiles` w `shared/graphs/g02.graph.json`. Selekcja env przez nową wartość
trybu (np. `EMAGENTS_G02_MODE=deterministic`), spójną z istniejącym `EMAGENTS_G02_PROFILE`.

## 3. Co omijamy w obecnym systemie (bez usuwania)

W trybie deterministycznym nie uruchamiamy wielagentowej ścieżki forward A02–A07, czyli
agentów `g02-a02-domain`, `g02-a03-canonical-sources`, `g02-a04-recent-developments`,
`g02-a11-market-cases`, `g02-a05-candidate-source-index`, `g02-a06-paper-retrieval`,
`g02-a07-paper-review`. To właśnie ta warstwa zawodzi w Rundach 9–11 (`docs/08`), bo agent
LLM nie potrafi niezawodnie sterować narzędziami MCP. Wszystkie te pliki agentów, kontrakty
i seamy zostają w repo nietknięte i nadal dostępne w trybach `run` oraz `run-codex`.

Findingi F-A do F-H z `docs/08` dotyczą wyłącznie ścieżki agentowej, więc w trybie
deterministycznym są nieistotne dla działania i pozostają jako dług techniczny do osobnej
naprawy, nie jako blocker integracji. To samo dotyczy F-C (scheduler nie zatrzymuje się po
`BLOCKED`): jeśli sterownik deterministyczny wywołuje A09 bezpośrednio, a nie przez pełny
scheduler grafu, F-C nie wpływa na tryb deterministyczny.

A01 zostaje używane w obu światach, bo działa i produkuje `research_plan@1`. Tryb
deterministyczny konsumuje jego wyjście jako wejście, nie zastępuje go.

## 4. Co i jak zastępujemy

Zastąpienie jest logiczne, nie fizyczne. W ścieżce wartości tryb deterministyczny podmienia
rolę agentów A02–A07 silnikiem Scouta, ale robi to przez wybór trybu, a nie przez nadpisanie
plików. Tabela ról:

| Rola w grafie | Obecnie (ścieżka agentowa) | W trybie deterministycznym |
|---|---|---|
| Plan badawczy | A01 Planner (LLM, działa) | bez zmian, A01 jak dotąd |
| Discovery i pobranie | A02–A06 (agenci + seamy MCP) | `run_student` Scouta (jedno wywołanie) |
| Ocena trafności pracy | A07 Paper Review (LLM) | werdykt OpenRouter Scouta (fail-open) |
| Indeks i korpus | A05/A06 seamy | adapter → `candidate_source_index@1`, `retrieved_corpus@1` |
| Recenzja artefaktu | A10 Reviewer (LLM) | deterministyczny fast-track z `reviewed_flow` |
| Synteza i handoff | A09 Synthesizer | bez zmian, A09 finalize jak dotąd |

## 5. Mapa plików Scouta: co kopiujemy 1:1, co pomijamy

Kopiujemy 1:1 do `shared/scripts/g02/scout/` (rdzeń, czysto stdlib):

- `engine.py` — `run_student`, `RunResult`, `Candidate`, `apply_selection`,
  `export_references`, `copy_to_converter`, `_write_manifest`, ranking i dedup wersji.
- `providers.py` — `build_search_providers`, `build_resolvers`, `parse_sources`,
  źródła OpenAlex/Semantic Scholar/arXiv/CORE.
- `http_util.py` — `request_with_retry`, pacing per host, `set_retry_hook`, bezpieczniki
  HTTP (`HTTP_MAX_CALLS_PER_RUN`).
- `state_store.py` — `ScoutStore` (sqlite: rejestr przebiegów, werdykty, dedup cross-run).
- `constants.py` — progi planera, longlisty, snowballa, deduplikacji.
- `prompts.py` — prompty ekspansji/translacji/trafności jako kod.
- `app_config.py` — logika konfiguracji i domyślnych wartości; do adaptacji ścieżek workspace.
- `secret_store.py` — odczyt sekretów; do uzgodnienia z modelem env EduMaterials.
- `__init__.py` — żeby pakiet był importowalny.

Pomijamy (warstwa desktop/web, niepotrzebna w trybie terminalowym i grafowym):

- `desktop_app.py`, `web_app.py`, `cli.py` (komenda `app`), katalog `web_static/`,
  zależność pywebview oraz `launcher.py`/`__main__.py` w wersji okienkowej.
- Funkcje CLI Scouta (`search`, `doctor`, `setup`, `audit`) przenosimy jako wzorzec wywołania
  `run_student`, nie jako równoległy interfejs; sterowaniem zajmuje się `deterministic_flow.py`.

Przenosimy też testy Scouta do `tests/scout/` (`test_engine`, `test_providers`, `test_funnel`,
`test_store`, `test_goldset`, `test_http`), żeby zachować dowód, że logika silnika działa po
przeniesieniu.

## 6. Mapowanie wyniku Scouta na kontrakty A09

A09 w trybie `fast` (`research_synthesis_prepare` w `shared/scripts/g02/synthesis.py`)
oczekuje zrecenzowanych `paper_review@1`, `retrieved_corpus@1`, `candidate_source_index@1`,
finalnej selekcji źródeł, `research_plan@1` oraz metadanych profilu. Adapter produkuje to
z `RunResult`:

| Kontrakt A09 | Źródło w `RunResult` / Scoucie | Praca adaptera |
|---|---|---|
| `research_plan@1` | wyjście A01 (już istnieje) | tylko odczyt, brak fabrykacji |
| `candidate_source_index@1` | `RunResult.items` (rank, `score_R`, `rel_score`, `cited_by`, rok, DOI, venue, OA) + stuby | przepisanie pól na schemat indeksu |
| `retrieved_corpus@1` | `RunResult.downloaded` (PDF) + `Candidate` + `MANIFEST.md` + bibtex/csl | dodać SHA-256 i kontrolę `%PDF-`, reszta wprost |
| `paper_review@1` (evidence cards) | werdykt `{relevant, score, summary ~50 słów, reason, model}` per praca | mapowanie statusu (niżej) |
| finalna selekcja źródeł | `apply_selection` top N | lista wybranych plików/DOI |

Mapowanie statusu werdyktu na konserwatywne etykiety A09: `relevant=1` i wysoki `score` →
`supported_by_reviewed_source`; `relevant=None` (fail-open, brak werdyktu) → `needs_human_check`;
niski `score` lub brak streszczenia → `context_only`; brak evidence → `insufficient_evidence`.

Ograniczenie do zapisania w handoffie: Scout ocenia i streszcza na poziomie pracy, nie wydobywa
evidence per claim (to była rola głębokiego A07/A08, wyłączonego w `fast`). EvidenceMap A09
będzie więc tematowy, a wszystkie źródła w wersji „jedno wywołanie" trafią pod jeden scope
tematu głównego planu. To dopuszczalne w `fast` i obsłużone statusami `context_only` oraz
`insufficient_evidence`. A08 raportujemy jawnie jako pominięte.

## 7. Tryb deterministyczny: jak wpięty technicznie

Profile wykonania już istnieją: `planner.py` czyta `EMAGENTS_G02_PROFILE`, a `g02.graph.json`
trzyma `default_execution_profile` i mapę `execution_profiles`. Wybór runnera per tryb jest
już faktem w `g02_flow.py`: `run` używa `stub_node_runner` (bez LLM), `run-codex` używa
`codex_node_runner`. To są dokładnie punkty, w które wpinamy nowy tryb, nic nie przebudowując.

Wpięcie:

1. `g02_flow.py`: nowa podkomenda `run-deterministic`, która woła `deterministic_flow.run(...)`.
   Istniejące `run` i `run-codex` zostają bez zmian.
2. `deterministic_flow.py`: nowy sterownik. Reużywa `reviewed_flow` (fast-track review) oraz
   `synthesis.prepare_synthesis`/`research_synthesis_finalize`. Nie dotyka schedulera ścieżki
   agentowej.
3. `g02.graph.json`: dodanie klucza `deterministic` w `execution_profiles` (limity N,
   oversample, koszt). Klucz addytywny, `default_execution_profile` zostaje `fast`.
4. Selekcja env: `EMAGENTS_G02_MODE=deterministic` przełącza sterownik na ścieżkę Scouta.
   Brak wartości lub inna wartość zachowuje dotychczasowe zachowanie.

Dzięki temu te same dane wejściowe można uruchomić w trzech trybach (`run`, `run-codex`,
`run-deterministic`) bez konfliktu, co ułatwia porównanie i późniejszą decyzję o usunięciu
starej ścieżki.

## 8. Kroki migracji

Faza 0 — wstawienie silnika (cel: `run_student` działa z terminala wewnątrz repo). Szac. 2–3 dni.

1. Utworzyć `shared/scripts/g02/scout/` i skopiować pliki rdzenia z sekcji 5 bez zmian logiki.
2. Przepiąć workspace Scouta na `.emagents/` (override `EMAGENTS_HOME`), żeby katalog PDF,
   cache sqlite i rejestr przebiegów żyły w runtime EduMaterials.
3. Uzgodnić konfigurację i sekrety: zmapować `OPENROUTER_API_KEY`, `POLITE_POOL_EMAIL`,
   `OPENALEX_API_KEY`, `CORE_API_KEY`, `S2_API_KEY` oraz limity (`LLM_MAX_COST_PER_RUN_USD`,
   `DEFAULT_TARGET_N`, `OVERSAMPLE_FACTOR`, `SUMMARY_WORDS`) na model env EduMaterials.
4. Weryfikacja kroku: wywołać `run_student` na przykładowym temacie i potwierdzić pobrane PDF,
   `MANIFEST.md` z zachowanym niezmiennikiem oraz brak wycieku sekretów w runtime.

Faza 1 — adapter i recenzja (cel: poprawne artefakty A09 z `RunResult`). Szac. 3–4 dni.

5. Napisać `scout_adapter.py` mapujący `RunResult` na `candidate_source_index@1`,
   `retrieved_corpus@1` (z SHA-256 i kontrolą `%PDF-`) oraz `paper_review@1` per źródło wg
   tabeli i mapowania statusów z sekcji 6.
6. Wpiąć deterministyczny fast-track z `reviewed_flow`, który zatwierdza wygenerowane
   `paper_review@1` bez agenta A10 i wystawia `review_decision@1`.
7. Weryfikacja kroku: testy adaptera na mocku `RunResult` potwierdzają, że artefakty
   przechodzą walidatory kontraktów oraz że `prepare_synthesis` przyjmuje zestaw bez ręcznych
   poprawek.

Faza 2 — spięcie i twardnienie (cel: jedno polecenie A01 → Scout → A09). Szac. 2–4 dni.

8. Napisać `deterministic_flow.py`: odczyt `research_plan@1` z A01, zbudowanie jednego
   zapytania (temat plus keywords i intent), `run_student`, `apply_selection` top N, adapter,
   fast-track, `research_synthesis_prepare`/`finalize`.
9. Dodać podkomendę `run-deterministic` w `g02_flow.py` i profil `deterministic` w
   `g02.graph.json`.
10. Przenieść testy Scouta do `tests/scout/` i dodać test end-to-end trybu deterministycznego
    na mocku sieci.
11. Higiena paczki: build obu hostów, brak `web_static`/binariów/`__pycache__` w bundlu,
    skan sekretów, `graph_check` zielony z nowym profilem.
12. Weryfikacja końcowa: pełny przebieg z terminala kończy się poprawnym `SolutionInputCandidate`.

Łączny szacunek: około 1–2 tygodnie, realistycznie ~1,5 tygodnia na przetestowaną ścieżkę.

## 9. Definicja gotowości

Z terminala EduMaterials jedno polecenie (`run-deterministic` lub przebieg z
`EMAGENTS_G02_MODE=deterministic`) startuje od planu A01 i kończy poprawnym
`SolutionInputCandidate` zgodnym z kontraktem wejściowym Graph03. Pobrane PDF leżą w katalogu
runtime z `MANIFEST.md`, `prepare_synthesis` przechodzi walidację bez ręcznych poprawek, a
przetestowane testy Scouta oraz test adaptera są zielone. Stare agenty i tryby `run`/`run-codex`
pozostają obecne i nienaruszone.

## 10. Do zweryfikowania na starcie implementacji

Dokładne pola wymagane przez walidator `prepare_synthesis` w `synthesis.py`, żeby adapter
trafił w nie za pierwszym podejściem (identyczność zadania, refy A07, powiązania source/corpus).

Sposób, w jaki `ScoutStore` i `engine` nazywają oraz lokalizują katalog przebiegu, żeby
`retrieved_corpus@1` wskazywał dokładnie te pliki, które pobrał Scout, bez dublowania z
`oa_retrieval.py`.

Czy `secret_store.py` Scouta (DPAPI/plik env) da się pogodzić z przekazywaniem sekretów przez
env procesu, zgodnie z higieną sekretów stosowaną w Rundach 9–11.

## 11. Czego świadomie nie ruszamy w tej iteracji

Agentów A02–A07, ich kontraktów, skilli i seamów MCP. Runnerów Codex i Claude. Findingów
F-A do F-H (dług ścieżki agentowej). Bramki człowieka (Human Source Selection Gate i Human
Research Gate w wersji interaktywnej). A08 Claim Verification (pozostaje wyłączone w `fast`).
Decyzję o usunięciu starej ścieżki, którą podejmujemy dopiero po potwierdzeniu, że tryb
deterministyczny działa end-to-end.

## 12. Plan implementacji krok po kroku

Plan jest podzielony na kamienie milowe M0–M5. Każdy kamień to jedna sesja robocza: ja
przygotowuję zmiany, Ty uruchamiasz weryfikację z sekcji „Definicja zaliczenia". Dopiero po
zaliczeniu przechodzimy dalej. Wszystko jest addytywne; tryby `run` i `run-codex` mają działać
nieprzerwanie po każdym kroku.

### Węzeł a12 i łańcuch kontraktów

Warstwę deterministyczną reprezentuje jeden nowy węzeł grafu `g02-a12-deterministic-scout`.
Konsumuje `research_plan@1` z A01, a produkuje cały powiązany łańcuch, którego wymaga A09.
Sam A09 zostaje bez zmian i jest wołany po a12.

`prepare_synthesis` (`synthesis.py:324`) waliduje przechodnie powiązanie i wspólny `task_id`,
więc a12 musi wyprodukować dokładnie taki łańcuch refów:

```text
research_plan@1            (A01)           task_id = T
  └─ candidate_source_index@1   .research_plan_ref      -> plan          (task_id = T)
       └─ human_approved_source_set@1  .candidate_source_index_ref -> indeks   (task_id = T)
            └─ retrieved_corpus@1      .approved_source_set_ref  -> approved   (task_id = T)
                 └─ paper_review@1 [per źródło]  .task_id = T, .source_id ∈ corpus.documents(accepted)
                      └─ review_decision@1  (fast-track, bez A10)
A09: prepare_synthesis(plan, indeks, approved, corpus, [paper_review_refs], reviewed_paper_reviews=…)
     -> finalize_synthesis -> research_state@1 + SolutionInputCandidate
```

Krytyczne reguły walidatora, które adapter musi spełnić za pierwszym razem: wszystkie cztery
artefakty współdzielą jeden `task_id`; `index.research_plan_ref`, `approved.candidate_source_index_ref`
i `corpus.approved_source_set_ref` wskazują dokładnie poprzedni ref; każdy `paper_review@1` ma
`task_id == plan.task_id`, unikalny `source_id`, a ten `source_id` należy do dokumentów korpusu o
statusie `accepted` lub `duplicate`. Naruszenie któregokolwiek punktu kończy się `ValueError` w
`prepare_synthesis`.

### M0 — Vendoring i smoke silnika

Cel: `run_student` działa z poziomu repo, w runtime EduMaterials, bez zmiany logiki Scouta.

1. Utworzyć `shared/scripts/g02/scout/` i skopiować 1:1 pliki rdzenia: `engine.py`, `providers.py`,
   `http_util.py`, `state_store.py`, `constants.py`, `prompts.py`, `app_config.py`, `secret_store.py`,
   `__init__.py`. Pominąć `desktop_app.py`, `web_app.py`, `cli.py` (komenda `app`), `web_static/`,
   `launcher.py`.
2. Poprawić tylko importy względne, jeśli nazwa pakietu się zmienia (`llmwiki_radar` ->
   `g02.scout`); zero zmian w logice funkcji.
3. Skierować workspace Scouta na `.emagents/` przez `EMAGENTS_HOME` (katalog PDF, sqlite cache,
   rejestr przebiegów w runtime EduMaterials).
4. Zmapować sekrety i konfigurację: `OPENROUTER_API_KEY`, `POLITE_POOL_EMAIL`, `OPENALEX_API_KEY`,
   `CORE_API_KEY`, `S2_API_KEY`, oraz `LLM_MAX_COST_PER_RUN_USD`, `DEFAULT_TARGET_N`,
   `OVERSAMPLE_FACTOR`, `SUMMARY_WORDS` na model env EduMaterials (przekazywanie przez env procesu,
   bez zapisu do plików repo).

Definicja zaliczenia: wywołanie `run_student("przykładowy temat", n=5, …)` zwraca `RunResult`,
w katalogu runtime są pobrane PDF i `MANIFEST.md` z zachowanym niezmiennikiem
`N_pdf + N_stub + N_rejected == N_attempted`, skan runtime nie pokazuje sekretów.

### M1 — Deklaracja węzła a12 w grafie (bez logiki)

Cel: graf zna nowy węzeł i profil, stare ścieżki bez zmian.

5. Dodać `agents/g02-a12-deterministic-scout.md` jako dokumentację węzła deterministycznego:
   konsumuje `research_plan@1`, produkuje `candidate_source_index@1`, `human_approved_source_set@1`,
   `retrieved_corpus@1`, `paper_review@1[]`; oznaczyć jako wykonanie deterministyczne (brak workera LLM).
6. Dodać węzeł `g02-a12-deterministic-scout` do `shared/graphs/g02.graph.json` z polami
   `produces`/`consumes` jak wyżej, oraz wpis `deterministic` w `execution_profiles` (limity N,
   oversample, koszt). `default_execution_profile` zostaje `fast`.

Definicja zaliczenia: `graph_check` zielony na source i obu bundlach z nowym węzłem i profilem;
profile `fast`/`strict` i węzły A02–A07 niezmienione; build obu hostów przechodzi.

### M2 — Adapter: RunResult → łańcuch kontraktów (rdzeń pracy)

Cel: z jednego `RunResult` powstają cztery powiązane artefakty, które przechodzą walidatory.

7. Napisać `shared/scripts/g02/scout_adapter.py` z funkcjami budującymi artefakty (wszystkie
   przyjmują wspólny `task_id`):
   - `build_candidate_source_index(run_result, plan_ref, task_id)` z `RunResult.items` (rank,
     `score_R`, `rel_score`, `cited_by`, rok, DOI, venue, OA) i stubów; ustawia `research_plan_ref`.
   - `build_approved_source_set(index_ref, selected)` przez seam `source_selection.py`
     (`parse_selection_template`/`_normalize_selection`/finalize), podając auto top N jako
     „wybór"; ustawia `candidate_source_index_ref`. To deterministyczny odpowiednik bramki.
   - `build_retrieved_corpus(run_result, approved_ref, task_id)` z pobranych PDF; dolicza SHA-256
     (`hashlib`) i kontrolę nagłówka `%PDF-`; każdy dokument dostaje `source_id` i status
     `accepted`; ustawia `approved_source_set_ref`.
   - `build_paper_reviews(run_result, task_id, corpus)` po jednym `paper_review@1` na zaakceptowane
     źródło; evidence card z werdyktu `{relevant, score, summary, reason}`; mapowanie statusu wg
     sekcji 6; `source_id` musi należeć do korpusu.
8. Zapis artefaktów przez istniejący store (`core/artifacts.py`, `artifacts.hydrate`/zapis) i zwrot refów.

Definicja zaliczenia (testy na mocku `RunResult`): każdy artefakt przechodzi swój walidator
schematu; `index.research_plan_ref`, `approved.candidate_source_index_ref`,
`corpus.approved_source_set_ref` wskazują poprawne poprzedniki; wszystkie cztery dzielą jeden
`task_id`; `source_id` recenzji zawierają się w dokumentach korpusu `accepted`.

### M3 — Fast-track recenzji + wpięcie A09

Cel: A09 przyjmuje łańcuch a12 bez ręcznych poprawek i produkuje kontrakt Graph03.

9. Dla każdego `paper_review@1` wywołać `_fast_track_review_decision(task)` z `reviewed_flow.py`
   (zwraca `review_decision@1` bez A10) i zebrać descriptory `reviewed_paper_reviews` z provenance.
10. Wywołać `prepare_synthesis(plan_ref, index_ref, approved_ref, corpus_ref, paper_review_refs,
    reviewed_paper_reviews=…, profile=…)`, potem `finalize_synthesis(...)` ->
    `research_state@1` + `SolutionInputCandidate`.
11. Opcjonalnie wywołać `finalize_research_bundle(research_state_ref, decision)` z deterministyczną
    decyzją Human Research Gate, jeśli chcemy `user_approved_research_bundle@1`; w wersji minimalnej
    zatrzymujemy się na `SolutionInputCandidate`.

Definicja zaliczenia: `prepare_synthesis` zwraca `ready` bez `ValueError`; `SolutionInputCandidate`
jest kompaktowy, A08 raportowane jawnie jako pominięte, etykiety statusu mieszczą się w zbiorze
konserwatywnym; spełnione SY-01..SY-08 na poziomie tematu.

### M4 — Sterownik trybu i podkomenda (spięcie end-to-end)

Cel: jedno polecenie z terminala robi A01 → a12 → A09.

12. Napisać `shared/scripts/g02/deterministic_flow.py`: odczyt `research_plan@1` z A01, złożenie
    jednego zapytania (temat główny + keywords + intent z planu), `run_student`, `apply_selection`
    top N, adapter (M2), fast-track + A09 (M3), emisja `SolutionInputCandidate`.
13. Dodać podkomendę `run-deterministic` w `shared/scripts/g02/g02_flow.py` obok `run` i
    `run-codex`, oraz obsługę `EMAGENTS_G02_MODE=deterministic`.

Definicja zaliczenia: jedno polecenie startuje od planu A01 i kończy poprawnym
`SolutionInputCandidate`; pobrane PDF leżą w katalogu runtime z manifestem; tryby `run` i
`run-codex` nadal działają na tym samym wejściu.

### M5 — Testy, higiena, równoległość trybów

Cel: dowód działania i czysta paczka, trzy tryby obok siebie.

14. Przenieść testy Scouta do `tests/scout/` (`test_engine`, `test_providers`, `test_funnel`,
    `test_store`, `test_http`, `test_goldset`) i dodać `tests/test_scout_adapter.py` oraz test
    end-to-end trybu deterministycznego na mocku sieci.
15. Higiena paczki: build obu hostów, brak `web_static`/binariów/`__pycache__` w bundlu, skan
    sekretów, `graph_check` zielony na trzech hostach z profilem `deterministic`.

Definicja zaliczenia: pełny `pytest` zielony (warstwa Scouta + adapter + e2e); `run`, `run-codex`
i `run-deterministic` współistnieją bez konfliktu; bundle czyste.

### Kolejność i punkty kontroli kontraktów

Pracujemy ściśle M0 → M5. Trzy najważniejsze punkty „czy dobrze czyta kontrakty i przekazuje
informacje" to: w M2 zgodność schematów i przechodnie powiązanie refów; w M3 akceptacja przez
`prepare_synthesis` bez ręcznych poprawek; w M4 przejście całego łańcucha z jednego polecenia.
Jeśli którykolwiek punkt nie przechodzi, zatrzymujemy się na nim i poprawiamy adapter, nie idąc dalej.

## 13. Audyt i dostrojenie planu (2026-06-24)

Po ponownej analizie obu repozytoriów dopisuję odkrycia i korekty. Część korekt wynika z
nowych decyzji projektowych podjętych w trakcie audytu.

### 13.1 Determinizm Scouta i przepływ danych, kluczy oraz API (potwierdzone)

`run_student` (`engine.py:1321`) ma deterministyczny, ograniczony przepływ sterowania. Kolejne
etapy, krok po kroku:

1. Bezpieczniki HTTP: `set_min_interval` (pacing per host) i `reset_run_budget` (twardy,
   thread-local licznik `HTTP_MAX_CALLS_PER_RUN=500`, zerowany na starcie przebiegu).
2. Budowa zapytań per język. Dla każdego języka `expand_query` (LLM) zwraca curated query plus
   słowa kluczowe i domenę; gdy język tematu inny niż docelowy, `translate_query` (LLM). Obie
   funkcje są fail-open: brak klucza lub błąd degraduje do dosłownego tematu.
3. Transparencja okna lat: `openalex_match_count` (OpenAlex) liczy `year_drop_pct`.
4. Pula zapytań: zapytanie per język plus zapytanie ze słów kluczowych plus opcjonalne fasety,
   ograniczone `MAX_QUERIES=20`.
5. Pętla wyszukiwania per zapytanie: `openalex_search` (OpenAlex) plus `semantic_scholar_extend`
   (S2, wymaga klucza) plus dostawcy `extra_search` (CORE/crossref/econbiz). Dedup po DOI.
6. Opcjonalny snowball przypisów top-seedów (OpenAlex).
7. `_dedup_versions` scala preprint z wersją wydawcy. Filtr OA. `prerank_candidates` po
   dopasowaniu tokenowym intencji i wpływie.
8. Bramka trafności przed pobraniem jest TOKENOWA (`min_intent_match`), nie LLM. Odsiewa szum
   przed pobraniem.
9. Pobranie do `target = max(n, ceil(oversample*n))`, kwota językowa, dedup cross-run z cache.
10. Dla pobranych, opcjonalnie werdykt LLM `openrouter_relevant` na ~6000 znakach tekstu PDF:
    `{relevant, score, summary, reason}`. To NIE odrzuca pracy, daje tylko `rel_score` do rankingu
    i streszczenie. Cost-capped (`max_cost_usd`), cache w store, fail-open (`relevant=None`).
11. Prestiż venue (`fetch_source_stats`), `rank_items` z `DEFAULT_RANK_WEIGHTS` (`RANK_W_REL=0.4`
    itd.), `_write_manifest` z niezmiennikiem `N_pdf + N_stub + N_rejected == N_attempted`.

Klucze i API: `email` jako User-Agent polite-pool (OpenAlex/Unpaywall/S2/arXiv);
`openalex_api_key` jako parametr `api_key`; `s2_api_key` jako nagłówek `x-api-key`; `core_api_key`
w dostawcy CORE; klucz LLM jako `Authorization: Bearer`. Wszystkie klucze wędrują argumentami z
konfiguracji, nigdy na sztywno.

Źródła niedeterminizmu, które trzeba przyjąć świadomie: wywołania LLM (ekspansja, ocena), choć
przy `temperature=0` i fail-open; `datetime.now().year` w liczeniu recency (zmienia ranking między
latami kalendarzowymi); dane live z API (cytowania, FWCI, status OA zmieniają się w czasie);
jitter retry (tylko timing). Wniosek dla nazewnictwa: tryb jest deterministyczny w sterowaniu, nie
bitowo-powtarzalny w wyniku. Krok LLM wpływa na ranking (`RANK_W_REL`), więc włączenie i wyłączenie
oceny LLM zmienia wybór top N. Stąd potrzeba jawnego przełącznika determinizmu (niżej).

### 13.2 Największa pułapka pierwotnego planu: ciężki łańcuch kontraktów

Audyt schematów pokazał, że wejście A09 wymaga pięciu ciężkich, wzajemnie powiązanych
artefaktów, a `paper_review@1` ma 22 pola wymagane, w tym `reviewed_document_sha256`, `topic_ids`,
`claim_ids`, `method`, oraz evidence cards z polami `relation`, `locations` i `confidence`.
`candidate_source_index@1` wymaga per źródło 15 pól (m.in. `coverage_unit_ids`, `role_assignments`,
`provenance_records`), a `human_approved_source_set@1` i `retrieved_corpus@1` kolejnych
kilkunastu. Scout nie zna większości tych pól (nie wydobywa zlokalizowanych cytatów ani claimów).
Ręczne wytwarzanie tych pięciu artefaktów w adapterze, tak jak zakładała pierwotna sekcja 12,
byłoby pracochłonne i kruche (ryzyko odrzuceń przez walidatory, w tym kontrole anty-fabrykacji
z A07, por. F-12-4).

Ta pułapka zostaje zneutralizowana przez decyzję z 13.3a.

### 13.3 Decyzje doprecyzowujące (z rozmowy)

(a) Kontrakty na stykach A01→Scout oraz Scout→A09 przepisujemy pod Scouta. Zamiast wpasowywać
Scout w ciężkie istniejące schematy, definiujemy nowe, cienkie kontrakty dopasowane do tego, co
Scout naturalnie przyjmuje i zwraca. Najważniejsze jest, żeby działający Scout podłączył się jak
najłatwiej; resztę pipeline'u doginamy do niego.

(b) Rezygnujemy z OpenRouter. Skoro pracujemy w Codex/Claude, kroki LLM Scouta (ekspansja
zapytania, ocena trafności, streszczenie) kierujemy do modelu środowiska, w którym akurat
działamy, a nie do zewnętrznego OpenRouter. Znika `OPENROUTER_API_KEY`, modele `OPENROUTER_MODEL_*`
i wycena per token OpenRouter.

(c) Priorytet wykonania: najpierw doprowadzić wejście A01→Scout i pełny przebieg Scouta zwracający
jego natywny wynik. Mapowanie Scout→A09 jest wtórne i upraszczane swobodnie.

### 13.4 Dostrojona architektura

Dwa cienkie kontrakty zamiast pięciu ciężkich:

- `scout_search_request@1` (A01→Scout): `task_id`, `query` (zbudowane z planu), opcjonalne
  `keywords`, `intent`, `target_n`, `year_from/to`, `output_language`. Adapter wejścia czyta
  `research_plan@1` i składa jedno zapytanie.
- `scout_result@1` (Scout→A09): cienka serializacja `RunResult`. Lista źródeł z polami, które
  Scout i tak ma (`doi`, `title`, `year`, `authors`, `venue`, `oa_status`, `cited_by`, `fwci`,
  `rel_score`, `abstract_short`/`summary`, `filename`, `is_retracted`, `intent_match`, `rank`,
  `score_R`), plus `run_directory_ref`, manifest i SHA-256 per plik (dolicza adapter).

A09 dostaje nową, deterministyczną ścieżkę wejścia, która buduje `research_state@1` i
`SolutionInputCandidate` bezpośrednio ze `scout_result@1`, bez wymagania pełnego łańcucha pięciu
artefaktów. To jest dodatkowe wejście A09 obok istniejącego `prepare_synthesis`, nie podmiana.

Granica, której nie wolno przekroczyć: upraszczamy WEJŚCIE A09 i wejście Scouta, ale WYJŚCIE A09
(`SolutionInputCandidate` / `user_approved_research_bundle@1`) musi pozostać zgodne z kontraktem
wejściowym Graph03, bo Graph03 jest realnym konsumentem w dół. Scout-friendly dotyczy dwóch styków,
nie handoffu do Graph03.

Warstwa LLM Scouta staje się wymienna. Definiujemy interfejs `llm_complete(system, user) -> text`
i implementację opartą o model hosta (Codex/Claude) zamiast OpenRouter. Prompty z `prompts.py`
zostają bez zmian (prompt-as-code), zmienia się tylko transport. Dwa realne backendy:

- Pod agentem (Codex/Claude): bounded kroki LLM (ekspansja, ocena/streszczenie) wykonuje natywnie
  model środowiska. Ryzyko z Rund 9–11 nie wraca, bo to pojedyncze, proste wywołania, nie
  wielokrokowa orkiestracja narzędzi MCP.
- Tryb czysto terminalowy bez modelu: backend LLM nieobecny, Scout degraduje do rankingu
  tokenowego (fail-open), pipeline nadal działa.

Przełącznik determinizmu: `verify_llm=False` daje przebieg w pełni deterministyczny (ranking
tokenowy, bez kroku LLM), `verify_llm=True` włącza ocenę modelu hosta jako usprawnienie. To czyni
różnicę „tryb deterministyczny" kontra „tryb usprawniony" jawną i sterowalną.

### 13.5 Korekty do sekcji 12

M2 (adapter): zamiast budować pięć ciężkich artefaktów, adapter serializuje `RunResult` do
`scout_result@1` (cienki) i dolicza SHA-256 oraz kontrolę `%PDF-`. Spada ryzyko i nakład.

M3 (A09): zamiast `prepare_synthesis` z pełnym łańcuchem, dodajemy deterministyczne wejście A09
przyjmujące `scout_result@1` i produkujące `research_state@1` plus `SolutionInputCandidate`.
Fast-track recenzji A10 staje się zbędny w tej ścieżce, bo nie wytwarzamy `paper_review@1` jako
osobnych zrecenzowanych artefaktów; ewentualne statusy ufności przenosimy wprost ze `scout_result@1`.

Nowy krok przed M2: adapter wejścia A01→Scout (`scout_search_request@1`) i bridge LLM do modelu
hosta. To jest teraz priorytet numer jeden (decyzja 13.3c), realizowany zaraz po M0.

M4 (sterownik): bez zmian co do idei, ale łańcuch jest krótszy: A01 → `scout_search_request@1`
→ `run_student` (LLM przez host) → `scout_result@1` → deterministyczne wejście A09 →
`SolutionInputCandidate`.

Reszta sekcji 12 (M0 vendoring, M1 węzeł a12 w grafie, M5 testy i higiena) zostaje aktualna.

### 13.6 Pozostałe drobne dziury i zalecenia

Determinizm nazwy. Nazwa „tryb deterministyczny" jest poprawna dla sterowania, ale z włączonym
LLM wynik nie jest bitowo powtarzalny. Zalecenie: w grafie i CLI rozróżnić `deterministic`
(verify_llm wyłączone) od `enhanced` (verify_llm przez host), albo udokumentować to jako jeden tryb
z parametrem.

Wersja Pythona. Rdzeń EduMaterials używa `from datetime import UTC` (3.11+). Scout używa zwykłego
`datetime` bez `UTC`, więc na 3.10 nie psuje się z tego powodu, ale całość i tak wymaga 3.11+ przez
istniejący rdzeń. Do potwierdzenia przy M0.

Higiena sekretów. Nie wnosimy do repo ani do bundla `scout.env`/`radar.env` ani plików `_*_env`.
Klucze (OpenAlex, S2, CORE, polite-pool email) przekazujemy przez env procesu, spójnie z higieną
z Rund 9–11. Po usunięciu OpenRouter znika jego klucz w ogóle.

Własność pobierania. W tym trybie pobiera Scout (Unpaywall/resolvery/preprint/stub), nie A06.
Tym samym findingi A06 (DOAB HTTP 403 i migracja DSpace-6→7, OpenAlex 401 incydentalny) nie
dotyczą ścieżki Scouta. `retrieved_corpus@1`, `retrieval_directory@1` i `oa_retrieval.py` nie są
używane w tym trybie. Scout sam jest właścicielem `source_id` (np. z DOI), spójnego w całym wyniku.

Koszt. Twardy bezpiecznik kosztu Scouta tracił sens jako wycena OpenRouter, ale samą ideę limitu
(maks. liczba wywołań/tokenów na przebieg) warto utrzymać dla modelu hosta, żeby krok oceny nie
puchł przy dużym N.

Wątkowość. `run_student` używa thread-local budżetu HTTP i `set_retry_hook`. Przy uruchamianiu z
jednego procesu sterownika to bezpieczne; nie wołamy wielu przebiegów współbieżnie w jednym wątku.

### 13.7 Kolejność wdrożenia: najpierw Scout standalone, potem A01, potem A09

Wdrożenie jest bramkowane w trzech fazach w tej kolejności. Każda faza musi przejść, zanim
ruszy następna. Ta kolejność jest nadrzędna wobec numeracji M z sekcji 12: M-y są listą prac,
a poniższe fazy określają, kiedy je wykonujemy i co blokuje co.

Faza A, Scout standalone w EduMaterials (bramka). Najpierw umieszczamy Scout w repo i sprawdzamy,
że działa sam, uruchamiany z terminala na podstawowym wejściu, i że cały przebieg przechodzi
poprawnie. Bez podpinania do A01 i bez podpinania do A09. Zakres prac: M0 z sekcji 12 (vendoring
rdzenia do `shared/scripts/g02/scout/`, workspace na `.emagents/`, konfiguracja i sekrety przez
env). Test wykonujemy najprościej, bez LLM (`verify_llm=False`), żeby zweryfikować rdzeń
deterministyczny: wyszukiwanie, pobranie, ranking, manifest.

Definicja zaliczenia Fazy A: pojedyncze polecenie z terminala (odpowiednik `search "temat" -n 5
--out <katalog>` Scouta, wywołane wewnątrz repo) kończy się bez wyjątku i zwraca `RunResult`;
w katalogu są pobrane PDF i `MANIFEST.md`; niezmiennik `N_pdf + N_stub + N_rejected == N_attempted`
jest zachowany; brak klucza LLM nie wywala przebiegu (fail-open); skan runtime nie pokazuje
sekretów. Opcjonalnie powtarzamy z modelem hosta jako krokiem oceny, gdy backend LLM jest gotowy.

Faza B, podpięcie wejścia A01 → Scout. Dopiero po zielonej Fazie A. Adapter wejścia czyta
`research_plan@1` z działającego A01 i składa `scout_search_request@1` (jedno zapytanie z tematu,
słów kluczowych i intencji). Definicja zaliczenia: plan A01 napędza `run_student` i daje ten sam
typ wyniku co w Fazie A, tyle że zapytanie pochodzi z planu, nie z ręcznego argumentu.

Faza C, podpięcie wyjścia Scout → A09. Dopiero po zielonej Fazie B. Adapter wyjścia serializuje
`RunResult` do `scout_result@1`, a A09 dostaje nowe deterministyczne wejście, które buduje
`research_state@1` i `SolutionInputCandidate`. Definicja zaliczenia: jedno polecenie przechodzi
całość A01 → Scout → A09 i kończy poprawnym `SolutionInputCandidate` zgodnym z wejściem Graph03.

Mapowanie faz na M z sekcji 12: Faza A = M0 (plus M1 deklaracja węzła a12, jeśli chcemy go widzieć
w grafie już teraz, opcjonalnie). Faza B = adapter wejścia (nowy krok przed M2). Faza C = M2 (cienki
`scout_result@1`) i M3 (deterministyczne wejście A09). M4 (sterownik i podkomenda) domyka Fazę C.
M5 (testy i higiena) wykonujemy na końcu, po przejściu A → B → C.

### 13.8 Co Scout robi po wyszukaniu (zachowanie potwierdzone w kodzie)

To jest dokładnie to zachowanie, którego chcemy, i tak właśnie działa zvendorowany moduł
(`shared/scripts/g02/scout/engine.py`, funkcja `run_student`). Potwierdzone czytaniem kodu.

Najważniejsze rozstrzygnięcie: Scout najpierw POBIERA pliki PDF (tylko Open Access, legalnie), a
streszczenie robi OSOBNO dla każdego pobranego pliku. Nie tworzy jednego podsumowania ze wszystkich
prac i nie streszcza bez pobierania. Prace zamknięte, których nie można pobrać legalnie, zapisuje
jako stub z metadanymi, bez pliku.

Sekwencja po wylistowaniu kandydatów:

1. Ustala `target = max(N, ceil(oversample*N))` (domyślnie 1,5×N) i ewentualną kwotę językową.
   Sprawdza dedup cross-run i pomija prace już pobrane w poprzednich przebiegach.
2. Pobiera PDF przez `resolve_and_download` etapami, żeby oszczędzać zapytania: najpierw bezpośrednie
   `pdf_url` z OpenAlex i warianty arXiv (bez dodatkowych callów), potem Unpaywall, potem resolvery
   CORE/Crossref, na końcu Semantic Scholar per DOI z kluczem.
3. Każde pobranie weryfikuje nagłówkiem `%PDF` (`_save_if_pdf`). Gdy URL zwraca HTML strony
   docelowej, scrapuje `citation_pdf_url` i linki `.pdf` na głębokość 1. Zapisuje plik na dysk z
   ochroną przed kolizją nazw.
4. Gdy żaden URL nie da pliku, a praca jest OA, zapisuje stub `.md` (metadane + DOI), zamiast obchodzić
   paywall. Preprint arXiv dociąga tylko dla ważnych prac bez wersji wydawcy, jeśli na to pozwolono.
5. Dopiero po udanym pobraniu, jeśli `verify_llm` jest włączone, tworzy streszczenie i ocenę trafności
   dla TEGO JEDNEGO pliku: `extract_relevance_text` wycina abstrakt, wstęp i wnioski (około 6000
   znaków), a model zwraca `{relevant, score, summary ~50 słów, reason}`. To per praca, cache'owane,
   z limitem kosztu i fail-open. Bez `verify_llm` jest tylko skrót abstraktu z metadanych.
6. Dokłada do `result.items` bogaty rekord per praca (plik, DOI, tytuł, rok, cytowania, FWCI, venue,
   OA status, licencja, `rel_score`, streszczenie, intent_match), dociąga prestiż venue, liczy ranking
   ważony `rank_items`, zapisuje `MANIFEST.md` z niezmiennikiem
   `N_pdf + N_stub + N_rejected == N_attempted` i zwraca `RunResult`. Wybór top N i przeniesienie
   reszty do rezerwy robi `apply_selection`.

Zależność: krok streszczenia używa `pypdf` do odczytu tekstu PDF (brak `pypdf` → pusty tekst, ocena
pominięta, fail-open). EduMaterials ma `pypdf` zvendorowany w `shared/scripts/_vendor/pypdf`. Samo
wyszukiwanie i pobieranie jest czysto stdlib; `pypdf` potrzebny tylko do streszczeń.

Dopasowanie do EduMaterials. Pobieranie i selekcja pokrywają rolę A02 (wyszukiwanie) i A06
(retrieval, OA resolution, download, walidacja), więc w trybie Scouta A06 i `oa_retrieval.py` są
nieużywane. Streszczenie per praca to bounded krok LLM, który zgodnie z 13.3b kierujemy do modelu
hosta (Codex/Claude). Cross-paper synteza pozostaje zadaniem A09; Scout dostarcza pobrane PDF-y plus
ranking i streszczenia per praca, a A09 składa z tego pakiet dla Graph03. Granica obowiązków zgodna
z planem.

## 14. Dziennik implementacji

### 2026-06-24 — Faza A, standalone Scout in-repo: wykonane

Zakres wykonany. Rdzeń Scouta jest obecny w `shared/scripts/g02/scout/` jako vendored kopia
deterministycznego silnika. Pliki rdzenia (`engine.py`, `providers.py`, `http_util.py`,
`state_store.py`, `constants.py`, `prompts.py`, `app_config.py`, `secret_store.py`, `projects.py`,
`__init__.py`) pozostają zgodne z kopią źródłową `llmwiki_radar`, bez zmian logiki. Warstwa
desktop/web pozostaje poza zakresem tej integracji.

Runtime EduMaterials. Dodano `shared/scripts/g02/scout/runtime.py`, który kieruje workspace Scouta
do `.emagents/g02/scout/`, buduje katalogi przebiegów i PDF (`runs/<run_id>/pdf`), czyta kontakt
oraz klucze providerów z env procesu i nie zapisuje sekretów do repo. Domyślne zmienne:
`EMAGENTS_HOME`, `EMAGENTS_RESEARCH_CONTACT_EMAIL`, `POLITE_POOL_EMAIL`, `OPENALEX_API_KEY`,
`SEMANTIC_SCHOLAR_API_KEY`, `S2_API_KEY`, `CORE_API_KEY`.

Runner terminalowy. Przepisano `shared/scripts/g02/scout/_smoke.py` jako samodzielny runner Fazy A.
Obsługiwane wywołanie bez konfiguracji pakietu:

```text
python shared/scripts/g02/scout/_smoke.py "value at risk garch" -n 5
```

Runner domyślnie działa bez LLM (`verify_llm=False`), bez OpenRouter (`openrouter_key=""`), bez
ekspansji zapytania (`query_expansion=False`) i z lokalnym `ScoutStore`, chyba że podano `--no-store`.
Opcje `--workspace`, `--out`, `--run-id`, `--email`, `--sources`, `--dedup-cross-run` oraz klucze
providerów pozwalają odtworzyć live smoke bez podpinania do A01 lub A09.

Dokumentacja i testy. Dodano `shared/scripts/g02/scout/README.md` z opisem granic Fazy A oraz
`tests/test_g02_scout_phase_a.py` z testami offline dla runtime i runnera. Testy sprawdzają m.in.,
że `_smoke.py` przekazuje do `run_student` ścieżkę PDF pod `.emagents/g02/scout/runs/<run_id>/pdf`,
wyłącza LLM, nie używa OpenRouter, nie włącza ekspansji zapytania i zachowuje kontrolę nad store.

Weryfikacja wykonana lokalnie:

- `py_compile` dla `runtime.py`, `_smoke.py` i `tests/test_g02_scout_phase_a.py` przechodzi.
- `python -B shared/scripts/g02/scout/_smoke.py --help` działa.
- Import runtime zwraca workspace `.emagents/g02/scout`.
- Import `RunResult` z `g02.scout.engine` działa po dodaniu `shared/scripts` do `PYTHONPATH`.

Ograniczenia po tym bloku:

- Pełny live smoke (`search → download → MANIFEST.md`) nie został wykonany, bo wymaga sieci,
  kontaktu polite-pool/API i realnego przebiegu na zewnętrznych źródłach.
- `pytest` nie został uruchomiony, bo w aktualnym interpreterze `C:\Python313\python.exe` brakuje
  modułu `pytest`.
- Po kompilacji lokalnie istnieje `__pycache__`; jest ignorowany przez `.gitignore` i wykluczany
  z bundlowania przez `scripts/build-plugin.py`, więc nie powinien trafić do paczki.

Rzeczy świadomie niewykonane w tym bloku:

- Brak `scout_search_request@1`.
- Brak `scout_result@1`.
- Brak adaptera A01 → Scout.
- Brak adaptera Scout → A09.
- Brak `deterministic_flow.py` i podkomendy `run-deterministic`.
- Brak deklaracji węzła A12 w grafie.
- Brak bridge LLM do modelu hosta.
- Brak pełnego przeniesienia oryginalnych testów Scouta do `tests/scout/`.

### 2026-06-24 — Faza A live smoke: PASS (bramka zaliczona)

Środowisko: Python 3.14.4, WSL2, bez kluczy API (polite pool przez email). Komenda:

```text
python3 shared/scripts/g02/scout/_smoke.py "value at risk backtesting in GARCH models" \
  -n 5 --email <kontakt> \
  --intent "empiryczne metody i nowsze dowody do odświeżenia wykładu o backtestingu VaR" \
  --lang both
```

Wynik: exit code 0; OpenAlex candidates 10; OA pool 5 (50%); Downloaded PDF 2/5; Stubs 3;
Rejected 0; niezmiennik MANIFEST 2 + 3 + 0 == 5 OK; workspace `.emagents/g02/scout/` bez sekretów
i bez plików env; brak klucza LLM → fail-open (Semantic Scholar pominięty gracefully, przebieg nie
padł). Wszystkie pięć kryteriów Fazy A: PASS. Decyzja: Faza B = GO, brak blokerów po stronie Scouta.

Obserwacje przeniesione do Fazy B:

- `run_student` przyjmuje `progress: Callable[[str, str], None]`, więc w integracji można tam podpiąć
  event-log agenta zamiast `print`.
- Do integracji przekazujemy `ScoutStore(workspace)` z `workspace` z `runtime.workspace_dir()`
  (pod spodem `core.paths.runtime_home()`); `--no-store` jest tylko dla smoke.
- Semantic Scholar wymaga `S2_API_KEY`; bez klucza działają OpenAlex i snowball. Do odnotowania w
  konfiguracji przy podłączaniu do A02/A05.
- Pokrycie OA zależy od tematu (tu około 40%); dla tematów lepiej pokrytych OA spodziewamy się 3–5
  PDF z 5. To cecha danych, nie błąd kodu.

### 2026-06-24 — Kontrola blokera `g02_flow.py` / `reviewed_flow.py`: OK

Sprawdzono aktualny stan dwóch plików, które wcześniej były podejrzane o blokowanie dalszej pracy.
`shared/scripts/g02/g02_flow.py` nie zawiera bajtów NUL (`nul_count=0`) i parsuje się poprawnie.
`shared/scripts/g02/reviewed_flow.py` również nie zawiera bajtów NUL (`nul_count=0`), parsuje się
poprawnie i kończy normalnym `_clear_checkpoint(...)` oraz `return _report(...)`, bez urwanego
stringu w końcówce pliku.

Weryfikacja lokalna: `py_compile` dla obu plików przechodzi; import `g02.g02_flow` i
`g02.reviewed_flow` działa; `g02_flow.py --help` działa; `front-door`, `inputs` dla A01 i zwykły
stub `run` przechodzą na `mocks/g02/research_graph_input.json` bez sieci. Wniosek: ten bloker nie
jest aktualny w bieżącym workspace i nie trzeba się nim zajmować przed Fazą A live ani Fazą B.

### 2026-06-24 — Faza B, wejście A01 → Scout: zaimplementowane

Zakres wykonany. Dodano cienki kontrakt `scout_search_request@1` w
`shared/contracts/scout_search_request.schema.json` oraz adapter `shared/scripts/g02/scout_request.py`.
Adapter czyta natywne `research_plan@1` A01 i produkuje listę requestów, po jednym na topic z
`topics[]`, z zachowaniem `task_id` i `topic_id`.

Utrwalone decyzje mapowania. `query` pochodzi z `topic.name`; `keywords` to deterministyczna lista
`core_terms + allowed_expansion_areas`, przekazywana do Scouta jako `facets` z
`facets_required=[query]`; `intent` pochodzi z `topic.purpose`; `excluded_terms` są przenoszone do
kontraktu, ale jeszcze nie filtrują wyników; `target_n` ma jeden punkt konfiguracji w adapterze,
domyślnie 15 z dolnym limitem 5; pojedynczy `work_type` jest przekazywany, a przy wielu typach
zostaje domyślne puste `work_type`.

Runner. `_smoke.py` nadal działa standalone z ręcznym tematem, ale dostał opcjonalne
`--plan-json <path-or-artifact-ref>` i `--topic-id <id>`. Dla planu wielotopicowego wybór topicu jest
jawny. Brak `OPENALEX_API_KEY` zatrzymuje przebieg czytelnym błędem konfiguracji; email pozostaje
tylko `mailto` polite-pool.

Weryfikacja offline. `mocks/g02/EXAMPLE g02-a01-planner.artifact.json` daje stabilne 2 requesty,
po jednym dla `TOPIC_BAYESIAN_COMPUTATION` i `TOPIC_VARIATIONAL_INFERENCE`; każdy waliduje się
względem `scout_search_request@1`. Testy obejmują brak keywords, brak zakresu lat, jeden topic,
wiele topiców, plan minimalny, wybór `topic_id`, mapowanie `lang`/`work_type` oraz `_smoke.py`
zasilany planem A01 bez sieci. `graph_check` dla g01/g02 pozostaje zielony. A09, graf, A02–A07,
`g02_flow.py` i `reviewed_flow.py` nie były ruszane w tym bloku.

### Następny rekomendowany blok — Faza C, wyjście Scout → A09

Następny blok powinien rozpocząć się dopiero po ewentualnym krótkim smoke per topic z prawdziwym
`OPENALEX_API_KEY`. Zakres Fazy C: serializacja natywnego `RunResult` do `scout_result@1`, agregacja
wyników per `topic_id` i nowe deterministyczne wejście A09, które zbuduje `research_state@1` oraz
`SolutionInputCandidate` bez odtwarzania ciężkiego łańcucha A05/A06/A07.

### 2026-06-24 — Faza B live: PASS (A01 → Scout → PDF, oba topici)

Środowisko: Python 3.14.4, WSL2, `OPENALEX_API_KEY` ustawiony, bez kluczy S2/CORE. Wejście:
`mocks/g02/EXAMPLE g02-a01-planner.artifact.json` → 2 `scout_search_request@1`. Uruchomienie per
topic przez `_smoke.py --plan-json ... --topic-id ...` z `-n 5`.

- TOPIC_BAYESIAN_COMPUTATION: OpenAlex 21, OA 19 (90%), +4 fasety, okno 2021+ (odcięte ~44%),
  pobrane 8/5, stuby 2, rejected 0, manifest 8+2+0=10 OK, selected 5 / reserved 3.
- TOPIC_VARIATIONAL_INFERENCE: OpenAlex 27, OA 27 (100%), +4 fasety, okno 2021+ (odcięte ~60%),
  pobrane 8/5, stuby 4, rejected 0, manifest 8+4+0=12 OK, selected 5 / reserved 3.
- Oba: exit 0, katalog `runs/.../pdf/`, `MANIFEST.md`, niezmiennik OK, brak sekretów, bez LLM/OpenRouter.

Potwierdzone działanie łącznika: keywords A01 (`core_terms`) trafiają jako fasety, okno lat liczone
z `recency_window_years=5`, bramka trafności tokenowa (bez LLM) odcięła szum przed pobraniem.
Klucz OpenAlex dał skok pokrycia OA z około 40% (Faza A na samym email) do 90–100%. `target_n=15`
z adaptera nadpisano w teście przez `-n 5`.

Decyzje do rozstrzygnięcia w Fazie C (wynikłe z testu):

1. Dedup cross-topic. Przy jednym workspace i `dedup_cross_run` praca pobrana dla topicu 1 zostanie
   pominięta w topicu 2, nawet jeśli jest dla niego trafna. Rekomendacja: nie dublować plików, ale w
   `scout_result@1` zapisywać przynależność pracy do wielu `topic_id`, zamiast wyłączać dedup.
2. Co idzie do A09 per topic. `result.items` ma selected (5) i reserved (3). Do A09 przekazujemy
   pełną listę z oznaczeniem selected/reserved, a nie tylko selected; selected jako korpus główny,
   reserved jako zapas.
3. Liczniki pokrycia. `N_attempted` po bramce trafności (10/12) różni się od puli OA (19/27), więc
   `scout_result@1` musi nieść jawnie: oa_pool, attempted, downloaded, stubs, rejected,
   dropped_by_relevance_gate, żeby A09 raportowało pokrycie uczciwie.

### 2026-06-24 — Faza B2, trwały A01 → równoległy Scout: implementacja offline zakończona

Zaimplementowano addytywny profil `scout`, bez zmiany profilu `fast` i bez zmian w trybach `run` /
`run-codex`. A01 ma binding Claude Opus/medium. Przy profilu `scout` dostaje limit sześciu topiców
i instrukcję wyboru 4–6 wyszukiwalnych dziedzin zakotwiczonych w zatwierdzonym intake. Jeden knob
`execution_profiles.scout.scout.total_target=50` jest dzielony przez liczbę topiców przez
`round(50/N)`.

Nowy runner `shared/scripts/g02/scout_fanout.py` uruchamia produkcyjnie osobny proces na topic,
wymaga `OPENALEX_API_KEY` z env, nie używa OpenRouter ani LLM i wyłącza dedup podczas pobierania.
Po zakończeniu wszystkich procesów agreguje prace po DOI albo `clean_title`, zachowując wszystkie
`topic_id` i lokalne kopie. Operacja MCP `research_scout_fanout` przyjmuje zapisany plan A01, a prompt
MCP `research-scout` prowadzi host Claude Code przez prepare/finalize A01 i następnie fan-out.

Trwały layout:

```text
.emagents/g02/scout/runs/<task_id>/
  plan.json                                  # research_plan@1
  requests/<topic_id>.json                   # scout_search_request@1
  topics/<topic_id>/pdf/*.pdf                # zweryfikowane pliki Scouta
  topics/<topic_id>/MANIFEST.md              # manifest przebiegu topicu
  topics/<topic_id>/retrieved_corpus.json    # scout_retrieved_corpus@1
  index.json                                 # scout_run_index@1
```

`local_ref` w korpusach i wszystkie ścieżki w indeksie są względne wobec katalogu przebiegu.
`index.json` zawiera statusy i liczniki topiców, przydzielony budżet oraz mapę deduplikacji z pełnym
członkostwem cross-topic. Jest to wejście przygotowane dla przyszłego adaptera A07; nie jest to pełny
A06 `retrieved_corpus@1`.

Walidacja bez sieci: `graph_check` PASS; dedykowane testy A01/Scout/MCP/build: 30 PASS. Pełny zestaw:
172 PASS, 1 SKIP oraz 1 niezależny fail starego stub harnessu (`test_stub_harness_revise_runs_one_`
`correction_without_second_review`: reviewer A01 liczony dwa razy). Zgodnie z decyzją użytkownika
nie wykonano testu live, nie wywołano OpenAlex i nie pobrano realnych PDF-ów.

### 2026-06-24 — Faza B2 live Claude Code CLI: pobieranie PASS, one-shot A01 do retestu

Pełny zapis znajduje się w `docs/08_Log_wynikow_TEST.md`, Runda 18, a checklista zamknięcia w
`docs/07_Rejestr_DEV_TEST_1b1.md`. Live MCP uruchomił A01 jako Opus (96 s,
`subagent_tokens=31 589`), cztery procesy Scouta i zakończył cały przebieg w około 418 s. Pobrano
70 PDF dla czterech topiców, zapisano komplet plan/request/manifest/corpus/index, otrzymano 66
unikalnych prac i cztery poprawne membershipy cross-topic. Nie wykryto sekretów w JSON.

Pierwszy draft A01 nie był zgodny mechanicznie z `research_plan@1` i wymagał trzech wywołań
finalizera. Dodatkowo didactic topic użył zbyt szerokich terminów i zebrał szum międzydziedzinowy.
Po teście wdrożono `plan_output_template`, deterministyczne boundary fields i normalizację znanych
aliasów oraz walidację dziedzinowego zakotwiczenia/ogólnych query. Zgodnie z decyzją właściciela
fan-out używa teraz jawnie `oversample=1.2`; nie dodajemy dalszej selekcji nadmiaru. Faza B2 wymaga
jednego ponownego live runu, który potwierdzi finalizację A01 za pierwszym razem. Walidacja offline
po poprawkach: 27 dedykowanych PASS; pełny suite 177 PASS, 1 SKIP i jeden wcześniejszy FAIL stub
harnessu poza tą ścieżką.

## 15. Aktualizacja decyzji 2026-06-24: klucz API, łącznik A01, wiele topiców

Ta sekcja aktualizuje trzy rzeczy i ma pierwszeństwo nad wcześniejszymi zapisami tam, gdzie się różni.

### 15.1 Klucz OpenAlex API wymagany domyślnie

Domyślnym trybem pracy Scouta w EduMaterials jest praca z kluczem OpenAlex, bo działa wtedy
znacznie lepiej niż na samym polite-pool przez email (wyższe limity, stabilniejszy throughput).
Wymuszamy obecność klucza: ścieżka deterministyczna (Faza B i dalej) czyta `OPENALEX_API_KEY`
z env przez `runtime.provider_keys()` i przy jego braku zwraca czytelny błąd konfiguracji, zamiast
po cichu spadać na email. Email (`EMAGENTS_RESEARCH_CONTACT_EMAIL`) zostaje jako uzupełnienie polite
pool i parametr `mailto`, nie jako tryb zastępczy. To ujednolica zachowanie z A02, gdzie klucz
OpenAlex jest oznaczony jako wymagany (`provider_config.py`, `key_required == "openalex"`). Standalone
`_smoke.py` może zachować nadpisanie kluczem przez flagę, ale domyślnie też powinien wymagać klucza.

### 15.2 Łącznik A01 → Scout (najważniejszy element spójności)

Kanoniczny przykład wyjścia A01 to `mocks/g02/EXAMPLE g02-a01-planner.artifact.json`
(`research_plan@1`). Nie zmieniamy tego, co produkuje A01. Struktura jest stała; zmienia się tylko
liczba topiców w `topics[]`. Adapter wejścia musi deterministycznie przekształcać ten artefakt na
wejście Scouta i jest testowany właśnie na tym pliku.

Proponowane mapowanie pól (per topic w `topics[]`); część pozostaje do ustalenia z devem:

| Wejście Scouta | Źródło w `research_plan@1` | Uwagi |
|---|---|---|
| `query` | `topic.name` | główny string zapytania |
| `keywords` | `topic.search_strategy.core_terms` (+ `allowed_expansion_areas` jako druga warstwa) | deterministyczny zamiennik ekspansji LLM (która jest wyłączona); kandydat na `facets`/`facets_required` w `run_student` |
| `intent` | `topic.purpose` | używane przez pre-ranking tokenowy Scouta |
| `excluded_terms` | `topic.search_strategy.excluded_terms` | Scout nie ma natywnego wykluczania; do filtra po stronie adaptera lub odłożone |
| `target_n` (liczba prac) | `global_constraints.candidate_limit_per_topic` lub `topic.stop_rule.candidate_limit` (tu 12); albo cel pobrań z sumy `coverage_requirements[].minimum_sources` | DO USTALENIA z devem: limit discovery (12) kontra docelowa liczba pobrań (mniejsza) |
| `year_from`/`year_to` | `topic.search_strategy.year_from/to` → fallback `global_constraints.year_from/to` → jeśli puste, a `approved_research_scope.recency_window_years` ustawione i `include_recent_developments`, wylicz `year_from = rok_bieżący − recency_window_years` | tu wszystkie null, więc okno z recency (5) → `year_from` ≈ rok−5 |
| `lang` | `topic.search_strategy.languages` (tu `["en"]`) → `en`/`pl`/`both` | mapowanie listy na tryb Scouta |
| `work_type` | `topic.search_strategy.work_types` | `run_student` przyjmuje jeden typ; przy liście wielu → zostaw domyślne (wszystkie) lub wybierz `article`; do ustalenia |
| `output_language` | `output_language` planu | dla opisów i raportu |
| `created_from` | `task_id` + `topic_id` | trasowalność z powrotem do planu |

Otwarte pytania do ustalenia z devem: mechanizm keywords w `run_student` (`facets` kontra sklejone
zapytanie), docelowe `target_n`, obsługa `excluded_terms` i wielu `work_types`.

### 15.3 Wiele topiców: jeden przebieg Scouta na topic

Zastępuje pierwotną decyzję o jednym zbiorczym zapytaniu. A01 z natury rozbija pracę na `topics[]`,
a Scout jest deterministyczny i daje opis per pobrany PDF, więc robimy jeden przebieg Scouta na topic
(`run_student` per topic), nie sklejamy wszystkiego w jedno zapytanie. Wyniki agregujemy z kluczem
`topic_id`, a A07 i A09 pracują per topic. Adapter wejścia produkuje listę `scout_search_request@1`,
po jednym na topic. Dedup między topikami robimy po fakcie po DOI/clean_title, zapisując przynależność
pracy do wielu `topic_id` zamiast pomijania, żeby nie zgubić pracy trafnej dla dwóch topiców.

## 16. Faza B2: pełna synchronizacja intake → A01 → Scout → A07 (bez A09)

Cel: z działającego MCP planner A01 generuje 4–6 topiców zakotwiczonych w intake'u, orkiestrator
woła deterministyczny Scout raz na topic równolegle, A07 robi lekki opis każdej pobranej pracy pod
kątem jej topicu, a na dysku lądują PDF-y i jeden zbiorczy JSON opisów. A09 świadomie poza zakresem.

Decyzje zablokowane:

- A01 binding → Opus/medium. Topici ściśle z driverów, claimów, konceptów i approved teaching context.
  Nazwy topiców formułowane jako dziedziny zdatne do wyszukiwania.
- Liczba topiców 4–6, wybiera A01. Nowy profil wykonania (np. `scout`) z `max_topics=6`; `fast` nietknięty.
- Budżet ~50 PDF łącznie; `target_n` per topic = round(50 / liczba_topiców); `scout_request` czyta to
  zamiast sztywnego `DEFAULT_TARGET_N=15`.
- Scout równolegle per topic (orkiestrator, osobne przebiegi, osobne `runs/<topic_id>/pdf`), klucz
  OpenAlex wymagany. Dedup cross-topic po fakcie, z przynależnością do wielu `topic_id`.
- A07 jako warstwa opisu, tryb LEKKI (nowy profil, nie rusza pełnego `paper_review@1`): czyta tylko
  celowane okna (≤4) pod kątem `topic.purpose` + `coverage_requirements` + `related_claims`/
  `related_concepts`/`related_update_needs`, nie całe PDF-y. Model Sonnet/high. Równolegle per topic.
- Wyjście A07: jeden zbiorczy `reviews.json` dla przebiegu, opis per praca (schemat w sekcji 17).

Praca do wykonania:

1. Binding `g02-a01-planner` → opus/medium w `g02.graph.json`; nowy profil `scout` (`max_topics=6`);
   wpięcie `target_n=round(50/N)` w `scout_request`.
2. Wzmocnienie promptu A01 pod kotwiczenie topiców w intake'u i nazwy zdatne do wyszukiwania.
3. Orkiestracja równoległa: N przebiegów Scouta per `scout_search_request@1`, wspólny workspace
   read-only na cache, dedup cross-topic po fakcie.
4. Adapter Scout → minimalny `retrieved_corpus@1` per topic (source_id, lokalny ref, sha256), żeby
   `prepare_paper_review` przyjął źródła.
5. Lekki profil review w A07 (Sonnet/high), okna celowane planem, wyjście do zbiorczego `reviews.json`.
6. Test końcowy w MCP: intake → A01 → równoległy Scout → A07 light → ~50 PDF + `reviews.json`.

Realignment: zastępuje wcześniejszy pomysł cienkiego `scout_result` + osobnego wejścia A09 (13.3a,
13.4) dla warstwy opisu. Opisy robi teraz A07; wiązanie do A09 to kolejna faza.

Uwaga implementacyjna (z wersji wgranej, stan po realizacji Fazy B2): zrealizowany milestone jest
PDF-only, A07 odłożony do następnej tury, więc tytuł tej sekcji odnoszący się do A07 dotyczy docelowej
warstwy, a sama Faza B2 kończy się na PDF-ach i indeksach. Rozstrzygnięcia adaptera A01 → Scout:
`topic.name` pozostaje wymaganym zapytaniem, `core_terms` i `allowed_expansion_areas` trafiają do
deterministycznych `facets`, `target_n` pochodzi wyłącznie z łącznego budżetu profilu `scout`
(`scout.total_target` dzielone przez liczbę topiców), `excluded_terms` są zachowane w requestcie dla
audytu i przyszłego filtra, pojedynczy `work_type` jest przekazywany wprost, a lista wielu typów
oznacza brak dodatkowego zawężenia. Trwałe kontrakty operacyjne z przyszłym A07:
`scout_retrieved_corpus@1` (per topic, zawiera co najmniej `source_id`, `local_ref`, `sha256`, DOI,
tytuł, rok, `topic_ids`; nie udaje pełnego A06 `retrieved_corpus@1`) oraz `scout_run_index@1`
(refy plan/request, status i liczniki każdego procesu, mapa dedupu z pełnym członkostwem cross-topic).
Pełne liczby przebiegów i decyzje są w dzienniku, wpisy „Faza B2" z 2026-06-24.

## 17. Hand-off A07 → A09: karty ustaleń jako kandydaci na rozszerzenie prezentacji

To jest sedno celu G02. Cały graf research istnieje po to, żeby zdobyć najnowsze informacje z nauki,
które pozwolą rozszerzyć istniejącą prezentację będącą wejściem G01. Dlatego to, co A07 wyciąga z
PDF-ów, musi być z definicji kandydatami na rozszerzenie prezentacji, powiązanymi z tym, co wyszło z
intake'u, i opartymi na realnej treści plików.

Łańcuch znaczeniowy:

```text
G01 intake (istniejąca prezentacja) -> drivers, claims, concepts, update-needs, flow-issues
  -> A01 topici (każdy podpięty pod claim/concept/update-need)
  -> Scout pobiera PDF-y per topic
  -> A07 czyta PDF-y soczewką "co nowego, czego wykład nie ma, dotyczy tego claimu/konceptu"
       -> karty ustaleń (intake-zakotwiczone, z dowodem)
  -> A09 grupuje, deduplikuje, rozstrzyga zgodność/sprzeczność, nadaje pewność
       -> SolutionInputCandidate (kontrakt do G03)
  -> G03 tworzy zaktualizowaną prezentację
```

Zasada nadrzędna: A09 jest organizatorem i ramą, nie ekstraktorem. A09 nie czyta PDF-ów i nic nowego
nie dokłada. Cokolwiek nie znajdzie się w kartach od A07, nie pojawi się w kontrakcie do G03. Cała
substancja merytoryczna jest po stronie A07.

Co A07 oddaje do A09 (payload, jedna karta na ustalenie):

- powiązanie z intakiem: `topic_id` plus konkretne `claim_ids` / `concept_ids` / `update_need_ids` /
  `flow_issue_ids` z planu A01;
- ustalenie: nowa informacja albo wynik z tej pracy, sformułowany pod kątem wykładu;
- relacja do obecnej treści (`extension_relation`): confirms / updates_outdated / adds_new_angle /
  contradicts / qualifies / didactic_example;
- dowód: krótki cytat lub fragment z lokalizacją (strona/sekcja), żeby było sprawdzalne i niefabrykowane;
- źródło: `source_id`, DOI, rok, venue, sygnał świeżości (praca z okna recency);
- etykieta pewności w konserwatywnym zbiorze, którego A09 i tak używa
  (`supported_by_reviewed_source`, `needs_human_check`, `insufficient_evidence`, `context_only`).

Forward-compatibility: to jest dokładnie to, co A09 natywnie konsumuje jako evidence_cards w
`paper_review@1` (mają `claim_ids`, `topic_ids`, `relation`, `summary`, `locations`, `confidence`),
z których `prepare_synthesis` buduje EvidenceMap, a `finalize_synthesis` robi SolutionInputCandidate.
Czyli lekki `reviews.json` z Fazy B2 jest zgodny z A09, o ile karty trzymają te pola. W kolejnej fazie
albo mapujemy lekkie karty na evidence_cards A09, albo dodajemy deterministyczne wejście A09 czytające
`reviews.json` wprost. W obu wariantach semantyka musi już być "kandydaci na rozszerzenie powiązani z
intakiem", nie ogólne streszczenia.

Granica: wyjście A09 (SolutionInputCandidate / `user_approved_research_bundle@1`) musi pozostać zgodne
z wejściem G03, bo G03 jest realnym konsumentem w dół. `reviews.json` od A07 to materiał wejściowy
framowany jako kandydaci na rozszerzenie; A09 robi z niego strukturę, pewność i pakiet do bramki człowieka.

Konsekwencja dla schematu lekkiej recenzji z sekcji 16: pole opisu rozwijamy w jawne `linked_intake_ids`
plus `extension_relation` plus krótki dowód z lokalizacją, żeby A07 od początku produkował kandydaty na
rozszerzenie prezentacji, a nie luźne opisy.

## 18. Finalny kontrakt wyjścia A09 → G03 (tryb scout, bez udziału człowieka)

Finalizujemy kontrakt wyjścia G02 jednostronnie, pod framework scout: intake → A01 → Scout → A07 →
A09 → G03. Bez Human Research Gate i bez udziału człowieka w A07 ani A09. W ścieżce
intake → A01 → Scout → PDF i tak nie ma człowieka, więc cała warstwa human-gate wypada. Gdy powstanie
G03, dopasujemy go do tej struktury.

### 18.1 Intake jako wspólny kontekst A07 i A09

Wejście G02 to `research_graph_input@1` (`mocks/g02/research_graph_input.json`). Koduje pierwszą
wersję prezentacji i jest źródłem prawdy o tym, co już jest, więc A07 i A09 muszą z niego korzystać.
Niesie: `task_id`, `output_language`, `user_approved_context` {course_name, audience_level,
target_duration_minutes, teaching_goal}, `approved_domains`, `approved_research_scope`
{verify_claims.priority, include_recent_developments, include_canonical_sources,
include_didactic_examples, recency_window_years}, `research_drivers[]` (DRV_*, priority, purpose,
related_*), `claim_cards[]` (CLM_*, text, verification_need), `concept_context_cards[]` (C*, label,
role), `selected_flow_issue_cards[]` (F_*, severity, summary, affected_slides, fix_hint),
`selected_update_need_cards[]`, `existing_source_cards[]` (SRC_*), `constraints`, `selection_profile`,
`locked_sections`, `artifact_refs_for_lazy_hydration`.

Przepływ kontekstu intake przez łańcuch:

- A07 dostaje `intake_ref` + `research_plan@1` + swój topic. Czyta PDF-y pod kątem konkretnych
  CLM/C/F/update-need przypisanych do topicu i wyciąga to, czego obecna prezentacja jeszcze nie ma.
- A09 dostaje `intake_ref` + karty A07. Organizuje ustalenia względem claimów, konceptów i flow-issues
  intake'u i ramuje, co nowego ma trafić do prezentacji.
- `intake_ref` jest niesiony przez cały łańcuch i jest jawnym polem kontraktu wyjścia.

### 18.2 Co wypada (brak człowieka)

Ze ścieżki scout usuwamy: Human Research Gate, krok `finalize_research_bundle`, kontrakty
`user_research_validation_packet@1` i `user_approved_research_bundle@1`, oraz pola po zatwierdzeniu
przez człowieka (`human_gate_decision`, `approved_at`, `approved_update_findings`,
`approved_optional_findings`, `rejected_findings`). A09 emituje `solution_input_candidate@1`
bezpośrednio jako wyjście do G03, bez bramki i bez approval. Stare kontrakty zostają w repo dla
dawnej ścieżki agentowej, ale nie są używane w trybie scout.

### 18.3 Finalna struktura solution_input_candidate@1 (wyjście A09 → G03)

Pola:

- `schema_version` = "solution_input_candidate@1", `artifact_version`, `task_id` (zgodny z intake).
- `synthesis_mode` = "scout_fast".
- `source_pipeline` = "intake -> a01 -> scout -> a07 -> a09".
- `intake_ref` (ref do `research_graph_input@1`), `plan_ref` (ref do `research_plan@1`).
- `presentation_context`: echo z `user_approved_context` {course_name, audience_level,
  target_duration_minutes, teaching_goal}, plus `output_language`, plus `locked_sections`
  (slajdy/sekcje, których G03 nie rusza).
- `topics_covered[]`: {topic_id, name, linked_claims, linked_concepts, linked_flow_issues,
  linked_update_needs, source_count, coverage_note}.
- `suggested_updates[]`: kandydaci na rozszerzenie prezentacji, każdy:
  - `update_id`;
  - `linked_intake_ids`: {claim_ids, concept_ids, flow_issue_ids, update_need_ids};
  - `affected_slides` (z flow-issues/konceptów, jeśli są);
  - `topic_id`;
  - `extension_relation`: confirms | updates_outdated | adds_new_angle | contradicts | qualifies |
    didactic_example;
  - `finding`: nowa informacja/wynik sformułowany pod wykład;
  - `rationale_vs_presentation`: dlaczego to rozszerza/zmienia obecny wykład (oparte na intake);
  - `evidence_refs[]`: {source_id, location (strona/sekcja), quote};
  - `source_refs[]`: {source_id, doi, year, venue};
  - `confidence`: supported_by_reviewed_source | needs_human_check | insufficient_evidence |
    context_only;
  - `novelty`: sygnał świeżości (w oknie recency).
- `optional_improvements[]`: ta sama struktura co `suggested_updates`, niższy priorytet
  (np. przykłady dydaktyczne, wzbogacenia).
- `unresolved_items[]`: {question, linked_intake_ids, why_unresolved, what_would_resolve}.
- `coverage_summary`: per claim/driver status covered | partial | uncovered + liczby źródeł.
- `evidence_map_ref`, `source_refs[]` (globalna lista wszystkich źródeł).
- `limitations[]`.
- `claim_assessment_performed` = false, `a08_status` = "skipped_scout_fast".
- `graph03_handoff_constraints`: {compact: true, no_full_text: true, output_language,
  locked_sections}.
- `generated_at`.

### 18.4 Mapowanie A07 → wyjście A09

Karty ustaleń A07 (sekcja 17) wchodzą wprost: każda karta z `extension_relation` typu confirms/
updates_outdated/adds_new_angle/contradicts/qualifies trafia do `suggested_updates`; didactic_example
i wzbogacenia do `optional_improvements`; braki i pytania do `unresolved_items`. Każda zachowuje
`linked_intake_ids`, `extension_relation`, `evidence_refs`, `source_refs`, `confidence`. A09 dokłada
tylko grupowanie po claim/topic, dedup, rozstrzygnięcie zgodności/sprzeczności, `coverage_summary` i
`presentation_context` z intake'u. A09 nie czyta PDF-ów ani niczego nie dopisuje poza tym, co przyszło
od A07.

### 18.5 Zmiany w kodzie (do wykonania przez deva)

- Zrewidować `shared/contracts/solution_input_candidate.schema.json` do struktury z 18.3: dodać
  `intake_ref`, `presentation_context`, `topics_covered`, rozbudowane `suggested_updates`/
  `optional_improvements`/`unresolved_items` z `linked_intake_ids` i `extension_relation`; usunąć
  zależność od warstwy human.
- W `shared/scripts/g02/synthesis.py`: w trybie scout pominąć `finalize_research_bundle`, Human
  Research Gate i `user_research_validation_packet@1`; `finalize_synthesis` produkuje
  `solution_input_candidate@1` jako finał, z `synthesis_mode="scout_fast"`,
  `claim_assessment_performed=false`, `a08_status="skipped_scout_fast"`, i niesie `intake_ref`.
- A07 i A09 przyjmują `intake_ref` (`research_graph_input@1`) jako wejście kontekstowe.
- `user_approved_research_bundle@1` i `user_research_validation_packet@1` zostają w repo dla starej
  ścieżki, ale nie są w łańcuchu scout.

## 19. Rozszerzenie: deterministyczne market cases przez Tavily + weryfikacja w A07

Sekcja przeniesiona z wgranej wersji (tam jako 18). Numer 19, bo sekcja 18 w tym pliku to finalny
kontrakt wyjścia A09 → G03. Opisuje planowane rozszerzenie ścieżki deterministycznej o wyszukiwanie
przypadków rynkowych (market cases) jako uzupełnienie pobieranych PDF-ów akademickich. Implementacja
należy do przyszłej tury, po ustabilizowaniu Fazy B2 i A07 dla PDF.

### 19.1 Problem i motywacja

Sekcja 3 tego dokumentu świadomie wyklucza A11 (`g02-a11-market-cases`) ze ścieżki deterministycznej,
bo agent LLM prowadzący otwarte szukanie w internecie był niestabilny (rundy 9–11, findings F-A–F-H).
Jednocześnie market cases są wartościowym kanałem dla A07 i A09: dają praktyczne przykłady wdrożeń
uzupełniające peer-reviewed papers. Plan akademicki (PDF-y) odpowiada na pytanie „co mówi nauka",
market cases odpowiadają na „kto to faktycznie wdrożył i z jakim wynikiem".

Rozwiązanie: zastąpić A11 deterministycznym wywołaniem Tavily wewnątrz potoku Scouta — tym samym
wzorcem, którym A02–A06 zostały zastąpione przez `run_student`. Tavily to clean REST API (POST JSON,
klucz w body, wynik to lista `{title, url, content, published_date}`), zero LLM, zero niedeterminizmu.

### 19.2 Architektura Wariant A (cel implementacji)

Tavily search działa **per topic**, sekwencyjnie po `run_student`, w tym samym wywołaniu `_smoke.py`.
Wyniki trafiają do katalogu `cases/` obok `pdf/` w layoucie B2 (sekcja 16).

Rozszerzony layout per topic:

```text
<EMAGENTS_HOME>/g02/scout/runs/<task_id>/topics/<topic_id>/
  pdf/*.pdf                  (Academic papers — Scout/run_student, już zaimplementowane)
  MANIFEST.md                (Academic papers manifest — już zaimplementowany)
  retrieved_corpus.json      (scout_retrieved_corpus@1 — planowany w Fazie B2)
  cases/*.md                 (Market cases — Tavily, jeden plik .md per case — NOWE)
  CASE_MANIFEST.md           (Market cases manifest z niezmiennikiem — NOWE)
```

Każdy plik `cases/<slug>.md` zawiera: tytuł, URL, snippet z Tavily (~300–400 znaków), datę publikacji,
domenę źródłową. Format analogiczny do stubów Scouta (metadane + referencja), bez pełnej treści strony.

`CASE_MANIFEST.md` trzyma niezmiennik: `N_fetched + N_failed == N_attempted`, identyczna zasada jak
`MANIFEST.md` dla PDF-ów. Każda próba jest zapisana — nic nie ginie cicho.

### 19.3 Dlaczego to jest fundamentalnie inne niż A11

Kluczowa różnica architektoniczna:

```
A11 (niestabilne):
  LLM → "szukaj market cases w internecie" → WebSearch × N → oceń jakość → szukaj więcej → ...
  Problem: LLM decyduje CO szukać, ILE razy, KIEDY skończyć — wielokrokowe sterowanie narzędziami

Tavily-in-Scout (stabilne):
  Scout (Python, deterministycznie) → POST api.tavily.com/search → lista URLi z tytułami
  LLM nie uczestniczy — Scout dostaje gotową listę, zapisuje metadane, koniec
```

Scout nie decyduje o jakości wyników poza filtrem domeny (opcjonalne) i limitem liczby casów.
Tavily rankuje wyniki po swojej stronie. Pula casów jest deterministyczna dla danego zapytania i klucza.

### 19.4 Implementacja po stronie Scouta

Nowy moduł `shared/scripts/g02/scout/web_cases.py` (nie mylić z `shared/scripts/g02/web_cases.py`,
który obsługuje pełną ścieżkę agentową z budgetem/cache/kontraktami). Ten plik jest lekki, stdlib-only.

Nowe elementy:

| Element | Przybliżony zakres | Uwagi |
|---|---|---|
| `TAVILY_API_KEY` w `scout/runtime.py` | ~5 linii | analogia do `OPENALEX_API_KEY` |
| `TavilyCase` dataclass (url, title, snippet, date, domain) | ~15 linii | osobny typ, nie `Candidate` |
| `tavily_search(topic, intent, n, api_key) -> list[TavilyCase]` | ~50 linii | POST + parse JSON, stdlib urllib |
| Query builder dla cases (inny niż akademicki) | ~30 linii | zapytanie w stylu "firma X wdrożyła Y", nie tytuł pracy |
| `run_cases(topic_id, topic, intent, n, api_key, cases_dir) -> CasesResult` | ~50 linii | orchestracja, analogia `run_student` |
| `_write_case_manifest(cases_dir, rows) -> None` | ~30 linii | niezmiennik N_fetched + N_failed == N_attempted |
| `--tavily-key` / `--market-cases N` w `_smoke.py` | ~20 linii | fail-open: brak klucza → cases puste, PDF normalnie |

Łącznie: ~200 linii nowego kodu wyłącznie w `scout/` package. Zero zmian w istniejącym kodzie Scouta,
G02, agentach, kontraktach.

Query builder dla cases jest konceptualnie ważny i musi być **oddzielny** od zapytań akademickich.
Przykład: dla topic "Value at Risk backtesting" zapytanie akademickie to
`"GARCH backtesting VaR estimation methods"` (OpenAlex), a zapytanie do Tavily to
`"VaR backtesting bank risk management implementation case study 2022 2023"` (web). To dwa różne języki.

Limit casów: domyślnie 5–10 per topic (Tavily zwraca max 10 wyników per call). Jeden call per topic,
zero paginacji. Fail-open: brak klucza `TAVILY_API_KEY` → `run_cases` nie jest wołany, Scout działa
normalnie z samymi PDF-ami.

### 19.5 Weryfikacja i rozszerzenie casów w A07 przez WebFetch

Po Fazie B2 A07 będzie czytać PDF-y i produkować karty dowodów (sekcja 17). Naturalne rozszerzenie:
A07 czyta też `cases/*.md` i dla każdego case'u woła WebFetch na znany URL, żeby uzyskać pełną treść
zamiast snippetu Tavily.

Architektura kroku w A07:

```text
Input: cases/<slug>.md  →  url, title, snippet (z Tavily, ~300 znaków)
Step:  WebFetch(url)    →  pełna treść strony (~3000–5000 znaków)
Output: karta dowodu    →  co firma/instytucja zrobiła, wynik, kontekst, cytat z lokalizacją URL
```

Wartość: snippet Tavily to sygnał odkrycia. WebFetch daje treść potrzebną do napisania karty dowodu
z realnym cytatem i lokalizacją — czyli to, czego sekcja 17 wymaga jako dowód sprawdzalny i niefabrykowany.

#### Granica ryzyka — WebFetch tak, WebSearch nie

| Operacja | Ryzyko | Decyzja |
|---|---|---|
| WebFetch(URL z Tavily) | Niskie — URL znany przed uruchomieniem A07, jeden call per case | **TAK** |
| WebFetch + podążanie za linkami na stronie | Średnie — zaczyna przypominać crawling | Nie na start |
| WebSearch("znajdź więcej o X") | Wysokie — wraca do A11 failure mode (otwarte szukanie) | **NIE w A07** |

WebSearch w A07 przywróciłby dokładnie ten wzorzec, który zawiódł w A11: LLM decydujący co i kiedy
szukać. WebFetch na konkretnym URL z Tavily jest bounded i single-step.

#### Fail-open dla niedostępnych stron

Część URLi z Tavily zwróci stronę logowania, paywall lub błąd HTTP. Instrukcja dla A07:
jeśli treść pobranej strony nie zawiera materiału pasującego do tematu, użyj snippetu z `cases/*.md`
jako jedynego dowodu i oznacz kartę `confidence: needs_human_check`. Przypadek nie jest odrzucany —
snippet Tavily już jest wartościowym sygnałem dla A09.

#### Rozszerzenie schematu karty dowodu (sekcja 17)

Karta dowodu dla web case wymaga dwóch dodatkowych pól obok istniejących:

| Pole | Typ | Dla PDF | Dla web case |
|---|---|---|---|
| `source_type` | `"academic_pdf" \| "web_case"` | `"academic_pdf"` | `"web_case"` |
| `evidence_location` | string | `"strona 5, sekcja 3.2"` | `"URL, akapit 2"` |
| `evidence_url` | string \| None | None | URL z Tavily |
| `evidence_excerpt` | string \| None | None | cytat z WebFetch |

A09 dostaje oba typy kart z identycznym interfejsem: `topic_id`, `claim_ids`, `extension_relation`,
`extension_finding`, `evidence_location`, `confidence`. Pole `source_type` służy tylko do raportowania
pokrycia (ile kart z papers, ile z cases) — A09 nie zmienia logiki grupowania ani pewności.

### 19.6 Pełny rozszerzony łańcuch znaczeniowy

Sekcja 17 definiuje łańcuch dla PDF-ów. Z market cases łańcuch staje się:

```text
G01 intake -> drivers, claims, concepts, update-needs, flow-issues
  -> A01 topici (każdy podpięty pod claim/concept)
  -> Scout per topic:
       run_student()  -> pdf/*.pdf + MANIFEST.md       (peer-reviewed evidence)
       run_cases()    -> cases/*.md + CASE_MANIFEST.md  (praktyczne case studies)
  -> A07 per topic:
       czyta PDF-y + WebFetch(URL z cases/*.md)
       -> karty dowodów source_type=academic_pdf  (co mówi nauka)
       -> karty dowodów source_type=web_case       (kto to wdrożył, z jakim wynikiem)
  -> A09 grupuje, deduplikuje, nadaje pewność
       -> SolutionInputCandidate (kontrakt do Graph03)
  -> G03 tworzy zaktualizowaną prezentację
```

### 19.7 Otwarte pytania do rozstrzygnięcia przy implementacji

**Liczba casów per topic:** Jaki limit `max_cases_per_topic` wpisać domyślnie w profil `scout`
z sekcji 16? Propozycja robocza: 5 (selected) + 3 (reserved), analogia do PDF. Ale Tavily daje max
10 per call, więc można też pobierać wszystkie 10 i zostawić selekcję A07. Do decyzji z devem przed
implementacją. Uwaga: przy 4–6 topicach i 8 casów/topic = 32–48 WebFetchów w A07 per przebieg —
warto to uwzględnić w estymacji czasu agenta.

**Query builder dla cases:** Czy query do Tavily budujemy z `topic.name` + `topic.purpose` (jak intent
Scouta), czy potrzebujemy osobnego pola w `scout_search_request@1`? Jeśli intent jest dobrze sformułowany
przez A01, powinien wystarczyć. Do weryfikacji na pierwszym live teście.

**Czy `CASE_MANIFEST.md` wchodzi do `scout_retrieved_corpus@1`:** Kontrakt z sekcji 16 opisuje corpus
jako zbiór PDF-ów z SHA-256. Cases nie mają SHA-256 (nie są plikami binarnymi). Opcje: (a) osobny
kontrakt `scout_cases@1` obok `scout_retrieved_corpus@1`, (b) jeden rozszerzony kontrakt z sekcją
`cases[]` obok `documents[]`. Do rozstrzygnięcia przy projektowaniu Fazy C.

**Kolejność implementacji:** Tavily-in-Scout (sekcja 19.4) należy zaimplementować w tym samym bloku
co reszta Fazy B2 (sekcja 16), żeby A07 dostał oba typy wejść od razu i schemat kart był kompletny
od początku. Wdrożenie WebFetch w A07 (sekcja 19.5) należy do bloku implementacji A07, nie Scouta.


## 20. Dziennik retest Fazy B2 — Runda 19 (2026-06-24)

**Status:** PASS — infrastruktura B2 zamknięta.

Retest wykonany na `mocks/g02/KP_intake_bundle.json` (`task_id: awif_2025_wyk_09_fra`).

### Wyniki kluczowych punktów kontrolnych

- `research_front_door`: ref `artifact://handoffs/g02_input.json` — OK.
- `research_planner_prepare` (scout): `ready=True`, `max_topics=6` — OK.
- A01 plan: 5 topiców, all drivers covered, 0 issues, `validate_research_plan` OK.
- `research_planner_finalize` (scout): status=ok, one-shot — **PASS**.
- `research_scout_fanout` (total_target=50, oversample=1.2): 5/5 completed, no crash — OK.
- `index.json` (scout_run_index@1): valid — OK.
- `retrieved_corpus.json` × 5 (scout_retrieved_corpus@1): valid — OK.
- Sekrety w artefaktach: brak — OK.
- A07/A09 nie uruchomione: OK.

### Finding F-N — 0 PDF przy FRA domain

OpenAlex znalazł 27 prac w puli (openalex_pool łącznie), ale downloaded=0.
Przyczyna 1: temat FRA (Forward Rate Agreement) to literatura głównie paywallowa — większość
artykułów w JFE, RFS, JBF nie jest open access. Przyczyna 2: query = `topic.name` (długi opis
wielosłowny) trafia gorzej w OpenAlex niż krótkie terminy akademickie.

**Rekomendacja:** `scout_request.build_scout_search_requests` powinien używać `search_strategy.core_terms[0]`
jako primary query do OpenAlex zamiast `topic.name`. To jest improvement backlog — nie blokuje B2.

---

## 21. Dziennik retest Fazy B2 — Runda 20 (2026-06-24) — Fix 1–4

**Status:** PASS — Fix 1–4 skuteczne, PDF yield 0→29.

### Fix 1–4 zaimplementowane

| Fix | Plik | Istota |
|-----|------|--------|
| Fix 1 | `shared/scripts/g02/scout_request.py` | query = `core_terms[:3]` joined, fallback: `topic.name` |
| Fix 2 | `shared/scripts/g02/scout_request.py` | `_year_bounds`: `year_from=None` gdy `include_canonical_sources=True` |
| Fix 3 | `shared/scripts/g02/scout_fanout.py` | `facets_required = keywords[:2]` (nie pełne query) |
| Fix 4 | `shared/scripts/g02/scout_fanout.py` | `snowball=True` |

### Wyniki Rundy 20

Dane wejściowe bez zmian: `mocks/g02/KP_intake_bundle.json`, ten sam plan `awif_2025_wyk_09_fra.1.0.0.json`.

| topic_id | OA pool | deduped | downloaded | stubs |
|----------|--------:|--------:|-----------:|------:|
| TOPIC_FRA_OTC_CASH_SETTLEMENT | 73 | 102 | 8 | 5 |
| TOPIC_FRA_NAARB_PRICING_SPOT_CURVE | 85 | 111 | 12 | 7 |
| TOPIC_FRA_PAYOFF_LONG_SHORT_HEDGING | 65 | 85 | 6 | 3 |
| TOPIC_FRA_SETTLEMENT_DAY_COUNT_EXAMPLES | 37 | 96 | 2 | 2 |
| TOPIC_FRA_TIMELINE_PEDAGOGY | 69 | 119 | 1 | 0 |
| **SUMA** | **329** | **513** | **29** | **17** |

Unique_work_count=28 (jeden PDF pobrany dla 2 tematów).

### Finding F-O — szum przy rozszerzonym recall

Wzrost puli (27→329 OA) generuje szum: 3 pobrane prace spoza dziedziny FRA
(`ΛCDM` astrofizyka, `day care` psychiatria, `nonlinear pedagogy` sport). Przyczyna:
genericne tokeny (`day`, `count`, `pedagogy`) w query matchują niepowiązane dziedziny.

**Backlog Fix 5:** bramka trafności dla prac bez abstraktu (obniżony próg zamiast score=0).
**Backlog Fix 6:** `verify_llm=True` selektywnie dla prac poniżej threshold domeny.


---

## 22. Runda 21 — Live test: Canonical/Recent Quota + A10 Review Loop (2026-06-24)

### Cel

Przetestować live całą nową ścieżkę: `research_graph_input@1` → A01 → A10 review (max 1) → Scout fanout z `quota_canonical=0.4` i `source_type` w corpus.

### Nowe funkcje wdrożone przed Rundą 21

| Komponent | Zmiany |
|-----------|--------|
| `scout/engine.py` | `_classify_source_type()`, `_apply_recency_quota()`, `quota_canonical`+`recency_year_from` w `run_student` |
| `scout_fanout.py` | `quota_canonical`, `recency_year_from`, `snowball=request.get()`, `source_type`+`source_type_basis` w corpus |
| `scout_request.py` | `_recency_year_from()`, `_year_bounds()` nulling, pola `recency_year_from`+`snowball`+`quota_canonical` |
| `research_server.py` | `_research_scout_prompt()` → 6-krokowy flow z A10 loop |

### A10 review — wynik

- Werdykt: **APPROVED** (1 wywołanie, findings=0, confidence=high)
- Decision spersystowany: `artifact://reviews/plan-review-live-001-attempt-1.json`
- Krok 5 (conditional revision): pominięty

### Walidacja requestów

Wszystkie 5 topiców: `quota_canonical=0.4` ✓, `recency_year_from=2021` ✓, `year_from=null` ✓, `snowball=True` ✓

### Wyniki per topic

| topic_id | downloaded | canonical | recent | OA pool |
|----------|------------|-----------|--------|---------|
| TOPIC_FRA_OTC_CASH_SETTLEMENT | 8 | 8 | 0 | 73 |
| TOPIC_FRA_NAARB_PRICING_SPOT_CURVE | 12 | 11 | 1 | 85 |
| TOPIC_FRA_PAYOFF_LONG_SHORT_HEDGING | 6 | 5 | 1 | 65 |
| TOPIC_FRA_SETTLEMENT_DAY_COUNT_EXAMPLES | 2 | 2 | 0 | 37 |
| TOPIC_FRA_TIMELINE_PEDAGOGY | 1 | 1 | 0 | 69 |
| **SUMA** | **29** | **27 (93%)** | **2 (7%)** | 329 |

### Analiza proporcji canonical/recent

Cel kwoty: 40% canonical. Wynik: 93% canonical.
Przyczyna: rollover — pula OA domeny FRA jest zdominowana przez starsze (canonical) prace.
Mechanizm kwoty działa poprawnie (canonical→recent rollover potwierdza implementację _apply_recency_quota).

### Finding F-P (info): Rollover OA pool

Proporcja końcowych PDF nie odzwierciedla kwoty 40/60 bo brakuje recent OA papers w tej niszy.
Mechanizm implementacji PASS. Dane do monitorowania w kolejnych rundach.

### Finding F-R (major, backlog): Brak adaptera A07

A07 (`synthesis.py`) oczekuje `retrieved_corpus@1` z polami: `approved_source_set_ref`,
`candidate_source_index_ref`, `run_directory_ref`, `policy`, `review_profile_ref` — których Scout nie dostarcza.
**Backlog Fix 7:** adapter `scout_retrieved_corpus@1` → `retrieved_corpus@1`.

### Testy regresyjne

37 targeted PASS, 1 pre-existing fail (test_plugin_build — niezwiązane).

### Werdykt Rundy 21: PARTIAL

Nowe funkcje canonical/recent i pętla A10 wdrożone i zweryfikowane. Blokada E2E: Fix 7 (adapter A07).

---

## 23. Aktualizacja implementacyjna — Scout → A07 light (kroki 1–6)

Po analizie realnego katalogu Rundy 21:

```text
.emagents/g02/scout-live-canonical-recent-20260624T182520Z/runs/awif_2025_wyk_09_fra
```

ustalenie jest następujące: A07 nie powinien zaczynać od luźnych artefaktów ani od mechanicznego
udawania pełnego A06 `retrieved_corpus@1`. Naturalnym wejściem A07 w trybie Scout jest cały katalog
przebiegu Scouta, bo zawiera `plan.json`, `index.json`, requesty per topic, korpusy per topic,
manifesty i PDF-y. `plan.json` i requesty niosą soczewkę researchu: topic, purpose, claimy,
koncepty, flow issues, coverage requirements, keywords i excluded terms.

### 23.1 Kanoniczny katalog handoffu

Nowy domyślny katalog produkcyjny:

```text
outputs/g02/<task_id>/scout/
  plan.json
  index.json
  requests/<topic_id>.json
  topics/<topic_id>/retrieved_corpus.json
  topics/<topic_id>/MANIFEST.md
  topics/<topic_id>/pdf/*.pdf
  topics/<topic_id>/pdf/_stubs/*.md
```

`.emagents` zostaje runtime/cache oraz źródłem legacy runów testowych. Jawne `--workspace` dalej działa
jako override testowy/manualny. Bez override `shared/scripts/g02/scout_fanout.py` zapisuje teraz do
`outputs/g02/<task_id>/scout/`.

### 23.2 A07 pozostaje agentem; bridge jest warstwą techniczną

Nowy moduł `shared/scripts/g02/scout_a07_bridge.py` nie zastępuje agenta A07. Jego rola:

- zwalidować katalog Scouta (`plan.json`, `index.json`, requesty, per-topic `scout_retrieved_corpus@1`);
- zbudować soczewkę topicu z A01;
- wykonać tani prefilter dokumentów przed użyciem LLM;
- wyciąć krótkie, celowane okna tekstowe z PDF;
- zapisać równoległe work items dla przyszłego A07 Sonnet/high;
- utworzyć agregat `reviews.json` zgodny z `scout_a07_reviews@1`.

Agent A07 w trybie Scout pracuje później na małych pakietach `(topic_id, source_id)`, nie na całych
PDF-ach ani na całym katalogu.

### 23.3 Równoległość A07 i trwały zapis

A07 może pracować równolegle, ale bez wspólnego pliku do zapisu przez workerów. Układ zapisu:

```text
outputs/g02/<task_id>/a07/
  reviews.json
  work/<topic_id>/<source_id>.input.json
  partial/<topic_id>/<source_id>.review.json
```

Reguła: bridge zapisuje immutable `work/*.input.json`. Każdy worker A07 zapisuje tylko swój jeden
`partial/*.review.json` atomowym replace. Proces nadrzędny odbudowuje `reviews.json` z partiali.
Dzięki temu równoległe wywołania nie tracą danych i nie nadpisują wspólnego agregatu.

### 23.4 Oszczędna analiza PDF

A07 nie czyta PDF-ów od deski do deski. Bridge wybiera okna:

- maksymalnie kilka okien na źródło (domyślnie 5);
- limit znaków na okno (domyślnie 1600);
- próbkuje strony zamiast ekstrahować cały dokument;
- preferuje front matter, conclusion/discussion oraz okolice keywords/coverage terms;
- dokumenty odrzucone przez tani prefilter nie mają czytanego tekstu PDF.

Realny run pokazał szum semantyczny (np. astronomia, day care, physical education, solar PV), więc
A07 musi być filtrem merytorycznym. Dokumenty dostają statusy:

- `review_candidate`;
- `context_only`;
- `irrelevant_for_topic`;
- `insufficient_metadata`.

Tylko źródła z realnym sygnałem topicu powinny trafiać do drogiego A07 Sonnet/high.

### 23.5 Kontrakt roboczy A07

Dodano kontrakt `shared/contracts/scout_a07_reviews.schema.json` (`scout_a07_reviews@1`). W stanie
`prepared` zawiera:

- `topic_reviews[]`;
- `source_reviews[]`;
- `lookup_pointers[]`;
- `coverage_gaps[]`;
- `irrelevant_sources[]`;
- `presentation_update_candidates[]` puste do czasu faktycznego uruchomienia agenta A07;
- `parallel_write_policy`.

Docelowo A07 wypełnia `presentation_update_candidates[]` substancją dla A09: konkretne informacje,
które mogą wzbogacić prezentację, powiązane z claimami/konceptami/slajdami, z dowodem i pewnością.

### 23.6 Co zostaje na kolejne kroki

Po krokach 1–6 mamy przygotowanie wejścia dla A07, ale nie uruchamiamy jeszcze modelu. Następny blok:

1. dodać hostowy runner A07 light (Sonnet/high) po `work/*.input.json`, z kontrolowaną równoległością;
2. zapisywać `partial/*.review.json` per źródło;
3. odbudowywać finalne `reviews.json` z `presentation_update_candidates[]`;
4. dopiero potem implementować A09 `scout_fast`, które z tych kandydatów tworzy gotowy
   `solution_input_candidate@1` dla G03, bez odsyłania G03 do researchu.

---

## 24. Aktualizacja implementacyjna: A07 partials -> A09 scout_fast (kroki 7-13)

Po krokach 7-13 spięto offline całą ścieżkę artefaktów po stronie Scout:

```text
outputs/g02/<task_id>/scout/
  -> outputs/g02/<task_id>/a07/work/<topic_id>/<source_id>.input.json
  -> outputs/g02/<task_id>/a07/partial/<topic_id>/<source_id>.review.json
  -> outputs/g02/<task_id>/a07/reviews.json
  -> solution_input_candidate@1 dla G03
```

To nadal nie uruchamia live Scouta ani realnych wywołań A07 Sonnet/high w tym środowisku. Zostały
jednak wdrożone kontrakty, zapis pośredni, agregacja i ścieżka A09, dzięki czemu środowisko testowe
może wykonać samą pracę modelową na przygotowanych work itemach.

### 24.1 Skąd A07 bierze soczewkę topicu

Soczewka topicu nie jest tworzona przez LLM i nie jest odtwarzana heurystycznie. `scout_a07_bridge.py`
składa ją deterministycznie z dwóch źródeł:

- `plan.json`, czyli utrwalonego planu A01 `research_plan@1`;
- `requests/<topic_id>.json`, czyli faktycznego `scout_search_request@1`, który uruchomił Scouta dla
  tego topicu.

W soczewce trafiają m.in. `topic_id`, nazwa topicu, `purpose`, coverage requirements, powiązane claimy,
koncepty, flow issues, update needs, realne `query`, `keywords` i `excluded_terms`. Dzięki temu A07
czyta okna PDF nie ogólnie, tylko pytaniem: "czy ten PDF wnosi coś do tej konkretnej potrzeby
prezentacji?".

### 24.2 Trwały zapis pracy równoległej A07

Dodano kontrakt `shared/contracts/scout_a07_partial_review.schema.json`
(`scout_a07_partial_review@1`). Każdy worker A07 dostaje jeden plik:

```text
work/<topic_id>/<source_id>.input.json
```

i zapisuje jeden wynik:

```text
partial/<topic_id>/<source_id>.review.json
```

Worker nie dotyka `reviews.json`. Agregację wykonuje osobny krok `aggregate_scout_a07_reviews()`, który
czyta partiale, aktualizuje statusy źródeł i odbudowuje:

- `presentation_update_candidates[]`;
- `lookup_pointers[]`;
- `coverage_gaps[]`;
- status całości: `prepared`, `partial` albo `completed`.

Ten układ jest bezpieczny dla równoległego A07: brak wspólnego pliku do zapisu przez wiele workerów,
brak ryzyka utraty wyniku przez nadpisanie.

### 24.3 A09 scout_fast jako finalny handoff do G03

Dodano `shared/scripts/g02/scout_synthesis.py`, czyli Scout-specyficzną ścieżkę A09. Wejściem jest
zagregowany `scout_a07_reviews@1`, opcjonalnie z intake `research_graph_input@1`. Wyjściem jest gotowy
`solution_input_candidate@1` z:

- `synthesis_mode = "scout_fast"`;
- `claim_assessment_performed = false`;
- `a08_status = "skipped_scout_fast"`;
- `slide_update_plan[]` i `suggested_updates[]` z konkretnymi zmianami do prezentacji;
- `coverage_gaps[]` oraz `unresolved_items[]` tylko jako informacja o brakach;
- `graph03_handoff_constraints.graph03_must_not_call_g02 = true`.

G03 nie ma wracać do G02. Dlatego A09 musi oddać gotowy kontrakt ze wszystkim, co G03 potrzebuje do
wytworzenia nowej prezentacji: treść zmiany, miejsce użycia, relację do istniejącej prezentacji,
źródła, poziom pewności i ograniczenia.

### 24.4 Budżet głębszego sprawdzenia w A09

A07 robi oszczędną substancję merytoryczną z krótkich okien PDF. A09 może dostać listę
`deep_dive_requests[]`, ale budżet jest twardo ograniczony do maksymalnie 5 źródeł. Nie oznacza to
czytania całych PDF-ów. To są tylko wskazane miejsca, gdzie A09 może zajrzeć głębiej, jeśli środowisko
testowe uruchamia A09 z narzędziami do dodatkowych bounded windows.

### 24.5 MCP i testy offline

Serwer MCP rozszerzono do wersji `0.14.0` o narzędzia:

- `research_scout_a07_prepare`;
- `research_scout_a07_partial_finalize`;
- `research_scout_a07_aggregate`;
- `research_scout_synthesis_prepare`;
- `research_scout_synthesis_finalize`.

Dodano test offline, który przechodzi przez całą ścieżkę bez live calli: fake Scout run -> A07 work
items -> partial review -> agregacja -> A09 `scout_fast` -> walidacja `solution_input_candidate@1`.

### 24.6 Co zostaje po tym bloku

Do środowiska testowego zostaje:

1. uruchomić live Scout według istniejącej ścieżki;
2. uruchomić realnego A07 Sonnet/high równolegle po `work/*.input.json`;
3. zapisywać wyniki przez `research_scout_a07_partial_finalize`;
4. wykonać `research_scout_a07_aggregate`;
5. uruchomić A09 scout_fast i sprawdzić finalny `solution_input_candidate@1` na wejściu G03.

W repo nie uruchamiano live testów ani modelu A07. Zmieniona została tylko ścieżka deterministyczna i
offline kontrakty potrzebne do bezpiecznego spięcia testowego.

---

## 25. Aktualizacja implementacyjna: realny runner A07 light i prompt E2E

Po dodatkowej weryfikacji rozdzielono dwa pojęcia:

- `scout_a07_bridge.py` przygotowuje dane i okna PDF;
- `scout_a07_runner.py` przygotowuje zadania modelowe A07 i wykonuje je przez hostowy executor.

Dodano kontrakt `shared/contracts/scout_a07_model_task.schema.json`
(`scout_a07_model_task@1`). Jest to wejście dla jednego wywołania A07 light:

- jeden `topic_id` i `source_id`;
- `topic_lens` z A01 i requestu Scouta;
- metadata źródła;
- tylko `selected_windows[]`, bez całego PDF;
- `intake_context`, czyli skompaktowane karty intake powiązane z topicem;
- `model_policy`: `recommended_model=sonnet`, `reasoning_effort=high`, `full_pdf_forbidden=true`;
- oczekiwany finalizer `research_scout_a07_partial_finalize`.

W `topic_lens.linked_intake_ids` dodano także `driver_ids`, żeby A07 widział nie tylko claimy,
koncepty i flow issues, ale również pierwotny powód researchu z G01/A01.

### 25.1 Runner A07 light

Nowy moduł `shared/scripts/g02/scout_a07_runner.py` realizuje brakujący blok wykonawczy:

```text
reviews.json + work/*.input.json
  -> tasks/*.task.json (scout_a07_model_task@1)
  -> executor A07 Sonnet/high
  -> partial/*.review.json
  -> aggregate reviews.json
```

Najważniejsze funkcje:

- `build_scout_a07_model_task(work_input_path, intake=...)`;
- `write_scout_a07_model_tasks(a07_dir, intake=...)`;
- `run_scout_a07_light(a07_dir, executor, max_workers=...)`;
- `command_executor([...])` dla środowiska, które chce podpiąć zewnętrzną komendę JSON stdin/stdout.

Runner jest równoległy na poziomie `(topic_id, source_id)`. Każdy worker zapisuje tylko swój partial
przez finalizer, a agregacja nadal odbywa się osobnym krokiem. To zachowuje regułę braku wspólnego
zapisu przez równoległe wywołania.

### 25.2 Skill A07 Scout light

Dodano skill `skills/g02-a07-scout-light-review` z bindingiem Claude:

```yaml
model: sonnet
effort: high
```

Skill mówi A07, że ma czytać wyłącznie `scout_a07_model_task@1`, nie pełny PDF, oraz zwracać surowy
JSON dla `research_scout_a07_partial_finalize`. Wyjściem mają być przede wszystkim
`presentation_update_candidates[]`, czyli substancja do prezentacji, nie ogólne streszczenie pracy.

### 25.3 MCP

Serwer MCP podniesiono do `0.15.0` i dodano:

- `research_scout_a07_tasks_prepare` do tworzenia `scout_a07_model_task@1`.

Istniejące narzędzia:

- `research_scout_a07_prepare`;
- `research_scout_a07_partial_finalize`;
- `research_scout_a07_aggregate`;
- `research_scout_synthesis_prepare`;
- `research_scout_synthesis_finalize`;

tworzą teraz pełną ścieżkę narzędziową od katalogu Scouta do finalnego kontraktu A09.

### 25.4 Prompt E2E

Zostawiono prompt `research-scout` jako bezpieczny wariant Scout-only, kończący się przed A07/A09.
Dodano osobny prompt `research-scout-e2e`, który prowadzi środowisko hosta przez:

1. A01/A10/Scout;
2. `research_scout_a07_prepare`;
3. `research_scout_a07_tasks_prepare`;
4. pętlę A07 light po taskach;
5. `research_scout_a07_partial_finalize`;
6. `research_scout_a07_aggregate`;
7. `research_scout_synthesis_prepare`;
8. `research_scout_synthesis_finalize`.

### 25.5 Co nadal wymaga live/model sprawdzenia

Kodowo istnieje już realny interfejs dla A07, ale w tym środowisku nie uruchomiono modelu Sonnet/high.
Do sprawdzenia w środowisku testowym:

1. live Scout z kluczem OpenAlex;
2. `research_scout_a07_prepare` na realnym katalogu `outputs/g02/<task_id>/scout`;
3. `research_scout_a07_tasks_prepare` i kontrola, czy taski zawierają właściwe karty intake;
4. realna pętla A07 Sonnet/high po taskach;
5. agregacja `reviews.json`;
6. A09 `scout_fast`;
7. walidacja `solution_input_candidate@1` na wejściu G03.

---

## 26. Blok DEV: domknięcie trybu scout przed live (2026-06-24)

Blok naprawczy wykonany w repo offline (środowisko DEV, Python 3.13). Celem było usunięcie
rzeczy, które „udawały działanie" tylko na przypadku testowym FRA, oraz utwardzenie styków przed
realnym przebiegiem LIVE w osobnym środowisku (WSL). Live nie był uruchamiany w tym bloku.

### 26.1 Prefilter A07 odzaszyty z domeny FRA (P1a)

`shared/scripts/g02/scout_a07_bridge.py` zawierał zaszyty słownik `DOMAIN_ANCHORS` (wyłącznie
słownictwo FRA/stóp procentowych), special-case `"fra"` w `prefilter_source` oraz FRA-specyficzne
tokeny w `GENERIC_TOKENS` (`day`, `count`, `pricing`, `value`, `valuation`, `cash`). Skutek: dla
dowolnej domeny innej niż FRA `domain_hits` było zawsze puste, więc żadne źródło nie mogło osiągnąć
statusu `review_candidate` (maksymalnie `context_only`). Prefilter „działał" tylko na teście FRA.

Naprawa: usunięto `DOMAIN_ANCHORS` i special-case; relevancja jest teraz liczona wyłącznie z
**dynamicznych kotwic** budowanych per topic z planu A01 i requestu Scouta (`lens['keywords']`,
`lens['anchor_tokens']` z `topic.name`/`purpose`/`query`/`core_terms`/coverage). `GENERIC_TOKENS`
jest teraz domenowo-neutralną listą stopwords (function words + generyczne słownictwo
research/dydaktyczne typu `introduction`, `overview`, `tutorial`, `recent`, `developments`).

Nowa logika statusu (domenowo-neutralna):

- `excluded_hits` przy słabym sygnale → `irrelevant_for_topic`;
- brak jakiejkolwiek kotwicy w metadanych → `irrelevant_for_topic` (patrz 26.2);
- pełny keyword phrase hit lub ≥3 anchor tokeny → `review_candidate`;
- 1–2 anchor tokeny → `context_only`.

### 26.2 Fix 5 deterministyczny: bramka off-domain bez abstraktu

Korpus Scouta (`scout_retrieved_corpus@1`) nie niesie pola abstraktu — prefilter ma tylko
`title`/`venue`/`work_type`/`doi`. Dlatego Fix 5 (deterministyczna bramka na szum F-O) jest
zrealizowany na poziomie metadanych: dokument bez żadnej kotwicy tematu jest klasyfikowany jako
`irrelevant_for_topic` z jawnym powodem „no topic anchor in metadata (likely off-domain)" i nie
trafia do drogiego A07. Download-time gating w silniku Scouta (vendored) pozostaje świadomie poza
zakresem tego bloku.

### 26.3 Generalizacja udowodniona testem (P1b)

Dotychczasowy fixture offline był wyłącznie FRA, więc asercja `review_candidate` przechodziła przez
zaszyty special-case. Dodano `test_prefilter_generalizes_to_non_fra_domain` (domena Bayesian/VI),
który dowodzi: źródło na temat → `review_candidate`, słabe → `context_only`, off-domain (day care)
→ `irrelevant_for_topic`, oraz że do soczewki niefra nie wycieka token `fra`.

### 26.4 Rejestracja skilla A07 light w manifeście (P2)

Binding `model: sonnet` / `effort: high` istniał w
`skills/g02-a07-scout-light-review/adapters/claude.frontmatter.yaml` (poprawna konwencja repo —
binding jest w adapterze, nie w `SKILL.md`), ale sam skill **nie był wpisany w
`plugin.manifest.json`**, więc build go nie pakował i bundle miał 23 skille przy 24 na dysku (to
też było źródłem niezwiązanego z resztą faila `test_plugin_build`). Dodano
`skills/g02-a07-scout-light-review` do manifestu. Build Claude renderuje teraz skill z wmergowanym
frontmatterem `model: "sonnet"`, `effort: "high"`; dysk i manifest = 24 skille; `graph_check`
zielony. Świadoma decyzja (najmniej inwazyjna): A07 light pozostaje krokiem sterowanym MCP +
promptem, bez własnego węzła grafu. Rejestracja węzła w grafie jest odłożona do osobnej, bardziej
„oficjalnej" tury.

### 26.5 Utwardzenie styku A07 model → partial (P3)

`normalize_scout_a07_partial` przestał zakładać, że model zawsze odda listy. Dodano `_as_list`,
więc `null`/obiekt w `presentation_update_candidates`/`lookup_pointers`/`coverage_gaps` nie wywala
już normalizacji (`enumerate(None)`), tylko jest traktowany jak pusta lista. `command_executor`
w `scout_a07_runner.py` dostał `parse_model_json`, który toleruje realny output modelu czatowego:
strict JSON → blok ```json → najszerszy `{...}`. Dodano `test_normalize_tolerates_loose_model_output`
(kandydat tylko z `finding`, puste/`null` kolekcje, pusty obiekt, oraz JSON w bloku fenced) — każdy
przypadek waliduje się jako `scout_a07_partial_review@1` bez ręcznych poprawek.

### 26.6 Traceability A09 → A01 (P4)

`scout_synthesis.finalize_scout_fast_solution` ustawiał `plan_ref="plan.json"` na sztywno. Teraz
`plan_ref` jest składany z `scout_run_ref` + `plan_ref` z `scout_a07_reviews@1` (lub zachowuje
`artifact://`), więc handoff do G03 wskazuje realny plan A01, nie samą nazwę pliku.

### 26.7 Status A09 w trybie scout i granica G03

A09 w trybie scout ma deterministyczny baseline oraz obowiązkowy modelowy przebieg
Opus/medium sterowany przez MCP i prompt. `research_scout_a09_task_prepare` przygotowuje baseline,
compact intake i bounded deep dive, a host uruchamia `g02-a09-scout-synthesis` dokładnie raz.
`research_scout_synthesis_finalize` scala zwrócone poprawki z deterministycznymi zabezpieczeniami.
Awaria albo brak modelu daje jawny `deterministic_fallback`, bez zatrzymania handoffu do G03.
Legacy `g02-a09-synthesizer` pozostaje bez zmian na grafie i w manifeście.

Kontrakt `solution_input_candidate@1` gwarantuje teraz kształt `slide_update_plan[].target`.
Zachowano istniejące `affected_slides` i `section_hint`, a addytywnie dodano `slide_ids`, `section`
i `placement`. Pozwala to utrzymać zgodność ze ścieżką Scout oraz nazewnictwem używanym przez G03.

### 26.8 Weryfikacja DEV offline (ten blok)

- `py_compile` dla `scout_a07_bridge.py`, `scout_a07_runner.py`, `scout_synthesis.py`: PASS.
- `tests/test_g02_scout_a07_bridge.py` + `tests/test_g02_scout_request.py`: 16 PASS (było 14;
  +`test_prefilter_generalizes_to_non_fra_domain`, +`test_normalize_tolerates_loose_model_output`).
- `graph_check` (source): `ok: true`, `errors: none`.
- Build Claude: skill A07 light renderowany z bindingiem sonnet/high; manifest = dysk = 24 skille.

Świadomie zostawione na LIVE (środowisko WSL, lista z 25.5 nadal obowiązuje): live Scout z
OpenAlex, realny przebieg A07 Sonnet/high, A09 scout_fast na realnych partialach, build obu bundli
i pełny `pytest`.

## 27. Deterministyczna warstwa decyzyjna A09 i bounded deep dive

### 27.1 Deduplikacja, grupowanie i priorytety

`shared/scripts/g02/scout_synthesis.py` zawiera trzy jawne etapy decyzyjne:

1. `_dedup_candidates` scala kandydatów według `topic_id`, `source_id` i znormalizowanego początku
   `finding`. Przy kolizji zachowuje wariant o wyższym confidence oraz sumuje identyfikatory intake,
   evidence refs i source refs.
2. `_rank_updates` przenosi `insufficient_evidence` oraz wpisy bez dowodu do
   `optional_improvements`. Główny plan i `slide_revision_priorities` wynikają z jawnych rang
   confidence i `extension_relation`.
3. `_group_updates` układa główny plan według slajdu, flow issue, claim albo topic. Sortowanie jest
   stabilne i deterministyczne.

Każdy niezużyty `lookup_pointer` trafia do `unresolved_items` z kodem
`lookup_pointer_not_resolved`. Pointery nie są przekazywane do `slide_update_plan`.

### 27.2 Selekcja i wykonanie deep dive

`prepare_scout_fast_synthesis` wybiera maksymalnie pięć unikalnych źródeł. Kolejność kryteriów to:
wysoki potencjał zmiany slajdu, sprzeczne ustalenia, ważny claim bez pewnego dowodu, źródło
canonical, wartościowe źródło recent oraz pozostały nierozwiązany pointer. Każdy request zapisuje
`selection_criterion` i czytelne `reason`.

`gather_deep_dive_windows` lokalizuje run przez `scout_run_ref`, odtwarza topic lens i korzysta z
tego samego `select_pdf_windows`, co A07. Limit wynosi 12 okien po 1800 znaków na źródło. Brak PDF,
corpus albo parsera daje pustą listę okien i jawną limitation. Pakiet waliduje kontrakt
`scout_a07_deep_dive@1`. Obowiązkowy modelowy A09 stosuje niższy budżet 8 okien po 1200 znaków;
limit 12/1800 pozostaje wyłącznie ogólnym capem deterministycznego narzędzia.

Okno z `matched_terms` tworzy ostrożny szkic gotowej aktualizacji z cytowanym fragmentem. Brak
takiego sygnału tworzy `deep_dive_no_matching_signal` albo `deep_dive_unavailable`, a pointer
pozostaje jawnie nierozwiązany.

### 27.3 MCP, G03 i status modelowego A09

Serwer MCP ma wersję `0.17.0` i udostępnia `research_scout_a09_task_prepare`. STEP 12 wymaga jednego
przebiegu `g02-a09-scout-synthesis` z Opus/medium, następnie przekazuje jego JSON i ten sam pakiet
deep dive do `research_scout_synthesis_finalize`. Model weryfikuje oraz poprawia baseline, nie tworzy
niezależnej syntezy i nie ma dostępu do pełnych PDF.

### 27.4 Weryfikacja DEV

Zakres testów w `tests/test_g02_scout_synthesis.py` obejmuje A1–A4 i B1–B3. Kontrola końcowa
obejmuje także regresję A07 bridge, MCP, `py_compile`, `graph_check` oraz build pluginu Claude.

## 28. Obowiązkowy modelowy A09 jako weryfikator baseline

### 28.1 Decyzje wykonawcze

- A09 jest weryfikatorem i poprawiaczem deterministycznego baseline.
- Binding hosta to `model: opus`, `effort: medium`.
- Budżet A09 wynosi maksymalnie 5 źródeł, 8 okien na źródło i 1200 znaków na okno.
- Integracja pozostaje MCP/prompt-driven, analogicznie do A07 light, bez nowego węzła grafu.
- Wyjściem G02 pozostaje `solution_input_candidate@1`.
- Awaria modelu nie zatrzymuje G02. Finalizer emituje baseline z
  `a09_model_pass=false` i `synthesis_engine="deterministic_fallback"`.

### 28.2 Kontrakt i compact intake

`scout_a09_model_task@1` zawiera deterministyczny plan, kandydatów A07, pakiet deep dive,
presentation context i compact intake. Compact intake obejmuje wyłącznie karty wskazane przez
`linked_intake_ids`: research drivers, claims, concepts, flow issues i update needs. Pozwala to
modelowi porównać rekomendację ze znaczeniem claimu bez przekazywania pełnego intake.

`model_policy` zapisuje faktyczny budżet pakietu deep dive, w tym `max_chars_per_window`.
`expected_output` kieruje surowy JSON do `research_scout_synthesis_finalize`.

### 28.3 Runner i audyt fallbacku

`shared/scripts/g02/scout_a09_runner.py` realizuje kolejno: prepare, deep dive 5/8/1200,
deterministyczny baseline, budowę taska, pojedyncze wywołanie executora i finalizację. Runner odrzuca
pusty albo niekompletny output modelu. Przy braku executora lub wyjątku zachowuje błąd w wyniku
runnera i przechodzi na deterministyczny handoff.

`solution_input_candidate@1` ma pola audytowe:

- `a09_model_pass=true`, `synthesis_engine="a09_opus_medium"` dla niepustego outputu modelu;
- `a09_model_pass=false`, `synthesis_engine="deterministic_fallback"` dla fallbacku.

### 28.4 MCP i STEP 12

`research_scout_a09_task_prepare` zwraca jeden `scout_a09_model_task@1` oraz dokładnie ten pakiet
deep dive, który musi trafić do finalizera. Prompt `research-scout-e2e` nakazuje hostowi:

1. przygotować task z budżetem 5/8/1200;
2. uruchomić `g02-a09-scout-synthesis` jako Opus/medium dokładnie raz;
3. przekazać surowy JSON oraz pakiet deep dive do `research_scout_synthesis_finalize`;
4. przy awarii wywołać finalizer bez `output`, bez fabrykowania odpowiedzi modelu.

### 28.5 Testy i stan weryfikacji

Testy źródłowe obejmują walidację taska, compact intake, budżet 8/1200, udany model pass,
wyjątek executora, audyt fallbacku, rejestrację narzędzia MCP i binding skilla Opus/medium.
Końcowe uruchomienie testów, `graph_check` i build pozostają osobnym krokiem weryfikacyjnym.

### 28.6 Dopracowanie kontraktu wyjścia do G03 (self-contained, schemat 1.4)

`solution_input_candidate@1` jest jedynym artefaktem przekraczającym granicę G02 → G03. Ma być
samowystarczalny: G03 nie czyta PDF-ów, wnętrza G02 ani dodatkowych artefaktów badawczych. Slajdów
G02 nie posiada (pochodzą z `lecture_baseline@1` w G01, a `solution_graph_input@1` łączy oba refy),
więc mapowanie finding→slajd robi G03 — kontrakt niesie do tego klucze złączenia (`linked_intake_ids`,
`target.slide_ids`/`section_hint`). Dopracowanie (schemat `x-version` 1.4):

- Opinia z przeanalizowanych artykułów jest jawna w każdym `suggested_updates`/`optional_improvements`:
  `finding` (co mówi źródło), `rationale` (dlaczego zmienia/rozszerza obecny wykład — z A07
  `rationale_vs_existing_presentation`), `extension_relation` (werdykt: confirms / updates_outdated /
  adds_new_angle / contradicts / qualifies / didactic_example), `confidence` (siła dowodu) oraz
  `evidence_refs` z krótkim cytatem i lokalizacją i obiektowe `source_refs` (doi/title/year/venue).
  A09 (opus/medium) weryfikuje i porządkuje te opinie; A08 jest jawnie pominięte
  (`claim_assessment_performed=false`, `a08_status="skipped_scout_fast"`).
- `coverage_summary[]`: per claim/driver status `covered` / `partial` / `uncovered` z liczbą źródeł,
  liczony deterministycznie z linków tego przebiegu. Daje G03 obraz, co badanie rozstrzygnęło, a co
  zostało otwarte, bez sięgania po A07.
- Bug fix: finalizer zapisuje dowody pod kluczem `evidence_refs` (wcześniej `evidence`), co schemat 1.3+
  wymaga jako pole obowiązkowe pozycji aktualizacji. `slide_ids` są koercowane do stringów (np. gdy
  `affected_slides` z kart flow-issue przychodzą jako liczby).
- Schemat dopuszcza `null` dla `intake_ref`, `plan_ref` i pól `presentation_context.*` na ścieżce bez
  intake; w realnym łańcuchu (intake → A01 → Scout → A07 → A09) pola te są wypełnione z
  `user_approved_context`.
- Flagi `graph03_handoff_constraints` są kompletne: `compact`, `no_full_text`, `no_full_pdfs`,
  `no_full_extracted_text`, `no_verbose_paper_reviews`, `ready_to_apply_updates_required`,
  `graph03_must_not_call_g02`, plus `output_language` i `locked_sections`.

Przykład wygenerowany realnym finalizerem: `mocks/g02/EXAMPLE g02-a09-solution_input_candidate.artifact.json`.
