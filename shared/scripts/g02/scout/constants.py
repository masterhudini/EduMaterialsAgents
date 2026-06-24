"""Stałe budżetowe i progi Radara 2.0 — JEDNO miejsce, każda z uzasadnieniem.

Implementacja zasady „reguły ogólne, nie szyte pod zapytanie": wszystkie progi
sterujące planerem, longlistą, snowballem i deduplikacją są tu, wersjonowane w
gicie. Wartości startowe wg specyfikacji docelowej §16; część (zwłaszcza
`FUZZY_TITLE_THRESHOLD`) wymaga kalibracji na realnych danych — patrz spec §18.

Etap 0 (fundament): moduł istnieje i jest importowalny, ale NIE jest jeszcze
wpięty w logikę wyszukiwania (to Etap 1/2). Trzymamy go osobno, żeby kalibracja
i wersjonowanie progów były jawne.
"""

from __future__ import annotations

# — Planer zapytań ————————————————————————————————————————————————
MAX_QUERIES = 20
"""Limit zapytań per przebieg — przeliczony na typowy koszt OpenAlex + S2."""

FACET_CAP = 4
"""Maks. liczba faset; więcej → wykładnicza liczba query z iloczynu kartezjańskiego."""

# — Longlista / shortlista (granica kosztu) ——————————————————————————
LONGLIST_CAP = 500
"""Górna granica przed triage; powyżej rośnie szum bez proporcjonalnego wzrostu recall."""

SHORTLIST_CAP = 60
"""Górna granica przed kosztownym pobraniem i konwersją."""

SOURCE_CAP = 150
"""Miękki limit wyników z jednego źródła przed deduplikacją; zapobiega dominacji
OpenAlex kosztem RePEc/SSRN/arXiv. Kalibrowalny per profil."""

# — Snowballing ————————————————————————————————————————————————————
SNOWBALL_HOPS = 1
"""Dwa skoki wykładniczo zwiększają szum; hop 2 dopiero po udowodnieniu hop 1 na gold-secie."""

SNOWBALL_FANOUT = 15
"""Per praca, per tryb (backward/forward/sibling/author/venue)."""

SNOWBALL_SEEDS = 10
"""Ile TOP prac (po trafności) rozwijamy przez przypisy w jednym hopie. Mało, bo to
najtrafniejsze prace „prowadzą" do fundamentów; więcej = szum + koszt."""

# — Bezpieczniki HTTP (warstwa sieci) ——————————————————————————————
HTTP_MIN_INTERVAL_SECONDS = 0.02
"""Min. odstęp między zapytaniami HTTP do TEGO hosta (≈50/s ceiling). Governor
prędkości: szybko (z kluczem premium OpenAlex), ale nie zalewa API jednym burstem.
Reaktywny retry + Retry-After łapie realne 429 — to tylko miękkie rozsunięcie."""

HTTP_MAX_CALLS_PER_RUN = 500
"""Twardy licznik zapytań HTTP w JEDNYM przebiegu (per wątek run_student). DRUGI,
NIEZALEŻNY bezpiecznik: nawet gdy pacing przepuści, nieskończona ekspansja/pętla
retry NIE zje całego dnia — przekroczenie limitu przerywa przebieg (HttpBudgetExceeded)."""

# — Deduplikacja / uczenie ————————————————————————————————————————
FUZZY_TITLE_THRESHOLD = 0.85
"""Próg fuzzy-title przy scalaniu rekordów. KALIBROWALNY (spec §18): wyższy dla
monografii, niższy dla working papers z wieloma wersjami."""

FEEDBACK_BATCH_SIZE = 30
"""Minimalna liczba werdyktów przed jednorazowym, regularyzowanym bounded re-rankingiem."""
