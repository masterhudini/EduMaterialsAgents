# Research Graph, rejestr DEV i TEST 1b1

## Zasada użycia

Rejestr rozdziela ukończenie implementacji w repozytorium od weryfikacji prowadzonej później w
osobnym katalogu i osobnym środowisku. DEV tworzy testy i mocki, lecz nie uruchamia pełnych pakietów,
live API ani forward testów.

Po zakończeniu każdego numerowanego zestawu aktualizowana jest lista DEV oraz kompletna lista
scenariuszy TEST. Commit powinien następować po osiągnięciu stanu wymaganego przez właściciela
repozytorium.

### Legenda markerów (od Rundy 7)

- `- [x]` — w sekcji TEST scenariusz wykonany i zaliczony (szczegóły w `08`); w sekcji DEV element
  implementacji ukończony w repozytorium.
- `- [ ]` — niewykonany lub niezaliczony; dopisek wyjaśnia powód.
- `❌ FAIL` (w treści) — wykonany, nie przeszedł zgodnie z zapisem; dopisek mówi co poprawić.
- `⏳ KOŃCOWY` (w treści) — świadomie odroczony do końcowego testu integracyjnego całej
  funkcjonalności: forward testy na realnym hoście (Claude/Codex) oraz pełny przepływ
  A01→…→A05 wraz z A11/A05/Tavily/SearXNG. Od kolejnych rund weryfikujemy już tylko nowe lub
  zmienione funkcjonalności oraz pozycje `⏳ KOŃCOWY` i `❌ FAIL`.

## Wspólna runda TEST 2 + TEST 3 przed commitem A01 i A02

Runda odbywa się w czystym, osobnym środowisku i obejmuje wszystkie powierzchnie używane przez
obecny pionowy wycinek:

- kontrakty JSON, moduły Python, artifact store, cache, resume oraz failure paths;
- serwer MCP przez bezpośrednie wywołania i rzeczywisty transport stdio;
- forward tests promptów i skilli A01, A02 oraz uniwersalnego reviewera na Claude i Codex;
- build i instalowalne bundle obu hostów, wraz z kontrolą zawartości oraz braku sekretów;
- offline fixtures OpenAlex, Semantic Scholar i arXiv;
- jawnie włączane live smoke tests tych trzech usług z prawdziwą konfiguracją środowiska.

Kolejność: pełny offline `pytest`, testy kontraktowe i failure paths, MCP, packaging, forward tests
obu hostów, a na końcu opt-in live API smoke. Nieudany etap zatrzymuje rundę przed kolejnym etapem,
jeżeli wynik mógłby być niemiarodajny. Wynik każdej fazy, wersję Pythona, host, konfigurację bez
wartości sekretów i listę pominiętych testów należy dopisać na górze `08_Log_wynikow_TEST.md`.
Checkbox wolno zaznaczyć tylko po wykonaniu odpowiadającego mu scenariusza.

## 1. G02-A10 Output Reviewer

### Status DEV

- [x] 1A. Zamrożono `review_task@1` i `review_decision@1`.
- [x] 1A. Wyrównano agent, skill i dokumentację kontraktów.
- [x] 1B. Ukończono deterministyczną warstwę reviewera.
- [x] 1C. Wykonano końcowy przegląd implementacji pierwszego zestawu.
- [x] 1D. Wprowadzono poprawki wynikające z rundy 2 TEST i zamrożono listę retestu.
- [x] 1E. Przeprowadzono repozytoryjną migrację namespace grafu, agentów i skilli do `g02`.

### TEST 1A, kontrakty

- [x] Poprawny minimalny `ReviewTask` przechodzi `review_task@1`.
- [x] Brak każdego wymaganego pola `ReviewTask` jest odrzucany.
- [x] Deskryptor artefaktu bez `type`, `ref`, `schema_version` lub `artifact_version` jest
  odrzucany.
- [x] `schema_version` inne niż `review_task@1` jest odrzucane.
- [x] Poprawny `ReviewDecision` dla każdego z trzech verdicts przechodzi kontrakt strukturalny.
- [x] Nieznany verdict, severity, confidence lub root cause jest odrzucany.
- [x] Finding bez wymaganych pól jest odrzucany.
- [x] `revision_scope` jako null oraz poprawny obiekt są obsługiwane zgodnie z kontraktem.
- [x] Deskryptor decyzji w `envelope@1.produced[]` używa `type: review_decision`, URI
  `artifact://` w `path` i `schema_version: review_decision@1`.

### TEST 1B, narzędzia deterministyczne

- [x] Poprawny `ReviewTask` przygotowuje dokładnie jeden autoryzowany artefakt.
- [x] Brak profilu, kryteriów lub severity rules daje `BLOCKED` z `review_profile_error`.
- [x] Niekompletny input daje `BLOCKED` z `invalid_or_incomplete_input`, jeśli istnieje audit
  identity.
- [x] Brak audit identity daje envelope `failed` bez decyzji.
- [x] Niedostępny artefakt daje `BLOCKED` z `external_dependency_blocked`.
- [x] `artifact://../...`, ścieżka absolutna i symlink poza artifact root są odrzucane.
- [x] Kontrakt artefaktu różny od `expected_output_contract` blokuje review.
- [x] Próba większa niż 1 bez `previous_decision_ref` blokuje review.
- [x] Poprzednia decyzja jest hydratowana, walidowana i przekazywana reviewerowi.
- [x] Poprzednia decyzja z innym `review_id`, zadaniem, producentem, profilem lub numerem próby
  jest odrzucana.
- [x] Poprzedni finding pozostaje otwarty z tym samym ID albo trafia do `closed_finding_ids`.
- [x] Duplikaty criterion IDs i requirement IDs blokują review.
- [x] Puste oraz zarezerwowane criterion IDs w profilu są odrzucane.
- [x] Puste identyfikatory audytowe, opisy kryteriów, wymagania i pola findings są odrzucane.
- [x] Alternatywne pola `artifacts` i `artifact_ref` nie pozwalają ominąć reguły jednego
  deskryptora `artifact`.
- [x] Nieznany expected output contract i niezgodny artifact type blokują review.
- [x] Shape validation badanego artefaktu jest przekazywana reviewerowi bez automatycznego
  zatwierdzania lub poprawiania artefaktu.
- [x] `APPROVED` z findings, root cause lub revision scope jest odrzucane.
- [x] `REVISE` bez findings albo z blockerem jest odrzucane.
- [x] `REVISE` z revision scope innego producenta jest odrzucane.
- [x] `BLOCKED` bez blocker finding lub bez root cause jest odrzucane.
- [x] `BLOCKED` z `producer_error` lub naprawialnym `insufficient_evidence` jest odrzucane;
  wyczerpanie prób pozostaje odpowiedzialnością runtime.
- [x] Finding z criterion ID spoza profilu i listy zarezerwowanej jest odrzucany.
- [x] Finding ID nie może jednocześnie występować jako otwarty i zamknięty.
- [x] Mapowanie severity działa w obu kierunkach dla wszystkich dozwolonych wartości.
- [x] Poprawna decyzja jest zapisywana pod bezpieczną nazwą i zwracana w `envelope@1`.
- [x] Kolejne wartości `attempt` zapisują osobne decyzje i nie nadpisują historii rewizji.
- [x] Błędne typy w niekompletnym zadaniu nie uniemożliwiają utworzenia strukturalnie poprawnej
  decyzji `BLOCKED`, jeśli zachowano audit identity.
- [x] Błąd zapisu decyzji daje envelope `failed` bez artefaktu wynikowego.
- [x] Niepoprawny envelope executora daje envelope `failed` bez decyzji.
- [x] Poprawny envelope `failed` executora jest zachowywany bez tworzenia decyzji.
- [x] Brak executora daje `BLOCKED` z `external_dependency_blocked`.
- [x] Wyjątek executora daje envelope `failed` i nie zostawia zatwierdzonej decyzji.
- [x] `research_review_prepare` i `research_review_finalize` są widoczne przez MCP i zwracają
  dane zgodne z operacjami Python.
- [x] Graph check w trybie source/Claude odrzuca brak fizycznego reviewera; wszystkie hosty
  odrzucają brak kontraktu reviewera i producer node bez `review_profile`.
- [x] Graph check w trybie source/Claude akceptuje manifest z jednym fizycznym reviewerem i
  kompletem profili.
- [x] Treść artefaktu zawierająca prompt injection pozostaje danymi i nie zmienia profilu,
  kryteriów ani zachowania reviewera.
- [x] Artefakt źródłowy nie zmienia się podczas przygotowania, review ani finalizacji.

### TEST 1C, spójność i packaging

- [x] Manifest wskazuje dokładnie jeden fizyczny `g02-a10-output-reviewer`.
- [x] Wszystkie dziewięć producer nodes ma właściwy `review_profile`.
- [x] Manifest wskazuje `review_task@1` i `review_decision@1`, a oba schematy znajdują się w
  źródłowym repo i wygenerowanym bundle.
- [x] `graph_check` działa na source plugin root.
- [x] `graph_check` działa na wygenerowanym bundlu Claude.
- [x] Host-aware `graph_check` działa na wygenerowanym bundlu Codex bez osłabienia kontroli
  kontraktów, profili, skilli i subgrafów.
- [x] Plugin source inventory nadal zawiera 10 agentów i 18 skilli.
- [x] Bundle Claude zawiera agenta reviewera i adapter używający operacji prepare/finalize.
- [x] Bundle Codex zawiera skill reviewera i wspólną definicję agenta, bez instrukcji adaptera
  właściwych wyłącznie dla Claude.
- [x] Bundle Codex nie zawiera pustego katalogu `skills/g02-review-research-output/agents`.
- [x] Wygenerowane bundle zawierają `review.py`, oba schematy i zaktualizowany MCP server.
- [x] MCP server raportuje wersję `0.2.0` i udostępnia obie operacje reviewera obok wcześniejszych
  narzędzi.
- [x] `envelope@1.produced[].path` używa `artifact://`, a deskryptory handoff nadal używają
  odrębnego pola `ref`.
- [x] Zwykłe, poprawne artifact refs nadal działają po utwardzeniu resolvera.
- [x] Dokumentacja 00–08, manifest, agent, skill i adaptery używają tych samych nazw kontraktów,
  decyzji, pól i operacji.
- [x] No-op harness pozostaje jawnie oznaczony i nie jest interpretowany jako test zachowania
  reviewera.

### Warunek zamknięcia zadania 1

- [x] DEV 1A zakończony.
- [x] DEV 1B zakończony.
- [x] DEV 1C zakończony.
- [x] DEV 1D zakończony.
- [x] DEV 1E zakończony.
- [x] TEST 1A zakończony w osobnym środowisku.
- [x] TEST 1B zakończony w osobnym środowisku.
- [x] TEST 1C zakończony w osobnym środowisku.
- [x] RETEST 1D zakończony w osobnym środowisku.
- [x] TEST 1E namespace zakończony w osobnym środowisku.
- [ ] Commit zestawu 1 wykonany po akceptacji wyników.

### 1D, poprawki po TEST, status DEV

- [x] Asercja `test_initialize_and_tools_list` oczekuje pełnego zestawu sześciu narzędzi MCP.
- [x] `graph_check` automatycznie rozpoznaje source, Claude i Codex na podstawie metadanych hosta;
  można także przekazać jawny parametr `host`.
- [x] Source i Claude nadal wymagają fizycznego reviewera oraz wszystkich producer agents.
- [x] Source, Claude i Codex wymagają tego samego fizycznego inventory agentów oraz kontrolują
  kontrakty reviewera, `review_profile`, skille i subgrafy.
- [x] Usunięto lokalny, pusty katalog `skills/g02-review-research-output/agents`, który był kopiowany
  do bundla wraz z całym katalogiem skilla.
- [x] Dokument 08 dodano do indeksu dokumentacji, a opis polityki hostów zsynchronizowano.

### RETEST 1D, lista końcowa przed commitem

- [x] Uruchomić `tests/test_mcp_server.py::test_initialize_and_tools_list`; wynik zawiera dokładnie
  sześć narzędzi, w tym `research_review_prepare` i `research_review_finalize`.
- [x] Uruchomić cały istniejący zestaw `tests/` przez właściwy `pytest`; oczekiwany wynik to brak
  failures.
- [x] Zbudować od czystej kopii oba warianty pluginu i potwierdzić brak mutacji plików źródłowych.
- [x] Uruchomić `check_all()` na source root; wynik ma `host: source`, `ok: true`.
- [x] Uruchomić `check_all(plugin_root=<bundle Claude>)`; host ma zostać wykryty jako `claude`,
  wynik `ok: true`.
- [x] Uruchomić `check_all(plugin_root=<bundle Codex>)`; host ma zostać wykryty jako `codex`,
  wynik `ok: true` przy zamierzonym wspólnym katalogu agentów pluginu.
- [x] Powtórzyć trzy kontrole z jawnym parametrem `host`; wyniki muszą odpowiadać autodetekcji.
- [x] Nieznana wartość `host` oraz jednoczesne markery Claude i Codex są odrzucane czytelnym
  błędem konfiguracji.
- [x] Source, Claude i Codex odrzucają brak fizycznego reviewera oraz brak dowolnego producer
  agenta.
- [x] Codex nadal odrzuca brak kontraktu reviewera, błędną wersję kontraktu, brak
  `review_profile`, brak fizycznego skilla i brak wskazanego subgrafu.
- [x] Bundle Codex zawiera top-level katalog `agents` zgodnie z `includeAgents = true` i nie zawiera
  pustego katalogu `skills/g02-review-research-output/agents`.
- [x] Bundle Claude nadal zawiera dokładnie jeden fizyczny `g02-a10-output-reviewer`.
- [x] Wynik retestu dopisać na górze sekcji „Wpisy” w `08_Log_wynikow_TEST.md`, bez zmiany
  wcześniejszych rund; następnie zaktualizować checkboxy TEST 1C i RETEST 1D w tym rejestrze.

### 1E, migracja namespace, status DEV

- [x] Techniczny identyfikator Research Graph zmieniono z `research` na `g02`.
- [x] Manifest grafu, pakiet skryptów, flow i mocki przeniesiono odpowiednio do
  `g02.graph.json`, `shared/scripts/g02/`, `g02_flow.py` i `mocks/g02/`.
- [x] Dziesięciu agentów otrzymało stabilne identyfikatory `g02-a01`–`g02-a10`; ich nazwy,
  pliki, frontmatter i wszystkie odwołania nie powtarzają słowa `research`.
- [x] Dziesięć skilli jednego agenta otrzymało prefiks `g02-aNN-`.
- [x] Osiem skilli współdzielonych lub wielowęzłowych otrzymało prefiks `g02-` bez kodu agenta.
- [x] Część opisowa wszystkich nazw skilli pozostała bez zmian.
- [x] Manifest pluginu, graf, agenci, skille, adaptery, komenda, skrypty, mocki, testy, README,
  dokumentacja 00–08 i historyczne odwołania używają nowego namespace.
- [x] Nazwy kontraktów, artefaktów, profili review, narzędzi MCP oraz komenda `/research`
  pozostały bez zmian.

### TEST 1E, namespace przed commitem

- [x] Source inventory zawiera dokładnie jeden `g02.graph.json`, 10 agentów `g02-a01`–`g02-a10`
  i 18 skilli `g02-*`; nie istnieją stare katalogi ani pliki komponentów.
- [x] Każdy plik agenta ma `name` identyczne z nazwą pliku bez `.md`.
- [x] Każdy `SKILL.md` ma `name` identyczne z nazwą katalogu, a nazwa spełnia regułę
  `[a-z0-9-]+` i limit 64 znaków.
- [x] Lista agentów odpowiada zamrożonej mapie `g02-a01`–`g02-a10`; kody są unikalne i nie ma
  braków w sekwencji.
- [x] Lista skilli zawiera dokładnie 10 nazw `g02-aNN-<skill>` i 8 nazw
  `g02-<shared-skill>` zgodnych z zatwierdzoną mapą.
- [x] `plugin.manifest.json` odpowiada fizycznemu inventory bez braków, starych ścieżek i
  duplikatów.
- [x] `g02.graph.json` używa `graph_id: g02`, właściwego orchestratora, reviewera, entry node,
  dziewięciu producer nodes i kompletnej sequence z nowymi identyfikatorami.
- [x] Każdy agentowy `Required Skills` wskazuje istniejące katalogi skilli; nie ma odwołań do
  nazw sprzed migracji.
- [x] W całym repo nie występują samodzielne identyfikatory agentów, skilli, ścieżek ani modułów
  obowiązujące przed migracją 1E.
- [x] Importy `g02` i `g02_flow`, CLI, MCP oraz mock input działają z nowych ścieżek.
- [x] `graph_check` przechodzi na source root oraz bundlach Claude i Codex.
- [x] Build Claude i Codex zawierają wspólne definicje agentów o nowych nazwach.
- [x] Oba bundle zawierają 18 skilli o nowych nazwach, właściwe adaptery, `g02_flow.py`,
  `review.py`, kontrakty i serwer MCP.
- [x] Build nie mutuje źródeł i nie tworzy pustych lub osieroconych katalogów po starych nazwach.
- [x] Pełny zestaw `pytest` przechodzi bez failures; testy grafu używają `g02` i nowych node IDs.
- [x] Kontrakty `research_*`, profile review, sześć nazw narzędzi MCP i komenda `/research`
  pozostają zgodne wstecznie.
- [x] Dokumentacja 00–08, README główny, README grafu, skryptów, kontraktów i mocków używają tej
  samej mapy nazw.
- [x] Wynik TEST 1E dopisać na górze `08_Log_wynikow_TEST.md`, a następnie zaznaczyć TEST 1E i
  warunek commitu w tym rejestrze zgodnie z faktycznym wynikiem.

## 2. G02-A01 Planner

### Status DEV

- [x] Zamrożono `research_graph_input@1`, ograniczony `research_planner_input@1` i
  `research_plan@1`.
- [x] Sfinalizowano definicję `g02-a01-planner` oraz wymagany skill
  `g02-a01-plan-research-scope` wraz z adapterami Claude i Codex.
- [x] Zaimplementowano scoping wejścia, walidację kompletności, shape check planu, bezpieczny zapis
  artefaktu, statusy envelope i obsługę rewizji w `shared/scripts/g02/planner.py`.
- [x] Zamrożono kryteria `RP-01`–`RP-06`, wymagania dowodowe, zachowania zabronione i severity
  rules profilu `research_plan`.
- [x] Dodano MCP `research_planner_prepare`, `research_planner_finalize` i
  `research_plan_review_task`; serwer raportuje wersję `0.3.0`.
- [x] `g02_flow.scoped_input()` przekazuje Plannerowi wyłącznie `research_planner_input@1`.
- [x] Zaktualizowano mock wejścia i dodano kompletny mock `research_plan@1`.
- [x] Zsynchronizowano dokumentację, README kontraktów, skryptów i mocków.
- [x] Przeprowadzono kontrolę statyczną bez tworzenia i uruchamiania testów.

### TEST 2, kontrakty i kompletność wejścia

- [x] Poprawny `research_graph_input@1` przechodzi kontrakt, a brak każdego nowego pola wymaganego
  (`schema_version`, drivers, constraints, selection profile, card arrays, output language) jest
  odrzucany.
- [x] `research_planner_input@1` powstaje wyłącznie z dozwolonych pól boundary input i zachowuje
  ich wartości bez mutacji.
- [x] Poprawne wejście bez claim cards przechodzi, jeżeli ma zatwierdzony driver concept,
  flow-issue albo update-need z istniejącą kartą upstream.
- [x] Brak driverów lub zatwierdzonych domen daje `needs_input` bez artefaktu.
- [x] Pusty `task_id`, output language albo wymagane pole zatwierdzonego kontekstu daje
  `needs_input`.
- [x] Duplikaty domain, driver, claim, concept, flow, update lub existing-source IDs są odrzucane.
- [x] Driver bez upstream linku, z nieznanym linkiem, pustym purpose, nieznanym typem albo
  priorytetem jest odrzucany.
- [x] Niepoprawne limity, puste listy languages/work types, odwrócone lata i selection target
  większy od candidate limit są odrzucane.
- [x] Lazy artifact refs bez `artifact://` są odrzucane, a przygotowanie pierwszego przebiegu nie
  hydratuje żadnego z nich.

### TEST 2, walidacja i finalizacja ResearchPlan

- [x] `mocks/g02/research_plan.json` przechodzi `research_plan@1` i pełny walidator semantyczny
  względem sparowanego mock input.
- [x] Poprawny plan jest zapisywany pod bezpiecznym `artifact://g02/research-plans/...`, zwraca
  `status: ok` oraz dokładnie jeden deskryptor `research_plan@1` z `artifact_version`.
- [x] Plan nie mutuje planner input ani obiektu przekazanego do finalizacji.
- [x] Pusty plan, przekroczenie `max_topics`, duplikaty albo niepoprawne formaty `TOPIC_*` i
  `COV_*` są odrzucane.
- [x] Topic bez drivera, purpose, zatwierdzonej domeny, source role, core terms, coverage albo stop
  rule nie tworzy artefaktu.
- [x] Nieznany driver lub upstream ID, niezatwierdzona domena i niezatwierdzony seed source są
  odrzucane.
- [ ] Topic priority nie może być niższy niż najwyższy priorytet powiązanego drivera.
- [x] Languages, work types i date window nie mogą rozszerzać global constraints.
- [ ] Candidate limit mieści się w konfiguracji, saturation passes są zachowane, a complementary
  search route jest wymagana.
- [x] Każdy driver trafia dokładnie do covered albo uncovered; overlap, unknown i unaccounted
  drivers są odrzucane.
- [ ] Uncovered driver bez odpowiadającego `input_issues.related_driver_ids` jest odrzucany.
- [ ] Użyteczny plan z poprawnie zadeklarowanym uncovered driverem zwraca `degraded`; high-priority
  uncovered nie może później uzyskać `APPROVED` od reviewera.
- [ ] Blocking input issue nie pozwala zapisać planu.
- [x] Zmiana task ID, output language, global constraints lub review profile jest odrzucana.
- [x] Pola publikacji, source records, claim verdicts i slide changes są odrzucane także przy
  zagnieżdżeniu.
- [ ] Błąd zapisu artefaktu zwraca `failed` bez deskryptora i bez częściowego zatwierdzonego pliku.

### TEST 2, rewizja i reviewer

- [x] Rewizja bez `previous_plan_ref` jest odrzucana, gdy przekazano `revision_items`.
- [x] Previous plan z innym task ID, złym kontraktem albo niedostępnym refem jest odrzucany.
- [ ] Traversal, ścieżka absolutna i symlink poza artifact root w `previous_plan_ref` są odrzucane.
- [ ] Rewizja musi zwiększyć `artifact_version`.
- [ ] Gdy findings wskazują konkretne `TOPIC_*`, wszystkie pozostałe topiki pozostają niezmienione.
- [x] `research_plan_review_task` buduje poprawny `review_task@1` z producentem
  `g02-a01-planner`, profilem `research_plan` i kryteriami `RP-01`–`RP-06`.
- [x] Deskryptor innego typu, kontraktu, bez artifact version lub bez `artifact://` nie pozwala
  zbudować review task.
- [ ] Deskryptor artefaktu przekazywany do `research_plan_review_task` musi zawierać jawne pole  — Runda 11: **F-E (blocker)**. Adapter wymaga `type: "research_plan"` (brak → `artifact descriptor type must be research_plan`) oraz `ref` (nie `artifact_ref`) z wartością `artifact://`. Prompt orkiestratora i dokumentacja MCP nie komunikują tych wymagań. Fix: zaktualizować schemat deskryptora lub prompt orkiestratora; dodać test dla deskryptora bez `type` i bez `ref`.
  `type` i `ref` (a nie `artifact_ref`); brak któregokolwiek jest odrzucany.
- [ ] `research_review_prepare` i `research_review_finalize` wymagają przekazania pełnego obiektu  — Runda 11: **F-F (blocker)**. Prepare zwraca BLOCKED kolejno na `missing original_task`, `missing producer_input` i `evidence_requirements[n]: missing requirement_id` (błędny klucz `criterion_id`). Orkiestrator musi przekazywać cały obiekt z `research_plan_review_task` bez modyfikacji. Fix: zaktualizować prompt orkiestratora; sprawdzić schemat `evidence_requirements[].requirement_id` jako required.
  `review_task@1` z `producer_input`; klucz w `evidence_requirements` to `requirement_id` (nie `criterion_id`).
- [x] Próba review większa niż 1 wymaga `previous_decision_ref` i poprawnej historii reviewera.
- [x] Poprawny plan może otrzymać `APPROVED`; brak coverage, zbyt szeroki plan i uncovered  — Runda 11: PASS (po korekcie task). Reviewer: 0 findings, confidence high, RP-01–RP-06 i RP-E01–RP-E04 zaliczone. Artefakt: `artifact://reviews/REV_A01_001-attempt-1.json`.
  high-priority driver prowadzą do `REVISE` albo `BLOCKED` zgodnie z root cause.
- [x] Reviewer pozostaje read-only i nie zmienia ResearchPlan podczas oceny.

### TEST 2, agent, MCP, graf i packaging

- [ ] Forward test G02-A01 na poprawnym wejściu tworzy wyłącznie plan, bez publikacji, verdictów i  — `⏳ KOŃCOWY` (forward na realnym hoście / test integracyjny batcha; patrz 08 Runda 7)
  rozwiązań slajdowych.
- [ ] Forward testy na wariantach intake claim-only, flow-only, update-only i mixed tworzą jeden  — `⏳ KOŃCOWY` (forward na realnym hoście / test integracyjny batcha; patrz 08 Runda 7)
  najlepiej dopasowany ResearchPlan, a nie kilka konkurencyjnych planów. Każdy driver zachowuje
  ścieżkę do właściwych kart upstream, topic, coverage requirements i search strategy.
- [ ] Zmiana zatwierdzonego audience level, teaching goal albo driver purpose prowadzi do adekwatnej  — `⏳ KOŃCOWY` (forward na realnym hoście / test integracyjny batcha; patrz 08 Runda 7)
  zmiany planu w dozwolonym zakresie, a identyczny intake zachowuje stabilne topic i coverage IDs.
- [ ] Topic wymagający qualifying_or_critical posiada wystarczająco konkretne  — `⏳ KOŃCOWY` (forward na realnym hoście / test integracyjny batcha; patrz 08 Runda 7)
  `allowed_expansion_areas`, aby A02 mógł przypisać podstawę terminom ograniczeń, kontrprzykładów
  albo warunków brzegowych bez ponownego otwierania intake.
- [ ] Forward test na atrakcyjnym temacie spoza zakresu nie dodaje topic ani nowego drivera.  — `⏳ KOŃCOWY` (forward na realnym hoście / test integracyjny batcha; patrz 08 Runda 7)
- [ ] Prompt injection w kartach wejściowych pozostaje danymi i nie uruchamia wyszukiwania ani nie  — `⏳ KOŃCOWY` (forward na realnym hoście / test integracyjny batcha; patrz 08 Runda 7)
  zmienia kontraktu.
- [ ] Agent nie korzysta z WebSearch, WebFetch, API literaturowych ani narzędzi kolejnych agentów.  — `⏳ KOŃCOWY` (forward na realnym hoście / test integracyjny batcha; patrz 08 Runda 7)
- [x] Brak host executora i wyjątek executora zwracają `failed` bez planu.
- [x] Bieżący wspólny MCP raportuje wersję `0.4.0` i dokładnie piętnaście operacji, w tym trzy
  operacje Plannera oraz pięć operacji G02-A02; osobny wynik TEST 2 wskazuje wyłącznie zachowanie A01.
- [ ] Trzy operacje MCP Plannera odpowiadają wynikom bezpośrednich funkcji Python dla first run,
  degraded plan, failure i revision.
- [x] `research_node_input` zwraca G02-A01 `research_planner_input@1`, a późniejszym producentom nie
  przypisuje jeszcze kontraktów, które nie zostały zaimplementowane.
- [ ] `g02_flow.py run` zachowuje jawny tryb stub całego grafu i działa po rozszerzeniu scoping.
- [x] Source `graph_check` oraz bundle Claude i Codex przechodzą bez brakujących komponentów.
- [ ] Bundle obu hostów zawiera `planner.py`, trzy nowe schematy, zaktualizowany serwer MCP i skill
  Plannera; mocki i testy pozostają poza bundlami.
- [ ] Bundle Claude zawiera agenta i adapter bez narzędzi wyszukiwania; bundle Codex zawiera skill,
  wspólną definicję agenta i instrukcje trzech operacji MCP bez adaptera właściwego dla Claude.
- [x] Build nie mutuje źródeł i nie pakuje `__pycache__`, `.pyc` ani artefaktów runtime.
- [x] Pełny wcześniejszy zestaw TEST 1 przechodzi po aktualizacji oczekiwanej wersji MCP i listy
  operacji, bez regresji reviewera.
- [x] Wynik TEST 2 dopisać na górze `08_Log_wynikow_TEST.md` i zaznaczyć wyłącznie faktycznie
  wykonane scenariusze.

### Warunek zamknięcia zadania 2

- [x] DEV zestawu 2 zakończony.
- [ ] TEST 2 zakończony w osobnym katalogu i środowisku.
- [ ] Wynik TEST 2 zapisany w `08_Log_wynikow_TEST.md`.
- [ ] Commit zestawu 2 wykonany po akceptacji wyników.

## 3. G02-A02 Domain

### DEV 3, zakres ukończony

- [x] Zamrożono `domain_research_input@1`, `query_plan@1`, `source_record@1`,
  `literature_tool_result@1`, `domain_candidate_sources@1` i `literature_provider_config@1`.
- [x] Zdefiniowano odpowiedzialność, granice, failure paths, resume i profil review agenta
  `g02-a02-domain`.
- [x] Zaktualizowano skille `g02-expand-research-query` i
  `g02-search-scholarly-metadata` wraz z adapterami obu hostów.
- [x] Zaimplementowano konfigurację providerów bez sekretów w pliku, walidację przy starcie,
  katalogi runtime, limity, timeout, retry, rate limiting i cache.
- [x] Wyrównano konfigurację z wymaganiami providerów z 2026-06-21: aktywny OpenAlex wymaga
  `OPENALEX_API_KEY`, Semantic Scholar dopuszcza pracę bez klucza, a arXiv zachowuje odstęp co
  najmniej 3 sekund. Status capabilities nie ujawnia wartości sekretów.
- [x] Zaimplementowano deterministyczne adaptery OpenAlex, Semantic Scholar i arXiv z allowlistą
  HTTPS, limitem rozmiaru odpowiedzi, paginacją i redakcją sekretów.
- [x] Zaimplementowano raw-response artifacts, normalizację do `source_record@1`, provenance oraz
  zapis `literature_tool_result@1`.
- [x] Zaimplementowano scoping jednego topic, walidację QueryPlan, finalizację
  `domain_candidate_sources@1`, rewizję i builder profilu `domain_candidates`.
- [x] Rozszerzono `query_plan@1` do wersji kontraktowej 1.1 w ramach major 1: każdy generated term
  ma dokładnie jeden `generated_term_bases` z zatwierdzonym origin term, expansion area i relacją
  semantyczną; walidator odrzuca brak, nadmiar, duplikat oraz wyjście poza topic.
- [x] Dodano MCP `research_provider_status`, `research_domain_prepare`,
  `research_metadata_search`, `research_domain_finalize` i `research_domain_review_task`; serwer
  raportuje wersję `0.4.0`.
- [x] Manifest G02-A02 wskazuje `domain_research_input@1` i `domain_candidate_sources@1`.
- [x] Dodano przykład QueryPlan oraz stałe odpowiedzi OpenAlex, Semantic Scholar i arXiv do
  późniejszych testów offline.
- [x] Zaktualizowano dokumentację setupu, kontraktów, architektury MCP/API i planu 1b1.
- [x] W fazie DEV nie uruchomiono testów funkcjonalnych ani połączeń z API.

### TEST 3, konfiguracja i bezpieczeństwo

- [x] Poprawny plik config, `EMAGENTS_RESEARCH_CONTACT_EMAIL` i wymagany dla aktywnego OpenAlex
  `OPENALEX_API_KEY` tworzą katalogi runtime i raportują trzy jawne capabilities bez wartości
  sekretów.
- [x] Jawna ścieżka config ma pierwszeństwo przed `EMAGENTS_RESEARCH_CONFIG`, konfiguracją projektu
  i przykładem w repo.
- [x] Brak kontaktowego e-maila przy włączonym OpenAlex lub arXiv kończy startup czytelnym błędem.
- [x] Brak `OPENALEX_API_KEY` przy włączonym OpenAlex kończy startup przed requestem czytelnym
  błędem; wyłączenie OpenAlex pozwala uruchomić pozostałych poprawnie skonfigurowanych providerów.
- [x] OpenAlex raportuje `configured_key` wyłącznie po skonfigurowaniu klucza. Semantic Scholar
  raportuje `optional_key` bez klucza i `configured_key` z kluczem. Wartości kluczy nie trafiają do
  statusu, błędów, logów, cache w postaci jawnej ani artefaktów.
- [x] Nieprawidłowy kontrakt config, ujemne limity, zbyt duży timeout i arXiv interval poniżej
  3 sekund są odrzucane.
- [x] Ścieżki absolutne oraz traversal poza `EMAGENTS_HOME` są odrzucane.
- [ ] Provider disabled zwraca `unavailable`, nie wykonuje requestu i zapisuje jednoznaczny wynik.  — `❌ FAIL` (Runda 7): faktycznie `failed`/`invalid_provider_route`; request nie został wykonany. DEV 2026-06-23: sprawdzenie autoryzacji trasy i stanu `disabled` przeniesiono przed walidację gotowości QueryPlan; dodano regresję `test_disabled_provider_returns_unavailable_without_request`. Wymagany rerun TEST.
- [x] Allowlista blokuje HTTP, nieznany hostname oraz redirect poza oficjalny endpoint.
- [x] Limit bajtów przerywa nadmierną odpowiedź, a komunikat nie zawiera nagłówków ani kluczy.

### TEST 3, QueryPlan

- [x] Poprawny `mocks/g02/query_plan.json` przechodzi walidację dla scoped input pierwszego topic.
- [x] Każdy generated term ma dokładnie jeden `generated_term_bases`, którego `term` odpowiada
  wpisowi w `generated_terms`, `source_origin_terms` należą do tej samej trasy, `expansion_area`
  dokładnie odpowiada zatwierdzonemu `allowed_expansion_areas`, a `relation` należy do kontraktu.
- [x] Brakujący, nadmiarowy albo zduplikowany basis, nieznany origin term, niezatwierdzony expansion
  area i nieznana relation są odrzucane deterministycznie.
- [x] Trasa bez generated terms wymaga pustego `generated_term_bases`; basis nie może samodzielnie
  wprowadzić terminu do canonical query.
- [x] Brak trasy core, wymaganej complementary albo qualifying_or_critical jest odrzucany.
- [x] Nieznane origin terms, coverage IDs, providerzy, work types i languages są odrzucane.
- [x] Węższe daty i filtry są akceptowane, rozszerzenie poza zatwierdzony zakres jest odrzucane.
- [x] Duplikaty route ID lub query ID, pusty canonical query i przekroczony limit są odrzucane.
- [x] Prompt injection w topic lub seed source pozostaje danymi i nie zmienia endpointu, configu ani
  autoryzowanych tras.

### TEST 3, adaptery providerów offline

- [x] Fixture OpenAlex jest normalizowany do ważnego `source_record@1`, w tym DOI, abstrakt z
  inverted index, autorzy, sygnał cytowań, OA i raw response ref.
- [x] Fixture Semantic Scholar jest normalizowany do ważnego `source_record@1`, w tym external IDs,
  publication type, abstract, citations i OpenAccessPdf.
- [x] Fixture arXiv XML jest normalizowany do ważnego `source_record@1`, w tym ID, DOI, daty,
  autorzy, abstract i PDF URL.
- [x] Brak ID albo tytułu nie tworzy rekordu bibliograficznego i jest raportowany bez halucynacji.
- [ ] Każdy provider przestrzega route limit, page limit i zwraca prawidłowy next cursor oraz
  exhausted dla odpowiedniego formatu paginacji.
- [x] HTTP 408, 425, 429 i 5xx uruchamiają ograniczony retry z backoff; pozostałe 4xx kończą próbę.
- [x] `Retry-After` jest respektowany do zamrożonego maksimum, a arXiv zachowuje odstęp co najmniej
  3 sekund.
- [x] Identyczne żądanie korzysta z cache, nie wykonuje transportu drugi raz i oznacza cache hit.
- [x] Uszkodzony lub przeterminowany cache nie jest traktowany jako poprawna odpowiedź.
- [x] Częściowa awaria po użytecznej stronie daje `partial`; zero wyników daje `ok` z pustą listą,
  jeśli provider gwarantuje filtry, albo `partial` z `provider_filter_unverifiable`; awaria przed
  wynikiem daje `failed` albo `unavailable`.
- [x] Raw response i `literature_tool_result@1` są zapisane jako osobne, możliwe do hydratacji
  artefakty z pełną proweniencją.

### TEST 3, live API smoke, wyłącznie opt-in

- [ ] Testy sieciowe są domyślnie pomijane i uruchamiają się wyłącznie po jawnej fladze środowiska;  — Runda 7: N/A w pakiecie `tests/`; live smoke wykonano osobnym opt-in harnessem (osobny `EMAGENTS_HOME`, limit 1–2 rekordy).
  używają osobnego katalogu `EMAGENTS_HOME`, limitu 1–2 rekordów i kontrolowanego timeoutu.
- [x] Preflight potwierdza obecność `EMAGENTS_RESEARCH_CONTACT_EMAIL` i `OPENALEX_API_KEY` bez
  drukowania wartości. `SEMANTIC_SCHOLAR_API_KEY` jest sprawdzany jako opcjonalny, ale zalecany.
- [x] OpenAlex przyjmuje skonfigurowany klucz, zwraca HTTP success i co najmniej jeden rekord dla
  stabilnego małego query; wynik, rekord i raw-response ref przechodzą kontrakty. Brak klucza jest
  zatrzymywany lokalnie przed requestem.
- [ ] Semantic Scholar wykonuje małe query z nagłówkiem `x-api-key`, gdy klucz jest skonfigurowany,  — Runda 7: tryb bez klucza zweryfikowany; ścieżka `x-api-key` wymaga opcjonalnego `SEMANTIC_SCHOLAR_API_KEY`.
  oraz poprawnie raportuje limit lub tryb bez klucza. Kod nie przekracza jednego requestu na sekundę.
- [x] arXiv wykonuje małe query bez klucza, wysyła identyfikujący User-Agent, zachowuje odstęp co
  najmniej 3 sekund i zwraca poprawny rekord z XML.
- [x] Pierwszy request każdego providera omija cache, a drugi identyczny request potwierdza cache hit
  bez ponownego połączenia, jeżeli cache jest włączony.
- [x] Po smoke testach automatyczny skan całego testowego `EMAGENTS_HOME`, przechwyconego stdout i
  stderr potwierdza brak jawnych wartości e-maila i obu kluczy. Artefakty zachowują tylko
  niesekretny status authentication i proweniencję.
- [x] Każdy live wynik odróżnia prawidłowe zero results, błąd autoryzacji, rate limit i awarię
  providera. Test nie prowokuje 429 przez celowe przekraczanie limitu.

### TEST 3, Domain artifact i reviewer

- [x] `research_domain_prepare` hydratuje wyłącznie zatwierdzony plan i jeden topic oraz zwraca
  `domain_research_input@1` bez kluczy API.
- [x] Brak planu, zły kontrakt, nieznany topic i brak gotowego providera zwracają odpowiedni
  `needs_input` albo `failed` bez uruchomienia agenta.
- [x] Poprawny wynik z query logs i niezmienionymi provider records zapisuje
  `domain_candidate_sources@1` i zwraca `ok`.
- [ ] Każdy wpis query log zgadza się z hydratowanym `literature_tool_result@1`; obcy, brakujący albo
  zmodyfikowany ref jest odrzucany.
- [x] Kandydat spoza wyników providera, zmienione metadane, duplikat source ID i przekroczony limit
  są odrzucane.
- [x] G02-A02 nie może przypisywać finalnych source roles ani verdictów claimów.
- [x] Coverage map używa wyłącznie kandydatów i approved coverage IDs, a basis ma wartość metadata,
  title albo abstract.
- [x] Niepełne coverage lub jawne provider issues zapisują użyteczny artefakt jako `degraded` z
  resume token; `completed` z lukami jest odrzucane.
- [x] Rewizja wymaga poprzedniego artefaktu, zachowuje task/topic i zwiększa artifact version.
- [x] Builder review tworzy dokładnie jeden `review_task@1`, profil `domain_candidates`, zamrożone
  DR-01 do DR-06 i ref tylko do ocenianego artefaktu.
- [x] Uniwersalny reviewer zwraca APPROVED, REVISE lub BLOCKED zgodnie z artefaktem i nie wykonuje
  wyszukiwania ani nie modyfikuje wyniku.

### TEST 3, agent, MCP, packaging i regresja

- [ ] Forward test G02-A02 tworzy QueryPlan, wywołuje wyłącznie narzędzia MCP, zachowuje neutralność  — `⏳ KOŃCOWY`. Runda 11: **F-G (blocker)**. Agent zatrzymuje się po zakończeniu skilla `g02-expand-research-query` i nie wywołuje `research_metadata_search` bez kolejnej wiadomości od orkiestratora. Fix: wzmocnić prompt agenta G02-A02 o jawny krok „po skill natychmiast wywołaj search dla każdej trasy bez oczekiwania".
  stanowisk i nie wykonuje pracy A03-A09.
- [ ] `query_plan@1` wygenerowany przez agenta G02-A02 jest akceptowany przez `research_metadata_search`  — Runda 11: **F-H (blocker)**. Agenty generują `routes[].queries[]` (zagnieżdżona tablica), pole `providers` i `route_type`; adapter oczekuje: jedno query płasko na route (`canonical_query`, `origin_terms`, `generated_terms`), `preferred_providers`, `purpose` (`"core"/"complementary"/"qualifying_or_critical"`), `artifact_version`. Fix: zaktualizować skill `g02-expand-research-query` (schemat i przykład w SKILL.md) do flat-route struktury; zaktualizować `mocks/g02/query_plan.json`; dodać offline test dry-run.
  bez iteracji: flat-route struktura, `preferred_providers`, `purpose`, `artifact_version`.
- [ ] Orkiestrator przekazuje do A02 cały `domain_research_input@1`, łącznie ze wszystkimi
  `provider_capabilities`, bez ręcznej rekonstrukcji. — Runda 13: **F-I**, poprawka DEV w skillu
  orkiestratora; wymagany retest forward.
- [ ] A02 nie składa ręcznie technicznego `domain_candidate_sources@1`. Persisted search/DOI refs,
  selected source IDs i minimalne coverage assignments trafiają do
  `research_domain_finalize_from_results`, który deterministycznie buduje query log, niezmienione
  candidates, DOI bindings, provider issues, remaining coverage i stop reason. — Runda 15:
  **F-J**, poprawka DEV wdrożona; wymagany retest forward obu topiców.
- [ ] Forward test G02-A02 zachowuje pełną ścieżkę `driver → topic → origin term → generated term  — `⏳ KOŃCOWY` (forward na realnym hoście / test integracyjny batcha; patrz 08 Runda 7)
  basis → route → coverage unit`; reviewer odrzuca semantycznie nieuzasadniony basis nawet wtedy,
  gdy jego shape przechodzi kontrakt.
- [ ] Dla jednego topic agent tworzy kilka uzasadnionych tras wyszukiwania, a nie kilka wariantów  — `⏳ KOŃCOWY` (forward na realnym hoście / test integracyjny batcha; patrz 08 Runda 7)
  ResearchPlan. Core, complementary i qualifying_or_critical różnią się celem oraz terminologią,
  lecz pozostają w tym samym zatwierdzonym zakresie.
- [ ] Agent nie używa WebSearch, WebFetch, shell HTTP, downloadera PDF ani bezpośrednich klientów API.  — `⏳ KOŃCOWY` (forward na realnym hoście / test integracyjny batcha; patrz 08 Runda 7)
- [ ] Forward testy A01 i A02 przechodzą osobno na Claude i Codex. Brak rzeczywistego izolowanego  — `⏳ KOŃCOWY` (forward na realnym hoście / test integracyjny batcha; patrz 08 Runda 7)
  executora hosta daje jawny failure i nie może zostać zaliczony jako test zachowania agenta.
- [x] MCP raportuje wersję `0.4.0` i dokładnie piętnaście operacji, w tym pięć operacji G02-A02 i
  dziesięć pozostałych.
- [ ] Pięć operacji MCP G02-A02 odpowiada wynikom bezpośrednich funkcji Python dla success,
  zero-result, partial, failure i revision.
- [ ] Manifest, agent, skille, kontrakty i MCP używają wyłącznie identyfikatorów G02-A02 oraz
  aktualnych nazw skilli.
- [x] Source `graph_check` oraz bundle Claude i Codex przechodzą bez brakujących komponentów.
- [x] Bundle zawiera moduły Domain, providerów, sześć schematów, example config, MCP i oba skille;
  mocki, testy, lokalny config i sekrety nie trafiają do bundla.
- [x] Build nie mutuje źródeł i nie pakuje `.emagents`, cache, raw responses, `__pycache__` ani `.pyc`.
- [x] TEST 1 i TEST 2 przechodzą po aktualizacji bieżącej wersji MCP i listy operacji, bez regresji
  reviewera oraz Plannera.
- [x] Wynik TEST 3 dopisać na górze `08_Log_wynikow_TEST.md` i zaznaczyć wyłącznie faktycznie
  wykonane scenariusze.

### Warunek zamknięcia zadania 3

- [x] DEV zestawu 3 zakończony.
- [ ] TEST 3 zakończony w osobnym katalogu i środowisku.
- [ ] Wynik TEST 3 zapisany w `08_Log_wynikow_TEST.md`.
- [ ] Commit zestawu 3 wykonany po akceptacji wyników.

### Usterki z TEST (zestawy 2 i 3, szczegóły w 08, Runda 5)

- [x] `plugin.manifest.json` zawiera agenta `g02-a11-market-cases` oraz skille
  `g02-a11-extract-case-evidence` i `g02-a11-find-market-cases`. Inwentarz źródła i manifestu jest
  zgodny: 11 agentów oraz 20 skilli. A11 pozostaje scaffoldem do późniejszego pionowego wycinka.
- [x] `tests/test_research_graph.py` wyznacza producer-agentów z `g02.graph.json`, zamiast utrzymywać
  drugą, zakodowaną na sztywno liczbę. Graf ma obecnie 10 producer-agentów.
- [x] Rejestr, README, implementacja i `test_mcp_server.py` są zgodne: MCP `0.4.0` udostępnia 15
  operacji, w tym `research_run_codex`. Planowane operacje Tavily nie są jeszcze do tej liczby
  wliczane.

Status TEST 2 i TEST 3 po Rundzie 6: warstwa deterministyczna A01 i A02, pełny pakiet `pytest`,
packaging, `graph_check` oraz live API smoke przeszły w osobnym środowisku. Właściciel zaakceptował
ten zakres jako bramkę wejściową do DEV A03, A04, A11 i A05. Forward testy hostów pozostają jawnie
odroczone do wspólnego testu integracyjnego nowego batcha; dlatego formalne checkboxy pełnego TEST 2
i TEST 3 pozostają niezaznaczone.

### Wynik retestu A01-A02, Runda 6

- [x] Użyć świeżej kopii repo i osobnego środowiska z zależnościami z `requirements-dev.txt`;
  brak `pytest` w bieżącym systemowym Pythonie nie jest wynikiem testu repo. (Runda 6: klon
  `ema-wsl`, `.venv` z `pytest` 9.1.1, Python 3.14.4.)
- [x] Build/dry-run raportuje dokładnie `Validated 20 skills and 11 agents`; oba bundle zawierają
  A11 jako scaffold, a `graph_check` przechodzi dla source, Claude i Codex. (Runda 6: graph_check
  source/Claude/Codex `ok: true`.)
- [x] MCP `0.4.0` raportuje dokładnie 15 zaimplementowanych operacji. Brak
  `research_web_case_search` i `research_web_case_extract` jest oczekiwany do czasu DEV A11.
- [ ] Wykonać pełne TEST 2 i TEST 3 według scenariuszy powyżej, osobno oznaczając: deterministyczne,
  forward Claude, forward Codex, live API i packaging. (Runda 6: deterministyczne + live API +
  packaging wykonane i zaliczone; **forward Claude/Codex pozostają do wykonania**.)
- [x] Live A02 ma dostęp HTTPS do `api.openalex.org`, `api.semanticscholar.org` i
  `export.arxiv.org`, a środowisko zawiera `EMAGENTS_RESEARCH_CONTACT_EMAIL`,
  `OPENALEX_API_KEY` oraz opcjonalnie `SEMANTIC_SCHOLAR_API_KEY`. Wartości sekretów nie mogą
  pojawić się w logu, artefakcie ani statusie providera. (Runda 6: live smoke 24/24, skan
  redakcji potwierdza brak wartości klucza.)
- [x] Nie zaliczać A11, Tavily ani ekstrakcji web w jutrzejszym teście A01-A02. Ich fixture'y mają
  przechodzić wyłącznie walidację shape i packaging; testy semantyczne oraz live należą do batcha
  A11 po A03 i A04, przed agregującym A05.

### Rozstrzygnięcia i pozycje odroczone po Rundzie 6

- [x] **Polityka bundla Codex rozstrzygnięta:** `hosts.codex.includeAgents = true` jest świadomą
  decyzją. Claude i Codex otrzymują wspólne definicje agentów, skille, runtime i MCP; różnią się
  adapterem wykonania. Historyczne wyniki Rund 4/5 w `08` opisują wcześniejszą konfigurację i nie są
  przepisywane. Bieżące wymagania, README, manifest i `graph_check.py` są zgodne.
- [ ] **Forward testy zachowania agentów A01/A02 i uniwersalnego reviewera na realnym host
  executorze (Claude/Codex LLM).** Niewykonane w Rundzie 6. Warstwa deterministyczna pod tymi
  agentami jest w pełni zielona. Testy zostają włączone do wspólnego testu integracyjnego batcha
  A03, A04, A11 i A05.

## 4. Batch DEV A03, A04, A11 i A05

### Zasady pracy i kolejność

- Każdy agent powstaje w osobnym promptcie i wymaga akceptacji właściciela przed rozpoczęciem
  kolejnego pionowego wycinka.
- Kolejność implementacji jest zgodna z zależnościami grafu: G02-A03 Canonical Sources, G02-A04
  Recent Developments, G02-A11 Market Cases, a następnie G02-A05 Candidate Source Index.
- A03, A04 i discovery A11 są logicznym fan-out po A02. Bieżący runtime nadal wykonuje je
  sekwencyjnie; implementacja nie może zakładać współbieżności, dopóki scheduler jej nie zapewni.
- Dla każdego agenta DEV obejmuje kontrakty i scoped input, moduł deterministyczny, operacje MCP,
  definicję agenta i skilli, profil review, mocki, testy, manifest, packaging i dokumentację.
- W repo deweloperskim wykonujemy kontrole statyczne i małe testy regresyjne bez live API. Pełna
  certyfikacja całego batcha odbywa się po zakończeniu A05 w świeżym, osobnym środowisku.
- Zalecane commity: osobny commit bazowy dokumentacji, po jednym commicie na A03, A04, A11 i A05,
  następnie osobny commit poprawek po teście integracyjnym.

### DEV 4, G02-A03 Canonical Sources

- [x] Zamrozić wejście A03 i semantykę `CanonicalCandidateSources` w `candidate_sources@1`.
- [x] Zaimplementować scoping z zatwierdzonego planu i `DomainCandidateSources`, bez sekretów i
  nieautoryzowanych artefaktów.
- [x] Zaimplementować kontrolowaną ekspansję cytowań, wyszukiwanie uzupełniające, klasyfikację ról,
  podstawę kanoniczności, poziom dostępu, surrogate links, coverage i search log.
- [x] Dodać prepare, search/expand, finalize i review-task do MCP oraz failure paths i resume.
- [x] Uzupełnić mocki, profil `canonical_sources`, testy offline i dokumentację.
- [x] Potwierdzić build obu hostów, `graph_check`, walidację skilli i pełną regresję po finalnym
  przeglądzie zmian A03. (DEV: 56 testów, trzy skille A03, dry-run 20 skilli/11 agentów, build i
  `graph_check` source/Claude/Codex przeszły.)
- [ ] Przedstawić ukończony pionowy wycinek do akceptacji przed DEV A04.

### TEST 4, G02-A03 Canonical Sources

Checkbox wolno zaznaczyć wyłącznie po wykonaniu wskazanego scenariusza w docelowym środowisku
testowym. Lokalny test DEV nie zastępuje live smoke ani forward testu agenta na realnym hoście.

#### A. Przygotowanie i regresja deterministyczna

- [x] Użyć świeżej kopii repo i nowego środowiska Python z `requirements-dev.txt`; ustawić osobny
  `EMAGENTS_HOME`, który można po teście w całości przeskanować pod kątem sekretów.
- [x] Uruchomić `python -m pytest tests/test_g02_canonical.py tests/test_mcp_server.py -q`; wszystkie
  testy A03 i bieżące 22 operacje MCP przechodzą.
- [x] Uruchomić `python -m pytest -q`; A01, A02, A10, packaging i pozostałe moduły nie mają regresji.
- [x] `research_canonical_prepare` przyjmuje dokładnie jeden zatwierdzony topic i odpowiadający mu
  reviewed `domain_candidate_sources@1`; odrzuca zły task, topic, ref lub artifact version.
- [x] Scoped input zawiera tylko zatwierdzone rekordy, zweryfikowane seedy, nierozwiązane seedy,
  role, coverage, limity i publiczny status providerów. Nie zawiera e-maila ani wartości kluczy.

#### B. Ekspansja, metadane i walidacja artefaktu

- [x] Fixture OpenAlex potwierdza `cited_by`, a fixture'y Semantic Scholar potwierdzają
  `references`, `cited_by` i `recommendations`, wraz z seed ID, provider ID, relation, distance 1,
  operation ID, raw-response provenance oraz niezmienionym `source_record@1`.
- [x] OpenAlex dopuszcza wyłącznie `cited_by`; Semantic Scholar dopuszcza `references`, `cited_by`
  i `recommendations`; arXiv i nieobsługiwana relacja zwracają kontrolowane `unavailable`.
- [x] Niezatwierdzony seed, brak identyfikatora właściwego providera, depth inne niż 1 i limit ponad
  scoped budget są odrzucane przed połączeniem sieciowym.
- [x] `research_metadata_search` przyjmuje `canonical_input`, nadal wymaga zgodnego `query_plan@1`
  i zapisuje wynik każdej wykonanej trasy, także zero-result, partial oraz failed.
- [x] Finalizacja odrzuca rekord zmodyfikowany względem reviewed A02 albo tool result, brak
  operation ref, niepełny search log, niezgodną projekcję provider issues i przekroczony limit.
- [x] Każdy użyty `literature_tool_result@1` ma `request.scope` zgodny z task, topic, ResearchPlan
  i reviewed A02 ref. Próba podpięcia wyniku z innego scope jest blokowana.
- [x] Każdy kandydat ma dokładnie jedną adnotację. Pojedynczy citation count nie wystarcza jako
  canonicality basis; `domain_authoritative` wymaga dokładnego seed ID zatwierdzonego w planie i
  evidence source `domain_authority`; access i library requirement odpowiadają rekordowi.
- [x] Coverage, nierozwiązane seedy, stop reason i status `completed`/`degraded` są wzajemnie
  zgodne. Surrogate pozostaje osobnym source ID i nie jest oznaczany jako semantyczny odpowiednik.
- [x] Rewizja wymaga poprzedniego artefaktu, zwiększa `artifact_version`, zmienia wyłącznie wskazane
  pola i zachowuje task, topic oraz niekwestionowane rekordy.
- [x] `research_canonical_review_task` tworzy ważny `review_task@1`, profil `canonical_sources`,
  kryteria `CS-01` do `CS-06` i ref wyłącznie do zapisanego artefaktu A03.

#### C. Live API i zachowanie operacyjne

- [x] Preflight potwierdza `EMAGENTS_RESEARCH_CONTACT_EMAIL`, `OPENALEX_API_KEY` oraz opcjonalny
  `SEMANTIC_SCHOLAR_API_KEY` bez drukowania wartości. Brak wymaganego sekretu kończy się lokalnie.
- [ ] Live OpenAlex `cited_by` dla stabilnego zweryfikowanego seeda zwraca 1–2 ważne rekordy,  — niewykonalne z mock seedem (placeholder `openalex_id`); ścieżka kodu i normalizacja zaliczone offline. Do wykonania z realnym seedem — 08 Runda 7.
  respektuje limit i zapisuje request ID, raw-response ref, paginację oraz config profile.
- [x] Live Semantic Scholar wykonuje co najmniej jedną relację dostępną dla stabilnego seeda. Tryb
  bez klucza, 429 lub quota limit jest raportowany jako jawny status, bez pozornego success.
- [x] Live complementary metadata search działa dla każdego gotowego providera: OpenAlex,
  Semantic Scholar i arXiv. Zero wyników pozostaje prawidłowym, audytowalnym wynikiem.
- [x] Powtórzone identyczne wywołanie potwierdza cache hit bez drugiego requestu. Timeout, 429/5xx,
  uszkodzony cache i częściowa odpowiedź przechodzą ograniczony retry oraz właściwy failure path.
- [x] Skan `EMAGENTS_HOME`, stdout i stderr nie znajduje jawnego e-maila ani kluczy. Artefakty
  zawierają tylko publiczny status konfiguracji i bezpieczny `config_profile`.

#### D. Forward test Claude i Codex

- [ ] Na Claude agent wykonuje prepare, dozwolone expand/search, buduje poprawne adnotacje,  — `⏳ KOŃCOWY` (forward na realnym hoście / test integracyjny batcha; patrz 08 Runda 7)
  finalizuje artefakt i tworzy review task bez bezpośredniego HTTP, WebSearch ani pobierania PDF.
- [ ] Ten sam scenariusz przechodzi na Codex z tą samą semantyką kontraktów i identyfikowalnością.  — `⏳ KOŃCOWY` (forward na realnym hoście / test integracyjny batcha; patrz 08 Runda 7)
- [ ] Scenariusz z zamkniętą monografią nie przypisuje jej niedostępnej treści. Dostępny surrogate  — `⏳ KOŃCOWY` (forward na realnym hoście / test integracyjny batcha; patrz 08 Runda 7)
  jest osobnym kandydatem, a citation count pozostaje sygnałem discovery, nie oceną jakości.
- [ ] Scenariusz z provider issue lub luką coverage kończy się `degraded`; brak rzeczywistego  — `⏳ KOŃCOWY` (forward na realnym hoście / test integracyjny batcha; patrz 08 Runda 7)
  izolowanego executora hosta daje jawny failure i nie jest zaliczany jako forward test.
- [ ] G02-A10 zatwierdza poprawny wynik, kieruje naruszenie `CS-*` do REVISE albo BLOCKED, a A03  — `⏳ KOŃCOWY` (forward na realnym hoście / test integracyjny batcha; patrz 08 Runda 7)
  wykonuje wyłącznie wskazaną rewizję.

#### E. Packaging i bramka wejścia do DEV A04

- [x] `python scripts/install_plugin.py --all --dry-run` raportuje 20 skilli i 11 agentów bez
  modyfikacji źródeł ani istniejącego `dist`.
- [x] `python scripts/build-plugin.py --host all` buduje bundle Claude i Codex; oba zawierają
  `canonical.py`, `citations.py`, nowy kontrakt, definicję A03 i wymagane skille.
- [x] `graph_check` przechodzi dla source oraz obu bundli. Bundle nie zawiera mocków, testów,
  `.emagents`, konfiguracji lokalnej, raw responses, cache, `__pycache__` ani `.pyc`.
- [x] Wynik TEST 4 dopisać jako nową rundę na górze `08_Log_wynikow_TEST.md`, oddzielając testy
  deterministyczne, live API, forward Claude, forward Codex i packaging.
- [ ] Po zaliczeniu testów oraz akceptacji właściciela wykonać osobny commit A03 i rozpocząć DEV A04.

### DEV 5, G02-A04 Recent Developments

- [x] Zamrozić wejście A04 i semantykę `RecentCandidateSources` w `candidate_sources@1`.
- [x] Zachować `approved_research_scope.recency_window_years` z intake w `research_plan@1` i
  deterministycznie materializować z niego inkluzywne okno kalendarzowe A04.
- [x] Zaimplementować zapytania w zatwierdzonym oknie dat, rozróżnienie preprint/peer review,
  maturity signals, `core_update`/`optional_trend`/`watch`, coverage i stop reason.
- [x] Współdzielić bezpieczny seam metadata i citation A02–A04 bez duplikowania transportu
  providerów.
- [x] Dodać prepare, finalize i review-task do MCP, profil `recent_developments`, failure paths,
  resume, mocki, testy offline i dokumentację.
- [x] Potwierdzić finalną regresję, walidację skilli, build obu hostów i `graph_check` po
  końcowym audycie zmian A04. (DEV: 72 testy, pięć skilli, dry-run 20 skilli/11 agentów, build i
  `graph_check` source/Claude/Codex przeszły.)
- [x] Audyt pre-commit A03/A04: wyniki metadata i citation są związane z dokładnym scoped input,
  domain authority wymaga zatwierdzonego seed ID, nieznany typ publikacji pozostaje `unknown`, a
  maturity signal wymaga właściwego rodzaju evidence. Pakiet ukierunkowany: 44 testy; packaging:
  6 testów; sześć współdzielonych skilli i source `graph_check` przeszły.
- [ ] Przedstawić ukończony pionowy wycinek do akceptacji przed DEV A11.

### TEST 5, G02-A04 Recent Developments

Checkbox wolno zaznaczyć wyłącznie po wykonaniu scenariusza w docelowym środowisku testowym.
Dzisiejsze testy DEV nie zastępują live smoke ani forward testu agenta na rzeczywistym hoście.

#### A. Intake, przygotowanie i regresja

- [x] Użyć świeżej kopii repo, nowego środowiska z `requirements-dev.txt` i osobnego
  `EMAGENTS_HOME` przeznaczonego do późniejszego skanu sekretów.
- [x] Potwierdzić, że intake `recency_window_years` przechodzi bez zmiany przez
  `research_planner_input@1` do `research_plan@1`; brak lub wartość niepoprawna jest blokowana.
- [x] `research_recent_prepare` dla topicu z rolą `current` zwraca `recent_research_input@1`; dla
  topicu bez tej roli albo przy wyłączonym recent discovery zwraca jawny, bezpieczny skip.
- [x] Dla okna pięciu lat i roku uruchomienia 2026 przygotowane lata wynoszą dokładnie 2022–2026.
  Jawne ograniczenia planu mogą okno zawęzić, lecz nigdy rozszerzyć.
- [x] Scoped input zawiera wyłącznie approved topic, reviewed A02, zweryfikowane seedy, role,
  coverage, limity i publiczne capabilities. Nie zawiera e-maila ani wartości kluczy.
- [x] `python -m pytest tests/test_g02_recent.py tests/test_mcp_server.py -q` przechodzi, a MCP
  `0.6.0` raportuje dokładnie 22 operacje.
- [x] `python -m pytest -q` przechodzi bez regresji A01–A03, A10, providerów i packagingu.

#### B. QueryPlan, operacje i semantyka recent artifact

- [x] Każda trasa `query_plan@1` ma dokładnie zamrożone `year_from` i `year_to`, zachowane
  exclusions, zatwierdzone terminy i coverage. Poszerzenie choć jednej daty jest odrzucane.
- [x] Przy zatwierdzonym `preprint` istnieje co najmniej jedna trasa preprint. arXiv nie jest
  autoryzowany, jeżeli topic nie dopuszcza preprintów.
- [x] `research_metadata_search` z `recent_input` działa dla OpenAlex, Semantic Scholar i arXiv,
  zwraca `recent_metadata` oraz zapisuje także zero results, partial i failed.
- [x] Opcjonalny `research_citation_expand` przyjmuje `discovery_input: recent_input`, tylko
  zweryfikowany seed i jeden hop, a zwrócone rekordy mają pulę `recent_expansion`.
- [x] Finalizacja odrzuca rekord spoza okna, bez roku, zmieniony względem A02/tool result, brak
  operation ref, niepełny log, niezgodne provider issues i przekroczony candidate limit.
- [x] Każdy użyty `literature_tool_result@1` ma `request.scope` zgodny z task, topic, ResearchPlan
  i reviewed A02 ref. Wynik z innego scope jest blokowany.
- [x] Każdy kandydat ma dokładnie jedną `recent_annotation`; recency basis dokładnie odpowiada
  rekordowi i oknu, a role wskazują zatwierdzony topic, claim IDs i coverage.
- [x] Rekord z `work_type: preprint` otrzymuje status preprint. Znany opublikowany typ otrzymuje
  `published_unknown`, a brak rozpoznanego typu pozostaje `unknown`; venue, article ani review nie
  są samodzielnym dowodem peer review.
- [x] Każdy maturity signal jest weryfikowalny w metadanych, abstrakcie lub citation operation.
  Fałszywy citation count, velocity, review type, multi-provider signal albo niedopasowany evidence
  source jest odrzucany.
- [x] `core_update` wymaga `established`, co najmniej dwóch sygnałów, abstraktu i braku statusu
  preprint. Słabszy wynik jest `optional_trend` albo `watch`; `quality_status` pozostaje
  `not_assessed`.
- [x] Coverage, remaining units, provider issues i stop reason są wzajemnie zgodne. Rewizja
  zwiększa wersję i zmienia wyłącznie pola wskazane przez findings.
- [x] `research_recent_review_task` tworzy ważny `review_task@1`, profil `recent_developments`,
  kryteria `RD-01` do `RD-06` i ref wyłącznie do zapisanego artefaktu A04.

#### C. Live API i zachowanie operacyjne

- [x] Preflight potwierdza e-mail, klucz OpenAlex i opcjonalny klucz Semantic Scholar bez
  drukowania wartości. Brak wymaganego sekretu kończy się przed requestem.
- [x] Live OpenAlex wykonuje małe zapytanie w dokładnym oknie i zwraca 1–2 rekordy z rokiem
  mieszczącym się w nim; wynik i raw-response ref przechodzą kontrakty.
- [x] Live Semantic Scholar wykonuje małe zapytanie recent. Brak klucza, quota albo 429 jest jawnie
  raportowany i nie staje się pozornym success.
- [x] Live arXiv wykonuje małe zapytanie preprint z User-Agent i rate limit. Rekord spoza okna nie
  przechodzi do artefaktu nawet wtedy, gdy provider go zwróci.
- [x] Dla stabilnego verified seeda wykonać jedną dozwoloną relację live. Brak relacji albo ID
  providera daje kontrolowane `unavailable`, bez wyszukiwania po podobnym tytule.
- [x] Powtórzone zapytanie potwierdza cache hit. Timeout, 429/5xx, uszkodzony cache i partial
  response uruchamiają ograniczony retry i prawidłowy failure path.
- [x] Skan całego `EMAGENTS_HOME`, stdout i stderr nie znajduje e-maila ani wartości kluczy.

#### D. Forward test Claude i Codex

- [ ] Claude wykonuje prepare, tworzy query plan, wywołuje wyłącznie dozwolone operacje, buduje  — `⏳ KOŃCOWY` (forward na realnym hoście / test integracyjny batcha; patrz 08 Runda 7)
  adnotacje, finalizuje i tworzy review task bez WebSearch, WebFetch, direct HTTP i pobierania PDF.
- [ ] Ten sam scenariusz przechodzi na Codex z identyczną semantyką kontraktów i proweniencji.  — `⏳ KOŃCOWY` (forward na realnym hoście / test integracyjny batcha; patrz 08 Runda 7)
- [ ] Scenariusz z nowym preprintem kończy się `optional_trend` albo `watch`, bez twierdzenia o  — `⏳ KOŃCOWY` (forward na realnym hoście / test integracyjny batcha; patrz 08 Runda 7)
  konsensusie i bez jakościowej oceny publikacji.
- [ ] Scenariusz z dojrzałym review może otrzymać `core_update` wyłącznie przy co najmniej dwóch  — `⏳ KOŃCOWY` (forward na realnym hoście / test integracyjny batcha; patrz 08 Runda 7)
  obserwowalnych sygnałach i abstrakcie. Sama data lub wysoki citation count nie wystarcza.
- [ ] Provider issue albo brak coverage daje `degraded`; brak prawdziwego executora hosta daje  — `⏳ KOŃCOWY` (forward na realnym hoście / test integracyjny batcha; patrz 08 Runda 7)
  jawny failure i nie jest zaliczany jako forward test.
- [ ] G02-A10 zatwierdza poprawny wynik, kieruje naruszenia `RD-*` do REVISE/BLOCKED, a A04 zmienia  — `⏳ KOŃCOWY` (forward na realnym hoście / test integracyjny batcha; patrz 08 Runda 7)
  tylko wskazane pola.

#### E. Packaging i bramka wejścia do DEV A11

- [x] `python scripts/install_plugin.py --all --dry-run` raportuje 20 skilli i 11 agentów bez
  mutacji źródeł lub istniejącego `dist`.
- [x] `python scripts/build-plugin.py --host all` buduje oba bundle z `recent.py`, nowym kontraktem,
  agentem A04, wspólnymi skillami i 22 operacjami MCP. Mocki i testy pozostają poza bundlem.
- [x] `graph_check` przechodzi dla source, Claude i Codex. Bundle nie zawiera `.emagents`, lokalnej
  konfiguracji, cache, raw responses, `__pycache__` ani `.pyc`.
- [x] Wynik TEST 5 dopisać jako nową rundę na górze `08_Log_wynikow_TEST.md`, osobno oznaczając
  deterministyczne, live API, forward Claude, forward Codex i packaging.
- [ ] Po zaliczeniu testów i akceptacji właściciela wykonać osobny commit A04 i rozpocząć DEV A11.

### DEV 6, G02-A11 Market Cases

- [x] Zamrożono `market_case_research_input@1`, web routes, `web_case_tool_result@1` i wariant
  `market_cases` kontraktu `candidate_sources@1` z osobnymi adnotacjami semantycznymi.
- [x] Zaimplementowano `research_web_case_search` z abstrakcją providerów: Tavily oraz kontrolowany
  darmowy adapter SearXNG. Agent nie otrzymuje ogólnego narzędzia przeglądarkowego.
- [x] Dla SearXNG dopuszczono wyłącznie instancję wskazaną przez administratora poza publicznym
  wywołaniem MCP, format JSON,
  ścisły budżet zapytań, cache, timeout, rate limit, tier-domain policy, blokadę redirectów poza
  autoryzowaną ścieżkę i pełną provenance. Publiczne, losowo wybierane instancje są zabronione.
- [x] Zaimplementowano tryby `tavily`, `searxng` i `auto_budgeted`; w ostatnim trybie SearXNG służy
  do taniego discovery, a Tavily do uzupełnienia braków, ważnych tras i ekstrakcji po bramce.
- [x] Zaimplementowano `research_web_case_extract` wyłącznie dla case'ów zatwierdzonych przez
  człowieka, wraz z ochroną przed prompt injection i limitami treści.
- [x] Dodano profil `market_cases`, materiality gate, source tiers, failure paths, resume, mocki obu
  providerów, testy redakcji sekretów i build.
- [x] Zsynchronizowano agenta, skille i adaptery Claude/Codex, pięć operacji MCP, graf, manifest,
  packaging, README oraz dokumenty 00–08. Pełne wykonanie testów pozostaje poza sesją DEV.
- [x] Akceptacja właściciela pionowego wycinka A11 przed rozpoczęciem DEV A05, potwierdzona
  2026-06-22.

#### Minimalne kontrole DEV A11, 2026-06-22

- [x] AST dziesięciu zmienionych plików Python, parse 49 plików JSON, odczyt ośmiu zmienionych
  kontraktów oraz walidacja schematów pięciu mocków A11: PASS.
- [x] Walidacja przykładowej konfiguracji providerów, manifestu, 20 skilli i adapterów obu hostów:
  PASS; inventory wynosi 11 agentów i 20 skilli.
- [x] Statyczny `graph_check`: PASS dla source; MCP `0.7.0` ma 27 operacji, a pięć publicznych
  operacji A11 nie przyjmuje ścieżki konfiguracji.
- [x] `git diff --check` i skan prywatnego e-maila oraz kluczy Tavily: PASS.
- [ ] `pytest`, build bundle, live API i forward Claude/Codex nie były uruchamiane w DEV.

### TEST 6, G02-A11 Market Cases

Wszystkie poniższe scenariusze pozostają niewykonane do osobnego środowiska TEST. Krótkie kontrole
DEV potwierdzają wyłącznie składnię i spójność statyczną, więc nie zaznaczają checkboxów TEST.

#### A. Kontrakty, scoped input i przygotowanie

- [x] Schematy `market_case_research_input@1`, `web_case_tool_result@1`,
  `web_case_extract_result@1`, `human_source_selection@1` oraz `candidate_sources@1` parsują się i
  przechodzą pozytywne oraz negatywne fixtures.
- [x] `research_market_cases_prepare` hydratuje dokładny reviewed ResearchPlan i A02 ref, wybiera
  jeden topic oraz zachowuje task ID i wersje obu artefaktów.
- [x] Scoped input zawiera wyłącznie topic, claim IDs, traceable market-case needs, role, coverage,
  limity, tier policy, provider mode, secret-free capabilities i język wyjścia.
- [x] Scoped input nie zawiera całego intake, rekordów A02, prywatnego e-maila, kluczy, endpointu
  SearXNG, cache paths ani nieautoryzowanych artefaktów.
- [x] Każdy need ma jednoznaczny `need_id`, coverage i origin do zatwierdzonego claimu, drivera,
  update need albo coverage; sfałszowany scope, wersja lub A02 ref kończy się jawnie.
- [ ] Brak zgody na przykłady dydaktyczne daje kontrolowany skip, brak gotowego providera daje
  jawny failure, a revision bez poprzedniego artefaktu jest odrzucana.

#### B. QueryPlan i operacje providerów offline

- [x] QueryPlan ma core, complementary i qualifying/critical route zgodnie z ResearchPlan;
  wszystkie terminy mają approved origin i generated-term basis.
- [x] Każda trasa zachowuje provider mode, filtry, coverage, limity oraz domeny wybrane wyłącznie z
  administrator tier policy. Provider syntax, dodatkowa domena i endpoint od modelu są odrzucane.
- [x] Publiczne schema pięciu operacji MCP A11 nie zawierają parametru `config`; profil runtime jest
  wybierany wyłącznie przez administratora.
- [x] Tavily i SearXNG fixtures zwracają niezmienione, poprawne `source_record@1` typu
  `market_case`, z URL, datą gdy dostarczona, tierem, raw ref, query ID i provenance.
- [x] `auto_budgeted` używa gotowego SearXNG do discovery i Tavily do kontrolowanego uzupełnienia;
  tryby pojedynczego providera nie uruchamiają drugiego adaptera.
- [ ] Zero results daje `ok`; disabled, missing key/endpoint, timeout, DNS, 429, 5xx, invalid JSON,
  zły content type i zbyt duża odpowiedź dają właściwe `partial`, `unavailable` albo `failed`.
- [ ] Cache hit nie zużywa kolejnego budżetu; limity wspólne, per-provider i rate limit są
  egzekwowane. Retry respektuje `Retry-After` i nie przekracza konfiguracji.
- [ ] Redirect poza origin lub na inną ścieżkę operacji jest blokowany; SearXNG może użyć wyłącznie  — `❌ FAIL` (Runda 8): redirect zablokowany (status `partial`, treść nieużyta) ale issue-code `unsafe_searxng_endpoint`, nie `cross_origin_redirect_blocked`. DEV 2026-06-23: kolejność walidacji poprawiona wspólnym `_validate_redirect_target` dla transportu, cache i ścieżki produkcyjnej; wymagany rerun TEST przed zaznaczeniem.
  jawnie zatwierdzonego endpointu, bez credentials w URL i bez losowej publicznej instancji.
- [x] Wyniki z innego tasku, topicu, ResearchPlan, A02 ref, route, query albo provider mode nie mogą
  zostać użyte przy finalizacji A11.

#### C. Finalizacja MarketCaseCandidateSources

- [x] Każdy candidate jest identyczny z rekordem w zapisanym `web_case_tool_result@1`; mutacja
  tytułu, daty, URL, tieru, provenance albo null metadata jest odrzucana.
- [x] Każdy candidate ma dokładnie jedną adnotację, a role, case identity, evidence type, source
  assessment, materiality, market fact i coverage cytują obserwacje title/snippet/date/URL.
- [x] Fakt rynkowy pozostaje oddzielony od interpretacji dydaktycznej, która mapuje się do
  zatwierdzonego topicu lub claimu. Agent nie tworzy publikacji naukowej ani DOI.
- [ ] Tier-3 bez potwierdzenia pozostaje `weak_signal`; wyższy tier lub poprawna korelacja są
  odnotowane osobno. Anegdota nie może wejść jako documented case.
- [ ] Materiality wymaga obserwowalnej skali, realnej konsekwencji i potwierdzenia tier 1/2;
  scientific quality pozostaje `not_assessed`, a DOI `absent`.
- [ ] Starszy case ma jawny historical/unknown regime context i nie może zostać oznaczony jako
  current regime bez podstawy.
- [ ] Coverage liczy wyłącznie case'y przechodzące materiality; remaining units, provider issues i
  stop reason są wyliczone zgodnie z rzeczywistym wynikiem.
- [x] `completed` z luką lub provider issue, fałszywy `candidate_limit`, niepoprawny revision target
  oraz zmiana pola poza findings reviewera są odrzucane.
- [x] Finalizacja zapisuje wersjonowany artefakt, zwraca `ok` przy pełnym coverage lub `degraded`
  przy użytecznej puli z jawnymi brakami, bez fałszywego statusu sukcesu.

#### D. Review G02-A10

- [x] `research_market_cases_review_task` tworzy jeden `review_task@1` o profilu `market_cases`,
  producencie `g02-a11-market-cases` i dokładnie jednym artefakcie.
- [ ] Kryteria MC-01–MC-06, wymagania dowodowe, prohibited behaviors i severity rules są kompletne,
  zgodne między agentem, skillem reviewera, runtime i dokumentacją.
- [ ] G02-A10 zatwierdza poprawny artefakt, kieruje naprawialne błędy do REVISE, a scope mismatch,
  zmieniony record, fabrykację, anegdotę lub ekstrakcję przed bramką do BLOCKED.
- [x] Kolejna rewizja zwiększa `artifact_version`, zachowuje nieobjęte pola i używa poprzedniej
  decyzji oraz producer revision response zgodnie z kontraktem reviewera.

#### E. Ekstrakcja po Human Source Selection Gate

Ta sekcja sprawdza egzekwowanie już zapisanego `human_source_selection@1`. Rzeczywiste pokazanie
dokumentu użytkownikowi, parser odpowiedzi i osobne finalne potwierdzenie są testowane w TEST 7F.

- [x] Brak zapisanego `human_source_selection@1`, status inny niż `approved`, brak finalnego
  potwierdzenia albo source ID poza `approved_for_download` blokuje request przed Tavily.
- [ ] Selection i market candidates muszą mieć ten sam task; candidate index ref musi być czytelny,
  source ID ma rozwiązać się dokładnie raz w indeksie i puli, a URL pochodzi wyłącznie z zapisanego
  rekordu i musi być credential-free HTTPS.
- [ ] Duplikat decyzji source ID, source wykluczony albo nie-market-case są odrzucane.
- [x] Tavily extraction zwraca dokładnie zatwierdzony URL, ogranicza rozmiar, zapisuje hash, raw ref,
  request ID, truncation i `content_boundary: untrusted_external_research`.
- [x] Pełna treść nie występuje inline w `web_case_extract_result@1`; prompt-injection flags i zakaz
  forwardowania tekstu downstream są zachowane.
- [ ] G02-A07 otrzymuje wyłącznie zatwierdzony descriptor i tworzy kompaktową evidence card z
  odrębnym faktem oraz interpretacją. Odrzucone case'y nie są ekstrahowane.

#### F. Live API i bezpieczeństwo sekretów

- [x] Opt-in live Tavily search zwraca realne, datowane i identyfikowalne case'y z allowlisted
  domen, poprawnym provenance i bez raw page extraction podczas discovery.  — Runda 8 PASS: 6 case'ów (risk.net itd.), `source_record@1` ważny, `abstract_source: search_snippet`, `raw_page_ref: None`, cache hit na powtórzeniu.
- [ ] Opt-in live Tavily extraction działa tylko po finalnej bramce i zachowuje dokładny URL oraz  — Runda 8: nie wykonano live (wymaga pełnego łańcucha A11→A05→human gate); egzekwowanie bramki + bounded untrusted zielone offline.
  bounded untrusted artifact. Koszt i liczba wywołań mieszczą się w konfiguracji.
- [ ] Opt-in live skonfigurowanego SearXNG używa JSON API tej jednej instancji; brak instancji daje  — Runda 8: nie wykonano (brak skonfigurowanej instancji SearXNG).
  jawny status i nie uruchamia wyszukiwania publicznego.
- [x] Skan repo, logów, cache, raw responses, MCP output i artefaktów nie znajduje wartości
  `TAVILY_API_KEY`, prywatnego e-maila ani innych sekretów.  — Runda 8: skan `EMAGENTS_HOME` 0 wycieków klucza i e-maila.
- [ ] Network failure, rate limit i częściowa dostępność providerów zachowują audytowalny wynik i
  nie uruchamiają WebSearch, WebFetch, shell HTTP ani przeglądarki zastępczej.

#### G. Forward Claude i Codex

- [ ] Claude wykonuje prepare, buduje wyłącznie zatwierdzone trasy, korzysta z MCP, zachowuje rekordy
  providerów i tworzy ugruntowane adnotacje bez bezpośredniego web access. — `⏳ KOŃCOWY`
- [ ] Ten sam scenariusz przechodzi na Codex z identycznymi kontraktami, scope, provider issues,
  materiality i coverage. — `⏳ KOŃCOWY`
- [ ] Oba hosty rozróżniają realny case, weak signal i anegdotę, nie przypisują publication date
  jako event date bez podstawy oraz nie oceniają scientific quality. — `⏳ KOŃCOWY`
- [ ] Provider degradation daje `degraded`, brak operacji MCP daje jawny external dependency status,
  a żaden host nie używa własnego browse jako fallback. — `⏳ KOŃCOWY`
- [ ] Prompt injection w snippet lub zatwierdzonej stronie pozostaje danymi i nie zmienia workflow,
  konfiguracji, decyzji bramki ani treści innych artefaktów. — `⏳ KOŃCOWY`

#### H. Packaging i integracja A02–A05

- [x] Inventory zawiera 11 agentów i 20 skilli; oba bundle zawierają agenta A11 zgodnie z polityką
  hosta, dwa skille z właściwymi adapterami, cztery nowe kontrakty i oba moduły runtime.  — Runda 8: dry-run `Validated 20 skills and 11 agents`, build obu bundli OK.
- [ ] MCP raportuje bieżącą wersję `0.9.0` i dokładnie 39 operacji, w tym pięć A11, trzy A05 i dziewięć operacji bramki/A06; MCP **PASS** w Rundzie 8. `graph_check` pozostał **FAIL** na source/Claude/Codex przez brak `retrieval_directory@1`; DEV 2026-06-23 dodał kontrakt i typed descriptor, wymagany rerun TEST.
  source, Claude i Codex przechodzą `graph_check`.
- [x] Bundle nie zawierają mocków, testów, `.emagents`, cache, raw responses, runtime config,
  `__pycache__`, `.pyc` ani sekretów. Build i dry-run instalacji nie mutują źródeł.  — Runda 8: higiena bundla czysta, dry-run bez mutacji.
- [ ] Graf wiąże A11 z `market_case_research_input@1`, `candidate_sources@1`, profilem
  `market_cases` oraz pozycją po A04 i przed A05; scheduler może pozostać sekwencyjny.
- [ ] Reviewed A02, A03, A04 i A11 trafiają do A05 bez cross-stream deduplikacji przed A05; pełny
  przepływ i SEARCH_MORE zostaną sprawdzone po implementacji A05. — `⏳ KOŃCOWY`
- [x] Wyniki TEST 6 należy dopisać jako nową rundę na górze `08_Log_wynikow_TEST.md`, bez zmiany
  historycznej Rundy 7; zaznaczyć tylko scenariusze faktycznie wykonane i zaliczone.  — Runda 8 dopisana.

#### I. Konkretny protokół wykonania TEST 6

1. Uruchomić najpierw offline `tests/test_g02_market_cases.py`, następnie pełną regresję. Zachować
   liczbę PASS/FAIL, wersję Pythona, commit i konfigurację provider mode bez wartości sekretów.
2. Wykonać macierz negatywną z sekcji A–E, korzystając z
   `mocks/g02/market_research_plan.json`, `mocks/g02/market_domain_candidate_sources.json`,
   `mocks/g02/market_case_source_record.json` oraz fixtures Tavily/SearXNG. Każda mutacja scope,
   rekordu, tieru, faktu lub decyzji bramki ma zakończyć się oczekiwanym statusem i issue code.
3. Wykonać osobno live discovery Tavily, live discovery skonfigurowanego SearXNG i gated Tavily
   extraction. Discovery nie może zapisać treści strony. Extraction musi zostać sprawdzona raz bez
   zatwierdzenia (brak requestu) i raz po zatwierdzeniu dokładnego source ID (jeden bounded request).
4. Wykonać scenariusze forward Claude i Codex na tym samym planie i porównać task, topic, coverage,
   source IDs, materiality, tier, fakt rynkowy, interpretację oraz status. Różnice stylistyczne są
   dopuszczalne, różnice kontraktowe lub dowodowe oznaczają FAIL.
5. Zbudować oba bundle, wykonać `graph_check` dla source i obu hostów, dry-run instalacji oraz skan
   repo, runtime artifacts, cache i logów pod kątem sekretów i prywatnego e-maila.
6. Zapisać w `docs/08_Log_wynikow_TEST.md` osobne wyniki dla offline, live, forward, bezpieczeństwa
   i packagingu. BLOCKED nie może zostać przepisane jako PASS.

Warunek zamknięcia TEST 6: A11 znajduje realny, udokumentowany case, zachowuje fakt oddzielnie od
interpretacji, nie pobiera strony podczas discovery i pozwala na ekstrakcję wyłącznie po finalnej
decyzji człowieka dotyczącej dokładnego source ID.

### DEV 7, G02-A05 Candidate Source Index

- [x] Zamrożono `candidate_index_input@1`, który przyjmuje wyłącznie dokładny ResearchPlan i
  artefakty A02, A03, A04 lub A11 związane z decyzją A10 `APPROVED`, oraz wyjście
  `candidate_source_index@1` z odnośnikiem do `candidate_source_review.md`.
- [x] Zaimplementowano konserwatywną deduplikację, role, jawne składowe rankingu, candidate
  coverage, display/reserve limits, adnotacje i stabilne cross-references przy wznowieniu.
- [x] Zachowano oddzielenie source tier case'ów, canonicality, maturity, access i
  `scientific_quality: not_assessed`; A05 nie pobiera treści i nie zapisuje decyzji za użytkownika.
- [x] Dodano trzy operacje MCP, profil `candidate_index`, refs rozszerzeń wyszukiwania, resume,
  selection-profile mock i testy kontraktowe/offline A05.
- [x] Generator tworzy audytowalny `candidate_source_review.md` w języku wyjściowym z opisem treści,
  podstawą opisu, ograniczeniami, coverage, instrukcją akcji i kopiowalnym szablonem bramki.

#### Minimalne kontrole DEV A05, 2026-06-22

- [x] AST wszystkich 40 plików Python, parse 52 plików JSON oraz odczyt kontraktów
  `candidate_index_input@1` 1.0 i `candidate_source_index@1` 1.1: PASS.
- [x] Walidacja manifestu, 11 agentów, 20 skilli i wymaganych adapterów oraz statyczny
  `graph_check` dla source: PASS.
- [x] `git diff --check`, zgodność inventory i dispatch MCP `0.8.0` / 30 operacji oraz skan zmian
  pod kątem prywatnego e-maila i kluczy: PASS.
- [ ] `pytest`, build bundle, live API i forward Claude/Codex nie są uruchamiane w DEV.

### TEST 7, G02-A05 Candidate Source Index i Human Source Selection Gate

Wszystkie checkboxy TEST 7 pozostają odznaczone do wykonania w osobnym środowisku. Kontrole DEV
nie potwierdzają zachowania agenta, parsera bramki ani interakcji z użytkownikiem.

#### A. Kontrakty i reviewed-only scoped input

- [x] `candidate_index_input@1` i `candidate_source_index@1` przechodzą pozytywne oraz negatywne
  fixtures, a `candidate_source_index@1` zachowuje kompatybilną listę `sources` wymaganą przez A11.
- [x] `research_candidate_index_prepare` przyjmuje dokładny ResearchPlan oraz pary artifact/ref
  review dla A02, A03, A04 i A11. Każda decyzja ma `APPROVED`, pustą listę findings i zgodne task,
  producer, profile, artifact ref oraz artifact version.
- [x] `REVISE`, `BLOCKED`, findings przy `APPROVED`, zły producer/profile, inny task, plan, topic,
  ref lub version są odrzucane przed zbudowaniem indeksu.
- [ ] Brak oczekiwanego reviewed streamu daje jawny `missing_reviewed_stream` i pozwala utworzyć
  `degraded` indeks, o ile pozostałe dane są użyteczne. Duplikat stream/topic jest odrzucany.
- [ ] Scoped input zawiera tylko topic, coverage, role, rekordy, reviewed adnotacje, politykę wyboru,
  język, upstream descriptors i refs rozszerzeń. Nie zawiera query plans, operation logs, pełnych
  review decisions, surowych odpowiedzi providerów, konfiguracji, cache paths ani sekretów.
- [ ] `previous_index_ref` musi wskazywać poprawny indeks tego samego tasku. Niepoprawny ref,
  traversal, obcy task lub błędny kontrakt kończą się jawnym failure.

#### B. Normalizacja, deduplikacja, provenance i resume

- [x] Identyczny DOI scala rekordy A02/A03/A04; testy osobno obejmują arXiv ID, ISBN, Semantic
  Scholar ID, OpenAlex ID oraz konserwatywny fallback title-year-first-author bez stabilnego ID.
- [ ] Różne wydania, tłumaczenia, rozdziały i preprint/version of record pozostają rozłączne, jeżeli
  nie ma jednoznacznej reguły równoważności. Konflikt trafia do `ambiguous_duplicate_groups`.
- [ ] Market case scala się wyłącznie po dokładnym canonical URL lub stabilnym ID. Dwie strony
  opisujące to samo zdarzenie pozostają oddzielnymi źródłami i mogą stanowić corroboration.
- [ ] Każde scalenie zapisuje typ i wartość klucza, retained source ID, occurrences, merged IDs oraz
  regułę. `provenance_records` zachowuje providerów i źródłowe rekordy ze wszystkich streamów.
- [ ] Jeden source ID nie może rozwiązywać się do dwóch grup. Brak source ID, tytułu albo source API
  kończy się failure zamiast wygenerowania zastępczej tożsamości.
- [ ] Resume z poprzednim indeksem zachowuje source ID dla tej samej grupy, przelicza ranking i
  coverage po rozszerzeniu wyszukiwania oraz tworzy nową artifact version bez mutacji starej.

#### C. Role, ranking, coverage i limity prezentacji

- [ ] Role canonical, current, survey, didactic, qualifying/critical i applied_case pochodzą z
  reviewed adnotacji lub jawnego stream fallback. Role nie są traktowane jako jakość ani stance.
- [ ] Ranking pokazuje wszystkie komponenty i wagi: coverage contribution, role fit, topic
  relevance, access, canonical signal, recency signal, market-case value i redundancy penalty.
- [ ] Remis jest deterministyczny po stable source ID. Zmiana wagi zmienia score w sposób
  odtwarzalny, a brak sygnału nie powoduje wygenerowania citation count, maturity lub quality.
- [ ] Source tier market case, canonicality, maturity, access i `scientific_quality: not_assessed`
  pozostają osobnymi polami. Tier 1/2 nie staje się oceną jakości naukowej.
- [ ] Coverage jest role-aware. `applied_case` może realizować dydaktyczny market-case requirement,
  ale samo mapowanie coverage bez wymaganej roli nie wystarcza do statusu `covered`.
- [ ] `covered`, `partial` i `missing` odpowiadają minimum_sources. Display, reserve i per-topic limit
  są przestrzegane, a obowiązkowa luka nie znika wskutek limitu ani wysokiego łącznego score.
- [ ] DOWNLOAD, LIBRARY, CITATION i RESERVE są wyłącznie rekomendacjami A05. Indeks nie zawiera
  decyzji człowieka, final confirmation ani automatycznego EXCLUDE.

#### D. Opisy treści i `candidate_source_review.md`

- [x] Artykuł z abstraktem otrzymuje krótki `content_summary`, `description_basis: abstract` i
  bounded `basis_excerpt`, który jest rzeczywistym fragmentem dostępnego abstraktu.
- [ ] Publikacja bez abstraktu otrzymuje `description_basis: metadata` i jawny komunikat, że opis
  nie streszcza zawartości publikacji. Tytuł, venue i rok nie są rozwijane w zmyślone findings.
- [x] Market case otrzymuje `description_basis: market_case_annotation`; opis łączy reviewed
  `market_fact.statement` i `didactic_interpretation.mechanism`, zachowując ich rozdzielenie w A11.
- [ ] Karta market case pokazuje tier i regime limitation oraz informuje, że pełna strona nie została
  jeszcze wyodrębniona. Tekst strony, raw response i instrukcje z treści zewnętrznej nie trafiają do
  dokumentu wyboru.
- [ ] Każda prezentowana karta pokazuje citation, source ID, typ, role, skrót treści, relevance do
  topic/coverage, podstawę opisu, access, limitations i rekomendowaną akcję.
- [ ] Dokument używa `output_language`, wskazuje machine-readable index ref i zawiera coverage,
  źródła prezentowane, rezerwę, luki oraz kompletny szablon DOWNLOAD, LIBRARY, CITATION, RESERVE,
  EXCLUDE, SEARCH_MORE i FINAL_CONFIRMATION.
- [ ] Tekst z abstraktu lub market snippet zawierający prompt injection pozostaje danymi i nie może
  zmienić rankingu, konfiguracji, instrukcji bramki, source IDs ani innych artefaktów.

#### E. Finalizacja, status i review G02-A10

- [x] `research_candidate_index_finalize` zapisuje wersjonowany JSON i Markdown z działającymi
  cross-references. Brak możliwości zapisania lub odczytania któregokolwiek artefaktu daje failure.
- [ ] Pełne mandatory coverage bez upstream issues daje `ok`; mandatory gap albo brak oczekiwanego
  streamu daje `degraded`, metrics i resume token. Błędny indeks nie daje pozornego sukcesu.
- [x] `research_candidate_index_review_task` tworzy jeden review task profilu `candidate_index`,
  producenta A05 i dokładnie jednego indeksu, którego document ref jest czytelny i kompletny.
- [ ] Kryteria CI-01–CI-08, CI-E01–CI-E03, prohibited behaviors i severity rules są identyczne w
  agencie, runtime, skillu reviewera i dokumentacji.
- [ ] A10 zatwierdza poprawny indeks, kieruje naprawialny ranking/coverage/opis do REVISE, a
  unreviewed input, utratę identity, sfabrykowany opis lub zapisaną decyzję człowieka do BLOCKED.
- [ ] Rewizja zwiększa artifact version, zachowuje untargeted fields i wiąże previous decision oraz
  producer revision response zgodnie z uniwersalnym kontraktem reviewera.

#### F. Rzeczywista interakcja Human Source Selection Gate

- [ ] Po APPROVED review A05 orkiestrator pokazuje użytkownikowi krótkie podsumowanie, liczbę źródeł
  i luk oraz klikalną ścieżkę do `candidate_source_review.md`, po czym prosi o decyzje per source.
- [ ] Orkiestrator przyjmuje copyable template oraz zwykły język, mapuje wyłącznie istniejące source
  IDs i odrzuca ID obce, duplikaty akcji, sprzeczne akcje i niepełny zakres decyzji.
- [ ] Po parsowaniu pokazuje użytkownikowi zestaw DOWNLOAD, LIBRARY, CITATION, RESERVE, EXCLUDE i
  SEARCH_MORE oraz prosi o odrębne finalne potwierdzenie. Przed nim nic nie jest pobierane.
- [ ] `human_source_selection@1` ma poprawny task i candidate index ref, rozłączne akcje, status
  zgodny z decyzją i `final_confirmation: true` wyłącznie po odpowiedzi użytkownika.
- [ ] SEARCH_MORE bez claim/topic/coverage/roli jest odrzucane. Poprawne żądanie wraca do właściwego
  A02/A03/A04/A11, tworzy nowy reviewed A05 index i ponownie pyta człowieka.
- [ ] Mandatory coverage naruszone wyborem daje ostrzeżenie. Kontynuacja wymaga SEARCH_MORE albo
  jawnej coverage exception z powodem i finalnym potwierdzeniem.
- [ ] Status `cancelled` kończy ścieżkę bez pobierania. LIBRARY, CITATION, RESERVE i EXCLUDE nie są
  przekazywane jako zgoda na automatyczny download.
- [ ] Zatwierdzony market case może uruchomić gated A11 extraction, a zwykła publikacja przechodzi do
  A06. Po ekstrakcji A06 ma utworzyć czytelny Markdown zgodny z faktem i mechanizmem pokazanym
  wcześniej na karcie A05 oraz oddzielny JSON audytowy. Odrzucony source ID nie uruchamia żadnej
  operacji sieciowej ani nie tworzy żadnego z tych plików.

#### G. MCP, packaging i forward hosts

- [ ] MCP raportuje `0.9.0` i 39 operacji, w tym prepare, finalize i review task A05 oraz operacje A06. Publiczne schema  — MCP/parity **PASS** w Rundzie 8; `graph_check` **FAIL** przez brak kontraktu katalogu. DEV 2026-06-23 dodał `retrieval_directory@1`; wymagany rerun TEST.
  nie przyjmują filesystem base, sekretu ani konfiguracji providera od modelu.
- [ ] Graf wiąże A05 z `candidate_index_input@1`, `candidate_source_index@1`, profilem
  `candidate_index`, dokumentem Markdown i user-source-selection-gate przed A06.
- [x] Oba bundle zawierają runtime A05, dwa kontrakty, agenta, sześć wymaganych skilli i poprawne
  adaptery, bez mocków, tests, runtime artifacts, cache, `__pycache__`, `.pyc` i sekretów.  — Runda 8: higiena bundla czysta.
- [ ] Claude i Codex na tym samym scoped input tworzą zgodne source IDs, basis, coverage, action
  recommendations i strukturę dokumentu. Żaden host nie pobiera treści ani nie podejmuje decyzji.
- [ ] Missing MCP operation, nieczytelny artifact ref lub brak host executora daje jawny status
  dependency failure, bez lokalnego browse, pobierania lub cichego pominięcia bramki.

#### H. Konkretny protokół wykonania TEST 7

1. Uruchomić `tests/test_g02_candidate_index.py`, następnie pełną regresję repo. Zapisać commit,
   środowisko, liczbę PASS/FAIL oraz wszystkie warnings.
2. Wykonać macierz A–E na scholarly source z abstraktem, scholarly metadata-only, duplikacie DOI,
   konflikcie wersji i reviewed market case. Użyć jawnych fixtures, nie live web.
3. Wykonać interakcję F na Claude i Codex: jedna odpowiedź przez template, jedna zwykłym językiem,
   jedna SEARCH_MORE, jedna coverage exception, jedna cancel oraz jedna odmowa final confirmation.
4. Potwierdzić logiem operacji, że przed final confirmation liczba pobrań i ekstrakcji wynosi zero.
5. Wykonać build obu hostów, trzy `graph_check`, dry-run instalacji, skan sekretów i kontrolę higieny
   bundle. Następnie dopisać nową rundę w `docs/08_Log_wynikow_TEST.md`.

Warunek zamknięcia TEST 7: użytkownik widzi treściowe opisy obu typów źródeł, rozumie podstawę i
ograniczenia każdej karty, może wybrać lub rozszerzyć wyszukiwanie, a żaden download nie rozpoczyna
się bez pokazania sparsowanego podsumowania i osobnego finalnego potwierdzenia.

### Wspólny TEST batcha po DEV 7, osobne środowisko

> **Runda 10 (2026-06-23):** realny forward na hoście Codex przez `run-codex --gates prompt` wystartował w świeżym
> `EMAGENTS_HOME=/tmp/emagents-g02-final.CFEyii`. Przygotowanie PASS: provider status `ok:true` (Tavily-only,
> SearXNG disabled), build obu bundli, inventory 20 skilli/11 agentów, MCP 39 operacji, `graph_check`
> source/Claude/Codex PASS, skan sekretów 0. Forward FAIL/BLOCKED przed bramką: A01/A02/A03/A04 zapisały
> `status: failed` przez niepoprawne `envelope@1` z workerów Codex, A10 zwracał `BLOCKED`, a scheduler mimo
> tego kontynuował downstream (`g02_flow.py:418-465`). A11/A05/gate/A06 nieosiągnięte; nic forwardowego nie
> zaznaczono. Szczegóły i findingi F-B/F-C/F-D: 08 Runda 10.

> **DEV po Rundzie 10 (2026-06-23):** wdrożono naprawy F-A–F-D bez zmiany checkboxów TEST.
> Schematy MCP typują wejście Plannera i bezpiecznie rozróżniają object, JSON string, `artifact://`
> oraz ścieżkę. Codex używa `--output-schema`, ładuje jawnie skille agenta i zwraca dokładny envelope
> finalizera. Nowy `reviewed_flow.py` zatrzymuje run po invalid/failed/BLOCKED, hydratuje wyłącznie typed
> artefakt, buduje pełny `review_task@1`, wymaga dokładnej decyzji A10 i zapisuje audyt operacji MCP.
> Dodano `--through`, `--topic-id`, `research_run_report@1` oraz dwustopniową bramkę bez trybu auto.
> Lokalna regresja DEV: 115 PASS / 1 SKIP; realny Codex forward i osobna Runda 11 nadal wymagane.

> **DEV fast prototype po Rundzie 11 (2026-06-23):** ustawiono `fast` jako domyślny profil
> wykonania. A01 dostaje ograniczony scoped input (`max_topics: 2`,
> `candidate_limit_per_topic: 12`, target źródeł 8) i ma wybierać dwa topic groups według
> priorytetu driverów, centralności claimów/konceptów oraz wpływu na flow, a nie według kolejności
> wejścia. A02 otrzymał jawny flat-route `query_plan@1`, natychmiastowe przejście do
> `research_metadata_search` i budżet jednego primary providera per route z fallbackiem tylko przy
> luce. A10 jest obowiązkowy dla A01/A05/A06; A02/A03/A04/A11 dostają deterministyczny fast-track
> approval przy czystej finalizacji `ok`, a `degraded` nadal kieruje do A10. Nie zaznaczono nowych
> checkboxów TEST; wymagany osobny forward fast A01→A02 i następnie A01→A06.

> **Runda 9 (2026-06-23):** próba forward A01→A06 na hoście Claude (headless `claude -p` + MCP). Mechanizm i ścieżka ref-owa `prepare` potwierdzone, ale wykryto **systemowy blocker F-A** (`*_prepare.input` bez `type` → agent wysyła string JSON → serwer traktuje go jako ścieżkę pliku → crash; `research_server.py:90-98`). Podejście `claude -p` uznane za nieodpowiednie do testów (blokada bypass, globalny tool-deferral, koszt/kruchość). **Żaden węzeł forward nie domknięty — nic nie zaznaczono.** Forward/końcowe powtórzymy w środowisku **Codex** (`run-codex`). Szczegóły: 08 Runda 9.

- [ ] Pełna regresja A01, A02 i A10 oraz wszystkie nowe testy kontraktowe i offline.  — `⏳ KOŃCOWY` (forward na realnym hoście / test integracyjny batcha; patrz 08 Runda 7)
- [ ] Live smoke OpenAlex, Semantic Scholar, arXiv, Tavily i skonfigurowanej instancji SearXNG;  — `⏳ KOŃCOWY` (forward na realnym hoście / test integracyjny batcha; patrz 08 Runda 7)
  niedostępny darmowy provider ma dawać kontrolowany fallback albo jawny status częściowy.
- [ ] Przepływ A01 → A02 → A03 → A04 → A11 discovery → A05 z review każdego producenta.  — `⏳ KOŃCOWY` (forward na realnym hoście / test integracyjny batcha; patrz 08 Runda 7)
- [ ] Gated A11 extraction uruchamia się wyłącznie dla zatwierdzonych case'ów i zachowuje  — `⏳ KOŃCOWY` (forward na realnym hoście / test integracyjny batcha; patrz 08 Runda 7)
  identyfikowalność do A08/A09; odrzucone case'y nie są pobierane.
- [ ] Forward tests A01, A02, A03, A04, A11, A05 i A10 na Claude oraz Codex.  — `⏳ KOŃCOWY` (forward na realnym hoście / test integracyjny batcha; patrz 08 Runda 7)
- [ ] Failure paths: brak providera, 429/5xx, częściowe wyniki, zero results, SEARCH_MORE, rewizja,  — `⏳ KOŃCOWY` (forward na realnym hoście / test integracyjny batcha; patrz 08 Runda 7)
  resume, niezgodna wersja planu i konflikt deduplikacji.
- [ ] Build obu hostów, `graph_check`, skan sekretów, brak runtime artifacts i zgodność inventory.  — `⏳ KOŃCOWY` (forward na realnym hoście / test integracyjny batcha; patrz 08 Runda 7)
- [ ] Wyniki zapisać jako nową rundę na górze `08_Log_wynikow_TEST.md`; checkboxy zaznaczyć wyłącznie  — `⏳ KOŃCOWY` (forward na realnym hoście / test integracyjny batcha; patrz 08 Runda 7)
  dla faktycznie wykonanych scenariuszy.

### Bramka gotowości do DEV 8, G02-A06 Paper Retrieval

**Werdykt (historyczny, runda A05):** repo było gotowe do rozpoczęcia projektowania pionowego
wycinka A06. Poniższe pozycje stanowiły zakres DEV A06 i zostały zrealizowane w rundzie DEV 8;
aktualny status i pełna checklista TEST znajdują się w sekcji „DEV 8, G02-A06 Paper Retrieval
(zrealizowane)" poniżej.

#### Gotowe wejścia i decyzje projektowe

- [x] A05 produkuje stable source IDs, pełne `SourceRecord`, access summary, rekomendacje oraz
  `candidate_source_review.md` przed bramką człowieka.
- [x] Istnieje `human_source_selection@1` z akcjami, SEARCH_MORE, coverage exceptions i
  `final_confirmation`; A11 extraction już egzekwuje zatwierdzenie dokładnego market source ID.
- [x] Agent A06, trzy wymagane skille, pozycja grafu po user gate i wpisy manifestu istnieją.
- [x] Zasady prawne i bezpieczeństwa są zamrożone: tylko DOWNLOAD, legalne OA, brak institutional
  login, bounded redirects/size/retry, walidacja identity i brak scientific interpretation.
- [x] Akceptacja właściciela pionowego wycinka A05 przed rozpoczęciem DEV A06.

## DEV 8, G02-A06 Paper Retrieval (zrealizowane)

**Werdykt:** pionowy wycinek A06 jest zaimplementowany na poziomie DEV i zintegrowany z resztą
grafu (A05 → user-source-selection-gate → A06, gated A11 extraction dla market case). Pełne testy
funkcjonalne, live OA API i forward Claude/Codex pozostają do wykonania w osobnym środowisku i są
spisane niżej jako batch TEST. W DEV nie uruchamiano `pytest`, venv, live API ani buildów.

#### Zrealizowane elementy DEV A06

- [x] Zamrożony kontrakt `human_approved_source_set@1` oraz deterministyczny parser/generator z
  `human_source_selection@1`. Wymaga drugiego finalnego potwierdzenia i rozłącznych akcji; market
  case niesie `market_candidate_sources_ref` do reviewed artefaktu A11.
- [x] Wykonawcza bramka orkiestratora (`g02_flow`, `source_selection`): pokazuje dokument, przyjmuje
  template lub zwykły język, prezentuje sparsowane podsumowanie i dopiero potem zapisuje zatwierdzenie.
- [x] `retrieved_corpus@1` (x-version 1.2) z task, approved set ref, validated documents, market
  cases, unavailable, failed, skipped library/citation/reserve/excluded, attempt log, checksums,
  wersje, licencje, run directory ref, policy i retrieval summary.
- [x] `retrieval_directory@1` opisuje jeden katalog wyniku, jego manifest, katalog PDF, katalog
  market case oraz liczby zapisanych plików; envelope zwraca `artifact://` typed descriptor.
- [x] Zamrożony scoped input `retrieval_input@1` oraz kontrakty pośrednie `open_access_resolution@1`,
  `retrieved_file_candidate@1`, `validated_document@1` i `web_case_extract_result@1`.
- [x] Deterministyczne OA resolvers (record/arXiv, Unpaywall po DOI, opcjonalny CORE po DOI,
  DOAB jako katalog, OAPEN jako źródło bitstreamu PDF), downloader z kontrolą HTTPS, prywatnego DNS,
  redirectów, timeoutu, retry i limitu bajtów, walidator dokumentu (content-type, `%PDF`, identity,
  page count), storage corpus, deduplikacja po checksumie, resume, provider config i redakcja sekretów
  (`CORE_API_KEY`, kontakt Unpaywall tylko ze środowiska).
- [x] Dziewięć operacji MCP A06 (`research_source_selection_prepare/validate/finalize`,
  `research_retrieval_prepare`, `research_oa_resolve`, `research_document_retrieve`,
  `research_document_validate`, `research_retrieval_finalize`, `research_retrieval_review_task`)
  oraz `research_web_case_extract`; publiczne schema nie przyjmują config path ani sekretów od modelu.
- [x] Profil review `retrieved_corpus` i kryteria RT-01–RT-08. RT-08 wymaga gated market-case
  bundle z dokładnie jedną adnotacją A11, czytelnym Markdown, osobnym JSON, checksumami,
  provenance i `content_boundary: untrusted_external_research`.
- [x] Mocki: `retrieval_provider_config.json`, `sample_article.pdf`, `html_login_instead_of_pdf.html`,
  `market_case_source_record.json` oraz odpowiedzi `unpaywall`, `core_works`, `doab_search`,
  `oapen_search` i komplet book search/metadata/bitstreams dla DOAB/OAPEN.
- [x] Testy offline `tests/test_g02_retrieval.py` (przeznaczone do uruchomienia w środowisku TEST).
- [x] Każdy zatwierdzony market case jest pakietem dwóch plików: czytelnego
  `<source_id>.market-case.md` oraz audytowego `<source_id>.market-case.json`. Markdown korzysta z
  dokładnie jednej reviewed adnotacji A11 i zawiera fakt rynkowy, mechanizm dydaktyczny, ocenę
  źródła/materialności, kontekst reżimu, powiązania, treść pobraną po bramce i ostrzeżenie o
  niezaufanym materiale. Manifest ma osobne refs i SHA-256 obu plików.
- [x] Node A06 w grafie ma `input_contract: retrieval_input@1`, `review_profile: retrieved_corpus`
  i `produces`; manifest wymienia agenta i trzy skille; sekcja `retrieval` w przykładowej konfiguracji
  providerów; dokumentacja 02/03/04 opisuje A06.

#### Batch TEST A06 do osobnego środowiska

- [ ] Pełny offline `pytest`, w tym `tests/test_g02_retrieval.py`; brak regresji w A01–A05, A10, A11.  — Runda 8: `test_g02_retrieval` **6/6 PASS**, ale pełny pytest **93/95** (FAIL: A11 redirect = finding 1; `graph_check` = finding 2). DEV 2026-06-23 naprawił oba miejsca i rozszerzył test katalogu; wymagany pełny rerun.
- [x] Walidacja zmienionych JSON Schema A06 i przykładowej konfiguracji providerów z sekcją `retrieval`.  — Runda 8: kontrakty A06 walidują się w testach offline.
- [ ] `prepare` odrzuca brak finalnego potwierdzenia, niezgodny task/candidate index, przekroczony limit  — Runda 8 potwierdziła osobne finalne potwierdzenie. DEV 2026-06-23 dodał jawne liczniki PDF/market case i `test_prepare_enforces_human_download_count_and_admin_cap`; pełny zakres wymaga rerun.
  dokumentów oraz wyłączony profil retrieval; produkuje minimalny `retrieval_input@1` bez sekretów.
- [x] Resolvery: record/arXiv, Unpaywall po DOI, CORE po DOI (z `CORE_API_KEY`), DOAB jako katalog  — Runda 8: `test_resolvers_include_*` + `test_doab_is_catalog_and_oapen_*` PASS (offline).
  bez file URL, OAPEN dostarcza ORIGINAL PDF bitstream; identity basis po DOI/ISBN/title.
- [ ] Downloader: kontrola HTTPS i portu 443, odrzucenie prywatnego/loopback DNS, limit redirectów,  — `⏳ KOŃCOWY`
  timeout, retry na 408/429/5xx, limit bajtów; plik tymczasowy nigdy nie jest zaakceptowanym dokumentem.
- [x] Walidacja: poprawny `%PDF` accepted, HTML login page i zły content-type rejected, identity  — Runda 8: `test_html_login_page_is_rejected` + `test_mixed_retrieval_*` (PDF accepted, checksum) PASS.
  mismatch rejected, duplikat po checksumie oznaczony jako `duplicate` bez drugiej kopii bajtów.
- [x] `finalize` tworzy jeden folder runtime z `documents/<id>.pdf`, `market-cases/<id>.market-case.json`  — Runda 8: `test_mixed_retrieval_creates_one_folder_with_pdf_and_market_case` PASS.
  i `retrieved_corpus.json`; każde zatwierdzone źródło występuje dokładnie raz w wyniku.
- [ ] Nowy pakiet market case: ten sam test ma utworzyć także
  `market-cases/<id>.market-case.md`, a `retrieved_corpus@1` ma zawierać `human_document_ref`,
  `human_document_sha256`, `machine_artifact_ref` i `machine_artifact_sha256`. Obie sumy muszą
  zgadzać się z plikami. To rozszerzenie powstało w DEV 2026-06-23 i wymaga nowego TEST.
- [ ] Czytelność dokumentu market case: otworzyć ścieżkę wypisaną jako
  `A06_MARKET_CASE_RUN_DIRECTORY`, odczytać Markdown bez narzędzi programistycznych i potwierdzić,
  że widoczne są tytuł, URL, zweryfikowany fakt A11, znaczenie dydaktyczne, tier, materiality,
  regime context, topic/claim oraz wyraźna granica niezaufanej treści strony.
- [ ] Spójność A11→A06: usunięcie lub podmiana reviewed `market_case_annotations` ma uniemożliwić
  utworzenie Markdown, umieścić source ID w `failed` i pozostawić `market_cases` puste. Test:
  `test_market_case_document_requires_exact_reviewed_a11_annotation`.
- [x] Gated A11 extraction tylko dla zatwierdzonego market source ID; plik zachowuje  — Runda 8: pokryte przez `test_mixed_retrieval_*` (market case w osobnym folderze) offline.
  `content_boundary: untrusted_external_research`, flagi prompt injection i ref do reviewed A11.
- [ ] LIBRARY, CITATION, RESERVE i EXCLUDE nie uruchamiają żadnej operacji sieciowej.  — `⏳ KOŃCOWY`
- [x] MCP inventory zawiera 9 operacji A06 bez publicznego parametru `config`; review task ma RT-01–RT-08.  — Runda 8: `test_a06_mcp_inventory_has_no_public_config_parameter` PASS (MCP `0.9.0`/39 łącznie).
- [ ] Live OA smoke (opt-in): Unpaywall z kontaktem ze środowiska, CORE z kluczem, DOAB/OAPEN; brak  — Runda 8: Unpaywall **PASS** (PLOS OA→2 cc-by; zamknięty→0); CORE poprawnie `unavailable` (brak klucza); OAPEN odpowiada; DOAB zwrócił HTTP 403. DEV 2026-06-23 ustalił, że DSpace 6 `/rest/` nadal działa, a 403 powodował domyślny `Python-urllib/3.14`; dodano stały `User-Agent: EduMaterialsAgents/0.9`. Wymagany rerun DOAB i osobny test CORE z kluczem.
  dostępu daje kontrolowany `unavailable`/`library_required`, nie udawany sukces.
- [ ] Live rzeczywisty PDF (opt-in): `EMAGENTS_RUN_LIVE_A06=1` uruchamia Unpaywall dla stałego
  otwartego DOI PLOS, produkcyjny downloader, walidację i finalizację. Test ma potwierdzić bajty
  `%PDF-`, SHA-256 oraz wydrukować `A06_LIVE_RUN_DIRECTORY` z PDF i `retrieved_corpus.json`.
- [ ] Integracja end-to-end: A02/A03/A04/A11 discovery → reviewed A05 → bramka użytkownika → A06.  — `⏳ KOŃCOWY`
  Przed final confirmation zero requestów download i zero plików w corpus.
- [ ] Resume: poprawny checksum nie jest pobierany ponownie, retry obejmuje tylko unresolved IDs,  — `⏳ KOŃCOWY`
  wynik to pełny nowy `RetrievedCorpus` z zachowaną historią prób.
- [ ] Forward A06 na Claude i Codex, build obu bundle, `graph_check`, skan sekretów, brak runtime  — Runda 8: build obu bundli + skan sekretów + higiena **OK**; `graph_check` **FAIL** (finding 2, blocker). DEV 2026-06-23 dodał brakujący kontrakt i test packagingu; graph/forward wymagają rerun. Forward Claude/Codex `⏳ KOŃCOWY`.
  artifacts; wyniki zapisać jako nową rundę na górze `docs/08_Log_wynikow_TEST.md`.

#### Konkretny rerun TEST A06 po rozszerzeniu dokumentu market case

1. Uruchomić `python -m pytest -q tests/test_g02_retrieval.py`; oczekiwane jest 8 PASS i 1 SKIPPED
   dla domyślnie wyłączonego live smoke.
2. Uruchomić test pakietu z widocznym outputem:
   `python -m pytest -q -s tests/test_g02_retrieval.py -k mixed_retrieval`.
3. Otworzyć katalog z `A06_MARKET_CASE_RUN_DIRECTORY` i ręcznie sprawdzić PDF, Markdown, JSON oraz
   `retrieved_corpus.json` według punktów powyżej.
4. Uruchomić pełny `python -m pytest -q`, następnie projektowe `graph_check.check_all` dla źródła i
   obu zbudowanych bundli. Historyczne 93/95 z Rundy 8 nie jest wynikiem tego rerunu.
5. Live rzeczywisty PDF uruchomić osobno według `tests/README.md`. Live gated Tavily extraction
   wykonać dopiero w pełnym łańcuchu A11→A05→final confirmation→A06.
6. Wynik dopisać jako nową rundę na górze `docs/08_Log_wynikow_TEST.md`; checkboxy powyżej
   zaznaczyć wyłącznie na podstawie faktycznie wykonanych asercji i inspekcji dokumentu.

## DEV fast P0-P5, 2026-06-23

Zakres implementacji i dalsza kolejność są zamrożone w
[`10_Plan_fast_prototyp_G02_do_Graph03.md`](10_Plan_fast_prototyp_G02_do_Graph03.md).
Wdrożono P0-P5 bez uruchamiania lokalnych testów: semantykę profilu fast, deterministyczny
generator query planu, `available_streams` dla A05, limity kosztowe oraz szybki preflight A10.
Nie zmieniono checkboxów TEST ani wyników w dokumencie 08. P6-P8 pozostają zakresem przyszłych
sesji dla A07, A09 i przełączenia domyślnego terminala runnera z A06 na A09.

## DEV fast P6-P8, 2026-06-23

Wdrożono P6-P8 bez uruchamiania lokalnych testów: A07 Paper Review z deterministycznym indeksem
tekstu i bounded windows, A09 fast synthesis bez A08, mandatory A10 dla A09, Human Research Gate z
checkpointem oraz finalizację `user_approved_research_bundle@1` po decyzji człowieka. Domyślny
terminal runnera Codex ustawiono na reviewed A09, a `fast` zachowuje jawne `skip_nodes` dla A08.

Przygotowano testy i mocki dla PDF/window indexing, A07 PDF, A07 market case bez sieci, fabricated
locations, identity mismatch, prompt injection flags, conditional A10 dla A07, A09 bez A08, jawnej
limitation fast, blokady A09 bez evidence refs, mandatory A10 dla A09, skip A08, pause/resume Human
Research Gate, przepływu A06 -> A07 -> A09, Graph03 handoff candidate i inventory MCP. Testy P6-P8
czekają na osobne środowisko TEST; nie zmieniono checkboxów TEST ani wyników w dokumencie 08.

## DEV audyt gotowości P0-P8 przed P9, 2026-06-23

Przeprowadzono statyczny audyt dokumentów 07-10, runtime, grafu, kontraktów, MCP, agentów, skilli i
przygotowanych testów. Bez uruchamiania testów poprawiono obsługę obu bramek terminalowych,
trzyczęściową decyzję Human Research Gate, wersjonowanie pojedynczej korekty, reviewed provenance
A07 -> A09, przebieg A09 przy zerowej liczbie pobranych dokumentów, agregację evidence statusów,
kontrakty pomocniczych artefaktów A09 oraz budżet i lokacje A07. P9 nadal oznacza wykonanie pełnej
weryfikacji w osobnym środowisku; historyczne wyniki w dokumencie 08 pozostają bez zmian.

## DEV deterministyczny pytest w sandboxie (Runda 12), 2026-06-23

Po raz pierwszy uruchomiono przygotowaną, deterministyczną część testów (P6-P8/P9) niezależnie od
środowiska pluginowego i MCP. Szczegóły, środowisko i tabela findingów w `08_Log_wynikow_TEST.md`,
Runda 12. Skrót:

- Pełny `tests/` przeszedł na zielono: **146 passed / 1 skipped / 0 failed** (1 skip = live PDF smoke).
- Pierwszy przebieg dał 12 failed; ustalono **4 przyczyny źródłowe** i wszystkie naprawiono:
  - F-12-1 (fixture, 8 testów A11): deterministyczne testy market-case były dławione przez globalny
    cap profilu `fast` (P4); przypięto `EMAGENTS_G02_PROFILE=strict` w fixture, jak w
    `test_g02_domain.py`. Pliki: `tests/test_g02_market_cases.py`.
  - F-12-2 (fixture, 2 testy A03): hand-built output deklarował puste `remaining_coverage_units` mimo
    niepokrytej mandatory coverage unit; uzupełniono. Plik: `tests/test_g02_canonical.py`.
  - F-12-3 (kod, 1 test A07): komunikat odrzucenia sfabrykowanej lokacji nie zawierał słowa
    „fabricated"; rozszerzono komunikat. Plik: `shared/scripts/g02/paper_review.py`.
  - F-12-4 (kod, REALNY BŁĄD, 1 test A07): dla market case offsety sekcji liczone na surowym
    markdownie kolidowały z bezwarunkowym doszywaniem abstractu w `document_text_window` (okno
    15-znakowe zamiast faktu); abstract doszywany teraz tylko dla `scholarly`, a market-case okno
    obejmuje cały bundel A06. Plik: `shared/scripts/g02/paper_review.py`.
- Status scenariuszy: deterministyczne A01-A11, A07, A09, reviewed_flow, MCP inventory i plugin build
  są PASS w sandboxie. Forward przez plugin/MCP (Rundy 9-11, F-A...F-H) oraz live API pozostają
  `⏳ KOŃCOWY` do osobnego środowiska TEST.
- Uwaga przenośności: runtime używa `datetime.UTC` (Python >= 3.11). TEST na 3.11+ (dotychczas 3.14)
  jest OK; przy 3.10 wymagany fallback lub `python_requires>=3.11`.
## Faza B2 Scout — live Claude Code CLI, Runda 18

Źródło pełnego wyniku: `docs/08_Log_wynikow_TEST.md`, Runda 18. Projekt i layout:
`docs/11_Plan_integracji_Scout_tryb_deterministyczny.md`, sekcje 15–17.

### Wynik pierwszego live runu

- [x] Claude Code uruchomił A01 jako Opus i wygenerował cztery intake-anchored topici.
- [x] Cztery procesy Scouta zakończyły się `completed` bez LLM/OpenRouter.
- [x] Zapisano 70 PDF, 66 unikalnych prac, cztery membershipy cross-topic.
- [x] Powstały `plan.json`, cztery requesty, cztery manifesty, cztery
  `scout_retrieved_corpus@1` i `scout_run_index@1`; brak sekretów w JSON.
- [ ] One-shot A01 → finalize: **PARTIAL**, ponieważ draft wymagał dwóch ręcznych korekt po błędach
  kontraktu (Finding F-L).
- [ ] Jakość didactic query: **PARTIAL**, ponieważ szerokie terminy zebrały szum z innych domen
  (Finding F-M).

### DEV po Rundzie 18

- [x] `plan_output_template` przekazuje A01 dokładny kształt kontraktu.
- [x] Finalizer przejął stałe boundary fields i bezpieczne aliasy zaobserwowane live.
- [x] Dodano walidację 3–6 core terms, kotwicy intake/domain i krótkich ogólnych query.
- [x] Fan-out używa jawnego `oversample=1.2` zgodnie z decyzją właściciela.
- [x] Dodano testy regresyjne dla F-L, F-M i oversample.
- [x] Offline po poprawkach: 27 dedykowanych PASS; pełna regresja 177 PASS / 1 SKIP / 1 znany FAIL
  starego stub harnessu poza zakresem Fazy B2.

### Retest zamykający Fazę B2

- [ ] Reinstall/reload pluginu i nowa sesja Claude Code CLI.
- [ ] A01 przechodzi `research_planner_finalize` za pierwszym razem bez ręcznej edycji.
- [ ] Wszystkie 4–6 topiców przechodzą walidację wyszukiwalności i są dziedzinowo trafne.
- [ ] Scout kończy wszystkie topici z `oversample=1.2` i zachowuje kompletny trwały layout.
- [ ] Po retest PASS można uznać wejście G02 → plan → PDF/index za zamknięte i przejść do A07/A09.
