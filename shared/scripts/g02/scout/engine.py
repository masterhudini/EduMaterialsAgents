"""Silnik potoku Student (M1) - agregacja, filtr OA, pobieranie, nazewnictwo.

Zaleznosci: wylacznie stdlib (urllib). Akwizycja PDF (wielopoziomowa):
  1) OpenAlex best_oa_location.pdf_url + wszystkie locations[].pdf_url,
  2) warianty arXiv (/abs/ -> /pdf/),
  3) wszystkie url_for_pdf z Unpaywall oa_locations,
  4) gdy URL zwraca HTML (strona docelowa) - scraping meta citation_pdf_url
     oraz linkow .pdf (glebokosc 1). To standard, ktorego uzywa Unpaywall/Zotero.
Naglowki: User-Agent + Accept: application/pdf + Referer (pomaga na czesc 403).

Decyzja projektowa (rejestr #9): nie filtrujemy OA po stronie serwera, lecz
pobieramy 2N kandydatow i dzielimy lokalnie - by policzyc WSKAZNIK POKRYCIA OA
(koncepcja par. 9, D1: blad selekcji proby).
"""

from __future__ import annotations

import json
import math
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import http_util
from .http_util import request_with_retry
from . import prompts
from .constants import (
    FACET_CAP, MAX_QUERIES, HTTP_MIN_INTERVAL_SECONDS, HTTP_MAX_CALLS_PER_RUN,
    SNOWBALL_FANOUT, SNOWBALL_SEEDS, LONGLIST_CAP,
)

USER_AGENT = "RadarPDF/0.1 (https://uew.edu.pl; mailto:{email})"
OPENALEX = "https://api.openalex.org/works"
UNPAYWALL = "https://api.unpaywall.org/v2/{doi}"
SEMANTIC = "https://api.semanticscholar.org/graph/v1/paper/search"

Progress = Callable[[str, str], None]  # (event, message)


@dataclass(slots=True)
class Candidate:
    doi: str
    title: str
    year: int | None
    first_author: str
    is_oa: bool
    pdf_url: str | None
    source: str  # "openalex" | "semantic_scholar"
    cited_by: int = 0
    alt_pdf_urls: list[str] = field(default_factory=list)  # z locations[] OpenAlex
    work_type: str = ""  # typ OpenAlex: article|review|preprint|...
    authors: str = ""
    abstract: str = ""
    # — Wzbogacony schemat metadanych (literature-harvester, koncepcja: §metadane) —
    oa_status: str = ""          # gold|green|hybrid|bronze|closed (OpenAlex open_access.oa_status)
    license: str = ""            # licencja wersji (np. cc-by) - kluczowe dla legalnosci pobrania
    version: str = ""            # publishedVersion|acceptedVersion|submittedVersion
    venue: str = ""              # czasopismo / seria working-paperow (institution_or_series)
    landing_page_url: str = ""   # strona docelowa rekordu (nie PDF)
    jel_codes: str = ""          # kody JEL po przecinku (z EconBiz/RePEc; OpenAlex rzadko)
    # — Sygnaly WARTOSCI/INTEGRALNOSCI (OpenAlex inline, zero dodatkowych callow) —
    is_retracted: bool = False   # bramka integralnosci: praca wycofana (OpenAlex is_retracted)
    fwci: float | None = None    # Field-Weighted Citation Impact (znormalizowany po polu/wieku)
    cnp: float | None = None     # citation_normalized_percentile.value (0..1, po polu+roku+typie)
    is_top10: bool = False       # is_in_top_10_percent (cytowania znormalizowane)
    source_id: str = ""          # OpenAlex source id (do prestizu venue: /sources/<id> summary_stats)
    issn_l: str = ""             # ISSN-L zrodla (klucz dla SCImago/SJR offline)

    def filename(self) -> str:
        return build_filename(self.year, self.first_author, self.title)


@dataclass(slots=True)
class RunResult:
    target_n: int
    openalex_total: int = 0          # unikalne kandydaty z samego OpenAlex (informacyjnie)
    total_found: int = 0             # cala pula po scaleniu OpenAlex+Semantic (mianownik D1)
    oa_count: int = 0                # ile z nich bylo OA
    downloaded: list[str] = field(default_factory=list)
    skipped_non_oa: int = 0
    failed: list[str] = field(default_factory=list)
    stubs: list[str] = field(default_factory=list)
    manifest_ok: bool = True
    versions_merged: int = 0
    year_from: int | None = None
    year_to: int | None = None
    work_type: str = ""
    sort: str = "relevance"
    year_drop_pct: float | None = None  # udzial trafien odcietych przez okno lat (transparencja D1)
    rejected: list[str] = field(default_factory=list)  # PDF odrzucone przez LLM (off-topic)
    unverified: int = 0  # pobrane, ale LLM nie zwrocil werdyktu (fail-open)
    llm_checks: int = 0
    llm_input_chars: int = 0
    llm_cost_usd: float = 0.0
    flagged: list[str] = field(default_factory=list)  # (zarezerwowane)
    items: list = field(default_factory=list)  # pozycje do rankingu/wyboru (UI)
    oversample: float = 1.5
    skipped_known: int = 0  # pominiete jako juz pobrane w poprzednim przebiegu (dedup cross-RUN)
    n_retracted: int = 0    # ile pobranych prac jest wycofanych (bramka integralnosci A1)

    @property
    def oa_coverage(self) -> float:
        """Wskaznik pokrycia OA (D1): udzial prac OA w zwroconej puli."""
        return (self.oa_count / self.total_found) if self.total_found else 0.0


# -- HTTP JSON (stdlib + backoff) ---------------------------------------
def _get_json(url: str, email: str, *, timeout: float = 15.0, retries: int = 3,
              headers: dict | None = None) -> dict[str, Any]:
    """JSON GET odporny na throttling (429/5xx + Retry-After + backoff/jitter przez
    request_with_retry; pacing per-host). 404 -> {}. Terminalny blad PROPAGUJE sie -
    wywolujacy rdzeniowi (OpenAlex) pozwalaja mu wyjsc (job=failed z komunikatem), a
    sciezki best-effort (Unpaywall/S2/source_stats) owijaja w try/except -> puste."""
    hdrs = {"User-Agent": USER_AGENT.format(email=email or "anonymous@example.com")}
    if headers:
        hdrs.update(headers)
    headers = hdrs
    try:
        raw = request_with_retry(url, headers=headers, timeout=timeout, max_attempts=max(2, retries))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {}
        raise
    return json.loads(raw.decode("utf-8"))


# -- Nazewnictwo wg formuly llmwiki_pdf: rok_autor_w1_w2_w3_w4 -----------
def _transliterate(text: str) -> str:
    """PL/diakrytyki -> ASCII (na potrzeby kluczy dedup). l z kreska recznie."""
    text = (text or "").replace("ł", "l").replace("Ł", "L")
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def _slug_part(value: str) -> str:
    """1:1 jak llmwiki_pdf/wiki_export.slug_part: NFKD -> ascii(ignore) ->
    [^A-Za-z0-9]+ -> _ , strip(_), lower."""
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Za-z0-9]+", "_", ascii_text).strip("_").lower()


def _title_tokens(title: str) -> list[str]:
    """Slowa tytulu do sluga: usun $...$ (math), rozbij, sluguj."""
    value = re.sub(r"\$.*?\$", " ", title or "")
    value = re.sub(r"[_/\\-]+", " ", value)
    return [part for part in (_slug_part(tok) for tok in value.split()) if part]


def build_filename(year: int | None, first_author: str, title: str, *, ext: str = ".pdf") -> str:
    """Formula llmwiki_pdf: {rok}_{autor}_{4 slowa tytulu}. Rok->0000, autor->xxx."""
    safe_year = str(year) if (year and re.fullmatch(r"\d{4}", str(year))) else "0000"
    author = _slug_part(first_author) or "xxx"
    words = _title_tokens(title)[:4] or ["untitled", "document"]
    stem = "_".join([safe_year, author, *words])
    return f"{stem}{ext}"


# -- Parsowanie OpenAlex ------------------------------------------------
def _abstract_from_inverted(inv: dict | None) -> str:
    """Rekonstrukcja abstraktu z OpenAlex abstract_inverted_index (slowo->pozycje)."""
    if not inv:
        return ""
    pos: dict[int, str] = {}
    for word, idxs in inv.items():
        for i in idxs or []:
            pos[i] = word
    return " ".join(pos[i] for i in sorted(pos))


def first_words(text: str, n: int = 25) -> str:
    words = (text or "").split()
    return (" ".join(words[:n]) + (" \u2026" if len(words) > n else "")).strip()


def _authors_str(authorships: list, *, limit: int = 3) -> str:
    names = [(a.get("author") or {}).get("display_name", "") for a in (authorships or [])]
    names = [x for x in names if x]
    head = ", ".join(names[:limit])
    return head + (" i in." if len(names) > limit else "")


def _clean_doi(raw: str | None) -> str:
    return raw.replace("https://doi.org/", "").strip().lower() if raw else ""


def parse_openalex_work(work: dict[str, Any]) -> Candidate | None:
    doi = _clean_doi(work.get("doi"))
    if not doi:
        return None
    oa = work.get("open_access") or {}
    best = work.get("best_oa_location") or {}
    prim = work.get("primary_location") or {}
    src = prim.get("source") or best.get("source") or {}
    auths = work.get("authorships") or []
    first = auths[0].get("author", {}).get("display_name", "") if auths else ""
    # Mining WSZYSTKICH locations[] po bezposrednie pdf_url (nie tylko best).
    alt: list[str] = []
    primary = best.get("pdf_url")
    for loc in work.get("locations") or []:
        u = (loc or {}).get("pdf_url")
        if u and u != primary and u not in alt:
            alt.append(u)
    return Candidate(
        doi=doi,
        title=work.get("title") or work.get("display_name") or "",
        year=work.get("publication_year"),
        first_author=first,
        is_oa=bool(oa.get("is_oa")),
        pdf_url=primary,
        source="openalex",
        cited_by=int(work.get("cited_by_count") or 0),
        alt_pdf_urls=alt,
        work_type=(work.get("type") or ""),
        authors=_authors_str(auths),
        abstract=_abstract_from_inverted(work.get("abstract_inverted_index")),
        oa_status=(oa.get("oa_status") or ""),
        license=(prim.get("license") or best.get("license") or "") or "",
        version=(prim.get("version") or best.get("version") or "") or "",
        venue=((src or {}).get("display_name") or ""),
        landing_page_url=(prim.get("landing_page_url") or best.get("landing_page_url") or work.get("id") or ""),
        is_retracted=bool(work.get("is_retracted")),
        fwci=_as_float(work.get("fwci")),
        cnp=_as_float(((work.get("citation_normalized_percentile") or {}) or {}).get("value")),
        is_top10=bool(((work.get("citation_normalized_percentile") or {}) or {}).get("is_in_top_10_percent")),
        source_id=((src or {}).get("id") or ""),
        issn_l=((src or {}).get("issn_l") or ""),
    )


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


_SORT_MAP = {
    "relevance": "relevance_score:desc",
    "citations": "cited_by_count:desc",
    "recency": "publication_date:desc",
}


def _oa_filter(year_from: int | None, year_to: int | None, work_type: str) -> str:
    parts: list[str] = []
    if year_from:
        parts.append(f"from_publication_date:{int(year_from)}-01-01")
    if year_to:
        parts.append(f"to_publication_date:{int(year_to)}-12-31")
    if work_type:
        parts.append(f"type:{work_type}")
    return ",".join(parts)


def openalex_match_count(topic: str, email: str, *, year_from=None, year_to=None, work_type="", api_key: str = "") -> int:
    """Liczba trafien (meta.count) dla zapytania z danymi filtrami. Tani sposob
    na transparencje: porownanie z/bez okna lat pokazuje koszt filtra (D1)."""
    q = {"search": topic, "per_page": 1, "mailto": email or ""}
    if api_key:
        q["api_key"] = api_key
    flt = _oa_filter(year_from, year_to, work_type)
    if flt:
        q["filter"] = flt
    try:
        data = _get_json(f"{OPENALEX}?{urllib.parse.urlencode(q)}", email, retries=2)
        return int((data.get("meta") or {}).get("count") or 0)
    except Exception:
        return 0


def verify_openalex_key(api_key: str, email: str) -> dict[str, Any]:
    """Szybki test łączności + akceptacji klucza OpenAlex: 1 minimalne zapytanie z
    kluczem. Rozróżnia: OK / klucz odrzucony (401/403) / inny błąd HTTP / brak sieci.
    Zwraca {ok, key_used, message} — do przycisku „Testuj klucz" w Konfiguracji."""
    # Zapytanie NEUTRALNE tematycznie (sam endpoint /works, bez 'search') — test
    # sprawdza KLUCZ i łączność, nie konkretny temat. Reguła ogólna, nie szyta pod ES.
    q = {"per_page": 1, "mailto": email or ""}
    if api_key:
        q["api_key"] = api_key
    url = f"{OPENALEX}?{urllib.parse.urlencode(q)}"
    try:
        raw = request_with_retry(url, headers={"User-Agent": USER_AGENT.format(email=email or "")}, timeout=12.0)
        json.loads(raw.decode("utf-8"))  # potwierdź poprawny JSON
        if api_key:
            msg = "Klucz działa — OpenAlex odpowiada z podniesionymi limitami."
        else:
            msg = "OpenAlex odpowiada (tryb grzecznościowy, bez klucza)."
        return {"ok": True, "key_used": bool(api_key), "message": msg}
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return {"ok": False, "key_used": bool(api_key), "message": f"Klucz odrzucony przez OpenAlex (HTTP {exc.code}) — sprawdź wartość."}
        return {"ok": False, "key_used": bool(api_key), "message": f"OpenAlex zwrócił błąd (HTTP {exc.code})."}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "key_used": bool(api_key), "message": f"Brak połączenia z OpenAlex ({type(exc).__name__})."}


def _openalex_get(url: str, email: str) -> dict[str, Any]:
    """GET + parse JSON OpenAlex (best-effort: błąd → {})."""
    try:
        raw = request_with_retry(url, headers={"User-Agent": USER_AGENT.format(email=email or "")}, timeout=15.0)
        return json.loads(raw.decode("utf-8"))
    except Exception:  # noqa: BLE001 - snowball jest best-effort, nie wywraca przebiegu
        return {}


def _short_oa_id(work_id: str) -> str:
    """„https://openalex.org/W123" → „W123" (format filtra openalex_id)."""
    return (work_id or "").rstrip("/").rsplit("/", 1)[-1]


def openalex_search(
    topic: str, n: int, email: str, *,
    year_from: int | None = None, year_to: int | None = None,
    work_type: str = "", sort: str = "relevance", api_key: str = "", progress: Progress | None = None,
) -> list[Candidate]:
    per_page = min(max(2 * n, 10), 200)
    q = {
        "search": topic, "per_page": per_page, "mailto": email or "",
        "sort": _SORT_MAP.get(sort, _SORT_MAP["relevance"]),
    }
    if api_key:
        q["api_key"] = api_key
    flt = _oa_filter(year_from, year_to, work_type)
    if flt:
        q["filter"] = flt
    if progress:
        extra = []
        if year_from or year_to:
            extra.append(f"lata {year_from or '…'}-{year_to or '…'}")
        if work_type:
            extra.append(f"typ={work_type}")
        extra.append(f"sort={sort}")
        progress("openalex", f"Zapytanie OpenAlex: „{topic}” ({', '.join(extra)}; do {per_page} poz.)")
    data = _get_json(f"{OPENALEX}?{urllib.parse.urlencode(q)}", email)
    out: list[Candidate] = []
    for work in data.get("results", []):
        cand = parse_openalex_work(work)
        if cand:
            out.append(cand)
    return out


# -- Semantic Scholar (best-effort) -------------------------------------
def semantic_scholar_extend(topic: str, email: str, *, limit: int = 10, api_key: str = "", progress: Progress | None = None) -> list[Candidate]:
    # Bez klucza API publiczny S2 niemal zawsze zwraca 429 -> nie pukamy w ogole
    # (oszczedza retry/429-szum). Z kluczem: naglowek x-api-key.
    if not api_key:
        if progress:
            progress("semantic", "Semantic Scholar pominiety (brak klucza API - publiczny limit dlawi)")
        return []
    query = urllib.parse.urlencode({"query": topic, "limit": limit, "fields": "title,year,externalIds,isOpenAccess,openAccessPdf,authors"})
    try:
        data = _get_json(f"{SEMANTIC}?{query}", email, retries=2, headers={"x-api-key": api_key})
    except Exception:
        if progress:
            progress("semantic", "Semantic Scholar niedostepny (throttling) - pomijam rozszerzenie")
        return []
    out: list[Candidate] = []
    for p in data.get("data", []) or []:
        doi = _clean_doi((p.get("externalIds") or {}).get("DOI"))
        if not doi:
            continue
        authors = p.get("authors") or []
        pdf = (p.get("openAccessPdf") or {}).get("url")
        out.append(
            Candidate(
                doi=doi, title=p.get("title") or "", year=p.get("year"),
                first_author=authors[0].get("name", "") if authors else "",
                is_oa=bool(p.get("isOpenAccess")), pdf_url=pdf, source="semantic_scholar",
            )
        )
    return out


# -- Unpaywall ----------------------------------------------------------
def unpaywall_pdf_urls(doi: str, email: str) -> list[str]:
    """WSZYSTKIE bezposrednie url_for_pdf z oa_locations (nie tylko best)."""
    try:
        data = _get_json(
            UNPAYWALL.format(doi=urllib.parse.quote(doi)) + f"?email={urllib.parse.quote(email or '')}",
            email, retries=2,
        )
    except Exception:
        return []
    if not data or not data.get("is_oa"):
        return []
    best = data.get("best_oa_location")
    ordered = ([best] if best else []) + (data.get("oa_locations") or [])
    out: list[str] = []
    seen: set[str] = set()
    for loc in ordered:
        u = (loc or {}).get("url_for_pdf")
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


# -- Waga pracy (citation velocity) + bramka preprintu --------------------
def _velocity(cand: "Candidate") -> float:
    """Cytowania na rok zycia pracy. Odporne na blad wieku (inaczej niz surowy
    cited_by, ktory faworyzuje prace stare)."""
    if not cand.year:
        return 0.0
    age = max(1, datetime.now().year - int(cand.year) + 1)
    return (cand.cited_by or 0) / age


def importance_threshold(pool: list["Candidate"], quantile: float = 0.2) -> float:
    """Prog velocity dla gornego kwantyla PULI (np. quantile=0.2 -> top 20%)."""
    vals = sorted(_velocity(c) for c in pool)
    if not vals:
        return float("inf")
    idx = max(0, min(len(vals) - 1, int(math.ceil((1.0 - quantile) * len(vals))) - 1))
    return vals[idx]


def _norm_tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", _transliterate(text or "").lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def arxiv_search_pdf(title: str, first_author: str, email: str, *, min_sim: float = 0.6) -> str | None:
    """Szukaj na arXiv po tytule; akceptuj TYLKO przy wysokim podobienstwie tytulu
    (Jaccard) i zgodnosci nazwiska - inaczej ryzyko wciagniecia zlej pracy."""
    if not title:
        return None
    q = urllib.parse.urlencode({"search_query": f'ti:"{title}"', "max_results": 5})
    try:
        xml = request_with_retry(
            f"http://export.arxiv.org/api/query?{q}",
            headers={"User-Agent": USER_AGENT.format(email=email or "anonymous@example.com")},
            timeout=15, max_attempts=3,
        )
    except Exception:
        return None
    ns = {"a": "http://www.w3.org/2005/Atom"}
    try:
        root = ET.fromstring(xml)
    except Exception:
        return None
    want = _norm_tokens(title)
    surname = (_transliterate(first_author).split()[-1].lower() if first_author.strip() else "")
    for e in root.findall("a:entry", ns):
        t = (e.findtext("a:title", default="", namespaces=ns) or "").strip()
        sim = _jaccard(want, _norm_tokens(t))
        if sim < min_sim:
            continue
        names = [(a.findtext("a:name", default="", namespaces=ns) or "") for a in e.findall("a:author", ns)]
        author_ok = (not surname) or any(surname in _transliterate(nm).lower() for nm in names)
        if not author_ok and sim < 0.85:  # slabe dopasowanie autora dopuszczamy tylko przy b. wysokim sim tytulu
            continue
        for l in e.findall("a:link", ns):
            if l.get("title") == "pdf" or l.get("type") == "application/pdf":
                href = l.get("href") or ""
                if href:
                    return href if href.endswith(".pdf") else href + ".pdf"
        m = re.search(r"arxiv\.org/abs/([\w.\-/]+)", e.findtext("a:id", default="", namespaces=ns) or "")
        if m:
            return f"https://arxiv.org/pdf/{m.group(1)}.pdf"
    return None



def semantic_scholar_pdf(doi: str, email: str, *, api_key: str = "") -> str | None:
    """openAccessPdf z Semantic Scholar dla KONKRETNEGO DOI - ostatnia linia
    akwizycji (S2 czesto ma autorskie/preprintowe PDF, ktorych Unpaywall jeszcze
    nie przetworzyl). Bez klucza pomijamy (publiczny limit dlawi). Best-effort:
    429/blad -> None, bez wywracania przebiegu."""
    if not api_key:
        return None
    try:
        data = _get_json(
            f"https://api.semanticscholar.org/graph/v1/paper/DOI:{urllib.parse.quote(doi)}?fields=openAccessPdf",
            email, retries=2, headers={"x-api-key": api_key},
        )
    except Exception:
        return None
    return ((data or {}).get("openAccessPdf") or {}).get("url")



def build_facet_queries(primary: str, facets: list[str] | None, *, cap: int = FACET_CAP) -> list[str]:
    """Zapytania FASETOWE dla planera (Etap 1, spec §16): kotwica `primary` + każda
    faseta osobno → ``"<primary> <facet>"``.

    Liniowo, NIE iloczyn kartezjański — koszt rośnie liniowo z liczbą faset, nie
    wykładniczo (stąd ``cap = FACET_CAP``). Fasety pochodzą z OBIEKTU INTENCJI (dane
    wpisane/wywnioskowane), więc termin specjalistyczny (np. „e-value", „anytime-valid")
    nie jest zaszyty pod temat — reguła OGÓLNA działa dla dowolnej intencji. Dedup +
    pominięcie pustych i duplikatu samego `primary` (to zapytanie idzie osobno).

    Empiria (gold-set ES): kotwica + fasety {e-value, anytime-valid, elicitability,
    sequential} podnoszą recall@50 z 35% (gołe zapytanie) do ~50%, wciągając klaster
    e-value, którego generyczna ekspansja keyword-bag NIE łapała."""
    primary = (primary or "").strip()
    seen = {primary.lower()}
    out: list[str] = []
    for facet in facets or []:
        facet = (facet or "").strip()
        if not facet:
            continue
        query = (f"{primary} {facet}" if primary else facet).strip()
        if query.lower() in seen:
            continue
        out.append(query)
        seen.add(query.lower())
        if len(out) >= cap:
            break
    return out


# -- Resolver akwizycji -------------------------------------------------
def _arxiv_variants(url: str | None) -> list[str]:
    if not url:
        return []
    m = re.search(r"arxiv\.org/(?:abs|pdf)/([\w.\-/]+?)(?:\.pdf)?$", url)
    return [f"https://arxiv.org/pdf/{m.group(1)}.pdf", f"https://arxiv.org/pdf/{m.group(1)}"] if m else []


def pdf_url_candidates(cand: "Candidate", email: str, extra_resolvers: list | None = None) -> list[str]:
    """Uporzadkowana, odduplikowana lista URL-i: OpenAlex pdf_url + locations[]
    (+arXiv) -> wszystkie url_for_pdf z Unpaywall -> dodatkowe resolvery (np. CORE,
    Crossref) gdy wlaczone. Resolvery sa best-effort: blad jednego nie psuje listy."""
    cands: list[str] = []
    if cand.pdf_url:
        cands.append(cand.pdf_url)
    cands += list(cand.alt_pdf_urls)
    cands += unpaywall_pdf_urls(cand.doi, email)
    for r in (extra_resolvers or []):
        try:
            cands += list(r.resolve(cand, email) or [])
        except Exception:  # noqa: BLE001
            continue
    cands += [v for u in list(cands) for v in _arxiv_variants(u)]
    out: list[str] = []
    seen: set[str] = set()
    for u in cands:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _headers(url: str, email: str) -> dict[str, str]:
    parts = urllib.parse.urlparse(url)
    referer = f"{parts.scheme}://{parts.netloc}/" if parts.scheme and parts.netloc else "https://doi.org/"
    return {
        "User-Agent": USER_AGENT.format(email=email or "anonymous@example.com"),
        "Accept": "application/pdf,text/html;q=0.9,*/*;q=0.8",
        "Referer": referer,
    }


def _fetch(url: str, email: str, *, timeout: float = 20.0) -> tuple[bytes | None, str, str]:
    """Pobierz zasob. Zwraca (dane, content_type, final_url). Nigdy nie rzuca."""
    try:
        req = urllib.request.Request(url, headers=_headers(url, email))
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(), (resp.headers.get_content_type() or ""), resp.geturl()
    except Exception:
        return None, "", url


def _save_if_pdf(data: bytes | None, dest: Path) -> bool:
    if not data:
        return False
    if not (data[:5].startswith(b"%PDF") or data[:1024].lstrip()[:5].startswith(b"%PDF")):
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return True


_META_PDF_RE = re.compile(
    rb'<meta[^>]+name=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+)["\']', re.I
)
_META_PDF_RE2 = re.compile(
    rb'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']citation_pdf_url["\']', re.I
)
_HREF_PDF_RE = re.compile(rb'href=["\']([^"\']+\.pdf[^"\']*)["\']', re.I)


def _scrape_pdf_links(html: bytes, base_url: str) -> list[str]:
    """Wyciagnij z HTML strony docelowej kandydatow na PDF: meta citation_pdf_url
    (standard Google Scholar/Unpaywall) oraz linki konczace sie na .pdf."""
    raw: list[str] = []
    for rx in (_META_PDF_RE, _META_PDF_RE2):
        raw += [m.group(1).decode("utf-8", "ignore") for m in rx.finditer(html)]
    raw += [m.group(1).decode("utf-8", "ignore") for m in _HREF_PDF_RE.finditer(html)]
    out: list[str] = []
    seen: set[str] = set()
    for u in raw:
        full = urllib.parse.urljoin(base_url, u)
        if full not in seen:
            seen.add(full)
            out.append(full)
    return out[:5]


def download_pdf(url: str, dest: Path, email: str, *, timeout: float = 30.0) -> bool:
    """Pobierz pojedynczy URL i zapisz, gdy to PDF (%PDF). Bez scrapingu."""
    data, _ct, _final = _fetch(url, email, timeout=timeout)
    return _save_if_pdf(data, dest)


def _try_urls(urls: list[str], dest: Path, email: str) -> tuple[bool, str]:
    """Sprobuj pobrac z listy URL-i; gdy URL zwraca HTML - scrapuj citation_pdf_url
    i linki .pdf (glebokosc 1). Zwraca (ok, final_url)."""
    for url in urls:
        data, ct, final = _fetch(url, email)
        if _save_if_pdf(data, dest):
            return True, final
        if data and ("html" in ct.lower() or b"<html" in data[:2000].lower()):
            for scraped in _scrape_pdf_links(data, final):
                d2, _ct2, f2 = _fetch(scraped, email)
                if _save_if_pdf(d2, dest):
                    return True, f2
    return False, ""


def resolve_and_download(cand: "Candidate", dest: Path, email: str, extra_resolvers: list | None = None,
                         *, s2_api_key: str = "") -> tuple[bool, str]:
    """Akwizycja ETAPAMI (P4: minimalizuj zapytania API/429). Najpierw URL-e
    BEZPOSREDNIE (z OpenAlex/arXiv - zero callow), i dopiero gdy zawioda eskaluj:
    Unpaywall (1 call) -> resolvery (CORE/Crossref) -> S2 per-DOI. Wiekszosc prac OA
    pobiera sie na etapie 1, wiec nie pukamy w Unpaywall/CORE/S2 bez potrzeby."""
    seen: set[str] = set()

    def fresh(urls: list[str]) -> list[str]:
        out: list[str] = []
        for u in urls:
            if u and u not in seen:
                seen.add(u)
                out.append(u)
        return out

    # Etap 1: bezposrednie pdf_url + locations[] + warianty arXiv (bez zapytan API)
    base = ([cand.pdf_url] if cand.pdf_url else []) + list(cand.alt_pdf_urls)
    ok, used = _try_urls(fresh(base + [v for u in base for v in _arxiv_variants(u)]), dest, email)
    if ok:
        return True, used
    # Etap 2: Unpaywall - dopiero gdy bezposrednie zawiodly
    ok, used = _try_urls(fresh(unpaywall_pdf_urls(cand.doi, email)), dest, email)
    if ok:
        return True, used
    # Etap 3: dodatkowe resolvery (CORE/Crossref) - best-effort
    for r in (extra_resolvers or []):
        try:
            urls = list(r.resolve(cand, email) or [])
        except Exception:  # noqa: BLE001
            continue
        ok, used = _try_urls(fresh(urls), dest, email)
        if ok:
            return True, used
    # Etap 4: Semantic Scholar per-DOI (tylko z kluczem)
    s2 = semantic_scholar_pdf(cand.doi, email, api_key=s2_api_key)
    if s2:
        ok, used = _try_urls(fresh([s2]), dest, email)
        if ok:
            return True, used
    return False, ""


def _unique_dest(pdf_dir: Path, base_name: str, doi: str, used: set[str]) -> Path:
    """Chron przed kolizja nazw (preprint + publikacja, rozne DOI -> ta sama nazwa)."""
    dest = pdf_dir / base_name
    if base_name not in used and not dest.exists():
        used.add(base_name)
        return dest
    tail = re.sub(r"[^A-Za-z0-9]", "", doi)[-6:] or "x"
    stem = base_name[:-4] if base_name.endswith(".pdf") else base_name
    alt = f"{stem}__{tail}.pdf"
    used.add(alt)
    return pdf_dir / alt


# -- Kompletnosc: stub + MANIFEST (wzorzec z perplexity-scout) -----------
def _write_stub(stub_dir: Path, cand: "Candidate") -> str:
    """Gdy praca OA nie ma pobieralnego PDF - zapisz stub .md (metadane + DOI),
    zeby NIC nie ginelo cicho. Zwraca nazwe pliku."""
    stub_dir.mkdir(parents=True, exist_ok=True)
    name = cand.filename()[:-4] + ".md"
    body = (
        f"# {cand.title}\n\n"
        f"- DOI: https://doi.org/{cand.doi}\n"
        f"- Rok: {cand.year or '?'}\n"
        f"- Pierwszy autor: {cand.first_author or '?'}\n"
        f"- Zrodlo: {cand.source}\n"
        f"- Status: OA wg metadanych, ale PDF niedostepny do pobrania (paywall/landing/403).\n"
        f"- Cytowania: {cand.cited_by}\n\n"
        f"> Zaślepka wygenerowana przez Radar PDF - brak pliku PDF. "
        f"Nie obchodzimy paywalli; rozwaz wariant Deep (sesja/EZproxy) lub preprint.\n"
    )
    (stub_dir / name).write_text(body, encoding="utf-8")
    return name


def _write_manifest(pdf_dir: Path, topic: str, *, run_meta_n: int, rows: list) -> None:
    """MANIFEST.md: tabela 1:1 referencja <-> plik <-> DOI <-> status, plus
    niezmiennik N_pdf + N_stub == N_attempted (naruszenie = sygnal bledu)."""
    pdf_dir.mkdir(parents=True, exist_ok=True)
    n_pdf = sum(1 for _c, st, _f in rows if st in ("pdf", "preprint"))
    n_stub = sum(1 for _c, st, _f in rows if st == "stub")
    n_rej = sum(1 for _c, st, _f in rows if st == "rejected")
    lines = [
        f"# MANIFEST - Radar PDF",
        "",
        f"- Zapytanie: {topic}",
        f"- Cel N: {run_meta_n}",
        f"- Przetworzone (OA): {len(rows)}  |  PDF: {n_pdf}  |  stub: {n_stub}  |  odrzucone LLM: {n_rej}",
        f"- Niezmiennik N_pdf + N_stub + N_rejected == N_attempted: {'OK' if n_pdf + n_stub + n_rej == len(rows) else 'NARUSZONY'}",
        "",
        "| Status | Plik | Rok | Pierwszy autor | DOI |",
        "|--------|------|-----|----------------|-----|",
    ]
    for cand, st, fname in rows:
        lines.append(f"| {st} | {fname} | {cand.year or '?'} | {cand.first_author or '?'} | {cand.doi} |")
    (pdf_dir / "MANIFEST.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# -- Dedup cross-wersji (preprint vs wersja wydawcy) ---------------------
_PREPRINT_DOI_PREFIXES = (
    "10.48550/arxiv",   # arXiv
    "10.2139/ssrn",     # SSRN
    "10.3386/",         # NBER working papers
    "10.21203/",        # Research Square
    "10.31222", "10.31235", "10.31234",  # OSF preprints (SocArXiv/PsyArXiv...)
    "10.20944/preprints",
)


def clean_title(title: str) -> str:
    """Tytul znormalizowany: ASCII-fold, lower, tokeny alnum zlaczone spacja.
    Klucz do wykrycia tej samej pracy pod roznymi DOI (preprint vs publikacja)."""
    return " ".join(re.findall(r"[a-z0-9]+", _transliterate(title or "").lower()))


def _is_preprint_doi(doi: str) -> bool:
    d = (doi or "").lower()
    return any(d.startswith(pfx) for pfx in _PREPRINT_DOI_PREFIXES)


def _work_key(cand: "Candidate") -> tuple[str, str]:
    """Tozsamosc pracy: (clean_title, nazwisko_pierwszego_autora). Rok celowo
    POZA kluczem (preprint i publikacja roznia sie rokiem) - chroni przed
    rozjechaniem wersji; ryzyko falszywego scalenia ogranicza wymog zgodnosci
    tytulu I nazwiska."""
    ct = clean_title(cand.title)
    surname = (_transliterate(cand.first_author).split()[-1].lower() if cand.first_author.strip() else "")
    return (ct, surname)


def _dedup_versions(cands: list["Candidate"]) -> tuple[list["Candidate"], int]:
    """Scal rozne wersje tej samej pracy w JEDEN rekord. Tozsamosc = wersja
    recenzowana (nie-preprint DOI), tiebreak: wyzszy cited_by. URL-e PDF
    wszystkich wersji trafiaja do alt_pdf_urls (preprint jako zapas akwizycji);
    is_oa = OR (jesli ktorakolwiek wersja jest OA, praca jest pozyskiwalna).
    Prace bez sensownego klucza (pusty tytul) NIE sa scalane."""
    groups: dict[tuple[str, str], list[Candidate]] = {}
    order: list[tuple[str, str]] = []
    singletons: list[Candidate] = []
    for c in cands:
        ct, surname = _work_key(c)
        if not ct or not surname:
            singletons.append(c)
            continue
        key = (ct, surname)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(c)

    merged = 0
    out: list[Candidate] = []
    for key in order:
        members = groups[key]
        if len(members) == 1:
            out.append(members[0])
            continue
        # primary = wersja recenzowana o najwyzszym cited_by; fallback: najwyzszy cited_by
        published = [m for m in members if not _is_preprint_doi(m.doi)]
        pool = published or members
        primary = max(pool, key=lambda m: (m.cited_by or 0))
        extra_urls: list[str] = list(primary.alt_pdf_urls)
        any_oa = False
        for m in members:
            any_oa = any_oa or m.is_oa
            for u in ([m.pdf_url] if m.pdf_url else []) + list(m.alt_pdf_urls):
                if u and u != primary.pdf_url and u not in extra_urls:
                    extra_urls.append(u)
        primary.alt_pdf_urls = extra_urls
        primary.is_oa = any_oa
        merged += len(members) - 1
        out.append(primary)
    return out + singletons, merged



# -- Ranking wielokryterialny (wybor robi czlowiek) ---------------------
DEFAULT_RANK_WEIGHTS = {"rel": 0.4, "impact": 0.3, "recency": 0.12, "type": 0.05, "prestige": 0.13}
_TYPE_SCORE = {"review": 1.0, "article": 0.7, "preprint": 0.4, "book-chapter": 0.5}
_RETRACTED_PENALTY = 0.02  # praca wycofana tonie na dol rankingu, ale NIE znika (nic nie ginie)


def _minmax(x: float, lo: float, hi: float) -> float:
    return 0.5 if hi <= lo else (x - lo) / (hi - lo)


def _impact_norm(it: dict, flo: float, fhi: float, vlo: float, vhi: float) -> float:
    """Wplyw pracy znormalizowany po polu/wieku - preferuj sygnaly OpenAlex,
    ktore juz to robia, zamiast surowej velocity (faworyzuje stare/duze pola):
    (1) citation_normalized_percentile.value (0..1, po polu+roku+typie),
    (2) fwci (log, min-max po puli), (3) fallback: citation-velocity (min-max)."""
    cnp = it.get("cnp")
    if cnp is not None:
        try:
            return min(1.0, max(0.0, float(cnp)))
        except (TypeError, ValueError):
            pass
    fwci = it.get("fwci")
    if fwci is not None:
        try:
            return _minmax(math.log1p(float(fwci)), flo, fhi)
        except (TypeError, ValueError):
            pass
    return _minmax(float(it.get("velocity") or 0), vlo, vhi)


def rank_items(items: list, weights: dict) -> list:
    """Policz wynik wielokryterialny R i posortuj malejaco. Skladowe znormalizowane
    do [0,1]: trafnosc (rel_score LLM; brak->0.5), WPLYW (znormalizowany: cnp/fwci/
    velocity - patrz _impact_norm), swiezosc (rok), typ, PRESTIZ venue
    (2yr_mean_citedness zrodla, min-max po puli; brak->0.5). Praca WYCOFANA dostaje
    twardy mnoznik karny (tonie, ale zostaje). Wagi dowolne dodatnie - normalizowane
    wewnetrznie. Zwraca nowe pozycje z polami *_norm, retracted, score_R i rank."""
    if not items:
        return []
    keys = ("rel", "impact", "recency", "type", "prestige")
    w = {k: max(0.0, float(weights.get(k, 0) or 0)) for k in keys}
    tot = sum(w.values()) or 1.0
    w = {k: v / tot for k, v in w.items()}
    years = [float(it.get("year") or 0) for it in items]
    ylo, yhi = min(years), max(years)
    fwcis = [math.log1p(float(it["fwci"])) for it in items if it.get("fwci") is not None]
    vels = [float(it.get("velocity") or 0) for it in items]
    pres = [math.log1p(float(it["venue_impact"])) for it in items if it.get("venue_impact") is not None]
    flo, fhi = (min(fwcis), max(fwcis)) if fwcis else (0.0, 0.0)
    vlo, vhi = min(vels), max(vels)
    plo, phi = (min(pres), max(pres)) if pres else (0.0, 0.0)
    out = []
    for it in items:
        rel = it.get("rel_score")
        rel = 0.5 if rel is None else float(rel)
        impact = _impact_norm(it, flo, fhi, vlo, vhi)
        recency = _minmax(float(it.get("year") or 0), ylo, yhi)
        typ = _TYPE_SCORE.get(it.get("work_type"), 0.6)
        vimp = it.get("venue_impact")
        prestige = _minmax(math.log1p(float(vimp)), plo, phi) if vimp is not None else 0.5
        R = (w["rel"] * rel + w["impact"] * impact + w["recency"] * recency
             + w["type"] * typ + w["prestige"] * prestige)
        retracted = bool(it.get("is_retracted") or it.get("retracted"))
        if retracted:
            R *= _RETRACTED_PENALTY
        it2 = dict(it)
        it2.update(rel_norm=round(rel, 3), impact_norm=round(impact, 3), recency_norm=round(recency, 3),
                   type_norm=round(typ, 3), prestige_norm=round(prestige, 3), retracted=retracted,
                   score_R=round(R, 4))
        out.append(it2)
    out.sort(key=lambda x: x["score_R"], reverse=True)
    for i, it in enumerate(out):
        it["rank"] = i + 1
    return out


# -- Pre-ranking PRZED pobraniem: dopasowanie do intencji + wplyw --------
# Nazwane stale (rozszerzalne) - funkcyjne slowa EN+PL pomijane przy dopasowaniu
# intencji, zeby liczyly sie slowa TRESCIOWE, nie "the/of/i/w".
_STOPWORDS = {
    "the", "a", "an", "of", "and", "or", "in", "on", "for", "to", "with", "without", "is", "are",
    "be", "by", "as", "at", "from", "that", "this", "these", "those", "we", "our", "you", "it",
    "its", "their", "using", "use", "based", "study", "studies", "analysis", "approach", "paper",
    "new", "via", "between", "into", "over", "under", "about", "can", "do", "does",
    "i", "oraz", "w", "we", "z", "ze", "na", "do", "dla", "od", "po", "przy", "przez", "o", "u",
    "jako", "ktory", "ktora", "ktore", "jest", "sa", "badanie", "badania", "analiza", "praca",
    "nowy", "nowa", "metoda", "podejscie", "czy", "lub", "albo",
}


def _content_tokens(text: str) -> set[str]:
    """Tokeny tresciowe (bez slow funkcyjnych, dlugosc > 2) do dopasowania intencji."""
    return {t for t in _norm_tokens(text) if len(t) > 2 and t not in _STOPWORDS}


def _text_relevance(query_tokens: set[str], text: str) -> float:
    """Pokrycie intencji w tekscie (tytul+abstrakt): jaka czesc slow Twojej intencji
    pojawia sie w pracy. Overlap wzgledem zapytania - nie karze dlugich abstraktow."""
    if not query_tokens:
        return 0.0
    toks = _content_tokens(text)
    if not toks:
        return 0.0
    return len(query_tokens & toks) / len(query_tokens)


def _coerce_token_sets(query_tokens: Any) -> list[set]:
    """Przyjmij pojedynczy zbior tokenow (wstecznie) ALBO liste zbiorow (wielojezyczne
    P1) i zwroc liste niepustych zbiorow."""
    if query_tokens is None:
        return []
    if isinstance(query_tokens, (set, frozenset)):
        sets = [set(query_tokens)]
    else:
        sets = [set(s) for s in query_tokens]
    return [s for s in sets if s]


def _relevance_multi(token_sets: list[set], text: str) -> float:
    """Najlepsze dopasowanie tekstu do KTOREGOKOLWIEK zestawu tokenow (jezyka).
    W trybie PL+ENG angielska praca dopasowuje sie do tokenow EN, a polska do PL
    - bez tego praca w drugim jezyku dostawalaby falszywe 0 (dzisiejszy bug)."""
    if not token_sets:
        return 0.0
    return max(_text_relevance(ts, text) for ts in token_sets)


def prerank_candidates(oa: list["Candidate"], query_tokens: Any) -> list["Candidate"]:
    """Uporzadkuj pule kandydatow PRZED pobieraniem wg: dopasowania do intencji
    (tytul+abstrakt, waga 0.6), wplywu znormalizowanego (cnp/fwci/velocity, 0.3),
    swiezosci (0.1). Dzieki temu z duzej puli pobieramy NAJWARTOSCIOWSZE pobieralne,
    a nie pierwsze z brzegu. rel_score (LLM) niedostepny przed pobraniem - dochodzi
    pozniej do finalnego rankingu. `query_tokens` to pojedynczy zbior tokenow (wstecznie)
    ALBO lista zbiorow (P1: po jednym na jezyk - dopasowanie liczone jako max)."""
    if not oa:
        return oa
    token_sets = _coerce_token_sets(query_tokens)
    fwcis = [math.log1p(float(c.fwci)) for c in oa if c.fwci is not None]
    vels = [_velocity(c) for c in oa]
    yrs = [float(c.year or 0) for c in oa]
    flo, fhi = (min(fwcis), max(fwcis)) if fwcis else (0.0, 0.0)
    vlo, vhi = (min(vels), max(vels)) if vels else (0.0, 0.0)
    ylo, yhi = (min(yrs), max(yrs)) if yrs else (0.0, 0.0)

    def influence(c: "Candidate") -> float:
        if c.cnp is not None:
            try:
                return min(1.0, max(0.0, float(c.cnp)))
            except (TypeError, ValueError):
                pass
        if c.fwci is not None:
            return _minmax(math.log1p(float(c.fwci)), flo, fhi)
        return _minmax(_velocity(c), vlo, vhi)

    def score(c: "Candidate") -> float:
        rel = _relevance_multi(token_sets, f"{c.title} {c.abstract}")
        return 0.6 * rel + 0.3 * influence(c) + 0.1 * _minmax(float(c.year or 0), ylo, yhi)

    return sorted(oa, key=score, reverse=True)


# -- Kwota jezykowa (P1): rozdziel pobrania miedzy pule PL i ENG ---------
def _apply_lang_quota(ranked: list["Candidate"], lang_map: dict[str, set],
                      split_pl: float, target: int) -> list["Candidate"]:
    """Przeporzadkuj juz zrankowana pule tak, by udzial PL w pierwszych `target`
    pozycjach wynosil ~split_pl (reszta = ENG), z PRZELEWEM: gdy ktoras pula nie
    wypelni slotu, dobiera druga (nic sie nie marnuje). Kolejnosc w obrebie puli
    zachowana (wg rankingu). split_pl<=0 -> ENG z przodu; >=1 -> PL z przodu."""
    def langs_of(c: "Candidate") -> set:
        return lang_map.get(c.doi, set())

    def with_rollover(primary: list["Candidate"]) -> list["Candidate"]:
        seen = {c.doi for c in primary}
        return primary + [c for c in ranked if c.doi not in seen]

    if split_pl <= 0.0:
        return with_rollover([c for c in ranked if "en" in langs_of(c)])
    if split_pl >= 1.0:
        return with_rollover([c for c in ranked if "pl" in langs_of(c)])

    n_pl = round(split_pl * max(1, target))
    pl_bucket = [c for c in ranked if "pl" in langs_of(c)]
    en_bucket = [c for c in ranked if "en" in langs_of(c) and "pl" not in langs_of(c)]
    chosen: list[Candidate] = []
    used: set[str] = set()
    for c in pl_bucket[:n_pl]:
        chosen.append(c); used.add(c.doi)
    for c in en_bucket:
        if len(chosen) >= target:
            break
        if c.doi not in used:
            chosen.append(c); used.add(c.doi)
    # Przelew: dobierz cokolwiek pozostalo (wg rankingu), by zapelnic target i nic nie zgubic.
    for c in ranked:
        if c.doi not in used:
            chosen.append(c); used.add(c.doi)
    return chosen


# -- Prestiz venue: summary_stats zrodla OpenAlex (cache per zrodlo) ------
OPENALEX_SOURCE = "https://api.openalex.org/sources/"


def fetch_source_stats(source_id: str, email: str, *, store: Any | None = None, api_key: str = "") -> dict:
    """Pobierz summary_stats zrodla OpenAlex (prestiz venue): {h_index, mean2yr}.
    Jeden call per ZRODLO, cache w store (reprodukowalnie, zgodnie z duchem aplikacji).
    Best-effort: blad/timeout -> {} (nie wywala przebiegu, prestiz wtedy neutralny)."""
    sid = (source_id or "").rstrip("/").rsplit("/", 1)[-1]
    if not sid.startswith("S"):
        return {}
    if store is not None:
        try:
            cached = store.get_source_stats(sid)
            if cached is not None:
                return cached
        except Exception:
            pass
    q = {"mailto": email or ""}
    if api_key:
        q["api_key"] = api_key
    try:
        data = _get_json(f"{OPENALEX_SOURCE}{sid}?{urllib.parse.urlencode(q)}", email, retries=2)
    except Exception:
        data = {}
    ss = (data or {}).get("summary_stats") or {}
    out = {"h_index": ss.get("h_index"), "mean2yr": ss.get("2yr_mean_citedness")}
    if store is not None and data:
        try:
            store.put_source_stats(sid, out)
        except Exception:
            pass
    return out


# -- Orkiestracja wariantu Student --------------------------------------
def run_student(
    topic: str,
    n: int,
    email: str,
    pdf_dir: Path,
    *,
    store: Any | None = None,
    polite_sleep: float = 1.0,
    allow_preprint: bool = False,
    preprint_quantile: float = 0.2,
    year_from: int | None = None,
    year_to: int | None = None,
    work_type: str = "",
    sort: str = "relevance",
    include_openalex: bool = True,   # credential-tier gate: skip built-in OpenAlex when False
    include_s2: bool = True,         # credential-tier gate: skip built-in Semantic Scholar when False
    verify_llm: bool = False,
    intent: str = "",
    openrouter_key: str = "",
    llm_model: str = "google/gemini-2.5-flash",
    search_lang: str = "both",
    search_lang_split_pl: float = 0.25,
    query_expansion: bool = False,
    facets: list[str] | None = None,
    facets_required: list[str] | None = None,
    snowball: bool = False,
    http_min_interval: float = HTTP_MIN_INTERVAL_SECONDS,
    http_max_calls_per_run: int = HTTP_MAX_CALLS_PER_RUN,
    min_intent_match: float = 0.1,
    s2_api_key: str = "",
    reject_mode: str = "flag",
    relevance_threshold: float = 0.5,
    model_price_usd_per_m: float = 0.075,
    max_cost_usd: float = 1.0,
    oversample: float = 1.5,
    summary_words: int = 50,
    dedup_cross_run: bool = True,
    openalex_api_key: str = "",
    extra_search: list | None = None,
    extra_resolvers: list | None = None,
    progress: Progress | None = None,
) -> RunResult:
    result = RunResult(target_n=n, year_from=year_from, year_to=year_to, work_type=work_type, sort=sort, oversample=oversample)
    # Bezpieczniki HTTP (warstwa sieci): governor prędkości (min-odstęp/host) + twardy
    # licznik zapytań na TEN przebieg (anty-pętla retry/ekspansja). Licznik jest
    # thread-local → zerowany na starcie KAŻDEGO przebiegu, przebiegi się nie mieszają.
    http_util.set_min_interval(http_min_interval)
    http_util.reset_run_budget(http_max_calls_per_run)
    used_names: set[str] = set()
    flagged_names: set[str] = set()
    manifest_rows: list = []
    # — Jezyk(i) wyszukiwania (P1): zbuduj zapytanie PER JEZYK, niezaleznie od
    # jezyka wpisanego w formularzu. Tlumaczenie przez OpenRouter (cache), z
    # degradacja do oryginalu gdy brak klucza/blad. OpenAlex/arXiv/CORE indeksuja
    # glownie angielski, wiec ENG drastycznie podnosi pokrycie.
    sl = (search_lang or "both").strip().lower()
    langs = ["en", "pl"] if sl == "both" else (["pl"] if sl == "pl" else ["en"])
    # lean refactor: query = user's literal topic per language (no LLM expansion/translation).
    queries: dict[str, str] = {}
    expand_keywords: dict[str, list] = {}
    for lang in langs:
        exp = {}  # lean refactor: no LLM query expansion/translation (a07 owns LLM)
        primary = topic  # query is the user's literal topic per language
        queries[lang] = (primary or topic).strip()
        expand_keywords[lang] = exp.get("keywords") or []
        if progress:
            tag = "ENG" if lang == "en" else "PL"
            note = "" if queries[lang] == topic else "  (tlumaczone z wpisanego)"
            progress("lang", f"Zapytanie [{tag}]: {queries[lang]}{note}")
            dom = (exp.get("domain") or "").strip()
            if dom:
                progress("lang", f"Domena [{tag}]: {dom}")
            if expand_keywords[lang]:
                progress("lang", f"Slowa kluczowe [{tag}]: {', '.join(expand_keywords[lang][:8])}")

    # Transparencja D1: ile trafien odcina okno lat (raz, dla zapytania 1. jezyka).
    primary_q = queries[langs[0]]
    if year_from or year_to:
        c_all = openalex_match_count(primary_q, email, work_type=work_type, api_key=openalex_api_key)
        c_win = openalex_match_count(primary_q, email, year_from=year_from, year_to=year_to, work_type=work_type, api_key=openalex_api_key)
        if c_all:
            result.year_drop_pct = max(0.0, 1.0 - c_win / c_all)
            if progress:
                progress("years", f"Okno lat odcina ~{result.year_drop_pct:.0%} trafien ({c_win}/{c_all}) - swiadoma selekcja.")

    # Odpytaj zrodla per UNIKALNY string zapytania (gdy PL==ENG, np. brak tlumaczenia,
    # robimy jeden przebieg). lang_map: doi -> zbior jezykow, ktore znalazly prace
    # (kwota jezykowa przy wyborze). Kazde zrodlo best-effort: blad nie wywala przebiegu.
    by_query: dict[str, set] = {}
    for lang in langs:
        by_query.setdefault(queries[lang], set()).add(lang)
        # Ekspansja (recall): dodatkowe zapytanie ze slow kluczowych. Czysto
        # ADDYTYWNE — dedup po DOI scala pule, ranking i tak posortuje. Bounded.
        kws = expand_keywords.get(lang) or []
        if kws:
            kw_q = " ".join(" ".join(kws).split()[:12]).strip()
            if kw_q and kw_q.lower() != queries[lang].lower():
                by_query.setdefault(kw_q, set()).add(lang)

    # Planer FASETOWY (Etap 1, spec §16): zapytania „kotwica + faseta" z obiektu
    # intencji. Kotwica = KAŻDA faseta WYMAGANA osobno (krótka, rdzeniowa → szerszy
    # recall niż pełny `topic`); gdy brak required → fallback na zapytanie per język.
    # Faseta = każda OPCJONALNA (dyskryminator, np. „e-value"). ADDYTYWNE — dedup po
    # DOI scala pulę, ranking sortuje. Bounded przez MAX_QUERIES (budżet OpenAlex/S2).
    # Empiria gold-set ES: dociąga klaster e-value, którego generyczna ekspansja
    # keyword-bag NIE łapała (recall@50 35%→~50%).
    if facets:
        for lang in langs:
            anchors = facets_required or [queries[lang]]
            added_q = 0
            for anchor in anchors:
                for fq in build_facet_queries(anchor, facets):
                    if len(by_query) >= MAX_QUERIES:
                        break
                    if fq.lower() not in {q.lower() for q in by_query}:
                        by_query.setdefault(fq, set()).add(lang)
                        added_q += 1
            if progress and added_q:
                progress("lang", f"Fasety [{('ENG' if lang == 'en' else 'PL')}]: +{added_q} zapytań")

    candidates: list[Candidate] = []
    seen: set[str] = set()
    lang_map: dict[str, set] = {}

    def _ingest(found: Any, qlangs: set) -> int:
        added = 0
        for c in found or []:
            if not c.doi:
                continue
            lang_map.setdefault(c.doi, set()).update(qlangs)
            if c.doi not in seen:
                candidates.append(c)
                seen.add(c.doi)
                added += 1
        return added

    for qi, (qstr, qlangs) in enumerate(by_query.items()):
        if qi > 0:
            time.sleep(polite_sleep)  # pacing miedzy jezykami (lagodzi throttling)
        if include_openalex:
            raw = openalex_search(qstr, n, email, year_from=year_from, year_to=year_to, work_type=work_type, sort=sort, api_key=openalex_api_key, progress=progress)
            _ingest(raw, qlangs)
        if include_s2:
            _ingest(semantic_scholar_extend(qstr, email, api_key=s2_api_key, progress=progress), qlangs)
        for prov in (extra_search or []):
            try:
                found = prov.search(qstr, n, email=email, year_from=year_from,
                                     year_to=year_to, work_type=work_type, sort=sort, progress=progress)
            except Exception as exc:  # noqa: BLE001
                if progress:
                    progress("source", f"Zrodlo {getattr(prov, 'name', '?')} niedostepne: {exc}")
                continue
            added = _ingest(found, qlangs)
            if progress:
                progress("source", f"Zrodlo {getattr(prov, 'name', '?')}: +{added} kandydatow")

    result.openalex_total = sum(1 for c in candidates if c.source == "openalex")

    # Snowball wstecz (Etap 3, opt-in): dociągnij PRZYPISY top-seedów — łapie pozycje
    # fundamentalne, do których trafne prace się odwołują, a których szukanie tematyczne
    # nie wyciąga. ADDYTYWNE (dedup po DOI, ranking sortuje), bounded fanoutem + budżetem HTTP.
    # lean refactor: snowball removed (was opt-in; default off)

    candidates, result.versions_merged = _dedup_versions(candidates)
    result.total_found = len(candidates)
    oa = [c for c in candidates if c.is_oa]
    result.oa_count = len(oa)
    result.skipped_non_oa = len(candidates) - len(oa)
    imp_threshold = importance_threshold(oa, preprint_quantile) if allow_preprint else float("inf")
    if progress:
        progress("filter", f"OA: {len(oa)}/{len(candidates)} (pokrycie {result.oa_coverage:.0%})")

    # PRE-RANKING przed pobraniem: dopasowanie do intencji liczone wzgledem tokenow
    # KAZDEGO jezyka (max) - praca w drugim jezyku nie dostaje falszywego 0.
    token_sets = [_content_tokens(f"{queries[lang]} {intent}") for lang in langs]
    oa = prerank_candidates(oa, token_sets)
    if progress and any(token_sets):
        nt = len(set().union(*token_sets)) if token_sets else 0
        progress("prerank", f"Pula uporzadkowana wg dopasowania do intencji ({nt} slow tresciowych) + wplywu - pobieram najlepsze.")

    # BRAMKA TRAFNOSCI (P3): odsiej szum PRZED pobraniem (np. fizyke z arXiv, ktora
    # ma dopasowanie ~0). Zostaw prace >= progu (max po jezykach). Brak takich ->
    # nie pobieraj nic (lepiej 0 niz N smieci). Dziala tez na kwote: pula PL kurczy
    # sie do prac trafnych, wiec _apply_lang_quota nie dobiera fizyki do slotow PL.
    if any(token_sets) and min_intent_match > 0:
        eligible = [c for c in oa if _relevance_multi(token_sets, f"{c.title} {c.abstract}") >= min_intent_match]
        dropped = len(oa) - len(eligible)
        if eligible:
            oa = eligible
            if progress and dropped:
                progress("relevance", f"Bramka trafnosci: odrzucono {dropped} prac ponizej progu {min_intent_match:.0%} (szum) - nie pobieram.")
        elif oa:
            oa = []
            if progress:
                progress("relevance", f"0 prac powyzej progu trafnosci {min_intent_match:.0%} - popraw zapytanie/jezyk; pomijam pobieranie.")

    target = max(n, math.ceil(oversample * n))  # oversampling: pobierz ~1.5N, wybor robi czlowiek
    # Kwota jezykowa (P1): w trybie PL+ENG ustaw udzial PL w pierwszych `target`
    # pozycjach na ~split_pl (reszta ENG), z przelewem gdy ktoras pula nie wypelni slotu.
    if sl == "both":
        oa = _apply_lang_quota(oa, lang_map, search_lang_split_pl, target)
        if progress:
            pct = round(search_lang_split_pl * 100)
            progress("lang", f"Kwota jezykowa: ~{pct}% PL / {100 - pct}% ENG w docelowych {target}.")
    # Dedup cross-RUN (koncepcja §7, decyzja #3): nie pobieramy ponownie pracy juz
    # sciagnietej w poprzednim przebiegu, gdy jej plik nadal istnieje. Tozsamosc =
    # clean_title (ten sam klucz co dedup cross-wersji). Skip nie liczy sie do
    # niezmiennika MANIFEST - praca po prostu nie jest "attempted".
    known_titles: set[str] = set()
    if store is not None and dedup_cross_run:
        try:
            known_titles = store.downloaded_clean_titles()
        except Exception:
            known_titles = set()
    for cand in oa:
        if len(result.downloaded) >= target:
            break
        if known_titles and clean_title(cand.title) in known_titles:
            result.skipped_known += 1
            if progress:
                progress("dedup", f"Pomijam (juz pobrane w poprzednim przebiegu): {cand.filename()}")
            continue
        if store is not None:
            try:
                store.register_paper(
                    {
                        "doi": cand.doi, "title": cand.title, "year": cand.year,
                        "authors": cand.first_author, "oa_status": (cand.oa_status or "oa"),
                        "source": cand.source, "clean_title": clean_title(cand.title),
                        "json_openalex": None, "license": cand.license, "version": cand.version,
                        "venue": cand.venue, "landing_page_url": cand.landing_page_url,
                        "jel_codes": cand.jel_codes, "publication_type": cand.work_type,
                        "retracted": 1 if cand.is_retracted else 0,
                    }
                )
            except Exception:
                pass
        dest = _unique_dest(pdf_dir, cand.filename(), cand.doi, used_names)
        if progress:
            progress("download", f"Pobieram: {dest.name}")
        ok, _used = resolve_and_download(cand, dest, email, extra_resolvers, s2_api_key=s2_api_key)
        if not ok and allow_preprint and _velocity(cand) >= imp_threshold:
            pre_url = arxiv_search_pdf(cand.title, cand.first_author, email)
            if pre_url:
                pre_dest = _unique_dest(pdf_dir, cand.filename()[:-4] + "__preprint.pdf", cand.doi, used_names)
                if progress:
                    progress("preprint", f"Wazna praca bez wersji wydawcy - probuje arXiv: {pre_dest.name}")
                if download_pdf(pre_url, pre_dest, email):
                    ok = True
                    dest = pre_dest
            time.sleep(0.5)
        if not ok:
            stub = _write_stub(pdf_dir / "_stubs", cand)
            result.stubs.append(stub)
            result.failed.append(f"{cand.doi} (brak PDF -> stub)")
            manifest_rows.append((cand, "stub", stub))
            if progress:
                progress("stub", f"Brak PDF -> zaślepka: {stub} ({len(result.stubs)})")
            time.sleep(polite_sleep)
            continue
        # Pobrane OK. Weryfikacja LLM NIE odrzuca - daje tylko score trafnosci do rankingu.
        rel_score = None
        llm_summary = ""
        # lean refactor: LLM relevance verification removed (a07 owns LLM); rel_score stays None
        result.downloaded.append(dest.name)
        if progress:
            progress("pdf", f"Pobrano ({len(result.downloaded)}/{target}): {dest.name}")
        if store is not None and dedup_cross_run:
            ct = clean_title(cand.title)
            try:
                store.mark_downloaded(cand.doi, ct, str(dest))
            except Exception:
                pass
            if ct:
                known_titles.add(ct)  # chron przed duplikatem w obrebie tego samego przebiegu
        manifest_rows.append((cand, "preprint" if "__preprint" in dest.name else "pdf", dest.name))
        if cand.is_retracted:
            result.n_retracted += 1
        result.items.append({
            "filename": dest.name, "doi": cand.doi, "title": cand.title,
            "year": cand.year, "cited_by": cand.cited_by, "work_type": cand.work_type,
            "source": cand.source, "source_api": cand.source, "is_preprint": "__preprint" in dest.name,
            "rel_score": rel_score, "velocity": round(_velocity(cand), 4),
            "authors": cand.authors,
            "abstract_short": (llm_summary or first_words(cand.abstract, summary_words)),
            "summary_source": ("llm" if llm_summary else "abstract"),
            "oa_status": cand.oa_status, "license": cand.license, "version": cand.version,
            "venue": cand.venue, "landing_page_url": cand.landing_page_url,
            "jel_codes": cand.jel_codes, "publication_type": cand.work_type,
            # Sygnaly wartosci/integralnosci (A1 + znormalizowany wplyw):
            "is_retracted": cand.is_retracted, "fwci": cand.fwci, "cnp": cand.cnp,
            "is_top10": cand.is_top10, "source_id": cand.source_id, "issn_l": cand.issn_l,
            "intent_match": (round(_relevance_multi(token_sets, f"{cand.title} {cand.abstract}"), 3) if any(token_sets) else None),
            "retrieved_at": datetime.now().isoformat(timespec="seconds"),
        })
        time.sleep(polite_sleep)

    # Prestiz venue: dociagnij 2yr_mean_citedness zrodla (cache per source, best-effort).
    # Tylko gdy store wspiera cache - inaczej pomijamy (np. testy offline z atrapa store).
    if store is not None and hasattr(store, "get_source_stats"):
        src_cache: dict[str, dict] = {}
        for it in result.items:
            sid = it.get("source_id") or ""
            if not sid:
                continue
            if sid not in src_cache:
                src_cache[sid] = fetch_source_stats(sid, email, store=store, api_key=openalex_api_key)
            it["venue_impact"] = src_cache[sid].get("mean2yr")
            it["venue_h_index"] = src_cache[sid].get("h_index")

    # Ranking wstepny (domyslne wagi) - UI moze przeliczyc na zywo po zmianie wag.
    result.items = rank_items(result.items, DEFAULT_RANK_WEIGHTS)

    _write_manifest(pdf_dir, topic, run_meta_n=n, rows=manifest_rows)
    result.manifest_ok = (len(result.downloaded) + len(result.stubs) + len(result.rejected) == len(manifest_rows))
    return result


# -- Raport selekcji (dla UI / CLI) -------------------------------------
def apply_selection(pdf_dir: Path, items: list, selected_filenames: list) -> dict:
    """Wybrane PDF zostaja w _scout_pdf; pozostale (pobrane) przenosimy do
    _scout_pdf/_rezerwa/ (nic nie kasujemy). Zwraca {selected, reserved}."""
    sel = set(selected_filenames or [])
    reserve_dir = pdf_dir / "_rezerwa"
    selected, reserved = [], []
    for it in items or []:
        name = it.get("filename")
        if not name:
            continue
        if name in sel:
            selected.append(name)
            continue
        src = pdf_dir / name
        if src.is_file():
            reserve_dir.mkdir(parents=True, exist_ok=True)
            try:
                src.replace(reserve_dir / name)
            except Exception:
                pass
        reserved.append(name)
    return {"selected": selected, "reserved": reserved}


# -- Most do modulu 2 (konwerter): wybrane PDF -> _mathpix_in -----------
