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
