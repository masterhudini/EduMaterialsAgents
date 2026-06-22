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
oraz scaffold A11 Market Cases z dwoma skillami. Definicje A11 opisują docelowy kontrakt pracy;
deterministyczny seam Tavily pozostaje zaplanowany razem z pionowym wycinkiem A11.

Deterministyczne seams reviewera, G02-A01 Plannera i G02-A02 Domain są wdrożone. G02-A02 posiada
konfigurację providerów, adaptery OpenAlex, Semantic Scholar i arXiv, cache, retry, rate limiting,
normalizację oraz zapis surowej proweniencji. Downloader, indeks tekstu PDF oraz rzeczywiste
wywoływanie agentów przez `g02_flow.py` pozostają kolejnymi etapami. Obecny tryb `run` w Pythonie
jest harness-em no-op dla całego grafu, a nie testem zachowania agentów.

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
- `[KH-TODO: CODEX-RESEARCH-RUNTIME-ADAPTER]`, warianty skilli dla Codex i narzędzia MCP do G02-A02
  są generowane, ale wykonanie prawdziwych node agents nadal wymaga adaptera runtime hosta.

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
