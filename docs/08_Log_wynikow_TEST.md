# Research Graph, log wyników TEST

## Zasada użycia

Jeden append-only log wyników testów wykonywanych w niezależnej kopii repo (środowisko `testing`).
Plik jest komplementarny wobec `07_Rejestr_DEV_TEST_1b1.md`:

- `07` to autorytatywna checklista DEV i lista scenariuszy TEST (źródło prawdy o zakresie).
- `08` (ten plik) to chronologiczny dziennik wykonania: data, środowisko, werdykt per scenariusz,
  błędy i rekomendacje.

Synchronizacja: po każdej rundzie dopisujemy nowy wpis na górze sekcji "Wpisy" i aktualizujemy
checkboxy TEST w `07` tylko dla scenariuszy faktycznie wykonanych i zaliczonych. Scenariusze
zablokowane pozostają odznaczone w `07`, a przyczyna trafia tutaj. Każdy wpis podaje krótką mapę
"co zmienić w 07".

Konwencja statusów: PASS, FAIL, BLOCKED (nie dało się wykonać), N/A.

Wyjątek techniczny: zamknięta migracja namespace może znormalizować identyfikatory komponentów
i ścieżki w starszych wpisach, aby nadal wskazywały aktualne pliki. Data, środowisko, wykonane
scenariusze, wyniki i werdykty historycznych rund pozostają niezmienne.

---

## Wpisy

### Runda 10 — 2026-06-23 — Realny forward Codex `run-codex` A01→A06: infrastruktura gotowa, przebieg zablokowany przez niepoprawne envelope workerów i brak stopu po `BLOCKED`

Środowisko: repo `ema-wsl` (WSL2), branch `main` @ `0ed20a6`, Python 3.14.4, `.venv` pytest 9.1.1, `codex-cli 0.142.0`. Sekrety wyłącznie w env: `TAVILY_API_KEY`, `OPENALEX_API_KEY`, `EMAGENTS_RESEARCH_CONTACT_EMAIL`, `SEMANTIC_SCHOLAR_API_KEY`; `CORE_API_KEY` nieobecny. Runtime testu: `EMAGENTS_HOME=/tmp/emagents-g02-final.CFEyii`. Konfiguracja `.emagents/config/g02-providers.json` skopiowana do runtime jako Tavily-only; SearXNG wyłączony (`endpoint: null`).

**Cel:** wykonać realne testy forward/końcowe przez `python3 shared/scripts/g02/g02_flow.py run-codex --gates prompt mocks/g02/research_graph_input.json`, zakres docelowy A01 → A02 → A03 → A04 → A11 → A05 → user-source-selection-gate → A06, z review A10 po każdym producencie. **Wynik: FAIL/BLOCKED przed bramką źródeł. Nie zaznaczono żadnego forward checkboxa w `07`.**

#### Przygotowanie — PASS

- `codex --version`: `codex-cli 0.142.0`; minimalny `codex exec` smoke zwrócił `{"ok":true,"scope":"codex_exec_smoke"}`.
- `codex mcp list`: `edu-materials-research` enabled.
- Provider status z `EMAGENTS_HOME=/tmp/emagents-g02-final.CFEyii`: `ok:true`; OpenAlex, Semantic Scholar, arXiv, Tavily, Unpaywall, DOAB i OAPEN ready; CORE wyłączony/brak klucza; SearXNG disabled/endpoint missing.
- Build: `python3 scripts/build-plugin.py --host all` utworzył `dist/claude` i `dist/codex`; inventory 20 skilli / 11 agentów w obu bundlach; MCP ma 39 operacji.
- `graph_check`: source `True`, Claude bundle `True`, Codex bundle `True`.
- Skan sekretów runtime po przebiegu: `secret_scan_hits=0`. W `dist` nie zostawiono `.emagents`, testów, `.pyc` ani `__pycache__`.

#### Przebieg forward — FAIL/BLOCKED

Uruchomienie:

```bash
script -q -f /tmp/emagents-g02-final.CFEyii/run-codex.transcript -c 'EMAGENTS_HOME=/tmp/emagents-g02-final.CFEyii python3 shared/scripts/g02/g02_flow.py run-codex --gates prompt mocks/g02/research_graph_input.json'
```

Log runu: `/tmp/emagents-g02-final.CFEyii/logs/run-g02-3364e0a32640.log`. Artefakty producentów zapisane w `/tmp/emagents-g02-final.CFEyii/artifacts/research/`.

- A01 `g02-a01-planner`: worker uruchomiony, ale zapisany artefakt ma `status: failed`; `codex worker failed`, bo zwrócony `envelope@1` był niepoprawny: `issues[0]` bez wymaganego `type`, `severity: "blocking"` spoza enum `["blocker","major","minor"]`. A10 review: `BLOCKED`.
- A02 `g02-a02-domain`: uruchomiony mimo zablokowanego A01; artefakt `status: failed`; `issues` bez wymaganych pól `severity` i `type`. A10 review: `BLOCKED`.
- A03 `g02-a03-canonical-sources`: uruchomiony mimo zablokowanych upstreamów; artefakt `status: failed`; `issues` bez wymaganych pól `severity` i `type`. A10 review: `BLOCKED`.
- A04 `g02-a04-recent-developments`: uruchomiony mimo zablokowanych upstreamów; artefakt `status: failed`; `severity: "blocking"` spoza enum i brak `type` w issues. Proces przerwano kontrolnie podczas review A04, bo dalsze downstreamy byłyby niemiarodajne.
- A11, A05, user-source-selection-gate i A06 **nie zostały osiągnięte**. Liczba pobrań/ekstrakcji przed final confirmation: 0, bo final confirmation nie wystąpił. Live SearXNG nie był wykonany, zgodnie z Tavily-only i brakiem administrator-pinned endpointu.

#### Findingi

1. **F-B (NOWY, blocker Codex forward).** `runners/codex.py` poprawnie waliduje finalny JSON workera i przy niezgodności zwraca `_fail` (`shared/scripts/g02/runners/codex.py:121-123`), ale prompt/adapter Codex workerów nie wymusza wystarczająco kontraktu `envelope@1`: workery realnie emitują `issues` bez wymaganych pól albo z `severity: "blocking"`. **Fix:** wzmocnić prompt/adapter przez schema-constrained output (`--output-schema` dla envelope albo lokalną normalizację aliasów i brakujących pól przed walidacją), oraz dodać test, że każdy worker-fail również spełnia `envelope@1`.
2. **F-C (NOWY, blocker scheduler integrity).** Scheduler po `review_decision == "BLOCKED"` tylko wychodzi z pętli prób (`break`), a następnie bezwarunkowo zapisuje `produced_refs[name] = ref` (`shared/scripts/g02/g02_flow.py:418-465`). To pozwoliło A02/A03/A04 ruszyć na failed artefaktach i zablokowanych upstreamach. **Fix:** po `BLOCKED`, invalid envelope lub invalid artifact zwracać `failed/BLOCKED` z runu i nie dodawać ref do `produced_refs`; downstreamy nie mogą startować bez zatwierdzonego/typed upstreamu.
3. **F-D (NOWY, brak realnego użycia deterministic MCP seam w `run-codex`).** W przebiegu artefakty producentów miały `typed:false` i były zapisanymi envelope `_fail`, nie kontraktami producentów. Nie ma dowodu na wykonanie `research_*_prepare/finalize/search` przez workery ani na scope driver→topic→route→coverage. **Fix:** runner powinien egzekwować producer protocol: prepare przez MCP, provider calls wyłącznie przez MCP, finalize przez MCP, a następnie review-task/review-finalize; w logu powinien powstać audyt per MCP operation.

#### Status `07`

- Forward/końcowe scenariusze A01, A02, A03, A04, A11, A05, A10, gate i A06 pozostają odznaczone.
- Packaging/build/`graph_check`/inventory/secret scan w tej rundzie: PASS, odnotowane tutaj, ale nie zaliczają pełnego checkboxa końcowego, bo run forward został zablokowany przed A05/A06.
- SearXNG live pozostaje niewykonany: brak administrator-pinned endpointu; Tavily-only nie zalicza live SearXNG checkboxów.

### Runda 9 — 2026-06-23 — Próba forward A01→A06 na hoście Claude (headless `claude -p` + MCP): mechanizm działa, ale ujawniony systemowy blocker F-A; podejście zarzucone na rzecz Codexa

Środowisko: repo `ema-wsl` (WSL2), branch `main` @ `0ed20a6` (po merge #19, **finding #2 naprawiony przez właściciela** — `shared/contracts/retrieval_directory.schema.json` istnieje, `graph_check` source **ok: true**). Python 3.14.4, `claude` CLI 2.1.186. Sekrety wyłącznie w env: `TAVILY_API_KEY` (klucz właściciela tej sesji), `OPENALEX_API_KEY`, `EMAGENTS_RESEARCH_CONTACT_EMAIL`, `SEMANTIC_SCHOLAR_API_KEY`. Osobny `EMAGENTS_HOME` w `/tmp`. Sekrety NIE zapisywane do plików repo/mcp.json — przekazywane przez env procesu workera; skrypty/`mcp.json`/stream poza repo (`/tmp`) i posprzątane.

**Cel:** uruchomić *prawdziwy* forward (izolowany executor LLM per węzeł woła wyłącznie narzędzia MCP) bez instalacji pluginu — przez headless `claude -p --mcp-config` jako runner host-agnostycznego silnika, z bramką w czacie i realnym pobieraniem PDF/Tavily na końcu. **Wynik: mechanizm potwierdzony, ale podejście `claude -p` okazało się złym narzędziem do testów; przerwane na A01 po wykryciu systemowego F-A. Decyzja właściciela: jutro powtórzyć w przygotowanym przez devów środowisku Codex.**

#### Co potwierdzono (działa)

- **Runner `claude -p` + MCP**: headless worker łączy się z `research_server.py` (stdio) przez `--mcp-config`, woła narzędzia `research_*`, zwraca JSON (`is_error:false`, `permission_denials:[]`). Smoke `research_provider_status` PASS (~12 s, ~$0.15 na Opusie).
- **Bezpieczeństwo sekretów**: `TAVILY_API_KEY` dociera do serwera MCP przez env procesu (tavily `ready:true`), bez zapisu do `mcp.json`. Skan: 0 wycieków.
- **`graph_check` zielony** na source (finding #2 naprawiony).
- **Ścieżka ref-owa prepare działa**: `front_door(<ścieżka intake>) → artifact://handoffs/research_graph_input.json`; `research_planner_prepare(input=<ten ref>) → {ready: true, planner_input: {...}}`. A01 worker (Opus, slim) poprawnie wykonał `prepare(ref)` i zaczął budować `research_plan@1` — **przerwany przed `finalize`** (decyzja stop), więc A01 forward NIE jest zaliczony.

#### Findingi

1. **F-A (NOWY, systemowy blocker forwardu wszystkich producentów A01–A06).** Narzędzia `*_prepare` deklarują argument `input` **bez `type`** w JSON Schema (tylko opis „object, path or artifact:// ref"). Headless-agent LLM domyślnie serializuje wejście jako **string JSON**. Loader `_planner_payload` (`shared/scripts/mcp/research_server.py:90-98`) dla stringa niebędącego `artifact://` wykonuje `json.loads(pathlib.Path(value).read_text())` → traktuje go jako **ścieżkę pliku** → `[Errno 36] File name too long`; agent się zapętla. **Substancja pipeline'u OK** — przy podaniu `input` jako `artifact://` ref (jak robi prawdziwy orkiestrator) `prepare` przechodzi. **Fix (do devów):** dodać `"type"` do schematu `input` (np. `["object","string"]`) i/lub w loaderze próbować `json.loads` gdy string wygląda na JSON (zaczyna się od `{`), zanim potraktuje go jako path. Dotyczy też `*_finalize` przyjmujących `input`.
2. **`claude -p` to złe narzędzie do tego testu (operacyjne).** (a) Harness Claude Code **blokuje** zagnieżdżony `--permission-mode bypassPermissions` (guardrail „unsafe agent / auto-mode bypass") — workery muszą iść bez bypassu (działa biała lista, ale to ograniczenie). (b) **Globalny tool-deferral**: każdy worker dziedziczy ~60–97 narzędzi jako *deferred* + pełną powierzchnię (Bash/Write/WebSearch/Task…), więc robi dodatkowy `ToolSearch` i ma osłabioną izolację (agent powinien widzieć TYLKO `research_*`). `--strict-mcp-config` ucina obce serwery MCP, ale nie deferral. (c) **Ciężki/wolny/kosztowny per węzeł** (Opus-planner), kruchy (crash F-A, parsowanie JSON z ```-fence). Łącznie: nie nadaje się na rzetelny, powtarzalny harness forward.

#### Decyzja i status checklisty

- **Podejście `claude -p` zarzucone.** Forward + końcowe powtórzymy w **środowisku Codex** przygotowanym przez devów (pierwszoklasowy `run-codex` / `runners/codex.py`, bramki w terminalu) — powinno być solidniejsze.
- **Żaden węzeł forward nie został domknięty** (A01 zatrzymany przed `finalize`), więc **w `07` nie zaznaczono żadnego pola forward/końcowego** jako zaliczone. Pozostają `⏳ KOŃCOWY`. Jedyny nowy trwały wynik to **finding F-A** (do naprawy przed forwardem) oraz potwierdzenie, że runner-mechanizm i ścieżka ref-owa działają.
- **Do devów (priorytet przed forwardem):** naprawić F-A; rozważyć, czy orkiestrator/agenci mają zawsze przekazywać `input` jako ref (wtedy F-A nie wystąpi w `/research`), ale schemat i tak warto utwardzić.



Środowisko: repo `ema-wsl` (WSL2), branch `main` na `0751f63` (po merge A05 #17 i A06 #18), Python 3.14.4,
`pytest` 9.1.1 z `.venv`. Sieć wychodząca dostępna. Sekrety wyłącznie w env: `TAVILY_API_KEY` (klucz
dostarczony przez właściciela w tej sesji), `EMAGENTS_RESEARCH_CONTACT_EMAIL`, `OPENALEX_API_KEY`,
`SEMANTIC_SCHOLAR_API_KEY`. `CORE_API_KEY` nieobecny (CORE OA pozostaje opcjonalny). Każdy przebieg
miał osobny `EMAGENTS_HOME` w `/tmp`. Wartości sekretów nie były zapisywane do plików repo ani logów;
skrypty live trzymane poza repo (`/tmp`).

**Cel rundy:** pierwsze faktyczne wykonanie wcześniej nieprzetestowanych funkcjonalności nowego batcha
(A11 Market Cases, A05 Candidate Source Index, A06 Paper Retrieval) na warstwie deterministycznej,
live API (Tavily dla A11; Unpaywall/DOAB/OAPEN/CORE dla A06) oraz packagingu. Forward Claude/Codex,
pełna integracja A01→…→A06 i live gated Tavily extraction świadomie odroczone — `⏳ KOŃCOWY`.

**Werdykt zbiorczy: warstwa deterministyczna A05 i A06 zielona; A11 zielona poza jednym FAIL kodu issue.
Live Tavily discovery (A11) i live Unpaywall (A06) — PASS. Packaging zbudowany i higieniczny, ale
`graph_check` FAIL na source i obu bundlach z powodu BRAKUJĄCEGO kontraktu `retrieval_directory@1`
(blocker A06). Trzy findingi (niżej).**

#### Liczby

- Pełny `pytest`: **93 passed, 2 failed** (95 łącznie). FAIL: A11 redirect (issue-code) + `test_research_graph::test_manifest_matches_registration` (graph_check).
- A11 `tests/test_g02_market_cases.py`: **8/9** (1 FAIL — finding 1).
- A05 `tests/test_g02_candidate_index.py`: **4/4 PASS**.
- A06 `tests/test_g02_retrieval.py`: **6/6 PASS**.
- Live Tavily discovery (auto_budgeted, SearXNG off): **PASS** — 6 realnych case'ów.
- Live OA: Unpaywall **PASS**; CORE poprawnie `unavailable` (brak klucza); DOAB **HTTP 403** (finding 3); OAPEN odpowiada (0 dla testowego ISBN).
- Packaging: dry-run 20 skilli/11 agentów bez mutacji źródeł; build obu bundli OK; higiena bundla czysta; MCP `0.9.0` / **39 operacji**. `graph_check` source/Claude/Codex: **FAIL** (jeden błąd — finding 2).

#### TEST 6, G02-A11 Market Cases

- A–E (deterministyka) — **PASS poza jednym FAIL** przez `tests/test_g02_market_cases.py` (8/9):
  contracts+config+scoped prepare; query plan + auto_budgeted result; finalize+review+MCP parity;
  walidator odrzuca zmodyfikowany rekord/scope/sfabrykowaną obserwację; limit odpowiedzi + blokada
  ekstrakcji przed bramką; **post-gate extraction → bounded untrusted artifact** (offline mock Tavily);
  rewizja zachowuje untargeted i odrzuca nieznany target/unscoped change. **FAIL: redirect issue-code
  (finding 1).**
- F (live Tavily) — **PASS**: discovery zwraca 6 datowalnych case'ów z allowlisted domen (risk.net itd.),
  każdy `source_record@1` (contract_ok), `record_type: market_case`, `tier_2_reputable_media`,
  `abstract_source: search_snippet` i `raw_page_ref: None` (**brak ekstrakcji strony w discovery**);
  powtórzenie → `provenance.cache_hit: True` (brak drugiego requestu); skan `EMAGENTS_HOME` — **0 wycieków**
  klucza/e-maila. Live SearXNG — **nie wykonano** (brak skonfigurowanej instancji). Live gated Tavily
  extraction — **nie wykonano** (wymaga pełnego łańcucha A11→A05→human gate; egzekwowanie bramki zielone
  offline).
- G (forward Claude/Codex) — **`⏳ KOŃCOWY`**.
- H (packaging) — inventory 11 agentów/20 skilli, build obu bundli, higiena czysta: **PASS**;
  `graph_check`: **FAIL** (finding 2, wspólny dla całego grafu).

#### TEST 7, G02-A05 Candidate Source Index

- A–E (deterministyka) — **PASS** przez `tests/test_g02_candidate_index.py` (4/4): prepare wymaga
  dokładnych APPROVED reviews i rzutuje reviewed-only scoped input; build deduplikuje i opisuje treść
  scholarly oraz market case; finalize zapisuje przyjazny dokument + review task; MCP inventory +
  prepare parity.
- F (rzeczywista interakcja Human Source Selection Gate) — **nie wykonano** (wymaga realnego hosta/orkiestratora) — `⏳ KOŃCOWY`.
- G (MCP/packaging/forward) — MCP `0.9.0`/39 i prepare parity **PASS**; `graph_check` **FAIL** (finding 2); forward **`⏳ KOŃCOWY`**.

#### DEV 8, G02-A06 Paper Retrieval

- Deterministyka — **PASS** przez `tests/test_g02_retrieval.py` (6/6): bramka wymaga osobnego final
  confirmation; resolvery record/unpaywall/core/doab/oapen; DOAB jako katalog i OAPEN ORIGINAL PDF
  bitstream; mixed retrieval tworzy jeden folder z PDF + market case; HTML login page odrzucony;
  MCP inventory A06 bez publicznego `config`.
- Live OA — **PASS z findingiem**: capabilities `record/unpaywall/doab/oapen` ready, `core` nieready
  (brak `CORE_API_KEY`), status nie ujawnia e-maila; Unpaywall na PLOS OA DOI `10.1371/journal.pone.0000308`
  → 2 kandydaci `version_of_record`, HTTPS PDF, licencja cc-by; zamknięty DOI → 0 (kontrolowany brak, bez
  fabrykacji); 0 wycieków. **DOAB live `/rest/search` → HTTP 403 (finding 3)**; OAPEN `/rest` odpowiada
  (0 dla testowego ISBN, bez fabrykacji).
- Integracja end-to-end, resume live, forward — **`⏳ KOŃCOWY`**.
- Packaging — build/hygiena **PASS**; `graph_check` **FAIL** (finding 2).

#### Findingi (do decyzji/poprawki dev)

1. **A11: redirect cross-origin raportowany jako `unsafe_searxng_endpoint`, nie `cross_origin_redirect_blocked`**
   (`tests/test_g02_market_cases.py::test_agent_cannot_supply_searxng_endpoint_or_cross_origin_redirect`).
   Przy wstrzykniętym transportcie walidacja `final_url` (`web_cases.py:427`) wywołuje
   `_validate_provider_url(..., final=True)` **przed** dedykowanym sprawdzeniem cross-origin (`:429`).
   Kod `cross_origin_redirect_blocked` powstaje wyłącznie w `_PinnedRedirectHandler` (`:168`), używanym
   tylko przez `_default_transport`, więc przy własnym transportcie jest nieosiągalny. **Substancja
   bezpieczeństwa zachowana** (redirect zablokowany, status `partial`, treść atakującego nieużyta) —
   różni się tylko kod issue. **Do decyzji:** przestawić kolejność sprawdzeń, albo dostroić oczekiwanie
   testu. Ścieżka produkcyjna (default transport) jest poprawna.
2. **A06 BLOCKER: brak kontraktu `retrieval_directory@1`.** Węzeł `g02-a06-paper-retrieval` w
   `shared/graphs/g02.graph.json` deklaruje `produces: ["retrieved_corpus@1", "retrieval_directory@1"]`,
   a `shared/scripts/g02/retrieval.py:367` emituje deskryptor `schema_version: retrieval_directory@1`,
   ale **brak `shared/contracts/retrieval_directory.schema.json`**. `graph_check` ładuje schemat każdego
   produkowanego kontraktu (`graph_check.py:175`) → KeyError → `graph_check` FAIL na source **oraz obu
   bundlach** (jedyny błąd na każdym hoście). Uciekło, bo DEV 8 jawnie nie uruchamiał `graph_check`/buildu.
   **Do poprawki:** dodać `retrieval_directory.schema.json`, albo usunąć `retrieval_directory@1` z
   `produces[]` i deskryptora (run directory jako nie-kontraktowy ref). Blokuje bramkę packagingu.
3. **A06: live DOAB `/rest/search` → HTTP 403.** DOAB używa starego DSpace-6 REST API (`directory.doabooks.org/rest/...`),
   które zwraca 403 (przestarzałe; DOAB/OAPEN przeszły na DSpace-7 `/server/api/`). OAPEN `/rest` jeszcze
   odpowiada. Offline (mocki starego formatu) przechodzi; live DOAB resolution wymaga migracji endpointu.
   Wynik kontrolowany (`RetrievalError`/failed), **bez udawanego sukcesu**.

   **Korekta diagnostyczna DEV 2026-06-23:** wynik HTTP 403 pozostaje historycznym wynikiem Rundy 8,
   ale przyczyną nie było wycofanie DSpace 6. `/rest/status` raportuje API 6/source 6.3, a ten sam
   `/rest/search` odpowiada 200 dla `User-Agent: EduMaterialsAgents/0.9` i 403 dla
   `Python-urllib/3.14`. Runtime otrzymał stały nie-sekretny User-Agent; potrzebny jest rerun TEST.

#### Follow-up DEV po Rundzie 8 — 2026-06-23 (bez nowego werdyktu TEST)

- Naprawiono klasyfikację redirectu A11 dla transportu wstrzykniętego, cache i ścieżki produkcyjnej.
- Dodano brakujący kontrakt `retrieval_directory@1`, typed descriptor `artifact://` i kontrolę bundla.
- Dodano stały User-Agent dla metadanych OA, klasyfikację HTTP status oraz kontrolę DNS każdego
  redirectu downloadera.
- Dodano domyślnie pomijany live smoke, który pobiera rzeczywisty PDF PLOS przez Unpaywall,
  waliduje `%PDF-` i SHA-256, finalizuje katalog i wypisuje `A06_LIVE_RUN_DIRECTORY`.
- Domknięto starszy finding Rundy 7: wyłączony provider jest teraz rozpoznawany przed walidacją
  gotowości QueryPlan, zwraca `unavailable/provider_disabled` i nie wykonuje requestu.
- Rozszerzono A06 o czytelny dokument market case. Po zatwierdzeniu źródła A06 wiąże dokładnie
  jedną reviewed adnotację A11 z gated extraction i zapisuje obok JSON także Markdown zawierający
  fakt, interpretację dydaktyczną, ocenę źródła/materialności, kontekst reżimu, powiązania i jawne
  ostrzeżenie o niezaufanej treści. `retrieved_corpus@1` 1.2 przechowuje odrębne refs i SHA-256 obu
  plików; brak dokładnej adnotacji A11 blokuje utworzenie dokumentu.
- Dodano asercje treści i checksum pakietu, negatywny test brakującej adnotacji oraz wydruk
  `A06_MARKET_CASE_RUN_DIRECTORY`. Następny domyślny rerun `tests/test_g02_retrieval.py` ma dać
  8 PASS i 1 SKIPPED (live PDF), a
  procedura wykonania i ręcznej inspekcji znajduje się w końcu sekcji TEST A06 pliku 07.
- Powyższe punkty są zmianami DEV. Historyczne 93/95 pozostaje bez zmian do ponownego uruchomienia
  pełnego pytest, `graph_check` na trzech hostach oraz testów live DOAB/PDF w środowisku TEST.

#### Odroczone (`⏳ KOŃCOWY`)

- Forward Claude/Codex dla A11, A05, A06; pełna integracja A01→A02→A03→A04→A11 discovery→A05→bramka→A06.
- Live gated Tavily extraction (po finalnej bramce człowieka) i live skonfigurowanej instancji SearXNG.
- Rzeczywista interakcja Human Source Selection Gate (TEST 7 F) na realnym hoście.

#### Mapa „co zmienić w 07" po tej rundzie

- TEST 6 (A11): zaznaczyć deterministyczne A–E pokryte `test_g02_market_cases.py` oprócz bulletu redirect
  (oznaczyć `❌ FAIL`, finding 1); zaznaczyć live Tavily discovery + skan sekretów w F (SearXNG/extraction
  live = nie wykonano); H — zaznaczyć inventory/build/higienę, `graph_check` `❌ FAIL` (finding 2).
- TEST 7 (A05): zaznaczyć deterministyczne A–E pokryte `test_g02_candidate_index.py` i MCP parity w G;
  `graph_check` `❌ FAIL`; F i forward `⏳ KOŃCOWY`.
- DEV 8 batch A06: zaznaczyć deterministyczne pozycje pokryte `test_g02_retrieval.py` i live Unpaywall;
  DOAB live z notą (finding 3); `graph_check`/packaging `❌ FAIL` (finding 2); integracja/forward/resume `⏳ KOŃCOWY`.

### Runda 7 — 2026-06-22 — Pełne domknięcie TEST 1–5 (A01–A04) + live API; baseline „ostatni pełny przebieg"

Środowisko: klon repo `ema-wsl` (WSL2), branch `main` (po merge `e75244b` z A03/A04), Python 3.14.4,
`pytest` 9.1.1 z `.venv`. Sieć wychodząca dostępna. Sekrety wyłącznie w env: `OPENALEX_API_KEY`
(używany bez nawiasów), `EMAGENTS_RESEARCH_CONTACT_EMAIL`. Semantic Scholar keyless. Wartości
sekretów nie były zapisywane do plików repo ani logów.

**Cel rundy:** jednorazowo, kompletnie domknąć całą warstwę wykonywalną (deterministyczna + live API
+ packaging) dla A01–A04 i zaznaczyć w `07` wszystko, co faktycznie przeszło, aby kolejne rundy
testowały już tylko nowe/zmienione funkcjonalności. Forward testy (host executor) i testy całościowe
(cały przepływ A01→…→A05, A11/A05/Tavily/SearXNG) świadomie odroczone do końcowego testu
integracyjnego batcha i oznaczone w `07` markerem `⏳ KOŃCOWY`.

**Werdykt zbiorczy: PASS na całej warstwie deterministycznej (A01–A04), live API (OpenAlex/arXiv
stabilnie; Semantic Scholar keyless = jawny `unavailable`/`failed`, kontraktowo poprawnie) oraz
packagingu A03/A04. Trzy findingi (poniżej). Forward + integracja: odroczone.**

#### Liczby

- Pakiet `tests/` (pytest, pełny): **76/76 PASS** (w tym `test_g02_canonical.py` 16 i
  `test_g02_recent.py` 18 — pełna deterministyka A03/A04).
- TEST 1 reviewer (harness `review.py`): **40/40 PASS**.
- TEST 2 planner: harness `planner.py` **32/32** + backfill (kontrakty/limity/rewizja/MCP/flow) **49/49 PASS**.
- TEST 3 domain: harness offline **47/47** + backfill (config precedence, byte-limit, QueryPlan,
  disabled provider, corrupt cache, status matrix, prepare rejections, **zbudowane poprawne wyjście
  A02** + finalize/rewizja/odrzucenia) **34/34 PASS**.
- TEST 3 live smoke (OpenAlex/arXiv records; S2 keyless explicit): OpenAlex+arXiv **PASS**;
  S2 keyless → `unavailable`/`failed` z jawnym issue (kontraktowo poprawne, patrz finding 3).
- TEST 4C/5C live (canonical citation/metadata + recent window): **12/12 PASS**.
- Packaging A03/A04 + `graph_check`: build obu hostów, `graph_check` source/Claude/Codex `ok: true`,
  MCP `0.6.0` / **22 operacje**.

#### TEST 4, G02-A03 Canonical Sources

- A/B (deterministyka) — **PASS** przez zatwierdzony `tests/test_g02_canonical.py` (16 testów):
  prepare scopuje reviewed domain + wyklucza sekrety, odrzuca mismatch upstream; citation expand
  zachowuje relację i rekord; wszystkie wspierane trasy (OpenAlex `cited_by`, S2
  `references`/`cited_by`/`recommendations`) normalizują się do `source_record@1`; arXiv i nieznana
  relacja → `unavailable`; nieautoryzowany seed → `failed`; `metadata_search` przyjmuje
  `canonical_input`; walidator odrzuca zmodyfikowany rekord, słabą podstawę, tool result spoza scope,
  fałszywy `domain_authoritative`, brak edge/false signal/nadmiarowy access; `completed` z gapem
  odrzucone; rewizja zachowuje untargeted; `build_canonical_review_task` → profil `canonical_sources`,
  `CS-01`–`CS-06`; `execute_canonical` bez executora → `failed`.
- C (live API) — **PASS** (live `live_a03_a04.py`): `prepare_canonical` ready; live OpenAlex
  complementary metadata z `canonical_input` → rekordy `source_record@1`; cache hit na powtórzeniu;
  redakcja klucza i e-maila w artefaktach **0/0**. Citation expand: S2 po realnym DOI seeda zwrócił
  jawny `failed` (HTTP 404) — explicit status, brak pozornego success. Patrz findingi 2 i 3.
- D (forward Claude/Codex) — **`⏳ KOŃCOWY`** (host executor, test integracyjny).
- E (packaging) — **PASS**: oba bundle zawierają `canonical.py`, `citations.py`, kontrakt
  `canonical_research_input@1`, agenta A03 i wymagane skille; `graph_check` 3 hosty `ok`; brak
  mocków/testów/`.emagents`/cache/`__pycache__`/`.pyc`; 0 sekretów. `install_plugin --dry-run` bez
  mutacji źródeł.

#### TEST 5, G02-A04 Recent Developments

- A/B (deterministyka) — **PASS** przez zatwierdzony `tests/test_g02_recent.py` (18 testów):
  planner zachowuje `recency_window_years` intake→plan; `prepare_recent` materializuje okno
  (5 lat, rok 2026 → **2022–2026**), skip dla topicu bez roli `current`, odrzuca mismatch domain;
  `recent_query_plan` + `metadata_search` scoped, pula `recent_metadata`; citation expand pula
  `recent_expansion`; MCP prepare/finalize/review parity; walidator odrzuca rekord spoza okna,
  zmodyfikowany rekord, tool result spoza scope, fałszywy maturity/peer status/quality, poszerzenie
  okna; `preprint` nie może być `core_update`; nieznany typ → `unknown`; `build_recent_review_task`
  → profil `recent_developments`, `RD-01`–`RD-06`; `execute_recent` bez executora → `failed`.
- C (live API) — **PASS** (live): `prepare_recent` ready, okno 2022–2026; live OpenAlex recent →
  2 rekordy z latami **[2023, 2022] w oknie**; live arXiv recent → `partial` (język); cache hit;
  redakcja **0/0**. S2 keyless → jawny status (finding 3).
- D (forward Claude/Codex) — **`⏳ KOŃCOWY`**.
- E (packaging) — **PASS**: oba bundle zawierają `recent.py`, kontrakt `recent_research_input@1`,
  agenta A04; MCP `0.6.0`/22; `graph_check` 3 hosty; higiena bundla czysta.

#### Findingi (do decyzji/poprawki dev)

1. **Disabled provider → `failed`, nie `unavailable`** (TEST 3, bullet „Provider disabled zwraca
   `unavailable`…"). Gdy provider jest wyłączony, `validate_query_plan` odrzuca trasę preferującą go
   (`invalid_provider_route: preferred providers must be configured and ready`), więc
   `search_metadata` zwraca `failed`/`invalid_query_plan` **zanim** dotrze do gałęzi `unavailable`
   (providers.py ~942). Substancja zachowana: **żaden request nie jest wykonywany**, wynik jest
   jednoznaczny. Ale status różni się od dokumentacji. Gałąź `unavailable` dla disabled providera jest
   w praktyce nieosiągalna. **Do decyzji:** poprawić dok na `failed`/`invalid_provider_route`, albo
   zmienić kolejność tak, by disabled provider dawał `unavailable`. Checkbox pozostawiony odznaczony.
2. **Live OpenAlex `cited_by` wymaga realnego seed id.** Seed w `mocks/g02/domain_candidate_sources.json`
   ma prawdziwy DOI (`10.1214/17-sts668`), ale placeholder `openalex_id` (`WMOCK0001`), więc live
   OpenAlex `cited_by` nie zwróci realnych rekordów (kontrolowane `failed`, bez fałszywego success).
   To ograniczenie danych mocka, nie kodu — deterministyczna normalizacja `cited_by` jest w pełni
   pokryta pytestem. Bullet „Live OpenAlex `cited_by` … zwraca 1–2 rekordy" pozostawiony odznaczony
   z notką; do wykonania w teście integracyjnym z realnym seedem.
3. **Semantic Scholar keyless live jest niedeterministyczny** (rate-limit). Pod limitem zwraca jawny
   `unavailable`/`failed` z issue — **kontraktowo poprawne** (TEST „bez klucza/429 = jawny status,
   bez pozornego success"). Aby live S2 zwracał rekordy, potrzebny `SEMANTIC_SCHOLAR_API_KEY`
   (opcjonalny). Bullety o jawnym statusie S2 — zaliczone; bullety wymagające rekordów S2 — zależne
   od klucza, oznaczone w `07`.

#### Odroczone do końcowego testu integracyjnego (`⏳ KOŃCOWY`)

- Forward testy zachowania agentów A01, A02, A03, A04 i uniwersalnego reviewera A10 na realnym host
  executorze (Claude oraz Codex). Powód: wymagają uruchomienia promptów agentów end-to-end przez
  izolowany executor hosta; rejestr stanowi, że brak takiego executora = jawny brak wykonania.
- Cały przepływ A01 → A02 → A03 → A04 → A11 discovery → A05 i sekcja „Wspólny TEST batcha po DEV 7".
  Powód: A11 (Tavily/SearXNG) i A05 są jeszcze DEV/scaffold.

#### Mapa „co zmienić w 07" po tej rundzie

- Dodano legendę markerów (`[x]` / `❌ FAIL` / `⏳ KOŃCOWY`) na początku rejestru.
- Zaznaczono wszystkie wykonane i zaliczone scenariusze deterministyczne TEST 2 i TEST 3 (backfill),
  oraz live i packaging TEST 4 i TEST 5; sekcje A/B TEST 4/5 zaznaczone na podstawie zatwierdzonego
  `tests/test_g02_canonical.py` i `tests/test_g02_recent.py`.
- Oznaczono `⏳ KOŃCOWY` przy forward testach (TEST 2/3/4D/5D) i sekcji wspólnego testu batcha.
- Oznaczono `❌ FAIL`/notą trzy findingi (disabled-provider status; live OpenAlex `cited_by` mock seed;
  S2 keyless rekordy zależne od klucza).
- Warunki zamknięcia zadań i akceptacje DEV pozostają w gestii właściciela.

### Decyzja DEV po Rundzie 6 — 2026-06-22 — bramka następnego batcha

Właściciel zaakceptował zakres Rundy 6 jako wystarczającą bramkę wejściową do developmentu G02-A03,
G02-A04, G02-A11 i G02-A05. Warstwa deterministyczna, live API, packaging i `graph_check` są zielone.
Niewykonane forward testy A01/A02/A10 zostają świadomie przeniesione do wspólnego testu
integracyjnego nowego batcha.

Rozstrzygnięto politykę hosta Codex: `plugin.manifest.json` zachowuje
`hosts.codex.includeAgents = true`. Oba bundle zawierają wspólne definicje agentów, a różnice
pozostają w adapterach wykonania. Historyczne wyniki Rund 4/5 poprawnie opisują konfigurację z czasu
ich wykonania i pozostają bez zmian. Bieżący stan dokumentują Runda 6 oraz rejestr 07.

### Runda 6 — 2026-06-22 — Pełny re-run TEST 1+2+3 z żywym dostępem do API

Środowisko: klon repo `ema-wsl` (WSL2), branch `main`, Python 3.14.4, `pytest` 9.1.1 z `.venv`.
**Sieć wychodząca dostępna** (inaczej niż Rundy 1–5): bezpośredni HTTPS do `api.openalex.org` (200),
`api.semanticscholar.org` i `export.arxiv.org`. Sekrety wyłącznie w env: `OPENALEX_API_KEY` (klucz
podany przez właściciela, używany bez nawiasów), `EMAGENTS_RESEARCH_CONTACT_EMAIL`. Semantic Scholar
uruchamiany keyless (klucz opcjonalny). Wartości sekretów nie były zapisywane do plików repo ani logów.

**Werdykt zbiorczy: PASS na całej warstwie wykonywalnej deterministycznie ORAZ na live API smoke.
Jedna rozbieżność config↔dokumentacja (Codex pakuje agentów). Trzy usterki repo z Rundy 5 — naprawione.
Forward testy zachowania agentów (host executor) nie wykonane w tej rundzie.**

#### Liczby

- Pakiet `tests/` (pytest): **39/39 PASS** (0.7 s).
- TEST 1 G02-A10 reviewer, harness deterministyczny na `review.py`: **40/40 PASS**.
- TEST 2 G02-A01 planner, harness na `planner.py` + sparowane mocki: **32/32 PASS**.
- TEST 3 G02-A02 domain, harness offline na `provider_config.py`/`query_planning.py`/`providers.py`/`domain.py`: **47/47 PASS**.
- TEST 3 live API smoke (OpenAlex + Semantic Scholar keyless + arXiv): **24/24 PASS**.
- Packaging/build + `graph_check`: oba bundle zbudowane, `graph_check` source/Claude/Codex `ok: true`.

#### TEST 1 — reviewer (deterministycznie) — PASS

Walidacja `review_task@1`: poprawny task przechodzi; brak każdego wymaganego pola (`review_id`,
`task_id`, `producer_agent`, `artifact`, `review_profile`, `acceptance_criteria`, `severity_rules`)
odrzucony; deskryptor artefaktu bez `type`/`ref`/`schema_version`/`artifact_version` odrzucony; `ref`
bez `artifact://` odrzucony; `attempt>1` bez `previous_decision_ref` odrzucony; duplikat i
zarezerwowany criterion_id odrzucone. Walidacja `review_decision@1`: APPROVED/REVISE/BLOCKED poprawne
przechodzą; APPROVED z findings, REVISE bez findings, REVISE z blockerem, BLOCKED bez blockera,
nieznany verdict/severity, nieautoryzowany criterion_id, open+closed overlap — odrzucone. Mapowanie
severity w obu kierunkach dla wszystkich wartości; nieznana wartość rzuca błąd. Narzędzia: `prepare_review`
zwraca dokładnie jeden zhydratowany artefakt; brak `severity_rules` z audit identity → BLOCKED
`review_profile_error`; brak audit identity → envelope `failed` bez decyzji; niedostępny artefakt →
BLOCKED `external_dependency_blocked`; `finalize_review_decision` zapisuje decyzję w `envelope@1` ze
ścieżką `artifact://`; `execute_review_task` bez executora → BLOCKED `external_dependency_blocked`,
wyjątek executora → `failed`, poprawny envelope reviewera → ok, błędny envelope → `failed`. Prompt
injection w treści artefaktu pozostaje danymi — profil i kryteria niezmienione.

#### TEST 2 — planner (deterministycznie) — PASS

`scope_planner_input` produkuje `research_planner_input@1`, odrzuca pola producenta, nie mutuje
źródłowego `research_graph_input@1`, przechodzi kontrakt. `validate_planner_input`: poprawne wejście
ok; pusty `task_id`, pusty `output_language`, brak driverów, duplikat drivera — odrzucone.
`validate_research_plan`: `mocks/g02/research_plan.json` przechodzi semantyczny walidator względem
scoped inputu i jest `complete`; odrzucone: pusty `topics`, zmiana `task_id`, zmiana `output_language`,
zły format `TOPIC_*`, duplikat topic id, zakazane pole producenta (`source_records`), zmiana
`global_constraints`. `finalize_research_plan`: `status: ok`, dokładnie jeden deskryptor
`research_plan@1` z `artifact_version` i ścieżką `artifact://`, brak mutacji obiektu planu.
`prepare_planner`: first run ready; `revision_items` bez `previous_plan_ref` → odrzucone.
`build_research_plan_review_task`: poprawny `review_task@1`, producent `g02-a01-planner`, profil
`research_plan`, kryteria `RP-01`–`RP-06`. `execute_planner`: brak executora → `failed`, wyjątek →
`failed`, happy path z wstrzykniętym planem → ok z deskryptorem `research_plan@1`.

#### TEST 3 — domain (offline) — PASS

Konfiguracja i bezpieczeństwo (`provider_config.py`): poprawny config → 3 capabilities; OpenAlex ready
z kluczem+e-mailem; status bez wartości sekretu; `configured_key`/`optional_key`/`configured_key`
poprawnie raportowane; brak e-maila przy OpenAlex/arXiv → błąd startu; brak `OPENALEX_API_KEY` przy
OpenAlex → błąd startu; wyłączenie OpenAlex pozwala uruchomić resztę bez klucza; zły `schema_version`,
ujemny limit, timeout>120, arXiv interval<3, ścieżka absolutna i traversal — odrzucone; allowlista
blokuje HTTP i obcy host, akceptuje oficjalny. QueryPlan: `mocks/g02/query_plan.json` waliduje się
względem scoped inputu; odrzucone — nieznana relacja, duplikat `route_id`, pusty canonical query,
work_type spoza zakresu, route limit ponad max, duplikat/nadmiarowy `generated_term_bases`. Adaptery
offline (wstrzyknięty transport + fixtures): OpenAlex/Semantic Scholar/arXiv normalizują się do ważnego
`source_record@1` (OpenAlex z DOI); brak `id` → brak rekordu. Transport: cache hit na identycznym 2.
wywołaniu; retry na 429 → sukces; nieretryowalne 404 kończy próbę po jednym wywołaniu; `final_url`
poza origin odrzucony. Builder: `build_domain_review_task` tworzy `review_task@1` z profilem
`domain_candidates`, kryteriami `DR-01`–`DR-06`, producentem `g02-a02-domain`.

#### TEST 3 — live API smoke — PASS (po raz pierwszy odblokowane siecią)

Ścieżka realnego kodu `prepare_domain` → `search_metadata` per provider, limit 2 rekordów, osobny
`EMAGENTS_HOME`. Wyniki na żywo:

- **OpenAlex**: `status ok`, 2 rekordy (np. „Nested sampling for general Bayesian computation"),
  `authentication: configured_key`, `source_record@1` poprawny, raw-response ref obecny, identyczne
  2. wywołanie = cache hit.
- **Semantic Scholar (keyless)**: `status partial` z `provider_filter_unverifiable` (język — zgodne z
  kontraktem), 2 rekordy, `optional_key`, `source_record@1` poprawny, raw ref, cache hit.
- **arXiv**: `status partial` (język), 2 rekordy (np. „Approximate Bayesian Computation with Path
  Signatures"), `authentication: none`, interval ≥3 s zachowany, raw ref, cache hit.
- **Redakcja**: pełny skan testowego `EMAGENTS_HOME` (artefakty, cache) i przechwyconego stdout/stderr —
  **wartość `OPENALEX_API_KEY` nie pojawia się nigdzie**. E-mail kontaktowy występuje tylko jako
  identyfikujący `mailto`/User-Agent wysyłany do providerów (zgodne z polityką polite-pool), nie jako
  wyciek do artefaktu.

#### Packaging / build / graph_check — PASS (z jedną rozbieżnością)

- `scripts/build-plugin.py` buduje oba bundle (Claude i Codex) bez mutacji plików źródłowych
  (`git status` czysty po buildzie).
- `graph_check.check_all`: source `host=source ok=true`; bundle Claude `host=claude ok=true`; bundle
  Codex `host=codex ok=true` (autodetekcja po markerach `.claude-plugin`/`.codex-plugin`).
- Inwentarz: 11 agentów i 20 skilli; `plugin.manifest.json` zgodny ze źródłem (11/20).
- Bundle higieniczne: **0** wystąpień klucza i e-maila; brak `mocks/`, `tests/`, `__pycache__`, `.pyc`,
  `.emagents`/cache/raw oraz lokalnego `g02-providers.json`; obecny `g02.providers.example.json`.
- MCP `research_server.py`: `SERVER_INFO.version = 0.4.0`, lista `TOOLS` = **dokładnie 15** operacji
  (z `research_run_codex`). Zgodne z oczekiwaniem dok. po Rundzie 5.

#### Usterki z Rundy 5 — status

1. **NAPRAWIONA.** `plugin.manifest.json` zawiera `g02-a11-market-cases` i jego dwa skille; inwentarz
   źródła i manifestu zgodny (11 agentów, 20 skilli). Testy packagingu przechodzą.
2. **NAPRAWIONA.** `tests/test_research_graph.py` wyznacza liczbę producer-agentów z grafu; testy
   `test_node_input_map_exposes_per_agent_context` i `test_nodes_receive_mocked_context` zielone.
3. **NAPRAWIONA.** MCP `0.4.0` z 15 operacjami — spójne między implementacją, `test_mcp_server.py`
   i (po aktualizacji) rejestrem.

#### Nowa rozbieżność do decyzji dev (config ↔ dokumentacja)

- **Bundle Codex zawiera teraz pełny katalog `agents/` z plikami 11 agentów.** Przyczyna:
  `plugin.manifest.json` → `hosts.codex.includeAgents = true` (zmiana z commita „Major runtime for
  codex and claude upgrade"). To **świadoma zmiana konfiguracji**, nie błąd builda (`graph_check`
  Codex nadal `ok: true`). Jednak wprost przeczy scenariuszom TEST w `07` (linie 118, 120, 152, 177,
  219, 341: „Bundle Codex bez plików agentów", „build Codex nadal nie pakuje agentów") oraz wynikom
  Rund 4/5 w `08`. **Decyzja dev:** albo zaktualizować `07`/`08`, że Codex celowo pakuje agentów,
  albo cofnąć `hosts.codex.includeAgents` do `false`. Do czasu decyzji odpowiednie checkboxy „Codex
  bez agentów" w `07` pozostawiono odznaczone/oznaczone jako nieaktualne.

#### Nie wykonane w tej rundzie

- **Forward testy zachowania agentów A01/A02 (i reviewera) na realnym host executorze (Claude/Codex
  LLM).** Wymagają uruchomienia samych promptów agentów end-to-end przez izolowany executor hosta;
  rejestr `07` stanowi, że brak takiego executora to jawny brak wykonania, nie zaliczenie. Warstwa
  deterministyczna pod tymi agentami jest w pełni zielona (powyżej). Do wykonania jako osobny krok.

#### Mapa „co zmienić w 07" po tej rundzie

- TEST 3 „live API smoke": zaznaczono scenariusze faktycznie wykonane (preflight kluczy bez druku,
  OpenAlex z kluczem, Semantic Scholar keyless, arXiv ≥3 s, cache miss/hit, skan redakcji, rozróżnienie
  statusów). Scenariusz celowego nieprowokowania 429 zachowany (limit 2 rekordów, brak pętli).
- TEST 2 i TEST 3 (warstwa deterministyczna): zaznaczono scenariusze pokryte harnessami powyżej.
- Forward testy (Claude/Codex) i scenariusze „Codex bez agentów" pozostają odznaczone (odpowiednio:
  niewykonane / rozbieżność do decyzji).
- Warunki zamknięcia zadań 2 i 3 pozostają odznaczone do czasu forward testów i decyzji o Codex/agentach.

---

### Runda 5 — 2026-06-21 — Zadania 2 i 3: G02-A01 Planner i G02-A02 Domain

Środowisko: kopia repo (`EduMaterialsAgents-testing2`), Python 3.10, build i checki w katalogu
lokalnym. Brak sieci wychodzącej (proxy 403). Sanity check ucięć: 0 plików uciętych.

**Werdykt zbiorczy: warstwa deterministyczna A01 i A02 PASS; trzy usterki repo; część scenariuszy
zablokowana środowiskowo (live API, host executor, packaging przez build).**

#### Co wykonano i wynik (offline, deterministycznie)

- G02-A01 Planner, `planner.py` + mocki: 20/20 PASS. Scoping wejścia do `research_planner_input@1`
  bez mutacji i bez pól producenta; `needs_input` przy braku `task_id` i pustym `output_language`;
  `mocks/g02/research_plan.json` przechodzi walidator semantyczny względem sparowanego inputu;
  finalizacja zapisuje `artifact://g02/research-plans/...`, `status: ok`, jeden deskryptor
  `research_plan@1` z `artifact_version`, bez mutacji obiektu planu; odrzucenie pól zagnieżdżonych
  producenta (`source_records`), zmiany `task_id`, pustej listy topiców; `build_research_plan_review_task`
  tworzy `review_task@1` z producentem `g02-a01-planner`, profilem `research_plan` i kryteriami
  `RP-01`–`RP-06`; zły deskryptor i brak executora oraz wyjątek executora dają `failed`.
- G02-A02 Domain, konfiguracja i bezpieczeństwo, `provider_config.py`: 12/12 PASS. Poprawny config z
  e-mailem kontaktowym i `OPENALEX_API_KEY` przechodzi; brak e-maila i brak klucza OpenAlex przy
  aktywnym OpenAlex odrzucone; wyłączenie OpenAlex pozwala uruchomić resztę; arXiv interval < 3 s,
  ujemny limit, ścieżka absolutna i traversal odrzucone; `provider_status` zwraca trzy capabilities
  (`enabled`/`ready`/`authentication`) bez wartości sekretów; wyłączony provider ma `enabled:false,
  ready:false`; allowlista blokuje HTTP i obcy host.
- G02-A02 Domain, QueryPlan, providerzy offline i artefakt, `query_planning.py`, `providers.py`,
  `domain.py`: 15/15 PASS. Fixture'y OpenAlex, Semantic Scholar i arXiv normalizują się do ważnego
  `source_record@1` (z DOI dla OpenAlex); brak ID albo `paperId` nie tworzy rekordu;
  `prepare_domain` zwraca `domain_research_input@1` bez kluczy API; `mocks/g02/query_plan.json`
  przechodzi walidator względem scoped inputu, a nieznana relacja i duplikat `route_id` są odrzucane;
  `build_domain_review_task` tworzy `review_task@1` z profilem `domain_candidates`, kryteriami
  `DR-01`–`DR-06` i producentem `g02-a02-domain`; klucz OpenAlex nieobecny w przygotowanym inpucie.
- MCP: serwer raportuje `0.4.0`; osiem operacji zadań 2 i 3 jest wystawionych i wywoływalnych;
  `research_provider_status` nie ujawnia wartości klucza (test z realną wartością klucza w statusie
  przechodzi).
- Regresja `tests/`: rdzeń (`test_core_runtime`, `test_mcp_server`) przechodzi; 5 faili pochodzi z
  dwóch usterek repo opisanych niżej, nie z zachowania reviewera/plannera/domain.

#### Usterki repo (do naprawy)

1. `plugin.manifest.json` nie zawiera 11. agenta `g02-a11-market-cases` ani jego dwóch skilli
   (`g02-a11-extract-case-evidence`, `g02-a11-find-market-cases`), które istnieją na dysku i w
   `g02.graph.json`. `validate_manifest` w `build-plugin.py` przerywa build:
   `manifest components.skills differs from source; missing=[...a11...]`. Inwentarz na dysku to 11
   agentów i 20 skilli, a manifest deklaruje 10 i 18. Skutek: build pada, a z nim trzy testy
   packagingu (`test_build_renders_all_skills_without_mutating_sources`, `test_dry_run...`,
   `test_manifest_declares_every_source_component`). Naprawa: dodać agenta i dwa skille a11 do
   manifestu, albo wycofać a11 ze źródła, zależnie od intencji.
2. `tests/test_research_graph.py` zakłada na sztywno 9 producer-agentów (`len(...) == 9`), a graf po
   dodaniu `g02-a11-market-cases` ma ich 10. Dwa failujące testy (`test_node_input_map_exposes_per_agent_context`,
   `test_nodes_receive_mocked_context`). Naprawa: zaktualizować oczekiwaną liczbę i mock kontekstu,
   albo dokończyć/wycofać integrację a11.
3. Rozjazd dokumentacji: rejestr `07` (TEST 2 i TEST 3) mówi o „dokładnie czternastu operacjach” MCP,
   a implementacja oraz `test_mcp_server.py` wystawiają 15 (dodatkowo `research_run_codex`). To
   opóźnienie dokumentacji, nie błąd kodu. Naprawa: zaktualizować liczbę w rejestrze do 15 albo
   uzasadnić wyłączenie `research_run_codex` z liczenia.

#### Zablokowane środowiskowo (nie z powodu braku kluczy)

- TEST 3 „live API smoke”: środowisko testowe nie ma sieci wychodzącej (proxy zwraca 403 dla
  `api.openalex.org`). Klucze nie odblokują tego tutaj. Do wykonania potrzebne środowisko z dostępem
  HTTPS do `api.openalex.org`, `api.semanticscholar.org`, `export.arxiv.org` oraz `OPENALEX_API_KEY`,
  `EMAGENTS_RESEARCH_CONTACT_EMAIL` (i opcjonalnie `SEMANTIC_SCHOLAR_API_KEY`).
- Forward testy zachowania agentów A01 i A02: wymagają rzeczywistego izolowanego executora hosta
  (Claude/Codex LLM). Rejestr sam stanowi, że brak takiego executora to jawny failure, nie zaliczenie.
- Wszystkie scenariusze packaging/bundle zadań 2 i 3: zablokowane usterką nr 1 (build nie przechodzi).
- Providerzy na poziomie transportu (retry/backoff, `Retry-After`, paginacja, cache hit, limit
  bajtów): pokryta normalizacja i allowlista; pełne ścieżki transportu nie były wyczerpująco
  ćwiczone w tej rundzie (wymagają wstrzykniętego transportu z symulacją kodów HTTP). Status: częściowe.

#### Mapa "co zmienić w 07" po tej rundzie

- Nie zaznaczono pojedynczych scenariuszy TEST 2 i TEST 3: wykonano reprezentatywny podzbiór warstwy
  deterministycznej, nie każdy enumerowany scenariusz, więc checkboxy pozostają puste do pełnego przebiegu.
- Warunki zamknięcia zadań 2 i 3 pozostają odznaczone.
- Dodano blok „Usterki z TEST (zestawy 2 i 3)” z trzema pozycjami do naprawy.

---

### Runda 4 — 2026-06-21 — G02-A10 Output Reviewer, pełny TEST 1A–1E (po migracji namespace g02)

Środowisko: kopia repo (`EduMaterialsAgents-testing1E`), Python 3.10, build i checki w katalogu
lokalnym. Zakres: powtórka całego zestawu 1A–1D na nowym namespace plus pełny TEST 1E (migracja
`research` -> `g02`).

Sanity check ucięć: 0 plików uciętych.

**Werdykt zbiorczy: PASS. Zero usterek. Migracja namespace spójna, zachowanie reviewera bez regresji.**

#### Liczby

- `tests/` (istniejący zestaw): 37 PASS / 0 FAIL.
- Harness reviewera (1A + 1B): 53 PASS / 0 FAIL (po dostosowaniu do enuma `reviewer_agent: g02-a10-output-reviewer`).
- TEST 1E (migracja namespace): 18/18 kontroli strukturalnych PASS + sprawdzenia importów, CLI i bundli PASS.
- `graph_check`: PASS na source, Claude i Codex.
- Build: oba bundle wygenerowane, bez mutacji źródeł i bez osieroconych katalogów po starych nazwach.

#### TEST 1A, kontrakty — PASS

35 sprawdzeń behawioralnych jak w Rundzie 2, na module `g02.review`. Dodatkowo potwierdzono, że
schemat `review_decision@1` wymusza nowy enum `reviewer_agent` (`g02-a10-output-reviewer`); stara
techniczna nazwa reviewera sprzed migracji jest odrzucana, co dowodzi spójności migracji w
kontraktach.

#### TEST 1B, narzędzia deterministyczne — PASS

18 sprawdzeń jak w Rundzie 2, bez regresji. Sześć narzędzi MCP nadal widocznych
(`research_*`, nazwy zachowane wstecznie zgodnie z 1E).

#### TEST 1C, spójność i packaging — PASS

Jeden fizyczny `g02-a10-output-reviewer`; 9 profili producentów; 10 agentów, 18 skilli (źródło i
manifest); MCP `version "0.2.0"` z sześcioma narzędziami; bundle Claude z agentem reviewera i
adapterem prepare/finalize; bundle Codex bez agentów i adaptera Claude; oba bundle z `review.py`,
oboma schematami, `g02_flow.py` i serwerem MCP; `graph_check` host-aware OK na trzech hostach.

#### RETEST 1D — PASS

`tests/` 37/37; `graph_check` source/Claude/Codex `ok: true`; brak pustego katalogu
`skills/g02-review-research-output/agents` w bundlu Codex; brak top-level `agents` w Codex.

#### TEST 1E, migracja namespace — PASS

- Dokładnie jeden `g02.graph.json`; 10 agentów `g02-a01`–`g02-a10`; 18 skilli `g02-*`; brak starych katalogów.
- Każdy agent: `name` == nazwa pliku bez `.md`.
- Każdy `SKILL.md`: `name` == nazwa katalogu, zgodna z `[a-z0-9-]+` i limitem 64 znaków.
- Kody agentów unikalne i ciągłe `a01..a10`.
- 10 skilli `g02-aNN-<skill>` + 8 skilli `g02-<shared>` zgodnie z mapą.
- `plugin.manifest.json` zgodny z fizycznym inventory (agenci i skille), bez braków i duplikatów.
- `g02.graph.json`: `graph_id: g02`, reviewer `g02-a10-output-reviewer`, 9 producer nodes z profilami.
- Brak identyfikatorów i ścieżek sprzed migracji w całym repo: zero trafień.
- Zachowane wstecznie: sześć nazw narzędzi MCP `research_*`, komenda `/research`, kontrakty
  `research_graph_input`, `review_task`, `review_decision`, `envelope`, `user_approved_research_bundle`.
- Importy `g02`, `g02.review`, `g02.g02_flow` działają; CLI `g02_flow.py run` z nowej ścieżki emituje
  `user_approved_research_bundle`.
- Build Claude: 10 agentów o nowych nazwach; build Codex: brak katalogu agentów; oba: 18 skilli,
  `g02_flow.py`, `review.py`, oba schematy, serwer MCP; brak osieroconych katalogów po starych nazwach.

Uwaga: nazwa pliku serwera MCP pozostaje `research_server.py`, a `SERVER_INFO.name` to
`edu-materials-research`. Zgodne z 1E (nazwy narzędzi MCP i komenda bez zmian), więc nie jest to
usterka, a świadoma zgodność wsteczna. Pięć początkowych „FAIL" w harnessie reviewera wynikało ze
starej nazwy `reviewer_agent` w samym harnessie, nie z repo; po dostosowaniu 53/53.

#### Mapa "co zmienić w 07" po tej rundzie

- Zaznaczone: cały blok TEST 1E oraz warunek zamknięcia „TEST 1E namespace".
- Commit zestawu 1: pozostaje odznaczony do akceptacji wyników.
- Zestaw 1 (G02-A10 Output Reviewer) jest technicznie czysty: 1A–1E zaliczone, brak otwartych usterek.

---

### Runda 3 — 2026-06-21 — Zestaw 1, RETEST 1D (poprawki po usterkach z Rundy 2)

Środowisko: kopia repo (`EduMaterialsAgents-testing1`), Python 3.10, build i checki w katalogu
lokalnym. Zakres: retest trzech usterek z Rundy 2 plus pełna lista RETEST 1D z rejestru `07`.

Sanity check ucięć: 0 plików uciętych. Dwa wcześniej obcięte pliki są teraz kompletne
(`graph_check.py` 154 linie, `tests/test_mcp_server.py` 85 linii).

**Werdykt zbiorczy: PASS. Trzy usterki z Rundy 2 naprawione.**

#### Liczby

- `tests/` (istniejący zestaw): 37 PASS / 0 FAIL z 37 (poprzednio 36/37).
- Harness reviewera (1A + 1B): 53 PASS / 0 FAIL (bez regresji).
- `graph_check`: PASS na source, Claude i Codex.

#### Status usterek z Rundy 2

1. NAPRAWIONA. `test_initialize_and_tools_list` oczekuje teraz pełnego zestawu sześciu narzędzi
   (z `research_review_prepare`, `research_review_finalize`). Test przechodzi.
2. NAPRAWIONA. `graph_check` jest host-aware: `resolve_host` rozpoznaje source/Claude/Codex po
   markerach `.claude-plugin/plugin.json` i `.codex-plugin/plugin.json`, można też podać jawny
   `host`. Codex pomija tylko obecność plików agentów, zachowując kontrolę kontraktów reviewera,
   `review_profile` i subgrafów. Wynik: source/claude/codex wszystkie `ok: true`.
3. NAPRAWIONA. Bundle Codex nie zawiera top-level katalogu `agents` ani pustego
   `skills/g02-review-research-output/agents`. Skill reviewera w Codex to samo `SKILL.md`.

#### RETEST 1D, wykonane sprawdzenia

- Sześć narzędzi MCP w `tools/list`: PASS.
- Cały `tests/` bez failures: PASS (37/37).
- Build obu wariantów od czystej kopii, bez mutacji źródeł: PASS.
- `check_all` source -> `host: source`, `ok: true`: PASS.
- `check_all` na bundlu Claude, autodetekcja `claude`, `ok: true`: PASS.
- `check_all` na bundlu Codex, autodetekcja `codex`, `ok: true` mimo braku agentów: PASS.
- Te same trzy kontrole z jawnym `host`: wyniki zgodne z autodetekcją: PASS.
- Nieznany `host` odrzucony `ValueError` ("unsupported graph-check host"): PASS.
- Dwa jednoczesne markery (Claude + Codex z realnymi `plugin.json`) odrzucone
  ("ambiguous plugin host markers"): PASS.
- Source/Claude odrzucają brak fizycznego reviewera oraz brak producer agenta: PASS.
- Codex odrzuca brak kontraktu reviewera: PASS.
- Bundle Codex bez top-level `agents` i bez pustego `skills/.../agents`: PASS.
- Bundle Claude zawiera dokładnie jeden fizyczny `g02-a10-output-reviewer`: PASS.

Uwaga rzetelnościowa: gałąź odrzucania „braku fizycznego skilla” dla węzłów `kind=skill` istnieje
w kodzie, ale `g02.graph.json` nie ma węzłów typu `skill` (skille są wywoływane wewnątrz
agentów, nie jako węzły grafu), więc ten konkretny przypadek jest n/a dla bieżącego grafu.
Sprawdzenie subgrafów pokryte testem `test_core_runtime.py::test_graph_check_subgraph_existence`.

#### Mapa "co zmienić w 07" po tej rundzie

- Zaznaczone: TEST 1C, RETEST 1D oraz wszystkie pozycje listy RETEST 1D.
- Commit zestawu 1: pozostaje odznaczony do akceptacji wyników.
- Zestaw 1 jest technicznie czysty: brak otwartych usterek, wszystkie testy zielone.

---

### Runda 2 — 2026-06-21 — Zestaw 1 (Universal Reviewer), TEST 1A–1C (powtórka na kompletnej kopii)

Środowisko: kompletna kopia repo (`EduMaterialsAgents-testing`), Python 3.10. Build i checki
uruchamiane w katalogu lokalnym (kopia poza zamontowanym FS). `pytest` niedostępny offline, więc
zestaw `tests/` odpalony lekkim runnerem zgodnym z używanym API (`fixture`, `raises`, `tmp_path`,
`monkeypatch`); scenariusze reviewera 1A/1B (brak ich w `tests/`) pokryte osobnym harnessem na
`research/review.py`.

**Werdykt zbiorczy: PASS z trzema usterkami do naprawy (nieblokującymi logiki reviewera).**

Sanity check ucięć: 0 plików `.py`/`.json` uciętych, kluczowe `.md` kończą się poprawnie. Kopia
zdatna do testów.

#### Liczby

- `tests/` (istniejący zestaw): 36 PASS / 1 FAIL z 37.
- Harness reviewera (1A + 1B): 53 PASS / 0 FAIL.
- `graph_check`: PASS na source root i na bundlu Claude; FAIL na bundlu Codex (z projektu, patrz niżej).
- Build: `dist/claude` i `dist/codex` wygenerowane, bez mutacji źródeł.

#### TEST 1A, kontrakty — PASS

35 sprawdzeń behawioralnych zaliczonych: poprawny minimalny `ReviewTask` przechodzi; brak każdego
wymaganego pola odrzucony; deskryptor artefaktu bez `type/ref/schema_version/artifact_version`
odrzucony; `schema_version` != `review_task@1` odrzucony; `ref` bez `artifact://` odrzucony; pola
legacy `artifacts`/`artifact_ref` odrzucone; `attempt>1` bez `previous_decision_ref` odrzucony;
duplikaty i zarezerwowane criterion IDs odrzucone. Decyzje: APPROVED/REVISE/BLOCKED poprawne
przechodzą; nieznany verdict/severity/confidence odrzucony; finding bez pól odrzucony; APPROVED z
findings, REVISE bez findings lub z blockerem, REVISE ze scope innego producenta, BLOCKED bez
blockera lub z `producer_error`, finding z nieautoryzowanym criterion_id — wszystko odrzucone.
Mapowanie severity działa w obu kierunkach.

#### TEST 1B, narzędzia deterministyczne — PASS

18 sprawdzeń zaliczonych: `prepare_review` zwraca dokładnie jeden zhydratowany artefakt; brak
severity rules -> BLOCKED `review_profile_error`; niekompletny input z audit identity -> BLOCKED;
brak audit identity -> envelope `failed` bez decyzji; niedostępny artefakt -> BLOCKED
`external_dependency_blocked`; `artifact://../...` odrzucone; niezgodny kontrakt artefaktu blokuje;
`attempt>1` bez historii blokuje; `finalize_review_decision` zapisuje decyzję w `envelope@1` ze
ścieżką `artifact://`; duplikaty finding IDs odrzucone; brak executora -> BLOCKED; wyjątek executora
-> `failed`; poprawny envelope executora akceptowany; błędny -> `failed`; poprawny `failed` executora
zachowany; artefakt źródłowy niezmieniony; prompt injection w treści pozostaje danymi (profil
nietknięty). Narzędzia `research_review_prepare`/`research_review_finalize` widoczne przez serwer MCP.

#### TEST 1C, spójność i packaging — PASS (z zastrzeżeniami)

PASS: jeden fizyczny `g02-a10-output-reviewer`; 9 profili producentów w grafie; 10 agentów, 18
skilli (źródło i manifest); bundle Claude zawiera `review.py` + oba schematy + agenta reviewera;
bundle Codex zawiera skill reviewera (`SKILL.md`), `review.py`, oba schematy, bez agentów i adaptera
Claude; serwer MCP `version "0.2.0"` z obiema operacjami reviewera; `envelope@1.produced[].path`
używa `artifact://`, a handoff używa `ref`; build nie mutuje źródeł; `graph_check` przechodzi na
source i na bundlu Claude.

#### Usterki do naprawy (zsynchronizowane z 07, sekcja "Usterki z TEST")

1. FAIL `tests/test_mcp_server.py::test_initialize_and_tools_list`: asercja oczekuje 4 narzędzi
   (`research_front_door, research_node_input, research_finalize, research_run_stub`), a serwer
   wystawia 6 (doszły `research_review_prepare`, `research_review_finalize`). To nieaktualny test po
   DEV 1B, nie błąd serwera. Naprawa: dodać oba narzędzia reviewera do oczekiwanego zbioru.
   Plik: `tests/test_mcp_server.py`, ~linia 34.
2. `graph_check` nie jest host-aware: na bundlu Codex (świadomie bez plików agentów) raportuje
   "has no physical agent file" dla reviewera i wszystkich producentów. Albo dodać tryb host-aware,
   albo udokumentować, że graph_check biegnie tylko na source i bundlu Claude.
   Plik: `shared/scripts/core/graph_check.py`.
3. Do potwierdzenia: pusty katalog `agents` w `dist/codex/.../skills/g02-review-research-output`.
   Plik builda: `scripts/build-plugin.py` (`render_skill_adapters`).

Uwaga środowiskowa (nie usterka repo): `build-plugin.py` uruchomiony bezpośrednio na zamontowanym
folderze pada na `shutil.rmtree` (`Operation not permitted`); w katalogu lokalnym build przechodzi.

#### Mapa "co zmienić w 07" po tej rundzie

- TEST 1A, 1B, 1C: zaznaczone wszystkie scenariusze i warunki zamknięcia (wykonane i zaliczone).
- Commit zestawu 1: pozostaje odznaczony do akceptacji wyników i naprawy trzech usterek.
- Dodano blok "Usterki z TEST" z trzema pozycjami do naprawy przed commitem.

---

### Runda 1 — 2026-06-21 — Zestaw 1 (Universal Reviewer), TEST 1A–1C

Środowisko: kopia repo w `testing`, Python 3.10, bez sieci (pip niedostępny), bez `pytest`.

**Werdykt zbiorczy: BLOCKED.** Kopia repo była fizycznie ucięta (transfer/wklejanie, nie błąd
logiki). Pakiet `core` nie importował się, więc testy dynamiczne 1A/1B/1C nie ruszyły. Część
sprawdzeń statycznych i packagingu wykonano.

#### Ucięte pliki (do ponownego, kompletnego wgrania)

Parser potwierdził twardo:

- `.py` (błąd `compile`): `shared/scripts/core/__init__.py`, `core/artifacts.py`, `core/graphs.py`,
  `core/handoff.py`, `core/state.py`, `core/validate_state.py`, `mcp/research_server.py`,
  `research/g02_flow.py`.
- `.json` (błąd `json.load`): `shared/contracts/research_graph_input.schema.json`,
  `contracts/user_approved_research_bundle.schema.json`, `shared/graphs/g02.graph.json`,
  `mocks/g02/research_graph_input.json`.

Ucięte w połowie zdania (wzrokowo): `README.md`, `agents/g02-a10-output-reviewer.md`,
`agents/g02-a01-planner.md`, `commands/research.md`, `skills/g02-review-research-output/SKILL.md`,
`skills/g02-orchestrate-research/SKILL.md`, adaptery `skills/g02-review-research-output/adapters/claude.md`
i `.../codex.md`.

Ocalałe i poprawne: `core/contracts.py`, `event_log.py`, `gate.py`, `graph_check.py`, `paths.py`,
`revision.py`, `locators.py`, `research/review.py`, oraz `review_task.schema.json`,
`review_decision.schema.json`, `envelope.schema.json`.

Uwaga: mieszane końce linii (CRLF plus pojedyncze CR) mimo `eol=lf` w `.gitattributes`. Sygnał, że
transfer nie przeszedł przez normalny checkout gita.

#### TEST 1A, kontrakty — BLOCKED (część zweryfikowana statycznie)

- Trzy schematy 1A kompletne i parsują się: `review_task@1`, `review_decision@1`, `envelope@1`.
- Listy pól wymaganych obu kontraktów reviewera kompletne; `review.py` pokrywa scenariusze
  walidacji (przegląd kodu).
- Scenariusze behawioralne: BLOCKED (import `core` niemożliwy przez ucięty `__init__.py`/`artifacts.py`).

#### TEST 1B, narzędzia deterministyczne — BLOCKED

- 0 z ~35 scenariuszy uruchomione. Zależą od importu `core` i serwera MCP, oba ucięte.
- `graph_check.py` ocalał, ale `check_all` importuje pozostałe moduły `core`.

#### TEST 1C, spójność i packaging — częściowo PASS, reszta BLOCKED

PASS (statycznie/packaging):

- Manifest wskazuje jeden fizyczny `g02-a10-output-reviewer`; 10 agentów, 18 skilli.
- Graf ma 9 profili producentów: `research_plan, domain_candidates, canonical_sources,
  recent_developments, candidate_index, retrieved_corpus, paper_evidence, claim_assessment,
  research_synthesis` (grep; plik grafu nie parsuje się jako JSON).
- Bundle Claude: zawiera `review.py` i oba schematy reviewera.
- Bundle Codex: skill `g02-review-research-output` (samo `SKILL.md`), `review.py`, oba schematy; bez
  agentów plugina i bez adaptera Claude.
- Serwer MCP: `SERVER_INFO version "0.2.0"`, rejestruje `research_review_prepare` i
  `research_review_finalize`.

BLOCKED:

- `graph_check` na source root i na plugin root (ucięty `core`).
- Uruchomienie serwera MCP (ucięty `research_server.py`, linia 169).
- Pełna spójność dokumentacji 00–07 z agentem/skillem reviewera (część plików ucięta).

Środowiskowe (nie błędy repo): `build-plugin.py` na zamontowanym folderze pada na `rmtree`
(`Operation not permitted`); w katalogu lokalnym build przechodzi. Do odpalenia `tests/` jeden do
jednego potrzebny `pytest` (tu offline niedostępny).

Do potwierdzenia po naprawie: pusty katalog `agents` w `skills/g02-review-research-output` w bundlu Codex.

#### Rekomendacje

1. Wgrać kompletne repo przez `git clone`/`git archive`, nie wklejaniem plików.
2. Po wgraniu uruchomić sanity check ucięć (kompilacja `.py`, `json.load` `.json`).
3. Dostarczyć `pytest` do środowiska testowego (wheel offline lub vendoring), by odpalić `tests/`.
4. Build testować w katalogu lokalnym, nie na mount.

#### Mapa "co zmienić w 07" po tej rundzie

- Sekcja "Warunek zamknięcia zadania 1": TEST 1A, 1B, 1C pozostają odznaczone (BLOCKED).
- Żaden checkbox w blokach "TEST 1A/1B/1C" nie do zaznaczenia (brak wykonania behawioralnego).
- Po ponownym wgraniu kompletnego repo: powtórka rundy i aktualizacja checkboxów wg wyników.
