# Research Graph, dokumentacja projektowa

## Cel zestawu

Ten katalog zbiera uzgodnienia dotyczące drugiego modułu systemu `EduMaterialsAgents`, czyli
`Research Graph`. Dokumenty są podstawą do dalszego podziału pracy między autora agentów,
skilli i deterministycznych narzędzi literaturowych oraz KH, który odpowiada za zgodność z
pozostałymi modułami i systemową warstwą orkiestracji.

Dokumentacja powstała na podstawie:

- `Research graph.md`,
- `Agent example.md`,
- `Skill example.md`,
- `State example.md`,
- `Koncepcja_LitPipe_Modul1_v0.3.md`,
- `LitPipe_Narzedzia_i_API.md`,
- aktualnego szkieletu repozytorium `EduMaterialsAgents`,
- decyzji podjętych w rozmowie projektowej.

Pliki w tym katalogu są częścią repozytorium i stanowią kontekst projektowy Research Graph.

## Dokumenty

1. [01_Kontekst_i_decyzje.md](01_Kontekst_i_decyzje.md)
   
   Cel modułu, zakres, zasady, zamknięte decyzje, granice odpowiedzialności i punkty dla KH.

2. [02_Architektura_agentow_i_skilli.md](02_Architektura_agentow_i_skilli.md)
   
   Docelowy przepływ, lista agentów, jeden uniwersalny reviewer, bramki człowieka oraz mapa
   współdzielonych skilli.

3. [03_Kontrakty_i_artefakty.md](03_Kontrakty_i_artefakty.md)
   
   Projekt wejścia do modułu, artefakty pośrednie, indeks źródeł, decyzje człowieka, macierz
   pokrycia i model oceny claimów.

4. [04_Backlog_i_podzial_pracy.md](04_Backlog_i_podzial_pracy.md)
   
   Kolejność realizacji, zależności, sugerowany podział odpowiedzialności oraz definicje
   ukończenia agentów, skilli i całego modułu.

5. [05_Notatka_dla_KH.md](05_Notatka_dla_KH.md)
   
   Krótkie przekazanie dla KH: decyzja o reviewerze, status integracji hostów i lista
   konsekwencji integracyjnych dla repozytorium.

6. [06_Plan_finalizacji_1b1.md](06_Plan_finalizacji_1b1.md)

   Wykonawczy plan finalizacji Research Graph agent po agencie, z zakresem pionowych wycinków,
   bramkami jakości, kolejnością commitów i końcową integracją.

7. [07_Rejestr_DEV_TEST_1b1.md](07_Rejestr_DEV_TEST_1b1.md)

   Osobna checklista ukończenia implementacji i późniejszych testów dla każdego pionowego
   wycinka.

8. [08_Log_wynikow_TEST.md](08_Log_wynikow_TEST.md)

   Chronologiczny, append-only log rund testowych wykonywanych w niezależnym środowisku, wraz
   z wynikami, usterkami i mapą zmian statusu w rejestrze 07.

## Status decyzji

### Status implementacji warstwy treści

Warstwa definicji zawiera 11 agentów i 20 skilli, w tym jeden uniwersalny reviewer, orkiestrator
oraz zaimplementowane A11 Market Cases, A05 Candidate Source Index i A06 Paper Retrieval. A11 ma scoped input,
deterministyczne operacje Tavily/SearXNG, wariant `candidate_sources@1`, profil review i gated
extraction. A05 ma reviewed-only scoped input, konserwatywną deduplikację, jawny ranking,
candidate coverage oraz generator czytelnego `candidate_source_review.md`. A06 ma dwuetapową
bramkę człowieka, resolvery record/Unpaywall/CORE/DOAB/OAPEN, bezpieczny downloader, walidację PDF
oraz typed deskryptor jednego katalogu wynikowego. Dla każdego zatwierdzonego market case zapisuje
czytelny dokument Markdown z faktem i interpretacją A11 oraz oddzielny JSON audytowy z pobraną
treścią oznaczoną jako niezaufana.

Deterministyczne seams reviewera oraz G02-A01, A02, A03, A04, A11, A05 i A06 są wdrożone. G02-A02 posiada
konfigurację providerów, adaptery OpenAlex, Semantic Scholar i arXiv, cache, retry, rate limiting,
normalizację oraz zapis surowej proweniencji. `g02_flow.py run-codex` uruchamia fizyczne definicje
agentów jako izolowane procesy `codex exec`; tryb `run` pozostaje harness-em no-op do testowania
wiringu i nie jest testem zachowania agentów. Produkcyjny downloader A06 ma domyślnie pomijany
live smoke pobierający rzeczywisty PDF przez Unpaywall. Indeks tekstu PDF, dalsze scoped inputs i
scheduler fan-out/fan-in pozostają kolejnymi etapami.

### Zamknięta decyzja nadrzędna

`[LOCKED PROJECT DECISION: SINGLE-REVIEWER]`

Research Graph posiada jedną fizyczną definicję `G02A10OutputReviewerAgent`. Wszystkie
logiczne etapy kontroli korzystają z tej definicji i przekazują jej specyficzny
`review_profile`. Dokumentacja i repozytorium muszą zostać dostosowane do tej decyzji.

### Status flag projektowych

- `[RESOLVED: RESEARCH-GRAPH-INPUT-CONTRACT]`, kontrakt został zatwierdzony i wdrożony jako
  `shared/contracts/research_graph_input.schema.json`.
- `[TK-DECISION: CLAIM-ASSESSMENT-MODEL]`, decyzja zostanie podjęta z TK podczas przeglądu 1b1
  agenta `g02-a08-claim-verification` i skilla `g02-a08-assess-claim-evidence`.
- `[RESOLVED: CODEX-RESEARCH-RUNTIME-ADAPTER]`, warianty skilli, paczka agentów, MCP
  `research_run_codex` oraz runner izolowanych `codex exec` są wdrożone. Pełny test zachowania
  wszystkich producentów pozostaje osobnym etapem TEST.

`[LOCKED PROJECT DECISION: SINGLE-REVIEWER]` oraz rozwiązany kontrakt wejściowy nie wymagają
dalszych decyzji.

## Język i przenośność

Dokumentacja projektowa jest po polsku. Docelowe definicje agentów i skilli będą pisane po
angielsku. Treści prezentowane użytkownikowi respektują `output_language`, domyślnie
`English`.

Definicje agentów i skilli mają być przenośnym Markdownem dla Claude Code i Codex. Wspólna
warstwa treści nie powinna zawierać wyboru konkretnego modelu ani składni narzędzi zależnej od
jednego dostawcy.

Research Graph obejmuje również własną deterministyczną warstwę narzędziową. Odpowiada ona za
wywołania API indeksów naukowych, normalizację i deduplikację rekordów, rozstrzyganie Open
Access, pobieranie oraz walidację dokumentów i przygotowanie pełnego tekstu do ukierunkowanej
analizy. Skille opisują, kiedy i jak używać tych narzędzi, a kod narzędzi zwraca przenośne dane
strukturalne zamiast logiki zależnej od konkretnego modelu.
