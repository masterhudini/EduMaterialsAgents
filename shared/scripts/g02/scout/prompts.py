"""Prompty LLM Scouta jako KOD (prompt-as-code) — jedno wersjonowane źródło prawdy.

Wzorzec przeniesiony z projektu n8n (Tutorial_FINAL): prompty trzymamy jako jawne
stałe/funkcje, nie inline w logice — żeby były (a) diffowalne w przeglądzie,
(b) benchowalne offline (patrz bench/replay_expand.py) bez uruchamiania sieci.

Każda funkcja zwraca treść `system` promptu. Część użytkownika (`user`) buduje
wołający, bo zawiera dane wejściowe runu.
"""

from __future__ import annotations


def translate_system(lang_name: str) -> str:
    """System prompt do tłumaczenia zapytania na `lang_name` jako słowa kluczowe."""
    return (
        "You translate academic literature search queries. Translate the user's query to "
        f"{lang_name} as concise SEARCH KEYWORDS: domain terms only, no filler words, no quotes, "
        "one line. Preserve technical terms and acronyms (e.g. GNN, VaR, GARCH). "
        "Return ONLY the translated query, nothing else."
    )


def expand_system(lang_name: str) -> str:
    """System prompt do EKSPANSJI zapytania (recall): curated query + zestaw słów
    kluczowych z synonimami + etykieta domeny. Odpowiednik węzła `Translate &
    Keywords` z n8n, który emituje {openalex_query, keywords[], domain}."""
    return (
        "You expand academic literature search queries to improve recall. "
        f"Given the user's topic, return a JSON object with three fields, all in {lang_name}:\n"
        "1. \"query\": a concise search query (domain terms only, no filler words, no quotes), "
        "preserving technical acronyms (e.g. GNN, VaR, GARCH);\n"
        "2. \"keywords\": an array of 4-8 distinct domain keywords or short phrases, INCLUDING "
        "synonyms and alternative phrasings that relevant papers might use, preserving acronyms;\n"
        "3. \"domain\": a short field label (e.g. \"quantitative finance / econometrics\").\n"
        "Return ONLY the JSON object, nothing else."
    )


def relevance_system(summary_words: int) -> str:
    """System prompt werdyktu trafności (po pobraniu PDF): JSON relevant/score/
    summary/reason. Zachowany 1:1 z dotychczasowej logiki."""
    return (
        "Jestes asystentem selekcji literatury. Ocen, czy ARTYKUL jest NA TEMAT "
        "wzgledem zapytania i (jesli podana) intencji uzytkownika. Odpowiedz "
        "WYLACZNIE obiektem JSON: {\"relevant\": 0 lub 1, \"score\": liczba 0..1 (pewnosc ze NA TEMAT), "
        f"\"summary\": \"streszczenie ~{summary_words} slow PL: co badano/metoda -> glowny wynik\", "
        "\"reason\": \"krotkie uzasadnienie PL\"}."
    )
