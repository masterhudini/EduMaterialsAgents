# Research Graph, rejestr DEV i TEST 1b1

## Zasada użycia

Rejestr rozdziela ukończenie implementacji w repozytorium od weryfikacji prowadzonej później w
osobnym katalogu i osobnym środowisku. Bieżąca faza nie tworzy ani nie uruchamia testów.

Po zakończeniu każdego numerowanego zestawu aktualizowana jest lista DEV oraz kompletna lista
scenariuszy TEST. Commit powinien następować po osiągnięciu stanu wymaganego przez właściciela
repozytorium.

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

- [ ] Implementacja nie została rozpoczęta.

### TEST

- [ ] Lista zostanie zamrożona po ukończeniu implementacji zestawu 2.
