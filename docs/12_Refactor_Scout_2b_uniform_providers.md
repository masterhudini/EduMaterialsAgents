# 12. Refactor Scout — Faza 2b: uniform providers + lean `fetch` (ODŁOŻONE)

Status: **odłożone**. Plan zapisany 2026-06-25, do powrotu po domknięciu integracji Scout (M1–M6,
patrz `docs/11`) — albo wcale, jeśli Faza 2a okaże się wystarczająca.

## Kontekst
Faza 1 (zrobiona): usunięto martwy balast Scouta (`app_config.py`, `state_store.py`, `projects.py`,
`secret_store.py`, ≈1485 linii — zero importów w aktywnej ścieżce).

Faza 2a (robiona teraz): cięcie inert-kodu z `engine.py` (LLM/OpenRouter — grupa E, snowball — F,
export/biblio/converter — H) + **gate źródeł w `run_student`** (param `sources`/`include_openalex`,
naprawia „skip OpenAlex" bez ekstrakcji providerów). Po 2a `engine.py` ≈ 1200–1300 linii, OpenAlex-skip
działa, zero przepisywania orkiestracji.

Faza 2b (TEN dokument): pełna czystość architektoniczna — jeden rejestr providerów + cienki driver.
Wyższe ryzyko, bo przepisuje przetestowaną orkiestrację `run_student`. Dlatego odłożone.

## Cel 2b
`scout/` jako lean, EduMaterials-native rdzeń, gdzie **każde źródło to uniform provider** wybierany
jawną listą, a `fetch` to cienki driver. Zero wbudowanych źródeł w `engine`.

## Co się zmienia (mapa funkcji)

1. **Ekstrakcja OpenAlex z `engine.py` → `providers.py` jako `OpenAlexProvider`.**
   Przenoszone: `openalex_search`, `parse_openalex_work`, `_oa_filter`, `openalex_match_count`,
   `_openalex_get`, `_short_oa_id`, `verify_openalex_key`. OA-resolver `unpaywall_pdf_urls` jako
   `Resolver` w rejestrze. Interfejs jak istniejący `SearchProvider`/`Resolver` Protocol.

2. **Ekstrakcja Semantic Scholar → `S2Provider`.**
   Przenoszone: `semantic_scholar_extend`, `semantic_scholar_pdf` (resolver).

3. **arXiv** już ma `ArxivProvider` w `providers.py`; `arxiv_search_pdf`/`_arxiv_variants`
   (resolver) konsolidują się jako `Resolver`.

4. **Jeden rejestr** w `providers.py`: `build_search_providers(sources)` i `build_resolvers(sources)`
   obejmują OpenAlex/S2/arXiv/CORE/Crossref jednolicie. `parse_sources`/`scout_sources(tier)` sterują
   pełną listą — OpenAlex-skip jest wtedy naturalny (nie ma go na liście), bez gate'a z 2a.

5. **`run_student` → cienki `fetch(scout_search_request, sources, *, store=None)`** w `engine.py`
   (albo nowy `scout/fetch.py`):
   - dla każdego requestu: `search(wybrane providery)` → `_dedup_versions` → `prerank_candidates` →
     `resolve_and_download` → `rank_items` → `RunResult`.
   - **wycięte na stałe:** LLM/OpenRouter (E), snowball (F), `_write_manifest` (zastąpione artefaktem
     `scout_retrieved_corpus@1`), SQLite-hooki (store=None na stałe).
   - **zostaje:** search/dedup/prerank/download/rank — przeniesione 1:1, bez zmiany logiki.

6. **Cut nieużywanych providerów** (po audycie): `ConsensusProvider`, `PerplexityProvider` (LLM-owe,
   płatne, niepotrzebne w trybie deterministycznym + a07).

## Oczekiwany efekt
`scout/` z ~4600 (przed Fazą 1) → ~1000–1500 linii. `engine.py` przestaje być monolitem; staje się
biblioteką providerów + cienkim `fetch`.

## Ryzyko i dlaczego odłożone
- Przepisanie orkiestracji `run_student` (przeniesienie search/dedup/download/rank do `fetch`) dotyka
  przetestowanej ścieżki — wymaga starannego portu testów Scouta i porównania wynik-do-wyniku.
- Funkcjonalnie **2a wystarcza** (gate załatwia OpenAlex-skip), więc 2b to czystość, nie konieczność.
- **Trade-off:** 2b = trwały rozjazd z upstream `llmwiki_radar` (przejmujemy własność lean-kodu, brak
  łatwego merge'a w górę). Świadoma decyzja, do podjęcia osobno.

## Definicja gotowości 2b
`fetch` daje ten sam typ wyniku co dziś `run_student` (RunResult/`scout_retrieved_corpus@1`) na tych
samych wejściach; testy providerów i `fetch` zielone; `scout_sources(tier)` steruje całą listą źródeł
(w tym OpenAlex) bez gate'a; `engine.py` nie zawiera już wbudowanych źródeł ani kodu LLM.

## Kolejność wykonania (gdy wrócimy)
1. `OpenAlexProvider` + `S2Provider` w `providers.py` (przeniesienie 1:1, testy providerów zielone).
2. Konsolidacja resolverów (Unpaywall/CORE/arXiv/S2) w rejestrze.
3. `fetch` driver (port search/dedup/download/rank z `run_student`), `run_student` → cienki wrapper
   lub usunięty.
4. Cut `ConsensusProvider`/`PerplexityProvider` + reszty inert.
5. Wpięcie `scout_fanout`/`g02_flow` na `fetch`; port testów Scouta; porównanie wynik-do-wyniku.
