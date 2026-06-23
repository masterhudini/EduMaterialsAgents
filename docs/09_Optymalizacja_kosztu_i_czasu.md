# Optymalizacja kosztu, czasu i effortów Research Graph

Status: profil `fast` wdrożony jako domyślny prototyp; dokładniejsze profile pozostają do późniejszego strojenia.

Data zapisu: 2026-06-23.

Zakres: G02 Research Graph, modele Claude, efforty, koszt tokenowy, czas ścienny, miejsca możliwej optymalizacji bez obniżania wiarygodności naukowej.

## 1. Kontekst

Poprzednie testy pokazały, że schemat G02 potrafi pracować zbyt długo i nie jest optymalny tokenowo. Po ostatniej zmianie macierz modeli i effortów została ustawiona bardziej jakościowo niż kosztowo. Ta notatka zapisuje ocenę aktualnego stanu oraz możliwe dalsze kierunki optymalizacji, jeśli następne testy potwierdzą, że narzędzie ma być tańsze i szybsze.

Aktualizacja po Rundzie 11: ta notatka opisuje już wdrożony domyślny profil `fast`. Obowiązującym
źródłem technicznym pozostaje `shared/graphs/g02.graph.json` oraz frontmatter w
`skills/*/adapters/claude.frontmatter.yaml`.

## 2. Aktualna macierz agentów po ostatnich zmianach

| Agent                            | Model  | Effort | Rola w grafie                                                          |
| -------------------------------- | ------ | ------ | ---------------------------------------------------------------------- |
| `g02-a01-planner`                | sonnet | xhigh  | planowanie zakresu, maksymalnie dwóch priorytetowych topiców            |
| `g02-a02-domain`                 | sonnet | medium | ograniczona pula bazowa źródeł dla topicu                              |
| `g02-a03-canonical-sources`      | sonnet | medium | źródła kanoniczne, citation expansion, role źródeł                     |
| `g02-a04-recent-developments`    | sonnet | medium | aktualne publikacje i recent developments                              |
| `g02-a05-candidate-source-index` | opus   | medium | agregacja, deduplikacja, ranking i human source gate                   |
| `g02-a06-paper-retrieval`        | sonnet | medium | retrieval, OA resolution, download, walidacja dokumentów               |
| `g02-a07-paper-review`           | opus   | medium | ekstrakcja evidence cards z dokumentów lub zatwierdzonych market cases |
| `g02-a08-claim-verification`     | opus   | medium | ocena claimów względem evidence cards                                  |
| `g02-a09-synthesizer`            | opus   | medium | finalna synteza ResearchState, EvidenceMap i handoff                   |
| `g02-a10-output-reviewer`        | sonnet | medium | obowiązkowo A01/A05/A06/A09, warunkowo A02/A03/A04/A07/A11             |
| `g02-a11-market-cases`           | sonnet | medium | przypadki rynkowe przez kontrolowany web discovery                     |

## 3. Aktualne globalne bindingi

| Binding                         | Model  | Effort |
| ------------------------------- | ------ | ------ |
| `cross_artifact_reconciliation` | sonnet | medium |
| `deterministic_technical`       | sonnet | medium |
| `evidence_high_impact`          | opus   | medium |
| `research_planning`             | sonnet | xhigh  |
| `research_search`               | sonnet | medium |
| `synthesis_decision`            | opus   | medium |

Globalne bindingi są sensowne jako domyślne klasy zadań. Rozjazdy między nimi a agentami wynikają z nadpisania per agent. To jest użyteczne, ale trzeba pilnować, żeby nie powstały przypadkowe wysokie efforty tam, gdzie praca jest deterministyczna.

## 4. Aktualna macierz skillów

| Skill                                   | Model  | Effort | Uwagi kosztowe                                                                |
| --------------------------------------- | ------ | ------ | ----------------------------------------------------------------------------- |
| `g02-a01-plan-research-scope`           | sonnet | xhigh  | steruje wyborem maksymalnie dwóch priorytetowych topiców                      |
| `g02-a05-annotate-source-candidates`    | opus   | medium | uzasadnione, wpływa na decyzję człowieka                                      |
| `g02-a05-deduplicate-source-records`    | opus   | medium | potencjalnie do obniżenia, jeśli deduplikacja jest dobrze deterministyczna    |
| `g02-a05-rank-source-candidates`        | opus   | medium | sensowne, bo ranking wpływa na bramkę źródeł                                  |
| `g02-a06-resolve-open-access`           | sonnet | medium | praca w dużej mierze narzędziowa                                              |
| `g02-a06-retrieve-open-access-document` | sonnet | medium | kod obsługuje download i walidację                                            |
| `g02-a06-validate-retrieved-document`   | sonnet | medium | walidacja jest głównie deterministyczna                                       |
| `g02-a07-extract-paper-evidence`        | opus   | medium | koszt skaluje się z liczbą dokumentów                                         |
| `g02-a08-assess-claim-evidence`         | opus   | medium | sensowny kompromis                                                            |
| `g02-a09-synthesize-research-findings`  | opus   | medium | szybszy wariant prototypowy                                                   |
| `g02-a11-extract-case-evidence`         | opus   | medium | używane warunkowo przy market case                                            |
| `g02-a11-find-market-cases`             | sonnet | medium | szybszy profil discovery                                                      |
| `g02-assess-source-coverage`            | opus   | medium | wspólny skill A08/A09                                                         |
| `g02-classify-source-role`              | sonnet | medium | role mają być ograniczone przez kryteria                                      |
| `g02-expand-citation-graph`             | sonnet | medium | fast profile ogranicza szerokość citation expansion                           |
| `g02-expand-research-query`             | sonnet | medium | dobrze zdefiniowane topiki i przykład flat-route                              |
| `g02-normalize-source-metadata`         | sonnet | medium | normalizacja wspierana kodem                                                  |
| `g02-orchestrate-research`              | opus   | low    | sensowne, bo orkiestrator nie powinien wykonywać pracy producentów            |
| `g02-review-research-output`            | sonnet | medium | reviewer ograniczony do najważniejszych etapów albo warunkowych problemów     |
| `g02-search-scholarly-metadata`         | sonnet | medium | provider tools i Crossref walidują rekordy                                    |
| `g02-verify-doi-metadata`               | sonnet | medium | Crossref daje deterministyczny punkt odniesienia                              |

## 5. Ocena aktualnej konfiguracji

Poprzednia konfiguracja miała sens jakościowo, ale nie była dobrze zoptymalizowana kosztowo ani czasowo. Wdrożony profil `fast` przesuwa system w stronę szybkiego prototypu kosztem szerokości discovery i liczby review.

Największe źródła kosztu i czasu:

| Obszar                          | Ocena                                                                                                                                                                   |
| ------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A10 reviewer `sonnet/xhigh`     | Prawdopodobnie za ciężki, bo reviewer pojawia się po prawie każdym producencie. Jedno review na etap ogranicza pętle, ale nadal mnoży koszt przez liczbę etapów.        |
| A01 planner `opus/medium`       | Ryzykowne tokenowo. Planner wcześniej pracował długo, a Opus może wydłużyć planowanie. Tu potrzebny jest raczej krótki, mocno ograniczony plan niż głębsze rozumowanie. |
| A06 retrieval `sonnet/high`     | Za wysoko. To jest w dużej mierze techniczno-deterministyczny agent. Legalność, hash, typ pliku, zgodność DOI i status dostępności powinny być walidowalne narzędziowo. |
| A07 paper review `opus/high`    | Uzasadnione jakościowo, ale potencjalnie największy koszt, bo skaluje się z liczbą dokumentów i długością tekstu.                                                       |
| A09 synthesizer `opus/high`     | Może być zbyt ciężki, jeśli wcześniejsze etapy już produkują dobre evidence cards i claim assessments.                                                                  |
| Serialny przebieg A03, A04, A11 | To jest główny problem czasu ściennego. Po A02 te etapy są logicznie niezależne i mogą iść równolegle.                                                                  |
| Skille współdzielone            | `g02-assess-source-coverage` jako `opus/high` jest konserwatywny, ale kosztowny. Jeden frontmatter dla wielu konsumentów utrudnia precyzyjne strojenie kosztu.          |

## 6. Najważniejsze rekomendacje zmian, jeśli testy potwierdzą problem

Największy zwrot powinny dać zmiany A10, A01, A06 i A09.

| Element                          | Obecnie      | Propozycja optymalna                                           |
| -------------------------------- | ------------ | -------------------------------------------------------------- |
| `g02-a01-planner`                | opus/medium  | sonnet/xhigh                                                   |
| `g02-a02-domain`                 | sonnet/high  | sonnet/medium                                                  |
| `g02-a03-canonical-sources`      | sonnet/high  | sonnet/high zostawić                                           |
| `g02-a04-recent-developments`    | sonnet/high  | sonnet/medium albo high tylko dla tematów z dużą zmiennością   |
| `g02-a05-candidate-source-index` | opus/medium  | opus/medium zostawić                                           |
| `g02-a06-paper-retrieval`        | sonnet/high  | sonnet/medium                                                  |
| `g02-a07-paper-review`           | opus/high    | opus/medium, z eskalacją do high tylko dla trudnych dokumentów |
| `g02-a08-claim-verification`     | opus/medium  | opus/medium zostawić                                           |
| `g02-a09-synthesizer`            | opus/high    | opus/medium                                                    |
| `g02-a10-output-reviewer`        | sonnet/xhigh | sonnet/medium                                                  |
| `g02-a11-market-cases`           | sonnet/high  | sonnet/medium albo high tylko dla ważnych market-case needs    |

Szczególna uwaga: `xhigh` dla A10 trzeba sprawdzić w realnym runtime. Jeśli host nie obsługuje tej wartości albo traktuje ją jako bardzo drogi tryb, należy przejść na `high`, `medium` albo `low`, zależnie od wyników testów. **Jednocześnie trzeba zagwarantować że A10 wywołuje się maksymalnie raz na agenta którego sprawdza, a także trzeba pomyśleć gdzie tego A10 można zlikwidować.**

## 7. Rekomendowana macierz balanced

To jest proponowany kompromis między wiarygodnością i kosztem:

| Agent                            | Model  | Effort          |
| -------------------------------- | ------ | --------------- |
| `g02-a01-planner`                | sonnet | xhigh           |
| `g02-a02-domain`                 | sonnet | medium          |
| `g02-a03-canonical-sources`      | sonnet | high            |
| `g02-a04-recent-developments`    | sonnet | medium          |
| `g02-a05-candidate-source-index` | opus   | medium          |
| `g02-a06-paper-retrieval`        | sonnet | medium          |
| `g02-a07-paper-review`           | opus   | medium          |
| `g02-a08-claim-verification`     | opus   | medium          |
| `g02-a09-synthesizer`            | opus   | medium          |
| `g02-a10-output-reviewer`        | sonnet | medium          |
| `g02-a11-market-cases`           | sonnet | medium lub high |

Jeśli priorytetem jest szybkość, A10 można testowo ustawić nawet na `sonnet/low`, ponieważ deterministic validators powinny wykrywać błędy schematów i braków formalnych.

## 8. Możliwe profile wykonania

Docelowo warto nie przepisywać macierzy ręcznie, tylko dodać profile wykonania. Przykładowe profile:

### 8.1. Profil `fast`

Dla szybkich, tanich przebiegów, w których priorytetem jest orientacyjny research z kontrolowanym ryzykiem.

| Agent | Model            | Effort |
| ----- | ---------------- | ------ |
| A01   | sonnet           | xhigh  |
| A02   | sonnet           | medium |
| A03   | sonnet           | medium |
| A04   | sonnet           | medium |
| A05   | sonnet albo opus | medium |
| A06   | sonnet           | medium |
| A07   | opus             | medium |
| A08   | opus             | medium |
| A09   | opus             | medium |
| A10   | sonnet           | medium |
| A11   | sonnet           | medium |

Warunki bezpieczeństwa dla `fast`: zachować Crossref, zachować walidację kontraktów, zachować
obowiązkowy A10 review dla A01, A05, A06 i A09, uruchamiać A10 warunkowo dla discovery oraz A07 przy
`degraded`, brakujących lokalizacjach, konfliktach evidence, prompt injection albo centralnym
dokumencie, ograniczyć liczbę źródeł i dokumentów.

### 8.2. Profil `balanced`

Dla normalnego użycia edukacyjno-akademickiego, gdzie potrzebna jest wiarygodność, ale narzędzie nie może pracować bardzo długo.

Macierz jak w sekcji 7.

### 8.3. Profil `strict`

Dla zadań o wysokiej stawce, trudnych dokumentów, konfliktów DOI, claimów centralnych dla materiału albo gdy wynik ma trafić do publikowalnego research packa.

| Agent | Model            | Effort           |
| ----- | ---------------- | ---------------- |
| A01   | opus albo sonnet | medium           |
| A02   | sonnet           | high             |
| A03   | sonnet           | high             |
| A04   | sonnet           | high             |
| A05   | opus             | medium           |
| A06   | sonnet           | medium           |
| A07   | opus             | high             |
| A08   | opus             | medium albo high |
| A09   | opus             | high             |
| A10   | sonnet albo opus | medium           |
| A11   | sonnet           | high             |

W profilu `strict` nadal nie ma potrzeby automatycznie ustawiać A10 na najwyższy effort dla każdego etapu. Reviewer powinien być wspierany przez deterministic validation i czytać skrócony pakiet kontrolny, a nie pełne artefakty bez potrzeby.

## 9. Adaptive effort zamiast stałego effortu

Najlepszy kierunek to adaptive effort:

1. Startować od `medium`.
2. Eskalować tylko wtedy, gdy wystąpi jeden z warunków:
   - konflikt Crossref po DOI,
   - sprzeczne evidence cards,
   - brak wymaganego coverage,
   - wysokostawkowy claim centralny dla materiału,
   - duża rozbieżność między źródłami kanonicznymi i recent developments,
   - dokument trudny metodologicznie lub zawierający niejednoznaczne wyniki empiryczne,
   - reviewer widzi błąd materialny, którego deterministic validators nie domykają.
3. Nie eskalować przy brakach czysto formalnych, które da się wykryć i opisać deterministycznie.

Takie podejście pozwala utrzymać wiarygodność tam, gdzie jest potrzebna, bez płacenia najwyższym effortem w każdym przebiegu.

## 10. Najważniejsza poprawka architektoniczna: fan-out po A02

Modele i efforty nie rozwiążą całego problemu. Największy zysk czasu ściennego da równoleglenie logicznie niezależnych etapów po A02.

```mermaid
flowchart TD
    A01["A01 Planner"] --> A02["A02 Domain"]
    A02 --> A03["A03 Canonical Sources"]
    A02 --> A04["A04 Recent Developments"]
    A02 --> A11["A11 Market Cases"]
    A03 --> A05["A05 Candidate Source Index"]
    A04 --> A05
    A11 --> A05
```

To nie zmniejszy liczby tokenów samo w sobie, ale może mocno skrócić czas pracy użytkownika. Aktualny runner wykonuje sekwencję. Docelowy scheduler powinien mieć fan-out/fan-in po zatwierdzonym lub poprawionym A02.

Ryzyka fan-out:

- trzeba dobrze obsłużyć artifact locking i refs,
- `research_run_report@1` musi zachować czytelny porządek wyników,
- błędy w jednym ramieniu nie powinny kasować diagnostyki pozostałych ramion,
- A05 musi przyjmować komplet zatwierdzonych albo poprawionych upstream artifacts.

## 11. Odchudzenie A10 review

A10 powinien być tani, bo jest uruchamiany wiele razy. Największy potencjał:

1. Reviewer powinien dostawać skrócony pakiet kontrolny:
   - `artifact_ref`,
   - typ kontraktu,
   - review profile,
   - deterministic validation summary,
   - listę acceptance criteria z pass/fail/unknown,
   - krótkie delty lub próbki,
   - link do pełnego artefaktu tylko jako fallback.
2. Pełny artefakt powinien być czytany tylko gdy:
   - validation summary wskazuje konflikt,
   - kryterium wymaga oceny semantycznej,
   - producer zwrócił niejednoznaczne lub niekompletne uzasadnienie.
3. `REVISE` powinno być rzadkie:
   - tylko dla materialnych braków,
   - nie dla drobnych uwag stylistycznych,
   - advisory findings powinny pozostać nieblokujące.
4. Dla oczywistych błędów schematu reviewer może być pominięty albo pracować na minimalnym summary, ponieważ schema validator już dostarcza podstawę decyzji.

## 12. Odchudzenie A01 planner

A01 wcześniej pracował długo. Zwiększanie go do Opus może pogorszyć czas i koszt. Planner powinien być sterowany mocnymi ograniczeniami:

- limit topiców,
- limit coverage units,
- limit source roles,
- limit długości uzasadnień,
- zakaz rozwijania adjacent topics poza zatwierdzony scope,
- twarde stop rules,
- brak literatury i brak wyszukiwania.

Jeśli testy pokażą, że A01 nadal jest wolny, pierwsza zmiana powinna być na `sonnet/medium`, ewentualnie `sonnet/high` tylko jeśli plan traci jakość.

## 13. Odchudzenie A06 retrieval

A06 jest dobrym kandydatem do obniżenia effortu. Powód: główna praca powinna być wykonywana przez deterministyczne narzędzia:

- OA resolution,
- sprawdzenie legalnych linków,
- download,
- typ pliku,
- hash,
- rozmiar,
- zgodność DOI,
- zgodność source ID,
- status `available` albo `unavailable`.

Model powinien głównie interpretować wynik narzędzi i przygotować czytelny envelope. Propozycja: `sonnet/medium`, a w profilu `fast` nawet `sonnet/low`.

## 14. Kontrola kosztu A07 paper review

A07 może być największym kosztem w pełnym grafie, bo liczba wywołań rośnie z liczbą dokumentów i claimów.

Zalecenia:

- czytać tylko sekcje wskazane przez indeks tekstu PDF,
- zaczynać od claim-directed retrieval,
- nie przekazywać całego dokumentu, jeśli wystarczy abstract, introduction, methods, results, conclusion albo konkretne strony,
- robić pełniejsze czytanie tylko dla centralnych claimów,
- eskalować effort do high tylko gdy:
  - dokument jest metodologicznie trudny,
  - evidence jest sprzeczne,
  - claim ma wysoką stawkę dla materiału,
  - potrzebna jest interpretacja wyników empirycznych,
  - pojawia się konflikt między paper evidence i recent developments.

Domyślnie A07 może być `opus/medium`, a `opus/high` powinien być trybem selektywnym.

## 15. Kontrola kosztu A09 synthesizer

A09 obecnie jest `opus/high`. To ma sens, jeśli wcześniejsze artefakty są niejednoznaczne albo wynik ma wysoką stawkę. Jeśli jednak A07 i A08 dobrze strukturyzują evidence cards oraz claim assessments, A09 może pracować na `opus/medium`.

Warunki eskalacji A09 do high:

- wiele sprzecznych źródeł,
- dużo unresolved claims,
- ważne rekomendacje aktualizacji materiału,
- konflikt między evidence quality i pedagogical adequacy,
- potrzeba trudnego rozdzielenia claimów empirycznych, normatywnych i dydaktycznych.

## 16. Limity top-K i pruning kandydatów

Tokenowo kosztowne jest przenoszenie zbyt dużej liczby kandydatów do A05 i dalej.

Zalecenia:

- limity per topic,
- limity per provider,
- limity per source role,
- osobny limit dla canonical, recent i market cases,
- wcześniejsze usuwanie duplikatów providerowych,
- zachowanie raw provenance, ale przekazywanie downstream tylko skróconego deskryptora,
- twardy maksymalny rozmiar candidate index przed human gate.

A05 powinien dostać wystarczająco dużo kandydatów, żeby wybór człowieka był sensowny, ale nie pełny dump discovery.

## 17. Cache i deduplikacja wywołań narzędzi

Crossref, Tavily i provider records powinny być maksymalnie cache’owane.

Najważniejsze cache keys:

- Crossref: normalized DOI,
- Tavily: normalized query + source-tier policy + time window + allowed domains,
- OpenAlex/Semantic Scholar/arXiv: provider query + filters + limit + provider version,
- DOI verification result: DOI + provider metadata digest,
- OA resolution: DOI/source ID + approved source descriptor.

Crossref szczególnie powinien być cache’owany po DOI, bo ten sam DOI może wracać w A02, A03, A04, A05 i A06.

Cache hit powinien być zapisany w provenance, ale nie powinien ponownie zużywać requestu ani powodować dodatkowego namysłu modelu.

## 18. Skille współdzielone i problem jednego frontmatter

Niektóre skille są używane przez wielu agentów. Jeden frontmatter oznacza jeden model i effort dla różnych kontekstów.

Przykład: `g02-assess-source-coverage` jest używany przez A08 i A09. Obecnie został ustawiony jako `opus/high`, bo A09 ma wysokie wymagania syntezy. To jest bezpieczne, ale kosztowne.

Możliwe rozwiązania:

1. Zostawić jeden skill, ale dodać profile wykonania i adapter wybierający effort per invocation.
2. Rozdzielić skill na warianty:
   - coverage assessment dla claim verification,
   - coverage assessment dla final synthesis.
3. Utrzymać jeden skill, ale dodać w promptach wyraźne tryby:
   - minimal coverage check,
   - full synthesis coverage check.

Najlepsza opcja długoterminowo: profile albo adaptive effort per invocation, bez mnożenia bytów, jeśli host na to pozwoli.

## 19. Stan wdrożenia fast P0-P8

Wiążąca checklista implementacyjna znajduje się w
[`10_Plan_fast_prototyp_G02_do_Graph03.md`](10_Plan_fast_prototyp_G02_do_Graph03.md).
P0-P8 zostały wdrożone 2026-06-23. Profil `fast` prowadzi przez A07 i reviewed A09, jawnie pomija
A08 przez `skip_nodes`, zatrzymuje się na Human Research Gate i po wznowieniu tworzy kompaktowy
`user_approved_research_bundle@1` dla Graph03. Przygotowane testy P6-P8 czekają na osobne środowisko
TEST; nie dopisano wyników PASS.
