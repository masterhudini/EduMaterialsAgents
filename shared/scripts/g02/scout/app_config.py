from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import constants
from . import projects

# Wzorowane na llmwiki_pdf/app_config.py, ale samodzielne (kopia dla niezależności
# wersji). Różnice: katalogi i klucze Scouta; brak zależności od Mathpix; lokalny
# read_env_file zamiast importu z mathpix_batch.

# Ujednolicony, WSPÓLNY workspace LLM-Wiki — jeden prefiks llmwiki_, zero _radar_/_scout_.
# PDF-y trafiają do PROJECT-SCOPED llmwiki_in/<projekt> (skąd czyta konwerter), raporty do
# llmwiki_out/<projekt>/reports. Env i stan WSPÓLNE z konwerterem (llmwiki_env/llmwiki.env,
# llmwiki_state — osobny plik stanu per moduł). Patrz projects.py (kopia jak w konwerterze).
APP_STATE_DIR = "llmwiki_state"
ENV_DIR = "llmwiki_env"
APP_STATE_FILE = "radar_state.json"
DEFAULT_ENV_FILE = "llmwiki.env"      # WSPÓLNY env obu modułów
LEGACY_ENV_FILE = "radar.env"         # zgodność wsteczna: stary per-modułowy env

# Jedyny sekret Scouta to klucz OpenRouter. E-mail do polite-pool NIE jest
# sekretem (trafia do nagłówka requestów), więc nie podlega szyfrowaniu DPAPI.
SECRET_KEYS = {"OPENROUTER_API_KEY", "CORE_API_KEY", "OPENALEX_API_KEY", "S2_API_KEY", "CONSENSUS_API_KEY"}

DEFAULT_ENV_VALUES: dict[str, str] = {
    # Wariant potoku: student (0 zł, bez LLM) | hybrid (tani LLM) | deep (premium).
    "DEFAULT_TIER": "student",
    # Kontakt do "polite pool" OpenAlex/Unpaywall — szybsza kolejka, dobre obyczaje.
    "POLITE_POOL_EMAIL": "",
    # Modele OpenRouter wg wariantu (ceny/nazwy zsondowane na zywo z OpenRouter).
    # Student: 2 opcje - flash-lite (tani, niezawodny) i Llama 3.3 70B :free (darmowy).
    "OPENROUTER_MODEL_HYBRID": "google/gemini-2.5-flash-lite",
    "OPENROUTER_MODEL_DEEP": "google/gemini-2.5-pro",
    # Twardy limit kosztu na jeden przebieg (USD) — bezpiecznik dla pętli uzupełniania.
    "LLM_MAX_COST_PER_RUN_USD": "1.00",
    # Ile tokenów wycinka (Abstract+Intro+Conclusions) wysyłamy na artykuł.
    "LLM_MAX_INPUT_TOKENS_PER_PAPER": "2000",
    # Domyślna liczba docelowych, dopasowanych artykułów.
    "DEFAULT_TARGET_N": "20",
    # Fallback preprintowy (arXiv) dla WAZNYCH prac bez wersji wydawcy (top kwantyl velocity).
    "PREPRINT_FALLBACK": "false",
    "PREPRINT_TOP_QUANTILE": "0.2",
    # Weryfikacja trafnosci LLM po pobraniu (Student z LLM). Wymaga klucza OpenRouter.
    "VERIFY_LLM": "false",
    # Oversampling: pobierz ~factor*N, wybor robi czlowiek (ranking + rezerwa).
    "OVERSAMPLE_FACTOR": "1.5",
    # Wagi rankingu (dowolne dodatnie, normalizowane wewnetrznie).
    # Wplyw = znormalizowany (cnp/fwci), prestige = 2yr_mean_citedness venue.
    "RANK_W_REL": "0.4",
    "RANK_W_IMPACT": "0.3",
    "RANK_W_RECENCY": "0.10",
    "RANK_W_TYPE": "0.05",
    "RANK_W_PRESTIGE": "0.15",
    # Cena modelu (USD/1M tok input) do estymacji i twardego limitu kosztu.
    # 0.10 = input gemini-2.5-flash-lite; model :free ma 0 (estymata wtedy zawyza, nieszkodliwie).
    "LLM_MODEL_PRICE_USD_PER_M": "0.10",
    # Odstep miedzy zadaniami (rate-limit/dobre obyczaje).
    "POLITE_SLEEP_SECONDS": "1.0",
    # Bezpieczniki HTTP (warstwa sieci, patrz constants.py). 1) governor predkosci:
    # min-odstep miedzy zapytaniami do hosta (~50/s). 2) twardy licznik zapytan w
    # JEDNYM przebiegu — anty-petla (nieskonczona ekspansja/retry nie zje calego dnia).
    "HTTP_MIN_INTERVAL_SECONDS": "0.02",
    "HTTP_MAX_CALLS_PER_RUN": "500",
    # Dlugosc streszczenia LLM (slowa) do okna wyboru.
    "SUMMARY_WORDS": "50",
    # Dedup cross-RUN: nie pobieraj ponownie pracy juz sciagnietej (gdy plik istnieje).
    "DEDUP_CROSS_RUN": "true",
    # Dodatkowe zrodla literatury (poza wbudowanym OpenAlex+Semantic Scholar).
    # Lista po przecinku z {arxiv, core, crossref, econbiz}. Puste = sam rdzen
    # (zachowanie domyslne, zero zmian). Kazde zrodlo best-effort.
    "SOURCES": "",
    # Klucz CORE (opcjonalny - CORE dziala bez niego, klucz podnosi limity).
    "CORE_API_KEY": "",
    # Klucz OpenAlex (opcjonalny - OpenAlex dziala z samym polite-pool mailto).
    "OPENALEX_API_KEY": "",
    # Klucz Semantic Scholar (opcjonalny). BEZ niego S2 jest POMIJANY (publiczny
    # limit niemal zawsze 429 - tylko szum). Z kluczem: naglowek x-api-key.
    "S2_API_KEY": "",
    # Klucz Consensus (consensus.app). Zrodlo 'consensus' jest AKTYWNE TYLKO z tym
    # kluczem - bez niego checkbox w UI jest nieaktywny, a provider nie jest budowany.
    "CONSENSUS_API_KEY": "",
    # Model Perplexity Sonar (przez OpenRouter) dla zrodla 'perplexity' — Sonar ma
    # live web search. Tani domyslny 'perplexity/sonar'; 'perplexity/sonar-pro' =
    # lepsza jakosc, drozej. BEZ osobnego klucza — uzywa klucza OpenRouter.
    "PERPLEXITY_MODEL": "perplexity/sonar",
    # Tylko Open Access (Unpaywall is_oa). Patrz koncepcja §9 D1 — przy false
    # potok Deep próbuje EZproxy/token uczelni. Domyślnie true (tanio, legalnie).
    "OA_ONLY": "true",
    # Język(i) odpytania źródeł, NIEZALEŻNIE od języka wpisanego w formularzu:
    # pl | en | both. 'both' = pytaj w obu językach i scal pulę. Tłumaczenie
    # zapytania robi OpenRouter (P1) — angielski drastycznie podnosi pokrycie
    # (OpenAlex: PL≈0 vs EN≈setki trafień dla tych samych haseł).
    "SEARCH_LANG": "both",
    # Udział puli PL w trybie 'both' (0..1; reszta = ENG). Miękka kwota z
    # przelewem: gdy PL nie wypełni slotu, resztę dobiera ENG (nic się nie marnuje).
    "SEARCH_LANG_SPLIT_PL": "0.25",
    # Ekspansja zapytania przez LLM (recall): poza tłumaczeniem zapytania dolicz
    # zestaw słów kluczowych (synonimy/inne sformułowania) i odpytaj nimi źródła
    # DODATKOWO. Wzorzec węzła „Translate & Keywords" z n8n. Działa TYLKO przy
    # kluczu OpenRouter; fail-safe (błąd → degradacja do zwykłego tłumaczenia).
    "QUERY_EXPANSION": "true",
    # Próg trafności PRZED pobraniem (P3): minimalne dopasowanie tytuł+abstrakt do
    # słów zapytania (max po językach). Odsiewa szum (np. fizykę z arXiv) zanim
    # cokolwiek pobierzemy. 0 = wyłącz bramkę. 0.1 ≈ „min. 1 słowo treściowe trafia".
    "MIN_INTENT_MATCH": "0.1",
    # Szyfrowanie sekretów w spoczynku przez Windows DPAPI (konto użytkownika).
    "ENCRYPT_SECRETS": "false",
}


def read_env_file(path: Path) -> dict[str, str]:
    """Minimalny parser plików .env (KEY=VALUE). Obsługuje komentarze (#),
    puste linie i wartości w cudzysłowie JSON. Samodzielny — bez zależności od
    konwertera. Sekrety w formacie ``dpapi:...`` są odszyfrowywane przezroczyście."""
    values: dict[str, str] = {}
    if not path or not Path(path).is_file():
        return values
    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if value.startswith('"') and value.endswith('"') and len(value) >= 2:
            try:
                value = json.loads(value)
            except ValueError:
                value = value[1:-1]
        if value.startswith("dpapi:"):
            try:
                from .secret_store import decrypt_if_protected

                value = decrypt_if_protected(value)
            except Exception:
                pass
        values[key] = value
    return values



def shared_openrouter_key(root: Path) -> tuple[str, str]:
    """Rozwiaz klucz OpenRouter ze WSPOLDZIELONYCH zrodel ekosystemu (llmwiki_pdf),
    bez kopiowania sekretu. Zwraca (klucz, zrodlo). Kolejnosc: API_openrouter.txt
    (czysty token), potem konwerter.env/mathpix.env (OPENROUTER_API_KEY, z DPAPI).
    Przeszukuje katalog roboczy oraz katalog pakietu (gdzie zwykle lezy _mathpix_env)."""
    roots = []
    for r in (root, Path(__file__).resolve().parents[1]):
        if r and r not in roots:
            roots.append(r)
    for r in roots:
        txt = r / "_mathpix_env" / "API_openrouter.txt"
        if txt.is_file():
            for line in txt.read_text(encoding="utf-8", errors="replace").splitlines():
                tok = line.strip()
                if tok.startswith("sk-or-"):
                    return tok, str(txt)
        for envname in ("_mathpix_env/konwerter.env", "konwerter.env", "_mathpix_env/mathpix.env", ".env"):
            ev = r / envname
            if ev.is_file():
                val = read_env_file(ev).get("OPENROUTER_API_KEY", "").strip()
                if val.startswith("sk-or-"):
                    return val, str(ev)
    return "", ""


@dataclass(slots=True)
class AppConfig:
    workspace_dir: Path
    env_file: Path
    values: dict[str, str] = field(default_factory=dict)

    @property
    def active_project(self) -> str:
        return projects.get_active(self.workspace_dir) or projects.DEFAULT_PROJECT

    @property
    def pdf_dir(self) -> Path:
        # PDF-y radaru = wspólne WEJŚCIE potoku llmwiki_in/<projekt> (konwerter czyta stąd).
        return projects.project_in_dir(self.workspace_dir, self.active_project)

    @property
    def reports_dir(self) -> Path:
        return (projects.project_out_dir(self.workspace_dir, self.active_project) / "reports").resolve()

    @property
    def converter_input_dir(self) -> Path | None:
        """Katalog _mathpix_in konwertera (most do modułu 2). Pusty = brak mostu."""
        raw = (self.values.get("CONVERTER_INPUT_DIR") or "").strip()
        return Path(raw).expanduser().resolve() if raw else None

    @property
    def tier(self) -> str:
        tier = (self.values.get("DEFAULT_TIER") or "student").strip().lower()
        return tier if tier in {"student", "hybrid", "deep"} else "student"

    @property
    def allow_preprint(self) -> bool:
        return str(self.values.get("PREPRINT_FALLBACK", "false")).strip().lower() == "true"

    @property
    def preprint_quantile(self) -> float:
        try:
            return float(self.values.get("PREPRINT_TOP_QUANTILE", "0.2"))
        except ValueError:
            return 0.2

    @property
    def openrouter_key(self) -> str:
        """Efektywny klucz: najpierw radar.env, potem wspoldzielone zrodla (konwerter)."""
        own = (self.values.get("OPENROUTER_API_KEY") or "").strip()
        if own:
            return own
        key, _src = shared_openrouter_key(self.workspace_dir)
        return key

    @property
    def openrouter_key_source(self) -> str:
        if (self.values.get("OPENROUTER_API_KEY") or "").strip():
            return self.env_file.name
        _key, src = shared_openrouter_key(self.workspace_dir)
        return src

    @property
    def verify_llm(self) -> bool:
        return str(self.values.get("VERIFY_LLM", "false")).strip().lower() == "true"

    @property
    def oversample_factor(self) -> float:
        try:
            return max(1.0, float(self.values.get("OVERSAMPLE_FACTOR", "1.5")))
        except ValueError:
            return 1.5

    @property
    def http_min_interval_seconds(self) -> float:
        """Bezpiecznik 1 (governor): min-odstęp HTTP/host. Fallback → constants."""
        try:
            return max(0.0, float(self.values.get("HTTP_MIN_INTERVAL_SECONDS", str(constants.HTTP_MIN_INTERVAL_SECONDS))))
        except (TypeError, ValueError):
            return constants.HTTP_MIN_INTERVAL_SECONDS

    @property
    def http_max_calls_per_run(self) -> int:
        """Bezpiecznik 2 (anty-pętla): twardy limit zapytań/przebieg. 0 = bez limitu."""
        try:
            return max(0, int(self.values.get("HTTP_MAX_CALLS_PER_RUN", str(constants.HTTP_MAX_CALLS_PER_RUN))))
        except (TypeError, ValueError):
            return constants.HTTP_MAX_CALLS_PER_RUN

    @property
    def rank_weights(self) -> dict:
        def f(k, d):
            try:
                return float(self.values.get(k, d))
            except ValueError:
                return float(d)
        return {"rel": f("RANK_W_REL", "0.4"), "impact": f("RANK_W_IMPACT", "0.3"),
                "recency": f("RANK_W_RECENCY", "0.12"), "type": f("RANK_W_TYPE", "0.05"),
                "prestige": f("RANK_W_PRESTIGE", "0.13")}

    @property
    def model_price_usd_per_m(self) -> float:
        try:
            return float(self.values.get("LLM_MODEL_PRICE_USD_PER_M", "0.075"))
        except ValueError:
            return 0.075

    @property
    def max_cost_usd(self) -> float:
        try:
            return float(self.values.get("LLM_MAX_COST_PER_RUN_USD", "1.00"))
        except ValueError:
            return 1.0

    @property
    def summary_words(self) -> int:
        try:
            return max(20, min(100, int(self.values.get("SUMMARY_WORDS", "50"))))
        except ValueError:
            return 50

    @property
    def dedup_cross_run(self) -> bool:
        return str(self.values.get("DEDUP_CROSS_RUN", "true")).strip().lower() == "true"

    @property
    def sources(self) -> set[str]:
        """Dodatkowe zrodla (poza OpenAlex+S2) wlaczone przez uzytkownika."""
        raw = (self.values.get("SOURCES") or "")
        return {s.strip().lower() for s in raw.replace(";", ",").split(",") if s.strip()}

    @property
    def core_api_key(self) -> str:
        return (self.values.get("CORE_API_KEY") or "").strip()

    @property
    def openalex_api_key(self) -> str:
        return (self.values.get("OPENALEX_API_KEY") or "").strip()

    @property
    def s2_api_key(self) -> str:
        return (self.values.get("S2_API_KEY") or "").strip()

    @property
    def consensus_api_key(self) -> str:
        return (self.values.get("CONSENSUS_API_KEY") or "").strip()

    @property
    def perplexity_model(self) -> str:
        """Model Perplexity Sonar (przez OpenRouter) dla źródła 'perplexity'."""
        return (self.values.get("PERPLEXITY_MODEL") or "perplexity/sonar").strip()

    @property
    def polite_sleep(self) -> float:
        try:
            return max(0.0, float(self.values.get("POLITE_SLEEP_SECONDS", "1.0")))
        except ValueError:
            return 1.0

    @property
    def oa_only(self) -> bool:
        return str(self.values.get("OA_ONLY", "true")).strip().lower() == "true"

    @property
    def search_lang(self) -> str:
        """Język(i) odpytania: pl | en | both (domyślnie both)."""
        v = (self.values.get("SEARCH_LANG") or "both").strip().lower()
        return v if v in {"pl", "en", "both"} else "both"

    @property
    def search_lang_split_pl(self) -> float:
        """Udział puli PL w trybie 'both' (0..1; reszta = ENG)."""
        try:
            return min(1.0, max(0.0, float(self.values.get("SEARCH_LANG_SPLIT_PL", "0.25"))))
        except (TypeError, ValueError):
            return 0.25

    @property
    def query_expansion(self) -> bool:
        """Ekspansja zapytania LLM (recall): słowa kluczowe + curated query."""
        return str(self.values.get("QUERY_EXPANSION", "true")).strip().lower() == "true"

    @property
    def min_intent_match(self) -> float:
        """Próg trafności przed pobraniem (0..1; 0 = bramka wyłączona)."""
        try:
            return min(1.0, max(0.0, float(self.values.get("MIN_INTENT_MATCH", "0.1"))))
        except (TypeError, ValueError):
            return 0.1

    def masked_values(self) -> dict[str, str]:
        masked = dict(self.values)
        for key in SECRET_KEYS:
            if masked.get(key):
                masked[key] = "********"
        return masked


def _prefer_existing(root: Path, new_name: str, legacy_name: str) -> Path:
    """Preferuj nową (radar) ścieżkę; gdy nie istnieje, a starsza (scout) istnieje —
    użyj starszej. Pozwala czytać workspace sprzed rebrandingu bez utraty danych."""
    new_p = root / new_name
    if not new_p.exists() and (root / legacy_name).exists():
        return root / legacy_name
    return new_p


class AppConfigStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or default_runtime_root()).resolve()

    @property
    def state_dir(self) -> Path:
        return self.root / APP_STATE_DIR

    @property
    def state_file(self) -> Path:
        return self.state_dir / APP_STATE_FILE

    @property
    def env_dir(self) -> Path:
        return self.root / ENV_DIR

    @property
    def default_env_file(self) -> Path:
        d = self.env_dir
        new_f = d / DEFAULT_ENV_FILE
        if not new_f.is_file() and (d / LEGACY_ENV_FILE).is_file():
            return d / LEGACY_ENV_FILE
        return new_f

    def is_configured(self) -> bool:
        return self.state_file.is_file() and self.env_file().is_file()

    def env_file(self) -> Path:
        state = self.read_state()
        configured = state.get("env_file")
        if configured:
            candidate = Path(str(configured)).expanduser()
            if candidate.is_file() or candidate.parent.exists():
                return candidate.resolve()
        return self.default_env_file.resolve()

    def read_state(self) -> dict[str, Any]:
        if not self.state_file.is_file():
            return {}
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def write_state(self, values: dict[str, Any]) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        state = self.read_state()
        state.update(values)
        for secret in SECRET_KEYS:
            state.pop(secret, None)  # sekrety nigdy nie trafiają do app_state.json
        self.state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def load(self) -> AppConfig:
        env_file = self.env_file()
        values = default_values_for(self.root)
        values.update(read_env_file(env_file))
        return AppConfig(workspace_dir=self.root, env_file=env_file, values=values)

    def setup(self, payload: dict[str, Any]) -> AppConfig:
        workspace = Path(str(payload.get("workspace_dir") or self.root)).expanduser().resolve()
        store = AppConfigStore(workspace)
        create_workspace_dirs(workspace)
        env_file = Path(str(payload.get("env_file") or store.default_env_file)).expanduser().resolve()
        values = default_values_for(workspace)
        values.update(read_env_file(env_file))
        values.update(env_values_from_payload(payload, keep_masked=False))
        write_env_file(env_file, values)
        store.write_state(
            {
                "workspace_dir": str(workspace),
                "env_file": str(env_file),
                "configured": True,
            }
        )
        return store.load()

    def save_config(self, payload: dict[str, Any]) -> AppConfig:
        config = self.load()
        values = dict(config.values)
        values.update(env_values_from_payload(payload, keep_masked=True, existing=values))
        env_file = Path(str(payload.get("env_file") or config.env_file)).expanduser().resolve()
        write_env_file(env_file, values)
        self.write_state({"workspace_dir": str(config.workspace_dir), "env_file": str(env_file)})
        return AppConfig(workspace_dir=config.workspace_dir, env_file=env_file, values=values)


def aihub_root() -> Path:
    """Stały, ogólnomaszynowy DOM LLM-Wiki — WSPÓLNY z konwerterem, niezależny od miejsca
    instalacji EXE. env ``LLMWIKI_AIHUB`` → ``<SystemDrive>\\llmwiki_AIHUB`` (zwykle C:).
    Identyczna logika jak ``llmwiki_converter/projects.aihub_root`` — skonsoliduje się, gdy
    radar dostanie kopię ``projects.py``. Gdy C:\\ zablokowany: ``LLMWIKI_AIHUB`` lub kreator."""
    override = os.environ.get("LLMWIKI_AIHUB")
    if override:
        return Path(override).expanduser().resolve()
    return Path(os.environ.get("SystemDrive", "C:") + os.sep) / "llmwiki_AIHUB"


def default_runtime_root() -> Path:
    # Kolejność: LLMWIKI_AIHUB (wspólny override) > LLMWIKI_RADAR_WORKSPACE/SCOUT (per-moduł,
    # zgodność wsteczna) > stały dom C:\llmwiki_AIHUB (zbieżny z konwerterem, niezależny od EXE).
    if not os.environ.get("LLMWIKI_AIHUB"):
        env_root = os.environ.get("LLMWIKI_RADAR_WORKSPACE") or os.environ.get("LLMWIKI_SCOUT_WORKSPACE")
        if env_root:
            return Path(env_root).expanduser().resolve()
    return aihub_root()


def default_values_for(root: Path) -> dict[str, str]:
    # PDF-y/raporty są PROJECT-SCOPED (liczone z aktywnego projektu) — bez stałych DEFAULT_*_DIR.
    return dict(DEFAULT_ENV_VALUES)


def create_workspace_dirs(root: Path) -> None:
    # Wspólny env + stan + roota potoku (llmwiki_in/out). Per-projekt podkatalogi przez projects.
    for name in (ENV_DIR, APP_STATE_DIR, projects.SHARED_INPUT_DIR, projects.SHARED_OUTPUT_DIR):
        (root / name).mkdir(parents=True, exist_ok=True)
    (root / APP_STATE_DIR / "runs").mkdir(parents=True, exist_ok=True)
    if not projects.get_active(root):
        projects.create_project(root, projects.DEFAULT_PROJECT)


def env_values_from_payload(
    payload: dict[str, Any],
    *,
    keep_masked: bool,
    existing: dict[str, str] | None = None,
) -> dict[str, str]:
    mapping = {
        "openrouter_api_key": "OPENROUTER_API_KEY",
        "polite_pool_email": "POLITE_POOL_EMAIL",
        "default_tier": "DEFAULT_TIER",
        "default_target_n": "DEFAULT_TARGET_N",
        "oa_only": "OA_ONLY",
        "preprint_fallback": "PREPRINT_FALLBACK",
        "preprint_top_quantile": "PREPRINT_TOP_QUANTILE",
        "verify_llm": "VERIFY_LLM",
        "oversample_factor": "OVERSAMPLE_FACTOR",
        "rank_w_rel": "RANK_W_REL",
        "rank_w_impact": "RANK_W_IMPACT",
        "rank_w_recency": "RANK_W_RECENCY",
        "rank_w_type": "RANK_W_TYPE",
        "rank_w_prestige": "RANK_W_PRESTIGE",
        "llm_model_price_usd_per_m": "LLM_MODEL_PRICE_USD_PER_M",
        "polite_sleep_seconds": "POLITE_SLEEP_SECONDS",
        "summary_words": "SUMMARY_WORDS",
        "dedup_cross_run": "DEDUP_CROSS_RUN",
        "sources": "SOURCES",
        "search_lang": "SEARCH_LANG",
        "search_lang_split_pl": "SEARCH_LANG_SPLIT_PL",
        "query_expansion": "QUERY_EXPANSION",
        "min_intent_match": "MIN_INTENT_MATCH",
        "core_api_key": "CORE_API_KEY",
        "openalex_api_key": "OPENALEX_API_KEY",
        "s2_api_key": "S2_API_KEY",
        "consensus_api_key": "CONSENSUS_API_KEY",
        "perplexity_model": "PERPLEXITY_MODEL",
        "default_pdf_dir": "DEFAULT_PDF_DIR",
        "default_reports_dir": "DEFAULT_REPORTS_DIR",
        "converter_input_dir": "CONVERTER_INPUT_DIR",
        "openrouter_model_hybrid": "OPENROUTER_MODEL_HYBRID",
        "openrouter_model_deep": "OPENROUTER_MODEL_DEEP",
        "llm_max_cost_per_run_usd": "LLM_MAX_COST_PER_RUN_USD",
        "llm_max_input_tokens_per_paper": "LLM_MAX_INPUT_TOKENS_PER_PAPER",
        "encrypt_secrets": "ENCRYPT_SECRETS",
    }
    out: dict[str, str] = {}
    for payload_key, env_key in mapping.items():
        if payload_key not in payload:
            continue
        raw = payload.get(payload_key)
        value = "" if raw is None else str(raw).strip()
        if keep_masked and env_key in SECRET_KEYS and value in {"", "********"}:
            if existing and env_key in existing:
                out[env_key] = existing[env_key]
            continue
        out[env_key] = value
    return out


def write_env_file(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered_keys = [
        "OPENROUTER_API_KEY",
        "POLITE_POOL_EMAIL",
        "DEFAULT_TIER",
        "DEFAULT_TARGET_N",
        "OA_ONLY",
        "PREPRINT_FALLBACK",
        "PREPRINT_TOP_QUANTILE",
        "VERIFY_LLM",
        "OVERSAMPLE_FACTOR",
        "RANK_W_REL", "RANK_W_IMPACT", "RANK_W_RECENCY", "RANK_W_TYPE", "RANK_W_PRESTIGE",
        "LLM_MODEL_PRICE_USD_PER_M",
        "POLITE_SLEEP_SECONDS",
        "SUMMARY_WORDS",
        "DEDUP_CROSS_RUN",
        "SOURCES",
        "SEARCH_LANG",
        "SEARCH_LANG_SPLIT_PL",
        "QUERY_EXPANSION",
        "MIN_INTENT_MATCH",
        "CORE_API_KEY",
        "OPENALEX_API_KEY",
        "S2_API_KEY",
        "CONSENSUS_API_KEY",
        "PERPLEXITY_MODEL",
        "DEFAULT_PDF_DIR",
        "DEFAULT_REPORTS_DIR",
        "CONVERTER_INPUT_DIR",
        "OPENROUTER_MODEL_HYBRID",
        "OPENROUTER_MODEL_DEEP",
        "LLM_MAX_COST_PER_RUN_USD",
        "LLM_MAX_INPUT_TOKENS_PER_PAPER",
        "ENCRYPT_SECRETS",
    ]
    encrypt = str(values.get("ENCRYPT_SECRETS", "")).strip().lower() == "true"

    def encode(key: str, value: str) -> str:
        if encrypt and key in SECRET_KEYS and value:
            from .secret_store import dpapi_available, protect

            if dpapi_available():
                value = protect(value)
        return f"{key}={quote_env_value(value)}"

    lines = [
        "# Radar PDF configuration",
        "# Sekrety zostaja lokalnie w tym pliku i nie sa pakowane do ZIP.",
    ]
    for key in ordered_keys:
        if key in values:
            lines.append(encode(key, values[key]))
    for key in sorted(set(values) - set(ordered_keys)):
        lines.append(encode(key, values[key]))
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def quote_env_value(value: str) -> str:
    if value == "":
        return ""
    if any(char.isspace() for char in value) or "#" in value:
        return json.dumps(value, ensure_ascii=False)
    return value
