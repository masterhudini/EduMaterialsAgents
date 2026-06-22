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
`G02A07PaperReviewAgent` analizuje jeden dokument i zwraca krótką kartę dowodową. G02-A08 Claim
Verification i synteza korzystają z kart, a pełny tekst jest ponownie otwierany tylko przy
konkretnej luce.

## 4. Zamknięte decyzje projektowe

### 4.1. Jeden uniwersalny reviewer

`[LOCKED PROJECT DECISION: SINGLE-REVIEWER]`

W module istnieje jedna fizyczna definicja `G02A10OutputReviewerAgent`. Każdy logiczny etap
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

### 4.2. Kolejność G02-A08 Claim Verification

G02-A08 Claim Verification odbywa się po G02-A07 Paper Review. Przed pobraniem LLM określa wyłącznie
potencjalną przydatność źródła na podstawie abstraktu. Właściwa ocena claimu korzysta z
wydobytych dowodów pełnotekstowych.

### 4.3. Wyszukiwanie bazowe i rozszerzenia

G02-A02 Domain tworzy pulę bazową dla każdego zatwierdzonego topic. Po zatwierdzeniu wyniku
G02-A03 Canonical Sources i G02-A04 Recent Developments rozszerzają tę pulę jako logicznie
niezależne strumienie korzystające z różnych profili wyszukiwania. Bieżący runner wykonuje je
sekwencyjnie; równoległość wymaga przyszłego schedulera fan-out/fan-in.

### 4.4. G02A05CandidateSourceIndexAgent

Dawny `SourceSelectionAgent` zostaje zastąpiony przez `G02A05CandidateSourceIndexAgent`.

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

### 4.9. Stały namespace grafów, agentów i skilli

`[LOCKED PROJECT DECISION: COMPONENT-NAMESPACE-GNN-ANN]`

Docelowe grafy używają kodów `g01` dla Intake Graph, `g02` dla Research Graph i `g03` dla
Solution Graph. Research Graph posiada jedenastu fizycznych agentów `g02-a01`–`g02-a11`.
Techniczna nazwa agenta ma postać `gNN-aNN-<role>` i nie powtarza słowa `research`.

Skill przypisany wyłącznie do jednego fizycznego agenta ma nazwę
`gNN-aNN-<dotychczasowa-nazwa-skilla>`. Skill współdzielony przez kilka agentów, wiele logicznych
węzłów albo cały graf ma nazwę `gNN-<dotychczasowa-nazwa-skilla>`. Część opisowa skilla zachowuje
dotychczasową nazwę i nie otrzymuje osobnego numeru.

Kody są zero-padded, nie zależą od kolejności workflow, pozostają niezmienne i nie są ponownie
wykorzystywane po usunięciu komponentu. Nazwa katalogu agenta lub skilla musi odpowiadać polu
`name`; dozwolone są małe litery, cyfry i myślniki.

### 4.10. Język

Definicje agentów i skilli są po angielsku. `output_language` określa język treści czytanej
przez użytkownika. Domyślną wartością jest `English`. Nazwy pól, identyfikatory, statusy i
wartości kontrolne pozostają po angielsku.

### 4.11. Źródła zamknięte

Źródła zamknięte mogą znajdować się w indeksie, pełnić funkcję canonical anchor i trafiać na
listę dostępu bibliotecznego. Bez dostępu do właściwego fragmentu nie mogą być bezpośrednim
dowodem semantycznym dla claimu.

### 4.12. Domyślne limity

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

W G02-A02 ta granica jest wdrożona przez lokalne, deterministyczne adaptery Python wystawione jako
narzędzia MCP. MCP jest powierzchnią wywołania hosta, a nie mechanizmem synchronizacji baz danych.
Każde wywołanie pobiera ograniczoną stronę API, zapisuje surową odpowiedź i znormalizowany wynik,
po czym zwraca `artifact://` ref. Cache ogranicza ponowne wywołania, lecz nie stanowi kopii indeksu.
Konfiguracja jawna przechowuje wyłącznie limity, ścieżki i włączone usługi. Klucze i kontaktowy
adres e-mail są pobierane ze zmiennych środowiskowych.

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
`g02-a08-claim-verification` i skilla `g02-a08-assess-claim-evidence`. Model rozdziela status dowodowy,
aktualność, jakość dydaktyczną, kontrowersyjność, confidence i rekomendowaną akcję.

### `[RESOLVED: CODEX-RESEARCH-RUNTIME-ADAPTER]`

Instalator generuje host-specific warianty skilli i paczkę wspólnych agentów. Operacja MCP
`research_run_codex` prowadzi `g02_flow.py`, a runner uruchamia każdy node jako izolowany
`codex exec` korzystający z definicji `agents/g02-aNN-*.md`. Scoped inputs etapów po G02-A02,
pełna semantyka kolejnych producentów oraz scheduler fan-out/fan-in są rozwijane osobno.

## 9. Konsekwencje dla aktualnego repozytorium

Repozytorium zawiera dziesięciu agentów wykonawczych, jednego fizycznego reviewera, 20 skilli,
manifest Research Graph oraz zatwierdzony kontrakt wejściowy. Dziesiątym producentem jest scaffold
G02-A11 Market Cases; jego operacje Tavily pozostają zaplanowane po pionowym wycinku A03-A05. Manifest wskazuje
`g02-a10-output-reviewer` jako wspólnego reviewera i przypisuje profil każdemu producentowi.
G02-A05 Candidate Source Index zastąpił Source Selection, G02-A08 Claim Verification znajduje
się po G02-A07 Paper Review, a oba human gates są zapisane jako kroki orkiestratora.

Warstwa uniwersalnego reviewera posiada `review_task@1`, `review_decision@1`, deterministyczne
przygotowanie i finalizację oraz powierzchnię MCP. G02-A01 posiada `research_planner_input@1`,
`research_plan@1`, scoping, walidację, zapis, profil review i obsługę rewizji. G02-A02 posiada
`domain_research_input@1`, `query_plan@1`, `source_record@1`, `literature_tool_result@1` oraz
`domain_candidate_sources@1`, a także trzy pierwsze adaptery discovery. Nadal wymagane są kontrakty
pozostałych producentów, kolejne operacje literaturowe, scoped input bundles kolejnych etapów,
fan-out i fan-in oraz pełne testy zachowania agentów i human gates. Wykonanie node agents, reviewer
loops, terminal gates oraz pause/resume są dostępne w obecnym runtime G02.

Mechanika state, envelope, gate, revision i artifact refs pozostaje wspólnym runtime.
