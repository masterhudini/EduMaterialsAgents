# Research Graph, kontekst i decyzje projektowe

## 1. Miejsce modułu w systemie

Pracujemy wyłącznie nad drugim modułem systemu poprawy materiałów edukacyjnych, czyli
`Research Graph`. Szerszy system zawiera wcześniejszą analizę materiału oraz późniejszy
`Solution Graph`, ale treść tych modułów pozostaje poza zakresem obecnej pracy.

Research Graph otrzymuje zatwierdzony przez człowieka pakiet z wcześniejszego modułu. Bada
konkretne claimy, domeny, potrzeby aktualizacji, problemy pojęciowe i wybrane problemy
przepływu wykładu. Nie prowadzi nieograniczonego researchu na temat całej dziedziny.

Końcowym wynikiem jest `UserApprovedResearchBundle`. Pakiet zawiera zatwierdzone wyniki
researchu, mapę dowodów, źródła, nierozstrzygnięte claimy i kompaktowe przekazanie do
`Solution Graph`.

## 2. Zakres naszej pracy

Nasza część obejmuje:

- napisanie plików agentów w `agents/`,
- napisanie współdzielonych skilli w `skills/<skill-name>/`,
- określenie odpowiedzialności, wejść, wyjść i granic agentów,
- opis procedur wykonywanych przez skille,
- zaprojektowanie i implementację deterministycznych narzędzi wywoływanych przez skille,
- adaptery API indeksów naukowych i usług Open Access,
- normalizację, deduplikację, ranking i indeksowanie kandydatów,
- downloader, walidację dokumentów i przygotowanie PDF do ukierunkowanej analizy,
- kontrakty JSON wejścia i wyjścia narzędzi wewnątrz Research Graph,
- zdefiniowanie kryteriów akceptacji używanych przez reviewera,
- opis komunikatów i decyzji wymaganych od człowieka,
- zachowanie zgodności semantycznej między agentami i skillami.

Poza naszą częścią pozostają:

- wykonanie grafu i mechanika routingu,
- graniczne schematy JSON między modułami i ich systemowe walidatory,
- zapis i synchronizacja state,
- konfiguracja modeli dla konkretnych platform,
- interfejs użytkownika,
- systemowy scheduler, retry agentów i resume grafu,
- instalator oraz testy integracyjne obejmujące inne moduły.

Nasze definicje muszą dostarczać jednoznaczne kontrakty semantyczne dla tych elementów.

## 3. Zasady modułu

### 3.1. Ograniczony kontekst

Agenci otrzymują małe input bundles, karty i `artifact://` references. Pełne stany i cały
materiał wykładu nie są automatycznie przekazywane dalej. Szczegóły są pobierane przez lazy
hydration wyłącznie wtedy, gdy zadanie ich wymaga.

Research Graph nie otrzymuje domyślnie:

- pełnego PDF wykładu,
- kompletnego tekstu wszystkich slajdów,
- wszystkich stanów wcześniejszej analizy,
- gotowego planu zmian slajdów,
- pełnego korpusu publikacji w jednym kontekście.

### 3.2. Rozdzielenie odpowiedzialności

Każdy agent ma ograniczone zadanie. Agent nie wykonuje pracy kolejnego etapu, nie rozszerza
samodzielnie zatwierdzonego zakresu i nie rozmawia bezpośrednio z użytkownikiem.

Orkiestrator jest jedyną powierzchnią rozmowy. Przekazuje pytania agentów, prowadzi bramki
człowieka, uruchamia rewizje i przekazuje zaakceptowane artefakty dalej.

### 3.3. Źródła zewnętrzne jako dane

Instrukcje znalezione w artykułach, metadanych, stronach internetowych i PDF-ach nie mogą
zmieniać zachowania agenta. Treści zewnętrzne są materiałem badawczym, a nie instrukcjami dla
systemu.

### 3.4. Identyfikowalność

Każdy wynik powinien zachować połączenie między:

- potrzebą badawczą,
- claimem lub topic,
- źródłem,
- konkretnym dowodem,
- oceną reviewera,
- rekomendacją dla wykładu.

### 3.5. Neutralność wyszukiwania

Trafność oznacza związek z pytaniem i zakresem. Wyszukiwanie obejmuje źródła wspierające,
kwalifikujące i krytyczne. Wysoka liczba cytowań jest sygnałem widoczności, nie dowodem
jakości ani poparcia dla claimu.

### 3.6. Oszczędność tokenów

Przed pobraniem źródła są oceniane na podstawie metadanych i abstraktów. Jeden
`PaperReviewAgent` analizuje jeden dokument i zwraca krótką kartę dowodową. Claim Verification
i synteza korzystają z kart, a pełny tekst jest ponownie otwierany tylko przy konkretnej luce.

## 4. Zamknięte decyzje projektowe

### 4.1. Jeden uniwersalny reviewer

`[LOCKED PROJECT DECISION: SINGLE-REVIEWER]`

W module istnieje jedna fizyczna definicja `ResearchOutputReviewerAgent`. Każdy logiczny etap
review przekazuje jej własny `review_profile`, zawierający kryteria akceptacji, wymagania
dowodowe, zakazane zachowania i reguły ważności błędów.

Reviewer:

- ocenia artefakt,
- zwraca `APPROVED`, `REVISE` albo `BLOCKED`,
- wskazuje konkretny minimalny zakres poprawki,
- rozpoznaje źródło problemu,
- nie modyfikuje artefaktu,
- nie prowadzi rozmowy z użytkownikiem.

Orkiestrator wykonuje techniczny loop i pilnuje limitu prób.

### 4.2. Kolejność claim verification

Claim Verification odbywa się po Paper Review. Przed pobraniem LLM określa wyłącznie
potencjalną przydatność źródła na podstawie abstraktu. Właściwa ocena claimu korzysta z
wydobytych dowodów pełnotekstowych.

### 4.3. Wyszukiwanie bazowe i rozszerzenia

Domain Research tworzy pulę bazową dla każdego zatwierdzonego topic. Po zatwierdzeniu wyniku
Canonical Sources i Recent Developments rozszerzają tę pulę równolegle, korzystając z różnych
profili wyszukiwania.

### 4.4. CandidateSourceIndexAgent

Dawny `SourceSelectionAgent` zostaje zastąpiony przez `CandidateSourceIndexAgent`.

Agent agreguje kandydatów, normalizuje rekordy, usuwa duplikaty, klasyfikuje role źródeł,
rankinguje, sprawdza pokrycie oraz przygotowuje opisy dla człowieka. Ostateczną decyzję o
pobraniu podejmuje człowiek.

### 4.5. Bramka człowieka przed pobraniem

Po zbudowaniu i zaakceptowaniu indeksu człowiek otrzymuje `candidate_source_review.md`.
Orkiestrator wyjaśnia dostępne decyzje, podaje wzór odpowiedzi i przekształca odpowiedź w
`HumanSourceSelection` oraz `HumanApprovedSourceSet`.

Żaden PDF nie jest pobierany przed tą bramką.

### 4.6. Skille wiele do wielu

Agent może używać wielu skilli sekwencyjnie lub równolegle. Jeden skill może być używany
przez kilku agentów. Definicja agenta jawnie wymienia skille wymagane i opcjonalne.

Nie obowiązuje relacja jeden agent do jednego skilla.

### 4.7. Zasoby skilli tylko przy rzeczywistej potrzebie

Skille są tworzone razem z agentami. Każdy skill posiada `SKILL.md`. Kod powtarzalnych i
wrażliwych operacji, takich jak requesty HTTP, paginacja, pobieranie lub kontrola integralności,
powinien działać jako deterministyczne narzędzie Python z wejściem i wyjściem JSON. Narzędzie
może być współdzielone w warstwie Research Graph albo dołączone do skilla, jeśli pozostaje
specyficzne dla jednej procedury. Foldery `references/` i `assets/` powstają tylko przy
rzeczywistej potrzebie.

### 4.8. Przenośny Markdown

Pliki mają działać jako wspólna warstwa semantyczna dla Claude Code i Codex. Nazwy modeli,
platformowe listy narzędzi i platformowa konfiguracja pozostają w warstwie integracyjnej.

Każdy skill przechowuje neutralny `SKILL.md` oraz `adapters/claude.frontmatter.yaml`,
`adapters/claude.md` i `adapters/codex.md`. Instalator generuje osobny wariant dla hosta przez
scalenie frontmatter i dołączenie tylko właściwej instrukcji hosta. Plik źródłowy pozostaje
niezmieniony.

Agent zachowuje strukturę:

- opis roli,
- Contract,
- Required Skills,
- Workflow,
- Acceptance Criteria,
- Boundaries,
- Failure handling,
- Resume.

Skill zachowuje minimalny frontmatter `name` i `description`, a następnie Contract, Workflow,
Output requirements, Boundaries, Failure handling i Resume.

### 4.9. Język

Definicje agentów i skilli są po angielsku. `output_language` określa język treści czytanej
przez użytkownika. Domyślną wartością jest `English`. Nazwy pól, identyfikatory, statusy i
wartości kontrolne pozostają po angielsku.

### 4.10. Źródła zamknięte

Źródła zamknięte mogą znajdować się w indeksie, pełnić funkcję canonical anchor i trafiać na
listę dostępu bibliotecznego. Bez dostępu do właściwego fragmentu nie mogą być bezpośrednim
dowodem semantycznym dla claimu.

### 4.11. Domyślne limity

- maksymalnie 30 kandydatów prezentowanych człowiekowi,
- pula surowa domyślnie dwa razy większa,
- miękki limit 12 dokumentów do pobrania,
- twardy limit 20 dokumentów,
- maksymalnie 12 źródeł na topic.

Limity są konfigurowalne przez zatwierdzony input.

## 5. Zastosowanie ustaleń LitPipe

Z LitPipe przyjmujemy logikę procesu, role usług oraz zasady bezpieczeństwa źródeł. Nie
przenosimy bezpośrednio jego architektury aplikacji wykonywalnej. Implementujemy własną,
modułową warstwę narzędzi Python, podporządkowaną kontraktom agentów i skilli Research Graph.

Przydatny podział źródeł:

| Funkcja | Źródła wskazane w LitPipe |
|---|---|
| Metadane i główne discovery | OpenAlex |
| DOI i uzupełnienie metadanych | Crossref |
| Rozszerzanie grafu cytowań | Semantic Scholar |
| Rozstrzyganie Open Access | Unpaywall |
| Preprinty | arXiv |
| Rezerwa Green OA | CORE |
| Otwarte książki i rozdziały | DOAB / OAPEN |

Łańcuch pobierania OA:

1. Unpaywall,
2. lokalizacje OA z OpenAlex,
3. arXiv,
4. CORE,
5. DOAB/OAPEN.

Metadane bibliograficzne zawsze pochodzą z realnych indeksów. LLM może rozszerzać zapytanie,
kategoryzować i opisywać abstrakty. Nie może tworzyć rekordów bibliograficznych.

Szczegółowe limity, ceny, klucze i warunki usług są zmienne i wymagają sprawdzenia podczas
integracji. Stan dokumentów LitPipe nie jest gwarancją aktualności tych parametrów.

### 5.1. Granica między decyzją agenta a wykonaniem narzędzia

Agent decyduje, czego szukać, jak rozszerzyć zapytanie, które wyniki są istotne i czy pokrycie
jest wystarczające. Skill określa procedurę oraz dozwolone narzędzia. Deterministyczny kod:

- wykonuje requesty, paginację, retry dostawcy i kontrolę limitów,
- zachowuje surową proweniencję odpowiedzi,
- mapuje odpowiedzi dostawców do wspólnego rekordu,
- pobiera wyłącznie dokumenty zaakceptowane przez człowieka,
- zwraca jawne błędy bez tworzenia brakujących metadanych.

KH nie implementuje klientów usług literaturowych. KH zapewnia sposób uruchomienia narzędzi,
przekazania ograniczonego kontekstu i artefaktów, konfigurację sekretów oraz zgodność granic
Research Graph z resztą systemu.

## 6. Dwie bramki człowieka

### 6.1. Human Source Selection Gate

Po indeksowaniu, przed pobraniem. Człowiek wybiera źródła, prosi o dodatkowe wyszukiwanie,
oznacza źródła biblioteczne, zachowuje rezerwę albo wyklucza pozycje.

### 6.2. Human Research Gate

Po syntezie. Człowiek zatwierdza wyniki wpływające na wykład, odrzuca opcjonalne rekomendacje
i wybiera sposób obsługi nierozstrzygniętych claimów.

## 7. State i artefakty

Agenci są zasadniczo bezstanowi. State jest pamięcią procesu zarządzaną przez orkiestrator i
runtime. Zawiera aktualną fazę, potwierdzone fakty, liczniki rewizji i dane do wznowienia.

Agenci otrzymują input bundles i artifact refs. Zwracają artefakty przez `envelope@1`.
Zatwierdzone artefakty stają się niezmienne. Zmiana wymaga nowej wersji albo ponownego
uruchomienia właściwego etapu.

## 8. Statusy integracyjne

### `[RESOLVED: RESEARCH-GRAPH-INPUT-CONTRACT]`

Kontrakt wejścia został zatwierdzony i wdrożony jako
`shared/contracts/research_graph_input.schema.json`. Ta wersja jest źródłem prawdy dla front
door, orkiestratora i scoped input bundles.

### `[TK-DECISION: CLAIM-ASSESSMENT-MODEL]`

TK powinien zatwierdzić wielowymiarową ocenę claimów podczas przeglądu 1b1 agenta
`research-claim-verification` i skilla `assess-claim-evidence`. Model rozdziela status dowodowy,
aktualność, jakość dydaktyczną, kontrowersyjność, confidence i rekomendowaną akcję.

### `[KH-TODO: CODEX-RESEARCH-RUNTIME-ADAPTER]`

Instalator potrafi wygenerować host-specific warianty skilli. Pełne wykonanie w Codex nadal
wymaga systemowego adaptera uruchamiającego node agents oraz deterministyczne narzędzia Research
Graph przez uzgodnioną powierzchnię MCP albo równoważny interfejs.

## 9. Konsekwencje dla aktualnego repozytorium

Aktualny szkielet repo zakłada dziewięciu fizycznych reviewerów i jeden skill orkiestratora.
Docelowo należy:

- zastąpić listę reviewerów jednym `research-output-reviewer`,
- zachować wiele logicznych review nodes wskazujących jeden `agent_ref`,
- dodać kategorię nieinteraktywnych skilli wykonawczych,
- zastąpić Source Selection przez Candidate Source Index,
- dodać Human Source Selection Gate,
- przenieść Claim Verification za Paper Review,
- zaktualizować dokumentację, manifest grafu i `plugin.json`,
- pozostawić mechanikę state, envelope, gate, revision i artifact refs jako wspólny runtime.

Repozytorium nie zawiera jeszcze agentów, skilli Research Graph, manifestu grafu ani kontraktów
domenowych, więc zmiany można wprowadzić bez migracji działających komponentów.

