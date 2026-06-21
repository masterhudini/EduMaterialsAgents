# Research Graph, notatka integracyjna dla KH

## 1. Cel

Projekt dotyczy wyłącznie drugiego modułu `EduMaterialsAgents`, czyli Research Graph. Nasza
warstwa przygotuje agentów, współdzielone skille i deterministyczne narzędzia literaturowe.
KH sprawdza zgodność kontraktów granicznych z pozostałymi modułami i dostosowuje systemową
mechanikę repozytorium, manifest, state oraz routing.

Pełny kontekst znajduje się w pozostałych dokumentach tego katalogu. Poniżej są elementy,
które bezpośrednio wpływają na Twoją część.

## 2. Zamknięta decyzja nadrzędna

`[LOCKED PROJECT DECISION: SINGLE-REVIEWER]`

Research Graph ma jedną fizyczną definicję `G02A10OutputReviewerAgent`.

W grafie nadal istnieje wiele logicznych etapów review, na przykład review planu, indeksu,
paper evidence i syntezy. Każdy etap uruchamia ten sam agent z innym `review_profile`.

Konsekwencje:

- repo nie powinno zawierać dziewięciu plików reviewerów,
- manifest potrzebuje rozróżnienia logical node od physical agent reference,
- każdy logical review node wskazuje `g02-a10-output-reviewer`,
- review profile określa producer, acceptance criteria i revision policy,
- `graph_check.py` weryfikuje kontrakty reviewera i profile producentów; w source i bundlu
  Claude sprawdza także physical reviewer reference, a w bundlu Codex respektuje
  `includeAgents: false`,
- plugin rejestruje jeden komponent reviewer.

Ta decyzja nie wymaga ponownego zatwierdzenia. Powinna zostać odzwierciedlona w repo.

## 3. Zatwierdzony kontrakt wejściowy

### `[RESOLVED: RESEARCH-GRAPH-INPUT-CONTRACT]`

Kontrakt został zatwierdzony i wdrożony jako
`shared/contracts/research_graph_input.schema.json`. KH nie musi ponownie podejmować tej decyzji.
Runtime i adaptery hostów powinny walidować dokładnie tę wersję kontraktu.

## 4. Decyzja przekazana do TK

### `[TK-DECISION: CLAIM-ASSESSMENT-MODEL]`

Proponowana ocena claimu ma osobne wymiary:

- `evidence_status`,
- `currency_status`,
- `pedagogical_status`,
- `controversy_status`,
- `confidence`,
- `recommended_action`.

Pytania kontrolne dla TK podczas przeglądu 1b1:

1. Czy downstream może konsumować osobne wymiary?
2. Czy Solution Graph oczekuje pojedynczego statusu kompatybilności?
3. Czy potrzebny jest deterministyczny mapping do starych etykiet `valid`, `obsolete`,
   `too_simplified`, `controversial` i `needs_context`?
4. Czy `recommended_action` powinno należeć do Research Graph, czy zostać ograniczone do
   semantycznej implikacji i przeliczone w Solution Graph?

Możliwe rozstrzygnięcie TK:

- `APPROVE`, model staje się kontraktem,
- `APPROVE_WITH_MAPPING`, model pozostaje i dodajemy etykietę kompatybilności,
- `REVISE`, potrzebna jest zmiana wymiarów uzgadniana wspólnie.

### `[KH-TODO: CODEX-RESEARCH-RUNTIME-ADAPTER]`

Host-specific skille są generowane dla Claude Code i Codex. Wariant Codex nie może jeszcze
wykonać prawdziwego grafu, dopóki warstwa systemowa nie dostarczy:

- rozszerzenia powierzchni MCP o operacje producentów po G02-A02 i kolejnych providerów,
- sposobu uruchamiania fizycznych node agents z ograniczonym input bundle,
- mapowania artifact refs i envelope między hostem a wspólnym runtime,
- testu end-to-end wykonywanego bez no-op node runnera.

Do czasu implementacji adapter Codex ma zakończyć działanie jawnym
`external_dependency_blocked`, zamiast symulować agentów w promptach.

Repo udostępnia obecnie MCP `0.4.0` z czternastoma operacjami dla wejścia grafu, G02-A01,
G02-A02, statusu providerów, wyszukiwania metadanych, uniwersalnego reviewera, finalizacji i
harnessu. TODO nie obejmuje ponownej implementacji tych operacji; pozostaje adapter realnych node
agents oraz narzędzia następnych zestawów.

MCP stanowi granicę wywołania. OpenAlex, Semantic Scholar i arXiv są obsługiwane przez lokalne
adaptery deterministyczne, które stosują limity, retry, rate limiting, cache i zapis proweniencji.
Plik konfiguracji nie zawiera sekretów. KH przekazuje `EMAGENTS_RESEARCH_CONTACT_EMAIL`, wymagany
dla aktywnego OpenAlex `OPENALEX_API_KEY` oraz opcjonalny `SEMANTIC_SCHOLAR_API_KEY` przez
środowisko albo magazyn sekretów hosta.

## 5. Zmiany przepływu względem obecnego repo

Docelowa kolejność:

```text
G02-A01 Planner
→ G02-A02 Domain
→ parallel G02-A03 Canonical Sources and G02-A04 Recent Developments
→ G02-A05 Candidate Source Index
→ Human Source Selection Gate
→ G02-A06 Paper Retrieval
→ G02-A07 Paper Review
→ G02-A08 Claim Verification
→ G02-A09 Synthesizer
→ Human Research Gate
```

Każdy agent wykonawczy jest oceniany przez tę samą fizyczną definicję reviewera.

Istotne zmiany:

- `G02A05CandidateSourceIndexAgent` zastępuje `SourceSelectionAgent`,
- G02-A08 Claim Verification przechodzi za G02-A07 Paper Review,
- przed retrieval dochodzi Human Source Selection Gate,
- G02-A06 Paper Retrieval przyjmuje `HumanApprovedSourceSet`,
- G02-A08 Claim Verification przyjmuje zaakceptowane EvidenceCards,
- Solution Graph otrzymuje kompaktowy handoff bez pełnych PDF-ów.

## 6. Human Source Selection Gate

Runtime powinien wygenerować:

- `candidate_source_index.json`,
- `candidate_source_review.md`.

Orkiestrator pokazuje link lub ścieżkę do Markdown, objaśnia działania i podaje wzór odpowiedzi.
Użytkownik wybiera:

- DOWNLOAD,
- LIBRARY,
- CITATION,
- RESERVE,
- EXCLUDE,
- SEARCH_MORE.

Odpowiedź jest parsowana do `HumanSourceSelection`, pokazywana ponownie i wymaga finalnego
potwierdzenia. `SEARCH_MORE` wraca do odpowiedniego agenta wyszukiwawczego. Akceptowany brak
pokrycia trafia do `coverage_exceptions`.

## 7. Skille wykonawcze

Repo zawiera interaktywny skill orkiestratora oraz nieinteraktywne skille używane przez agentów.

Relacja jest wiele do wielu. Każdy skill ma własny katalog `skills/<name>/SKILL.md`.
Nazwy skilli muszą być globalnie unikalne w obrębie pluginu.

Skille nie wykonują surowych requestów przez LLM. Wywołują narzędzia Research Graph z
kontraktem JSON. Warstwa ta, wraz z adapterami OpenAlex, Semantic Scholar, arXiv, Unpaywall i
usług uzupełniających, normalizacją, deduplikacją, downloaderem i przygotowaniem PDF, należy do
naszego modułu. Dodatkowe zasoby skilla powstają tylko wtedy, gdy kod jest specyficzny dla jego
procedury; narzędzia współdzielone mogą pozostać w `shared/scripts/g02/`.

KH zapewnia uruchamianie agentów i narzędzi przez runtime, przekazywanie ograniczonych input
bundles, storage i resume, konfigurację sekretów oraz integrację human gates z powierzchnią
rozmowy. KH nie odpowiada za implementację klientów usług literaturowych.

Każdy skill posiada neutralny `SKILL.md` i trzy wymagane pliki adapterów hosta. Build renderuje
`dist/claude` albo `dist/codex`, scala host-specific frontmatter, dołącza wyłącznie właściwy
adapter Markdown i instaluje wygenerowaną wersję. Źródłowy skill nie jest modyfikowany.

## 8. Kontrakty wymagane w runtime

Minimalny zestaw:

- wspólny `literature_tool_result@1` dla operacji dostawców,
- research graph input,
- research plan,
- trzy typy candidate sources,
- candidate source index,
- human source selection,
- human approved source set,
- retrieved corpus,
- paper review i evidence card,
- claim assessment state,
- review task,
- review decision,
- research state i evidence map,
- human validation packet,
- human approved research bundle.

Reviewer decision jest artefaktem w `envelope.produced[]`. Nie zastępuje statusu envelope.

## 9. Punkty integracyjne w obecnym repo

Do dalszej integracji:

- rozszerzyć `shared/contracts/` o zatwierdzone kontrakty pośrednie,
- zastąpić no-op execution w `shared/scripts/g02/g02_flow.py` rzeczywistym uruchamianiem
  agentów i ograniczaniem input bundles,
- dodać fan-out/fan-in dla niezależnych wyszukiwań i G02-A07 Paper Review,
- podłączyć deterministyczne narzędzia literaturowe i konfigurację sekretów,
- rozszerzyć testy o contracts, shape checks, revision loops i human gates,
- wyrównać starszy opis Research Graph w `docs/whole_outline.md`.

Deterministyczna powierzchnia reviewera udostępnia `research_review_prepare` i
`research_review_finalize`. Pierwsza operacja waliduje `review_task@1`, ogranicza dostęp do
jednego artefaktu oraz zwraca jego shape validation i historię rewizji. Druga waliduje i
utrwala `review_decision@1`. Wywołanie fizycznego node agenta nadal należy do adaptera runtime.

## 10. Mechanika pozostająca bez zmian

Istniejący core może nadal obsługiwać:

- `envelope@1`,
- state i resume,
- lazy hydration,
- revision policy,
- gate i freeze,
- event log,
- lokalizowanie agentów i skilli.

Należy rozstrzygnąć mapowanie severity między envelope i revision engine oraz sposób
rejestrowania jednego physical reviewer pod wieloma logical nodes.

## 11. Obserwacje techniczne z przeglądu repo

Poniższe punkty pozostają poza treścią agentów i skilli, ale mogą wpływać na integrację:

- `graph_check.py` sprawdza rejestrację komponentów wysyłanych do danego hosta, kontrakty
  reviewera i obecność profili. Source i Claude wymagają physical agent references. Codex
  pomija wyłącznie obecność plików agentów zgodnie z `includeAgents: false`. Checker nie
  weryfikuje jeszcze pełnej zgodności edges, sequence i orchestrator workflow.
- Test `test_graph_check_ok_with_no_manifests` przechodzi przy zerowej liczbie manifestów.
  Po dodaniu Research Graph potrzebne są testy faktycznej zawartości manifestu.
- Minimalny validator JSON Schema obsługuje ograniczony podzbiór specyfikacji. Nowe kontrakty
  muszą używać wspieranego podzbioru albo validator powinien zostać rozszerzony.
- `artifact://` resolver powinien potwierdzać, że rozwiązana ścieżka pozostaje w katalogu
  artifacts. Ma to znaczenie przy refs pochodzących z input bundles.
- Zapis state jest obecnie prostym zapisem pliku. Przy jednym writerze jest spójny z przyjętym
  modelem, ale odporność na przerwanie podczas zapisu może wymagać zapisu atomowego.
- Manifest Codex wskazuje wygenerowany katalog `skills/` pluginu. Build sprawdza, czy wszystkie
  źródłowe skille są zadeklarowane i czy ich nazwy są unikalne.
- Pliki agentów i skilli nie wybierają konkretnego modelu. Jeśli platforma wymaga dodatkowych
  metadata, instalator powinien dodać je bez zmiany wspólnej treści kontraktów i workflow.
- Aktualny `docs/research graph project.md` łączy właściwą specyfikację z przykładami agent,
  skill i state. Przed uznaniem go za źródło prawdy powinien zostać oczyszczony.

## 12. Oczekiwany wynik dalszej integracji

Od KH potrzebna jest implementacja i potwierdzenie:

```text
CODEX-RESEARCH-RUNTIME-ADAPTER: IMPLEMENTED | BLOCKED
MCP_OR_EQUIVALENT_SURFACE: <name and version>
NODE_AGENT_EXECUTION: <mechanism>
END_TO_END_TEST: PASS | FAIL
Notes: ...
```

Decyzję `CLAIM-ASSESSMENT-MODEL` podejmuje TK podczas przeglądu 1b1 właściwego agenta i skilla.

## 13. Aktualizacja integracyjna przed batch commitem, 2026-06-21

W celu umożliwienia testów agentów i skilli przed commitem została uzupełniona warstwa build oraz
instalacji. Zmiany techniczne nie przenoszą odpowiedzialności za runtime systemowy na autora
agentów i skilli. Ich celem jest zapewnienie powtarzalnego środowiska testowego dla obu hostów.

Wprowadzone elementy:

- `plugin.manifest.json` deklaruje komplet 18 skilli i 10 agentów;
- build porównuje manifest z katalogami źródłowymi i przerywa pracę przy pominiętym komponencie;
- build wymaga adapterów Claude i Codex, waliduje neutralny frontmatter, nazwę skilla oraz kodowanie
  UTF-8, a do bundle dołącza tylko adapter wybranego hosta;
- konfiguracja MCP otrzymuje interpreter Pythona użyty do lokalnego builda, zamiast zakładać
  dostępność komendy `python3`;
- wspólny instalator `scripts/install_plugin.py` obsługuje Claude i Codex, `install.sh` pozostaje
  wejściem POSIX, a `install.ps1` wejściem Windows;
- `--dry-run` wykonuje pełny build i walidację w katalogu tymczasowym bez modyfikowania `dist/`,
  rejestrów hosta ani istniejącej instalacji;
- reinstalacja Codex korzysta z katalogu staging, atomowej podmiany i zachowuje timestampowany
  backup poprzedniej wersji;
- `tests/test_plugin_build.py` kontroluje komplet komponentów, izolację adapterów, interpreter MCP,
  niezmienność źródeł i brak skutków ubocznych `--dry-run`;
- dodano `.gitattributes` oraz natywne instrukcje konfiguracji testów dla Windows.

Po tej zmianie pakowanie definicji agentów i skilli jest testowalne na obu hostach. Nadal otwarte
pozostają właściwe zadania integracyjne KH oznaczone `[KH-TODO: CODEX-RESEARCH-RUNTIME-ADAPTER]`:
wykonanie node agents, ograniczanie input bundles po G02-A01, pełny reviewer loop, human gates,
resume i test end-to-end. Deterministyczne klienty literaturowe, downloader i indeks PDF pozostają
w zakresie naszego modułu i będą uzupełniane podczas przeglądu 1b1 agentów oraz skilli.
