# Research Graph, dokumentacja projektowa

## Cel zestawu

Ten katalog zbiera uzgodnienia dotyczące drugiego modułu systemu `EduMaterialsAgents`, czyli
`Research Graph`. Dokumenty są podstawą do dalszego podziału pracy między autora agentów i
skilli oraz KH, który odpowiada za zgodność z pozostałymi modułami i warstwą orkiestracji.

Dokumentacja powstała na podstawie:

- `Research graph.md`,
- `Agent example.md`,
- `Skill example.md`,
- `State example.md`,
- `Koncepcja_LitPipe_Modul1_v0.3.md`,
- `LitPipe_Narzedzia_i_API.md`,
- aktualnego szkieletu repozytorium `EduMaterialsAgents`,
- decyzji podjętych w rozmowie projektowej.

Pliki w tym katalogu nie zostały dodane do repozytorium. Można je przenieść do repo po
uzgodnieniu lokalizacji i nazw.

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
   
   Krótkie przekazanie dla KH: decyzja o reviewerze, dwa punkty wymagające kontroli i lista
   konsekwencji integracyjnych dla repozytorium.

## Status decyzji

### Zamknięta decyzja nadrzędna

`[LOCKED PROJECT DECISION: SINGLE-REVIEWER]`

Research Graph posiada jedną fizyczną definicję `ResearchOutputReviewerAgent`. Wszystkie
logiczne etapy kontroli korzystają z tej definicji i przekazują jej specyficzny
`review_profile`. Dokumentacja i repozytorium muszą zostać dostosowane do tej decyzji.

### Punkty wymagające kontroli KH

W dokumentacji występują dokładnie dwie flagi dla KH:

- `[KH-DECISION: RESEARCH-GRAPH-INPUT-CONTRACT]`,
- `[KH-DECISION: CLAIM-ASSESSMENT-MODEL]`.

Pozostałe decyzje są przyjętymi założeniami modułu albo kwestiami implementacyjnymi do
wykonania zgodnie z backlogiem.

## Język i przenośność

Dokumentacja projektowa jest po polsku. Docelowe definicje agentów i skilli będą pisane po
angielsku. Treści prezentowane użytkownikowi respektują `output_language`, domyślnie
`English`.

Definicje agentów i skilli mają być przenośnym Markdownem dla Claude Code i Codex. Wspólna
warstwa treści nie powinna zawierać wyboru konkretnego modelu ani składni narzędzi zależnej od
jednego dostawcy.
