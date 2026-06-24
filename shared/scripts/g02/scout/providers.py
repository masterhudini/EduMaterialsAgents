"""Pluggable zrodla literatury (SourceProvider) i resolvery PDF.

Architektura (rekomendacja „economic literature harvester"): rdzen OpenAlex+S2
zostaje wbudowany w `engine.run_student` (zero zmian dla domyslnego przeplywu),
a DODATKOWE zrodla wpina sie tu jako jednolite obiekty wlaczane flaga `SOURCES`.
KAZDY provider jest best-effort: blad/timeout -> pusty wynik, nigdy nie wywala
przebiegu (przechwycone w engine). Zaleznosci: wylacznie stdlib (urllib).

Dwie role (obiekt moze pelnic obie - np. CORE):
  - SearchProvider.search(topic, n, **filters) -> list[Candidate]   (odkrywanie)
  - Resolver.resolve(cand, email) -> list[str]                      (URL-e PDF)

Tozsamosc prac bez DOI: provider syntetyzuje stabilny klucz "<zrodlo>:<id>",
zeby dedup po DOI i klucz SQLite (papers.doi) pozostaly unikalne.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Protocol, runtime_checkable

from . import engine
from .http_util import request_with_retry

_UA = "RadarPDF/0.1 (https://uew.edu.pl; mailto:{email})"


@runtime_checkable
class SearchProvider(Protocol):
    name: str
    def search(self, topic: str, n: int, **filters: Any) -> list["engine.Candidate"]: ...


@runtime_checkable
class Resolver(Protocol):
    name: str
    def resolve(self, cand: "engine.Candidate", email: str) -> list[str]: ...


# -- HTTP best-effort (z naglowkami; nigdy nie rzuca) -------------------
def _json_get(url: str, *, email: str = "", headers: dict | None = None, timeout: float = 15.0) -> dict | None:
    """Best-effort JSON GET dla providerow (CORE/EconBiz/Crossref) - TERAZ z odpornoscia
    na throttling (429/5xx + Retry-After + backoff przez request_with_retry). Terminalny
    blad -> None (provider degraduje sie, nie wywala przebiegu)."""
    hdrs = {"User-Agent": _UA.format(email=email or "anonymous@example.com"), "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    try:
        raw = request_with_retry(url, headers=hdrs, timeout=timeout, max_attempts=3)
        return json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return None


def _year_from_text(value: Any) -> int | None:
    m = re.search(r"(19|20)\d{2}", str(value or ""))
    return int(m.group(0)) if m else None


def _title_ok(a: str, b: str, *, min_sim: float = 0.55) -> bool:
    """Zabezpieczenie przed wciagnieciem zlej pracy przy dopasowaniu po tytule."""
    return engine._jaccard(engine._norm_tokens(a), engine._norm_tokens(b)) >= min_sim


# -- arXiv: pelnoprawne zrodlo wyszukiwania (quant/ML/ekonometria) ------
_ARXIV_API = "http://export.arxiv.org/api/query"
_ATOM = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


class ArxivProvider:
    """Wyszukiwanie e-printow arXiv (Atom XML). Wczesniej arXiv byl tylko
    fallbackiem preprintowym; tu jest pierwszoklasowym providerem dla zapytan
    ilosciowych. Kazdy wynik ma pdf_url (OA), wiec realnie zasila pobieranie."""

    name = "arxiv"

    # Kategorie quant/ML/ekonometria - TWARDO odcinaja fizyke (gdzie 'cross'/'flows'/
    # 'sectors' znacza cross-section / collective flow / detector sectors). Bez tego
    # nieostre `all:` lapie wielkie kolaboracje (LHCb/LIGO). Patrz diagnoza P2.
    _CATEGORIES = "cat:q-fin.* OR cat:cs.LG OR cat:stat.ML OR cat:econ.EM OR cat:cs.AI OR cat:cs.CE"

    def _build_query(self, topic: str) -> str:
        """Zapytanie fielded: AND najwyzej 4 slow TRESCIOWYCH (transliteracja PL,
        bez slow funkcyjnych) ZAWEZONE do kategorii. PL daje ~0 (slowa nie pasuja po
        kategoriach) - i dobrze: arXiv-PL nie ma juz czym zaśmiecać puli."""
        toks: list[str] = []
        seen: set[str] = set()
        for t in re.findall(r"[a-z0-9]+", engine._transliterate(topic or "").lower()):
            if len(t) > 2 and t not in engine._STOPWORDS and t not in seen:
                seen.add(t)
                toks.append(t)
            if len(toks) >= 4:
                break
        if toks:
            return "(" + " AND ".join(f"all:{t}" for t in toks) + f") AND ({self._CATEGORIES})"
        return f"({self._CATEGORIES})"

    def search(self, topic: str, n: int, *, email: str = "", year_from: int | None = None,
               year_to: int | None = None, **_: Any) -> list["engine.Candidate"]:
        q = urllib.parse.urlencode({
            "search_query": self._build_query(topic), "start": 0,
            "max_results": min(max(2 * n, 10), 100), "sortBy": "relevance",
        })
        try:
            raw = request_with_retry(f"{_ARXIV_API}?{q}",
                                     headers={"User-Agent": _UA.format(email=email or "anonymous@example.com")},
                                     timeout=20, max_attempts=3)
            root = ET.fromstring(raw)
        except Exception:
            return []
        out: list[engine.Candidate] = []
        for e in root.findall("a:entry", _ATOM):
            title = " ".join((e.findtext("a:title", default="", namespaces=_ATOM) or "").split())
            if not title:
                continue
            arxiv_id = ""
            m = re.search(r"arxiv\.org/abs/([\w.\-/]+)", e.findtext("a:id", default="", namespaces=_ATOM) or "")
            if m:
                arxiv_id = m.group(1)
            doi = (e.findtext("arxiv:doi", default="", namespaces=_ATOM) or "").strip().lower()
            names = [(a.findtext("a:name", default="", namespaces=_ATOM) or "") for a in e.findall("a:author", _ATOM)]
            pdf = ""
            for l in e.findall("a:link", _ATOM):
                if l.get("title") == "pdf" or l.get("type") == "application/pdf":
                    href = l.get("href") or ""
                    pdf = href if href.endswith(".pdf") else (href + ".pdf" if href else "")
                    break
            if not pdf and arxiv_id:
                pdf = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
            yr = _year_from_text(e.findtext("a:published", default="", namespaces=_ATOM))
            if year_from and yr and yr < int(year_from):
                continue
            if year_to and yr and yr > int(year_to):
                continue
            out.append(engine.Candidate(
                doi=(engine._clean_doi(doi) if doi else (f"arxiv:{arxiv_id}" if arxiv_id else "")),
                title=title, year=yr,
                first_author=(names[0] if names else ""), is_oa=True, pdf_url=(pdf or None),
                source="arxiv", work_type="preprint",
                authors=", ".join(names[:3]) + (" i in." if len(names) > 3 else ""),
                abstract=" ".join((e.findtext("a:summary", default="", namespaces=_ATOM) or "").split()),
                oa_status="green", version="submittedVersion",
                venue="arXiv", landing_page_url=(f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else ""),
            ))
        return out


# -- CORE: agregator repozytoriow OA (search + resolver) ----------------
_CORE_SEARCH = "https://api.core.ac.uk/v3/search/works"


class CoreProvider:
    """CORE v3 — pelne teksty z repozytoriow OA. Dla ekonomii czesto trafia w
    working papers (np. serie bankow centralnych), ktorych nie ma w Unpaywall.
    Pelni obie role: wyszukiwanie ORAZ resolver (po DOI/tytule). Klucz opcjonalny
    (bez niego dziala z nizszym limitem)."""

    name = "core"

    def __init__(self, api_key: str = "") -> None:
        self.api_key = (api_key or "").strip()

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def _query(self, q: str, limit: int, email: str) -> list[dict]:
        url = f"{_CORE_SEARCH}?{urllib.parse.urlencode({'q': q, 'limit': limit})}"
        data = _json_get(url, email=email, headers=self._headers(), timeout=20)
        return (data or {}).get("results") or []

    @staticmethod
    def _pdf_urls(rec: dict) -> list[str]:
        urls: list[str] = []
        dl = rec.get("downloadUrl")
        if dl:
            urls.append(dl)
        for link in rec.get("links") or []:
            if (link or {}).get("type") in ("download", "fulltext") and link.get("url"):
                urls.append(link["url"])
        for u in rec.get("sourceFulltextUrls") or []:
            if u:
                urls.append(u)
        out, seen = [], set()
        for u in urls:
            if u and u not in seen:
                seen.add(u)
                out.append(u)
        return out

    def search(self, topic: str, n: int, *, email: str = "", **_: Any) -> list["engine.Candidate"]:
        out: list[engine.Candidate] = []
        for rec in self._query(topic, min(max(2 * n, 10), 100), email):
            title = (rec.get("title") or "").strip()
            if not title:
                continue
            doi = engine._clean_doi(rec.get("doi"))
            authors = [(a or {}).get("name", "") for a in (rec.get("authors") or [])]
            authors = [a for a in authors if a]
            pdfs = self._pdf_urls(rec)
            out.append(engine.Candidate(
                doi=(doi or f"core:{rec.get('id') or engine.clean_title(title)[:40]}"),
                title=title, year=(rec.get("yearPublished") or _year_from_text(rec.get("publishedDate"))),
                first_author=(authors[0] if authors else ""), is_oa=True,
                pdf_url=(pdfs[0] if pdfs else None), alt_pdf_urls=pdfs[1:],
                source="core", cited_by=int(rec.get("citationCount") or 0),
                work_type=(rec.get("documentType") or ""),
                authors=", ".join(authors[:3]) + (" i in." if len(authors) > 3 else ""),
                abstract=(rec.get("abstract") or ""), oa_status="green",
                venue=", ".join((rec.get("dataProviders") and [str((rec["dataProviders"][0] or {}).get("name", ""))]) or []),
                landing_page_url=(f"https://core.ac.uk/works/{rec.get('id')}" if rec.get("id") else ""),
            ))
        return out

    def resolve(self, cand: "engine.Candidate", email: str) -> list[str]:
        d = (cand.doi or "")
        recs: list[dict] = []
        if d and not d.startswith(("core:", "arxiv:", "econbiz:")):
            recs = self._query(f'doi:"{d}"', 3, email)
        if not recs and cand.title:
            recs = self._query(f'title:"{cand.title}"', 3, email)
        urls: list[str] = []
        for rec in recs:
            if d and not d.startswith(("core:", "arxiv:", "econbiz:")):
                if engine._clean_doi(rec.get("doi")) == d:
                    urls += self._pdf_urls(rec)
                    continue
            if _title_ok(cand.title, rec.get("title") or ""):
                urls += self._pdf_urls(rec)
        out, seen = [], set()
        for u in urls:
            if u and u not in seen:
                seen.add(u)
                out.append(u)
        return out


# -- Crossref: normalizator DOI (resolver linkow PDF, best-effort) ------
class CrossrefResolver:
    """Crossref jako resolver ostatniej szansy: dla realnego DOI pobiera
    message.link[] z linkami do pelnego tekstu (gdy wydawca je wystawia).
    Crossref to przede wszystkim metadane — PDF bywa za entitlementem, wiec
    traktujemy go jako uzupelnienie kaskady, nie glowne zrodlo."""

    name = "crossref"

    def resolve(self, cand: "engine.Candidate", email: str) -> list[str]:
        d = (cand.doi or "")
        if not d or d.startswith(("core:", "arxiv:", "econbiz:")):
            return []
        data = _json_get(f"https://api.crossref.org/works/{urllib.parse.quote(d)}", email=email, timeout=15)
        msg = (data or {}).get("message") or {}
        out: list[str] = []
        for link in msg.get("link") or []:
            url = (link or {}).get("URL") or ""
            ct = (link.get("content-type") or "").lower()
            app = (link.get("intended-application") or "").lower()
            # Crossref daje rozne typy linkow; bierzemy te, ktore wygladaja na PDF
            # albo sa przeznaczone do maszynowego dostepu. Best-effort - i tak
            # czesc wroci 403 (entitlement), co downloader obsluguje lagodnie.
            looks_pdf = "pdf" in ct or "/pdf" in url.lower() or url.lower().endswith(".pdf")
            machine_app = app in ("text-mining", "syndication", "similarity-checking", "unspecified")
            if url and (looks_pdf or machine_app):
                out.append(url)
        return out


# -- EconBiz: dziedzinowe odkrywanie ekonomii (discovery, cienkie meta) -
class EconBizProvider:
    """EconBiz (ZBW) — dziedzinowy indeks ekonomii/biznesu. Wyniki sa mieszane
    (artykuly, working papers, ale i konferencje/eventy) i ubogie w metadane:
    zwykle brak DOI i brak bezposredniego PDF. Pelni role ODKRYWCZA — kandydaci
    przechodza przez kaskade resolverow (Unpaywall po DOI, CORE/arXiv po tytule);
    gdy PDF sie nie znajdzie, laduja jako stub (nic nie ginie). Domyslnie OFF."""

    name = "econbiz"
    _SKIP_SOURCES = {"events"}
    _SKIP_TYPES = {"event", "conference"}

    def search(self, topic: str, n: int, *, email: str = "", **_: Any) -> list["engine.Candidate"]:
        url = f"https://api.econbiz.de/v1/search?{urllib.parse.urlencode({'q': topic, 'size': min(max(2 * n, 10), 100)})}"
        data = _json_get(url, email=email, timeout=20)
        hits = ((data or {}).get("hits") or {}).get("hits") or []
        out: list[engine.Candidate] = []
        for h in hits:
            src = str((h.get("source") or "")).lower()
            typ = h.get("type")
            types = [str(t).lower() for t in (typ if isinstance(typ, list) else [typ])]
            if src in self._SKIP_SOURCES or any(t in self._SKIP_TYPES for t in types):
                continue
            title = h.get("title")
            title = (title[0] if isinstance(title, list) else title) or ""
            title = str(title).strip()
            if not title:
                continue
            creators = h.get("creator") or []
            first = (creators[0] if isinstance(creators, list) and creators else (creators or "")) or ""
            land = h.get("identifier_url")
            land = (land[0] if isinstance(land, list) and land else land) or ""
            out.append(engine.Candidate(
                doi=f"econbiz:{h.get('id')}", title=title,
                year=_year_from_text((h.get("date") or [""])[0] if isinstance(h.get("date"), list) else h.get("date")),
                first_author=str(first), is_oa=True, pdf_url=None, source="econbiz",
                work_type=(types[0] if types and types[0] != "none" else ""),
                landing_page_url=str(land), oa_status="unknown",
            ))
        return out


# -- Consensus: AI-owe wyszukiwanie literatury (wymaga klucza API) -------
# UWAGA: endpoint i mapowanie pol to NAJLEPSZE PRZYBLIZENIE - potwierdzic wg
# dokumentacji API Consensus (dostarczanej z kluczem). Provider jest best-effort:
# brak klucza / zly endpoint / blad -> [] (nie wywala przebiegu). Baze mozna nadpisac
# zmienna srodowiskowa CONSENSUS_API_BASE (gdyby docs podaly inny host/sciezke).
import os as _os
_CONSENSUS_SEARCH = _os.environ.get("CONSENSUS_API_BASE", "https://api.consensus.app/v1/search")


class ConsensusProvider:
    """Consensus (consensus.app) - wyszukiwanie literatury z AI. Pelni role
    ODKRYWCZA; gdy rekord ma bezposredni PDF -> pobieralny, inaczej kaskada
    resolverow albo stub. AKTYWNY TYLKO Z KLUCZEM (bez klucza search() zwraca [])."""

    name = "consensus"

    def __init__(self, api_key: str = "") -> None:
        self.api_key = (api_key or "").strip()

    def search(self, topic: str, n: int, *, email: str = "", **_: Any) -> list["engine.Candidate"]:
        if not self.api_key:
            return []
        url = f"{_CONSENSUS_SEARCH}?{urllib.parse.urlencode({'query': topic, 'limit': min(max(2 * n, 10), 50)})}"
        # Klucz najczesciej idzie naglowkiem; wysylamy oba popularne warianty (nadmiarowy jest ignorowany).
        data = _json_get(url, email=email, headers={"X-API-Key": self.api_key, "Authorization": f"Bearer {self.api_key}"}, timeout=25)
        if not data:
            return []
        items = (data.get("results") or data.get("papers") or data.get("data")
                 or (data if isinstance(data, list) else []))
        out: list[engine.Candidate] = []
        for rec in items or []:
            if not isinstance(rec, dict):
                continue
            title = (rec.get("title") or rec.get("paper_title") or "").strip()
            if not title:
                continue
            doi = engine._clean_doi(rec.get("doi") or (rec.get("externalIds") or {}).get("DOI"))
            raw_authors = rec.get("authors") or rec.get("author") or []
            if isinstance(raw_authors, list):
                names = [(a.get("name") if isinstance(a, dict) else str(a)) for a in raw_authors]
            else:
                names = [str(raw_authors)]
            names = [x for x in names if x]
            pdf = rec.get("pdf_url") or (rec.get("openAccessPdf") or {}).get("url")
            out.append(engine.Candidate(
                doi=(doi or f"consensus:{rec.get('id') or engine.clean_title(title)[:40]}"),
                title=title,
                year=(rec.get("year") or _year_from_text(rec.get("publication_date") or rec.get("date"))),
                first_author=(names[0] if names else ""),
                is_oa=bool(pdf), pdf_url=(pdf or None), source="consensus",
                authors=", ".join(names[:3]) + (" i in." if len(names) > 3 else ""),
                abstract=(rec.get("abstract") or rec.get("snippet") or ""),
                landing_page_url=(rec.get("url") or rec.get("consensus_url") or rec.get("landing_page_url") or ""),
                oa_status=("green" if pdf else "unknown"),
            ))
        return out


# -- Perplexity Sonar przez OpenRouter (online discovery; WSPOLNY klucz) -
class PerplexityProvider:
    """Perplexity Sonar przez OpenRouter — modele `perplexity/sonar*` maja LIVE web
    search, wiec lapia prace nowe / po cutoffie / inaczej sformulowane, ktore gubi
    keyword-search OpenAlex. Rola ODKRYWCZA: pyta model o liste prac (JSON), zwraca
    kandydatow -> kaskada resolverow (Unpaywall/CORE/Crossref po DOI) albo stub
    (jak EconBiz). Uzywa WSPOLNEGO klucza OpenRouter (jak weryfikacja LLM) — bez
    osobnego klucza/sekretu. Tani domyslny model `perplexity/sonar`. AKTYWNY TYLKO
    z kluczem OpenRouter (bez klucza search() zwraca [])."""

    name = "perplexity"

    def __init__(self, api_key: str = "", model: str = "perplexity/sonar") -> None:
        self.api_key = (api_key or "").strip()
        self.model = (model or "perplexity/sonar").strip()

    @staticmethod
    def _papers_from_content(content: str) -> list:
        """Wyluskaj liste prac: tablica JSON, albo obiekt z kluczem papers/results/
        data. Best-effort — cokolwiek innego -> []."""
        if not content:
            return []
        m = re.search(r"\[.*\]", content, re.S)
        if m:
            try:
                arr = json.loads(m.group(0))
                if isinstance(arr, list):
                    return arr
            except Exception:
                pass
        m = re.search(r"\{.*\}", content, re.S)
        if m:
            try:
                obj = json.loads(m.group(0))
                for k in ("papers", "results", "data"):
                    if isinstance(obj.get(k), list):
                        return obj[k]
            except Exception:
                pass
        return []

    def search(self, topic: str, n: int, *, email: str = "", **_: Any) -> list["engine.Candidate"]:
        if not self.api_key:
            return []
        want = min(max(2 * n, 10), 40)
        system = (
            "You are an academic literature search assistant with live web access. "
            "Return ONLY a JSON array of the most relevant peer-reviewed papers for the user's query. "
            "Each element: {\"title\": string, \"year\": number|null, \"doi\": string|null, \"authors\": string}. "
            "Strongly prefer items that have a DOI. No prose, no markdown — a JSON array only."
        )
        body = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"Query: {topic}\nReturn up to {want} papers as a JSON array."},
            ],
            "temperature": 0,
        }).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
            "HTTP-Referer": "https://local.llmwiki.radar", "X-Title": "Radar PDF",
        }
        try:
            raw = request_with_retry(engine.OPENROUTER, data=body, method="POST", headers=headers, timeout=45, max_attempts=3)
            data = json.loads(raw.decode("utf-8", "replace"))
            content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
        except Exception:
            return []
        out: list[engine.Candidate] = []
        for i, rec in enumerate(self._papers_from_content(content)):
            if not isinstance(rec, dict):
                continue
            title = str(rec.get("title") or "").strip()
            if not title:
                continue
            doi = engine._clean_doi(rec.get("doi"))
            authors = rec.get("authors") or ""
            if isinstance(authors, list):
                authors = ", ".join(str(a) for a in authors if a)
            authors = str(authors)
            out.append(engine.Candidate(
                doi=(doi or f"perplexity:{i}:{engine.clean_title(title)[:40]}"),
                title=title, year=_year_from_text(rec.get("year")),
                first_author=(authors.split(",")[0].strip() if authors else ""),
                is_oa=True, pdf_url=None, source="perplexity",
                authors=authors, abstract="", oa_status="unknown",
            ))
        return out


# -- Fabryki: z konfiguracji (flaga SOURCES) do list obiektow -----------
def parse_sources(raw: str) -> set[str]:
    return {s.strip().lower() for s in (raw or "").replace(";", ",").split(",") if s.strip()}


def build_search_providers(sources: set[str], *, core_api_key: str = "", consensus_api_key: str = "",
                           openrouter_key: str = "", perplexity_model: str = "perplexity/sonar") -> list[SearchProvider]:
    """Dodatkowe (poza wbudowanym OpenAlex+S2) providery wyszukiwania. Consensus
    dolaczany TYLKO gdy wybrany ORAZ jest klucz API. Perplexity (Sonar przez
    OpenRouter) — TYLKO gdy wybrany ORAZ jest klucz OpenRouter (wspolny, jak LLM)."""
    out: list[SearchProvider] = []
    if "arxiv" in sources:
        out.append(ArxivProvider())
    if "core" in sources:
        out.append(CoreProvider(core_api_key))
    if "econbiz" in sources:
        out.append(EconBizProvider())
    if "consensus" in sources and (consensus_api_key or "").strip():
        out.append(ConsensusProvider(consensus_api_key))
    if "perplexity" in sources and (openrouter_key or "").strip():
        out.append(PerplexityProvider(openrouter_key, perplexity_model))
    return out


def build_resolvers(sources: set[str], *, core_api_key: str = "") -> list[Resolver]:
    """Dodatkowe resolvery PDF doklejane do kaskady akwizycji."""
    out: list[Resolver] = []
    if "core" in sources:
        out.append(CoreProvider(core_api_key))
    if "crossref" in sources:
        out.append(CrossrefResolver())
    return out


_KNOWN_SOURCES = {"arxiv", "core", "crossref", "econbiz", "consensus", "perplexity"}
