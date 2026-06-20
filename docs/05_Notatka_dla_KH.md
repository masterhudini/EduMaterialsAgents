# Research Graph, notatka integracyjna dla KH

## 1. Cel

Projekt dotyczy wyłącznie drugiego modułu `EduMaterialsAgents`, czyli Research Graph. Warstwa
treści przygotuje agentów i współdzielone skille. KH sprawdza zgodność kontraktów z pozostałymi
modułami i dostosowuje mechanikę repozytorium, manifest, state, routing oraz integracje.

Pełny kontekst znajduje się w pozostałych dokumentach tego katalogu. Poniżej są elementy,
które bezpośrednio wpływają na Twoją część.

## 2. Zamknięta decyzja nadrzędna

`[LOCKED PROJECT DECISION: SINGLE-REVIEWER]`

Research Graph ma jedną fizyczną definicję `ResearchOutputReviewerAgent`.

W grafie nadal istnieje wiele logicznych etapów review, na przykład review planu, indeksu,
paper evidence i syntezy. Każdy etap uruchamia ten sam agent z innym `review_profile`.

Konsekwencje:

- repo nie powinno zawierać dziewięciu plików reviewerów,
- manifest potrzebuje rozróżnienia logical node od physical agent reference,
- każdy logical review node wskazuje `research-output-reviewer`,
- review profile określa producer, acceptance criteria i revision policy,
- `graph_check.py` powinien weryfikować physical reference, jeśli manifest wprowadzi takie pole,
- plugin rejestruje jeden komponent reviewer.

Ta decyzja nie wymaga ponownego zatwierdzenia. Powinna zostać odzwierciedlona w repo.

## 3. Decyzja KH numer 1

### `[KH-DECISION: RESEARCH-GRAPH-INPUT-CONTRACT]`

Do sprawdzenia jest zgodność proponowanego `ResearchGraphInput` z outputem wcześniejszego
modułu i potrzebami kolejnego modułu.

Najważniejsze pola:

- `human_approved_context`,
- `approved_research_scope`,
- `research_drivers`,
- `claim_cards`,
- `concept_cards`,
- `flow_issue_cards`,
- `update_need_cards`,
- `existing_source_cards`,
- `constraints`,
- `selection_profile`,
- `artifact_refs_for_lazy_hydration`,
- `output_language`.

Pytania kontrolne:

1. Czy wcześniejszy moduł może wytworzyć wszystkie wymagane karty?
2. Czy nazwy stanów i artifact refs są zgodne z istniejącymi kontraktami?
3. Czy `existing_source_cards` powinny wejść przez input, czy lazy hydration?
4. Czy selection limits należą do input bundle, konfiguracji grafu, czy obu z określoną
   kolejnością precedence?
5. Czy `HumanApprovedResearchBundle` zawiera wszystkie dane wymagane przez Solution Graph?

Możliwe rozstrzygnięcie:

- `APPROVE`, kontrakt pasuje,
- `APPROVE_WITH_RENAMES`, znaczenie zostaje, zmieniają się nazwy lub paths,
- `REVISE`, potrzebna jest zmiana semantyczna uzgadniana wspólnie.

## 4. Decyzja KH numer 2

### `[KH-DECISION: CLAIM-ASSESSMENT-MODEL]`

Proponowana ocena claimu ma osobne wymiary:

- `evidence_status`,
- `currency_status`,
- `pedagogical_status`,
- `controversy_status`,
- `confidence`,
- `recommended_action`.

Pytania kontrolne:

1. Czy downstream może konsumować osobne wymiary?
2. Czy Solution Graph oczekuje pojedynczego statusu kompatybilności?
3. Czy potrzebny jest deterministyczny mapping do starych etykiet `valid`, `obsolete`,
   `too_simplified`, `controversial` i `needs_context`?
4. Czy `recommended_action` powinno należeć do Research Graph, czy zostać ograniczone do
   semantycznej implikacji i przeliczone w Solution Graph?

Możliwe rozstrzygnięcie:

- `APPROVE`, model staje się kontraktem,
- `APPROVE_WITH_MAPPING`, model pozostaje i dodajemy etykietę kompatybilności,
- `REVISE`, potrzebna jest zmiana wymiarów uzgadniana wspólnie.

## 5. Zmiany przepływu względem obecnego repo

Docelowa kolejność:

```text
Research Planner
→ Domain Research
→ parallel Canonical Sources and Recent Developments
→ Candidate Source Index
→ Human Source Selection Gate
→ Paper Retrieval
→ Paper Review
→ Claim Verification
→ Research Synthesizer
→ Human Research Gate
```

Każdy agent wykonawczy jest oceniany przez tę samą fizyczną definicję reviewera.

Istotne zmiany:

- `CandidateSourceIndexAgent` zastępuje `SourceSelectionAgent`,
- Claim Verification przechodzi za Paper Review,
- przed retrieval dochodzi Human Source Selection Gate,
- Paper Retrieval przyjmuje `HumanApprovedSourceSet`,
- Claim Verification przyjmuje zaakceptowane EvidenceCards,
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

Obecne `skills/README.md` opisuje głównie interaktywnego orkiestratora. Projekt wymaga także
nieinteraktywnych skilli używanych przez agentów.

Relacja jest wiele do wielu. Każdy skill ma własny katalog `skills/research/<name>/SKILL.md`.
Codex installer spłaszcza katalogi po nazwie, więc nazwy muszą być globalnie unikalne.

Na początku skille nie wymagają `references/`, `scripts/` ani `assets/`.

## 8. Kontrakty wymagane w runtime

Minimalny zestaw:

- research graph input,
- research plan,
- trzy typy candidate sources,
- candidate source index,
- human source selection,
- human approved source set,
- retrieved corpus,
- paper review i evidence card,
- claim assessment state,
- review decision,
- research state i evidence map,
- human validation packet,
- human approved research bundle.

Reviewer decision jest artefaktem w `envelope.produced[]`. Nie zastępuje statusu envelope.

## 9. Punkty integracyjne w obecnym repo

Do aktualizacji:

- `agents/README.md`,
- `skills/README.md`,
- `shared/graphs/README.md`,
- `shared/contracts/README.md`,
- `shared/scripts/research/README.md`,
- `docs/research graph project.md`,
- `plugin.json`.

Do utworzenia:

- `shared/graphs/research.graph.json`,
- kontrakty JSON Schema,
- graph-specific shape checks,
- research flow helpers,
- rejestracje agentów i skilli,
- testy manifestu, contracts, shape checks, revision loops i gates.

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

- `graph_check.py` sprawdza obecnie głównie rejestrację agentów i skilli. Nie weryfikuje jeszcze
  pełnej zgodności edges, sequence, orchestrator workflow i logical-to-physical reviewer refs.
- Test `test_graph_check_ok_with_no_manifests` przechodzi przy zerowej liczbie manifestów.
  Po dodaniu Research Graph potrzebne są testy faktycznej zawartości manifestu.
- Minimalny validator JSON Schema obsługuje ograniczony podzbiór specyfikacji. Nowe kontrakty
  muszą używać wspieranego podzbioru albo validator powinien zostać rozszerzony.
- `artifact://` resolver powinien potwierdzać, że rozwiązana ścieżka pozostaje w katalogu
  artifacts. Ma to znaczenie przy refs pochodzących z input bundles.
- Zapis state jest obecnie prostym zapisem pliku. Przy jednym writerze jest spójny z przyjętym
  modelem, ale odporność na przerwanie podczas zapisu może wymagać zapisu atomowego.
- Installer Codex spłaszcza wszystkie katalogi skilli do globalnego katalogu po nazwie. Nazwy
  skilli Research Graph muszą być unikalne w całym środowisku.
- `agents/README.md` i `skills/README.md` zawierają pola metadata zależne od konkretnej
  platformy, takie jak `model` i `tools`. Wspólna treść projektowana tutaj jest przenośna, a
  platformowe metadata powinny zostać dodane przez warstwę integracyjną.
- `plugin.json` ma puste listy komponentów, więc wszystkie nowe agenty i skille wymagają
  rejestracji.
- Aktualny `docs/research graph project.md` łączy właściwą specyfikację z przykładami agent,
  skill i state. Przed uznaniem go za źródło prawdy powinien zostać oczyszczony.

## 12. Oczekiwany wynik kontroli KH

Po przeglądzie potrzebujemy krótkiej odpowiedzi:

```text
RESEARCH-GRAPH-INPUT-CONTRACT: APPROVE | APPROVE_WITH_RENAMES | REVISE
Notes: ...

CLAIM-ASSESSMENT-MODEL: APPROVE | APPROVE_WITH_MAPPING | REVISE
Notes: ...
```

Po zamknięciu tych dwóch punktów można zamrozić kontrakty v1 i rozpocząć implementację według
backlogu.
