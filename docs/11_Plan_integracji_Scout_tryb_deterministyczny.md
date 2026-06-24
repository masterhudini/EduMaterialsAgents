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
