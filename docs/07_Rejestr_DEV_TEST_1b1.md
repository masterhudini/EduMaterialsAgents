# Research Graph, rejestr DEV i TEST 1b1

## Zasada użycia

Rejestr rozdziela ukończenie implementacji w repozytorium od weryfikacji prowadzonej później w
osobnym katalogu i osobnym środowisku. Bieżąca faza nie tworzy ani nie uruchamia testów.

Po zakończeniu każdego numerowanego zestawu aktualizowana jest lista DEV oraz kompletna lista
scenariuszy TEST. Commit powinien następować po osiągnięciu stanu wymaganego przez właściciela
repozytorium.

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
- [x] Bundle Codex zawiera skill reviewera bez plików agentów Claude i bez instrukcji adaptera
  Claude.
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
- [x] Codex pomija wyłącznie obecność plików agentów; nadal kontroluje kontrakty reviewera,
  `review_profile`, skille i subgrafy.
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
  wynik `ok: true` mimo zamierzonego braku katalogu agentów pluginu.
- [x] Powtórzyć trzy kontrole z jawnym parametrem `host`; wyniki muszą odpowiadać autodetekcji.
- [x] Nieznana wartość `host` oraz jednoczesne markery Claude i Codex są odrzucane czytelnym
  błędem konfiguracji.
- [x] Source i Claude nadal odrzucają brak fizycznego reviewera oraz brak dowolnego producer
  agenta.
- [x] Codex nadal odrzuca brak kontraktu reviewera, błędną wersję kontraktu, brak
  `review_profile`, brak fizycznego skilla i brak wskazanego subgrafu.
- [x] Bundle Codex nie zawiera ani top-level katalogu `agents`, ani pustego katalogu
  `skills/g02-review-research-output/agents`.
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
- [x] Build Claude zawiera 10 agentów o nowych nazwach, a build Codex nadal nie pakuje agentów.
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

- [ ] Poprawny `research_graph_input@1` przechodzi kontrakt, a brak każdego nowego pola wymaganego
  (`schema_version`, drivers, constraints, selection profile, card arrays, output language) jest
  odrzucany.
- [ ] `research_planner_input@1` powstaje wyłącznie z dozwolonych pól boundary input i zachowuje
  ich wartości bez mutacji.
- [ ] Poprawne wejście bez claim cards przechodzi, jeżeli ma zatwierdzony driver concept,
  flow-issue albo update-need z istniejącą kartą upstream.
- [ ] Brak driverów lub zatwierdzonych domen daje `needs_input` bez artefaktu.
- [ ] Pusty `task_id`, output language albo wymagane pole zatwierdzonego kontekstu daje
  `needs_input`.
- [ ] Duplikaty domain, driver, claim, concept, flow, update lub existing-source IDs są odrzucane.
- [ ] Driver bez upstream linku, z nieznanym linkiem, pustym purpose, nieznanym typem albo
  priorytetem jest odrzucany.
- [ ] Niepoprawne limity, puste listy languages/work types, odwrócone lata i selection target
  większy od candidate limit są odrzucane.
- [ ] Lazy artifact refs bez `artifact://` są odrzucane, a przygotowanie pierwszego przebiegu nie
  hydratuje żadnego z nich.

### TEST 2, walidacja i finalizacja ResearchPlan

- [ ] `mocks/g02/research_plan.json` przechodzi `research_plan@1` i pełny walidator semantyczny
  względem sparowanego mock input.
- [ ] Poprawny plan jest zapisywany pod bezpiecznym `artifact://g02/research-plans/...`, zwraca
  `status: ok` oraz dokładnie jeden deskryptor `research_plan@1` z `artifact_version`.
- [ ] Plan nie mutuje planner input ani obiektu przekazanego do finalizacji.
- [ ] Pusty plan, przekroczenie `max_topics`, duplikaty albo niepoprawne formaty `TOPIC_*` i
  `COV_*` są odrzucane.
- [ ] Topic bez drivera, purpose, zatwierdzonej domeny, source role, core terms, coverage albo stop
  rule nie tworzy artefaktu.
- [ ] Nieznany driver lub upstream ID, niezatwierdzona domena i niezatwierdzony seed source są
  odrzucane.
- [ ] Topic priority nie może być niższy niż najwyższy priorytet powiązanego drivera.
- [ ] Languages, work types i date window nie mogą rozszerzać global constraints.
- [ ] Candidate limit mieści się w konfiguracji, saturation passes są zachowane, a complementary
  search route jest wymagana.
- [ ] Każdy driver trafia dokładnie do covered albo uncovered; overlap, unknown i unaccounted
  drivers są odrzucane.
- [ ] Uncovered driver bez odpowiadającego `input_issues.related_driver_ids` jest odrzucany.
- [ ] Użyteczny plan z poprawnie zadeklarowanym uncovered driverem zwraca `degraded`; high-priority
  uncovered nie może później uzyskać `APPROVED` od reviewera.
- [ ] Blocking input issue nie pozwala zapisać planu.
- [ ] Zmiana task ID, output language, global constraints lub review profile jest odrzucana.
- [ ] Pola publikacji, source records, claim verdicts i slide changes są odrzucane także przy
  zagnieżdżeniu.
- [ ] Błąd zapisu artefaktu zwraca `failed` bez deskryptora i bez częściowego zatwierdzonego pliku.

### TEST 2, rewizja i reviewer

- [ ] Rewizja bez `previous_plan_ref` jest odrzucana, gdy przekazano `revision_items`.
- [ ] Previous plan z innym task ID, złym kontraktem albo niedostępnym refem jest odrzucany.
- [ ] Traversal, ścieżka absolutna i symlink poza artifact root w `previous_plan_ref` są odrzucane.
- [ ] Rewizja musi zwiększyć `artifact_version`.
- [ ] Gdy findings wskazują konkretne `TOPIC_*`, wszystkie pozostałe topiki pozostają niezmienione.
- [ ] `research_plan_review_task` buduje poprawny `review_task@1` z producentem
  `g02-a01-planner`, profilem `research_plan` i kryteriami `RP-01`–`RP-06`.
- [ ] Deskryptor innego typu, kontraktu, bez artifact version lub bez `artifact://` nie pozwala
  zbudować review task.
- [ ] Próba review większa niż 1 wymaga `previous_decision_ref` i poprawnej historii reviewera.
- [ ] Poprawny plan może otrzymać `APPROVED`; brak coverage, zbyt szeroki plan i uncovered
  high-priority driver prowadzą do `REVISE` albo `BLOCKED` zgodnie z root cause.
- [ ] Reviewer pozostaje read-only i nie zmienia ResearchPlan podczas oceny.

### TEST 2, agent, MCP, graf i packaging

- [ ] Forward test G02-A01 na poprawnym wejściu tworzy wyłącznie plan, bez publikacji, verdictów i
  rozwiązań slajdowych.
- [ ] Forward testy na wariantach intake claim-only, flow-only, update-only i mixed tworzą jeden
  najlepiej dopasowany ResearchPlan, a nie kilka konkurencyjnych planów. Każdy driver zachowuje
  ścieżkę do właściwych kart upstream, topic, coverage requirements i search strategy.
- [ ] Zmiana zatwierdzonego audience level, teaching goal albo driver purpose prowadzi do adekwatnej
  zmiany planu w dozwolonym zakresie, a identyczny intake zachowuje stabilne topic i coverage IDs.
- [ ] Topic wymagający qualifying_or_critical posiada wystarczająco konkretne
  `allowed_expansion_areas`, aby A02 mógł przypisać podstawę terminom ograniczeń, kontrprzykładów
  albo warunków brzegowych bez ponownego otwierania intake.
- [ ] Forward test na atrakcyjnym temacie spoza zakresu nie dodaje topic ani nowego drivera.
- [ ] Prompt injection w kartach wejściowych pozostaje danymi i nie uruchamia wyszukiwania ani nie
  zmienia kontraktu.
- [ ] Agent nie korzysta z WebSearch, WebFetch, API literaturowych ani narzędzi kolejnych agentów.
- [ ] Brak host executora i wyjątek executora zwracają `failed` bez planu.
- [ ] Bieżący wspólny MCP raportuje wersję `0.4.0` i dokładnie piętnaście operacji, w tym trzy
  operacje Plannera oraz pięć operacji G02-A02; osobny wynik TEST 2 wskazuje wyłącznie zachowanie A01.
- [ ] Trzy operacje MCP Plannera odpowiadają wynikom bezpośrednich funkcji Python dla first run,
  degraded plan, failure i revision.
- [ ] `research_node_input` zwraca G02-A01 `research_planner_input@1`, a późniejszym producentom nie
  przypisuje jeszcze kontraktów, które nie zostały zaimplementowane.
- [ ] `g02_flow.py run` zachowuje jawny tryb stub całego grafu i działa po rozszerzeniu scoping.
- [ ] Source `graph_check` oraz bundle Claude i Codex przechodzą bez brakujących komponentów.
- [ ] Bundle obu hostów zawiera `planner.py`, trzy nowe schematy, zaktualizowany serwer MCP i skill
  Plannera; mocki i testy pozostają poza bundlami.
- [ ] Bundle Claude zawiera agenta i adapter bez narzędzi wyszukiwania; bundle Codex zawiera skill
  i instrukcje trzech operacji MCP bez plików agentów Claude.
- [ ] Build nie mutuje źródeł i nie pakuje `__pycache__`, `.pyc` ani artefaktów runtime.
- [ ] Pełny wcześniejszy zestaw TEST 1 przechodzi po aktualizacji oczekiwanej wersji MCP i listy
  operacji, bez regresji reviewera.
- [ ] Wynik TEST 2 dopisać na górze `08_Log_wynikow_TEST.md` i zaznaczyć wyłącznie faktycznie
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

- [ ] Poprawny plik config, `EMAGENTS_RESEARCH_CONTACT_EMAIL` i wymagany dla aktywnego OpenAlex
  `OPENALEX_API_KEY` tworzą katalogi runtime i raportują trzy jawne capabilities bez wartości
  sekretów.
- [ ] Jawna ścieżka config ma pierwszeństwo przed `EMAGENTS_RESEARCH_CONFIG`, konfiguracją projektu
  i przykładem w repo.
- [ ] Brak kontaktowego e-maila przy włączonym OpenAlex lub arXiv kończy startup czytelnym błędem.
- [ ] Brak `OPENALEX_API_KEY` przy włączonym OpenAlex kończy startup przed requestem czytelnym
  błędem; wyłączenie OpenAlex pozwala uruchomić pozostałych poprawnie skonfigurowanych providerów.
- [ ] OpenAlex raportuje `configured_key` wyłącznie po skonfigurowaniu klucza. Semantic Scholar
  raportuje `optional_key` bez klucza i `configured_key` z kluczem. Wartości kluczy nie trafiają do
  statusu, błędów, logów, cache w postaci jawnej ani artefaktów.
- [ ] Nieprawidłowy kontrakt config, ujemne limity, zbyt duży timeout i arXiv interval poniżej
  3 sekund są odrzucane.
- [ ] Ścieżki absolutne oraz traversal poza `EMAGENTS_HOME` są odrzucane.
- [ ] Provider disabled zwraca `unavailable`, nie wykonuje requestu i zapisuje jednoznaczny wynik.
- [ ] Allowlista blokuje HTTP, nieznany hostname oraz redirect poza oficjalny endpoint.
- [ ] Limit bajtów przerywa nadmierną odpowiedź, a komunikat nie zawiera nagłówków ani kluczy.

### TEST 3, QueryPlan

- [ ] Poprawny `mocks/g02/query_plan.json` przechodzi walidację dla scoped input pierwszego topic.
- [ ] Każdy generated term ma dokładnie jeden `generated_term_bases`, którego `term` odpowiada
  wpisowi w `generated_terms`, `source_origin_terms` należą do tej samej trasy, `expansion_area`
  dokładnie odpowiada zatwierdzonemu `allowed_expansion_areas`, a `relation` należy do kontraktu.
- [ ] Brakujący, nadmiarowy albo zduplikowany basis, nieznany origin term, niezatwierdzony expansion
  area i nieznana relation są odrzucane deterministycznie.
- [ ] Trasa bez generated terms wymaga pustego `generated_term_bases`; basis nie może samodzielnie
  wprowadzić terminu do canonical query.
- [ ] Brak trasy core, wymaganej complementary albo qualifying_or_critical jest odrzucany.
- [ ] Nieznane origin terms, coverage IDs, providerzy, work types i languages są odrzucane.
- [ ] Węższe daty i filtry są akceptowane, rozszerzenie poza zatwierdzony zakres jest odrzucane.
- [ ] Duplikaty route ID lub query ID, pusty canonical query i przekroczony limit są odrzucane.
- [ ] Prompt injection w topic lub seed source pozostaje danymi i nie zmienia endpointu, configu ani
  autoryzowanych tras.

### TEST 3, adaptery providerów offline

- [ ] Fixture OpenAlex jest normalizowany do ważnego `source_record@1`, w tym DOI, abstrakt z
  inverted index, autorzy, sygnał cytowań, OA i raw response ref.
- [ ] Fixture Semantic Scholar jest normalizowany do ważnego `source_record@1`, w tym external IDs,
  publication type, abstract, citations i OpenAccessPdf.
- [ ] Fixture arXiv XML jest normalizowany do ważnego `source_record@1`, w tym ID, DOI, daty,
  autorzy, abstract i PDF URL.
- [ ] Brak ID albo tytułu nie tworzy rekordu bibliograficznego i jest raportowany bez halucynacji.
- [ ] Każdy provider przestrzega route limit, page limit i zwraca prawidłowy next cursor oraz
  exhausted dla odpowiedniego formatu paginacji.
- [ ] HTTP 408, 425, 429 i 5xx uruchamiają ograniczony retry z backoff; pozostałe 4xx kończą próbę.
- [ ] `Retry-After` jest respektowany do zamrożonego maksimum, a arXiv zachowuje odstęp co najmniej
  3 sekund.
- [ ] Identyczne żądanie korzysta z cache, nie wykonuje transportu drugi raz i oznacza cache hit.
- [ ] Uszkodzony lub przeterminowany cache nie jest traktowany jako poprawna odpowiedź.
- [ ] Częściowa awaria po użytecznej stronie daje `partial`; zero wyników daje `ok` z pustą listą,
  jeśli provider gwarantuje filtry, albo `partial` z `provider_filter_unverifiable`; awaria przed
  wynikiem daje `failed` albo `unavailable`.
- [ ] Raw response i `literature_tool_result@1` są zapisane jako osobne, możliwe do hydratacji
  artefakty z pełną proweniencją.

### TEST 3, live API smoke, wyłącznie opt-in

- [ ] Testy sieciowe są domyślnie pomijane i uruchamiają się wyłącznie po jawnej fladze środowiska;
  używają osobnego katalogu `EMAGENTS_HOME`, limitu 1–2 rekordów i kontrolowanego timeoutu.
- [ ] Preflight potwierdza obecność `EMAGENTS_RESEARCH_CONTACT_EMAIL` i `OPENALEX_API_KEY` bez
  drukowania wartości. `SEMANTIC_SCHOLAR_API_KEY` jest sprawdzany jako opcjonalny, ale zalecany.
- [ ] OpenAlex przyjmuje skonfigurowany klucz, zwraca HTTP success i co najmniej jeden rekord dla
  stabilnego małego query; wynik, rekord i raw-response ref przechodzą kontrakty. Brak klucza jest
  zatrzymywany lokalnie przed requestem.
- [ ] Semantic Scholar wykonuje małe query z nagłówkiem `x-api-key`, gdy klucz jest skonfigurowany,
  oraz poprawnie raportuje limit lub tryb bez klucza. Kod nie przekracza jednego requestu na sekundę.
- [ ] arXiv wykonuje małe query bez klucza, wysyła identyfikujący User-Agent, zachowuje odstęp co
  najmniej 3 sekund i zwraca poprawny rekord z XML.
- [ ] Pierwszy request każdego providera omija cache, a drugi identyczny request potwierdza cache hit
  bez ponownego połączenia, jeżeli cache jest włączony.
- [ ] Po smoke testach automatyczny skan całego testowego `EMAGENTS_HOME`, przechwyconego stdout i
  stderr potwierdza brak jawnych wartości e-maila i obu kluczy. Artefakty zachowują tylko
  niesekretny status authentication i proweniencję.
- [ ] Każdy live wynik odróżnia prawidłowe zero results, błąd autoryzacji, rate limit i awarię
  providera. Test nie prowokuje 429 przez celowe przekraczanie limitu.

### TEST 3, Domain artifact i reviewer

- [ ] `research_domain_prepare` hydratuje wyłącznie zatwierdzony plan i jeden topic oraz zwraca
  `domain_research_input@1` bez kluczy API.
- [ ] Brak planu, zły kontrakt, nieznany topic i brak gotowego providera zwracają odpowiedni
  `needs_input` albo `failed` bez uruchomienia agenta.
- [ ] Poprawny wynik z query logs i niezmienionymi provider records zapisuje
  `domain_candidate_sources@1` i zwraca `ok`.
- [ ] Każdy wpis query log zgadza się z hydratowanym `literature_tool_result@1`; obcy, brakujący albo
  zmodyfikowany ref jest odrzucany.
- [ ] Kandydat spoza wyników providera, zmienione metadane, duplikat source ID i przekroczony limit
  są odrzucane.
- [ ] G02-A02 nie może przypisywać finalnych source roles ani verdictów claimów.
- [ ] Coverage map używa wyłącznie kandydatów i approved coverage IDs, a basis ma wartość metadata,
  title albo abstract.
- [ ] Niepełne coverage lub jawne provider issues zapisują użyteczny artefakt jako `degraded` z
  resume token; `completed` z lukami jest odrzucane.
- [ ] Rewizja wymaga poprzedniego artefaktu, zachowuje task/topic i zwiększa artifact version.
- [ ] Builder review tworzy dokładnie jeden `review_task@1`, profil `domain_candidates`, zamrożone
  DR-01 do DR-06 i ref tylko do ocenianego artefaktu.
- [ ] Uniwersalny reviewer zwraca APPROVED, REVISE lub BLOCKED zgodnie z artefaktem i nie wykonuje
  wyszukiwania ani nie modyfikuje wyniku.

### TEST 3, agent, MCP, packaging i regresja

- [ ] Forward test G02-A02 tworzy QueryPlan, wywołuje wyłącznie narzędzia MCP, zachowuje neutralność
  stanowisk i nie wykonuje pracy A03-A09.
- [ ] Forward test G02-A02 zachowuje pełną ścieżkę `driver → topic → origin term → generated term
  basis → route → coverage unit`; reviewer odrzuca semantycznie nieuzasadniony basis nawet wtedy,
  gdy jego shape przechodzi kontrakt.
- [ ] Dla jednego topic agent tworzy kilka uzasadnionych tras wyszukiwania, a nie kilka wariantów
  ResearchPlan. Core, complementary i qualifying_or_critical różnią się celem oraz terminologią,
  lecz pozostają w tym samym zatwierdzonym zakresie.
- [ ] Agent nie używa WebSearch, WebFetch, shell HTTP, downloadera PDF ani bezpośrednich klientów API.
- [ ] Forward testy A01 i A02 przechodzą osobno na Claude i Codex. Brak rzeczywistego izolowanego
  executora hosta daje jawny failure i nie może zostać zaliczony jako test zachowania agenta.
- [ ] MCP raportuje wersję `0.4.0` i dokładnie piętnaście operacji, w tym pięć operacji G02-A02 i
  dziesięć pozostałych.
- [ ] Pięć operacji MCP G02-A02 odpowiada wynikom bezpośrednich funkcji Python dla success,
  zero-result, partial, failure i revision.
- [ ] Manifest, agent, skille, kontrakty i MCP używają wyłącznie identyfikatorów G02-A02 oraz
  aktualnych nazw skilli.
- [ ] Source `graph_check` oraz bundle Claude i Codex przechodzą bez brakujących komponentów.
- [ ] Bundle zawiera moduły Domain, providerów, sześć schematów, example config, MCP i oba skille;
  mocki, testy, lokalny config i sekrety nie trafiają do bundla.
- [ ] Build nie mutuje źródeł i nie pakuje `.emagents`, cache, raw responses, `__pycache__` ani `.pyc`.
- [ ] TEST 1 i TEST 2 przechodzą po aktualizacji bieżącej wersji MCP i listy operacji, bez regresji
  reviewera oraz Plannera.
- [ ] Wynik TEST 3 dopisać na górze `08_Log_wynikow_TEST.md` i zaznaczyć wyłącznie faktycznie
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

Status TEST 2 i TEST 3: warstwa deterministyczna A01 i A02 przeszła reprezentatywny podzbiór
(A01 20/20, A02 27/27). Blokujący błąd builda został usunięty i lokalny build/dry-run przechodzi;
pełny packaging w osobnym środowisku pozostaje do wykonania jutro. Live API smoke i forward testy
hosta nadal wymagają odpowiednio sieci oraz rzeczywistego executora. Pojedyncze checkboxy nie są
zaznaczane do pełnego przebiegu.

### Bramka jutrzejszego retestu A01-A02

- [ ] Użyć świeżej kopii repo i osobnego środowiska z zależnościami z `requirements-dev.txt`;
  brak `pytest` w bieżącym systemowym Pythonie nie jest wynikiem testu repo.
- [ ] Build/dry-run raportuje dokładnie `Validated 20 skills and 11 agents`; oba bundle zawierają
  A11 jako scaffold, a `graph_check` przechodzi dla source, Claude i Codex.
- [ ] MCP `0.4.0` raportuje dokładnie 15 zaimplementowanych operacji. Brak
  `research_web_case_search` i `research_web_case_extract` jest oczekiwany do czasu DEV A11.
- [ ] Wykonać pełne TEST 2 i TEST 3 według scenariuszy powyżej, osobno oznaczając: deterministyczne,
  forward Claude, forward Codex, live API i packaging.
- [ ] Live A02 ma dostęp HTTPS do `api.openalex.org`, `api.semanticscholar.org` i
  `export.arxiv.org`, a środowisko zawiera `EMAGENTS_RESEARCH_CONTACT_EMAIL`,
  `OPENALEX_API_KEY` oraz opcjonalnie `SEMANTIC_SCHOLAR_API_KEY`. Wartości sekretów nie mogą
  pojawić się w logu, artefakcie ani statusie providera.
- [ ] Nie zaliczać A11, Tavily ani ekstrakcji web w jutrzejszym teście A01-A02. Ich fixture'y mają
  przechodzić wyłącznie walidację shape i packaging; testy semantyczne oraz live należą do batcha
  A11 po A03-A05.
