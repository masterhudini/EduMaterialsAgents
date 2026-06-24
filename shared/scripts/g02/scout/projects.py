from __future__ import annotations

"""Zarządzanie PROJEKTAMI (tematami) we współdzielonym workspace LLM-Wiki.

Projekt = nazwany podkatalog współdzielony przez radar i konwerter:

    <root>/llmwiki_in/<slug>/      ← PDF-y (radar PISZE, konwerter CZYTA) + projekt.json
    <root>/llmwiki_out/<slug>/     ← deliverable MD + digesty (konwerter PISZE)
    <root>/llmwiki_projects.json   ← rejestr {active, projects[]} czytany przez OBA moduły

Moduł jest CELOWO bez zależności (tylko stdlib) i nie importuje app_config — dzięki
temu radar może wziąć identyczną kopię, a testy są trywialne. Integrację z LLM
(propozycja nazwy z zapytania) wstrzykuje się jako `llm_fn`, więc tu nie ma `requests`.

Zasada (jak w całym projekcie): reguły OGÓLNE, nie szyte pod konkretny temat —
`slugify` działa dla dowolnego napisu (PL/EN), nie dla wybranych słów.
"""

import json
import os
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

# Nazwy współdzielone — EKOSYSTEMOWE (bo używają ich OBA moduły), stąd prefiks
# llmwiki_, nie _radar_/_converter_. Sekrety/raporty/stan zostają per-moduł.
SHARED_INPUT_DIR = "llmwiki_in"
SHARED_OUTPUT_DIR = "llmwiki_out"
REGISTRY_FILE = "llmwiki_projects.json"
DEFAULT_PROJECT = "default"
SIDECAR_FILE = "projekt.json"
AIHUB_DIRNAME = "llmwiki_AIHUB"


def aihub_root() -> Path:
    """Stały, ogólnomaszynowy DOM LLM-Wiki — wspólny dla radaru i konwertera, NIEZALEŻNY
    od miejsca instalacji EXE. Dzięki temu oba moduły zbiegają się w jednym workspace
    (współdzielone llmwiki_in/out + llmwiki_projects.json) bez konfiguracji.

    Kolejność: env ``LLMWIKI_AIHUB`` → ``<SystemDrive>\\llmwiki_AIHUB`` (zwykle C:).
    Tylko ZWRACA ścieżkę — katalog tworzy ``create_workspace_dirs``/setup („utwórz-lub-znajdź").
    Gdy C:\\ jest zablokowany (lockdown korpo): wskaż inny przez ``LLMWIKI_AIHUB`` albo
    wybierz folder w kreatorze first-run."""
    override = os.environ.get("LLMWIKI_AIHUB")
    if override:
        return Path(override).expanduser().resolve()
    drive = os.environ.get("SystemDrive", "C:")
    return Path(drive + os.sep) / AIHUB_DIRNAME

_SLUG_MAXLEN = 48
# ascii-fold dla znaków, których NFKD nie rozkłada (ł, đ, ø); ó/ą/ę itd. rozłoży NFKD.
_FOLD = {"ł": "l", "Ł": "L", "đ": "d", "Đ": "D", "ø": "o", "Ø": "O"}


@dataclass(slots=True)
class Project:
    slug: str
    title: str = ""
    created: str = ""


# --------------------------------------------------------------------------
# Slug
# --------------------------------------------------------------------------

def slugify(name: str, *, maxlen: int = _SLUG_MAXLEN) -> str:
    """Filesystem-safe kebab-slug. ascii-fold (ł→l, ó→o), lower, [a-z0-9-], scal myślniki.

    Pusty/sam-symbole → ``DEFAULT_PROJECT`` (nigdy nie zwraca pustego stringa)."""
    text = "".join(_FOLD.get(ch, ch) for ch in (name or ""))
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    text = re.sub(r"-{2,}", "-", text)
    text = text[:maxlen].strip("-")
    return text or DEFAULT_PROJECT


def unique_slug(root: Path, base: str) -> str:
    """``base`` jeśli wolny; inaczej ``base-2``, ``base-3``… (sprawdza rejestr ORAZ dysk)."""
    base = slugify(base)
    taken = {p.slug for p in list_projects(root)}
    taken |= {p.name for p in _scan_dir(root / SHARED_INPUT_DIR)}
    taken |= {p.name for p in _scan_dir(root / SHARED_OUTPUT_DIR)}
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


def _scan_dir(path: Path) -> list[Path]:
    if not path.is_dir():
        return []
    return [p for p in path.iterdir() if p.is_dir()]


# --------------------------------------------------------------------------
# Rejestr (llmwiki_projects.json w roocie — wspólny dla obu modułów)
# --------------------------------------------------------------------------

def registry_path(root: Path) -> Path:
    return root / REGISTRY_FILE


def load_registry(root: Path) -> dict:
    path = registry_path(root)
    if not path.is_file():
        return {"active": "", "projects": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"active": "", "projects": []}
    if not isinstance(data, dict):
        return {"active": "", "projects": []}
    data.setdefault("active", "")
    data.setdefault("projects", [])
    return data


def save_registry(root: Path, data: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    registry_path(root).write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def list_projects(root: Path) -> list[Project]:
    out: list[Project] = []
    for item in load_registry(root).get("projects", []):
        if isinstance(item, dict) and item.get("slug"):
            out.append(Project(slug=item["slug"], title=item.get("title", ""), created=item.get("created", "")))
    return out


def get_active(root: Path) -> str:
    """Slug aktywnego projektu lub '' gdy brak. (Caller decyduje o DEFAULT_PROJECT.)"""
    return load_registry(root).get("active", "") or ""


def set_active(root: Path, slug: str) -> None:
    data = load_registry(root)
    slugs = {p["slug"] for p in data["projects"] if isinstance(p, dict)}
    if slug not in slugs:
        data["projects"].append(asdict(Project(slug=slug, title=slug, created=date.today().isoformat())))
    data["active"] = slug
    save_registry(root, data)


# --------------------------------------------------------------------------
# Ścieżki projektu
# --------------------------------------------------------------------------

def project_in_dir(root: Path, slug: str) -> Path:
    return (root / SHARED_INPUT_DIR / slug).resolve()


def project_out_dir(root: Path, slug: str) -> Path:
    return (root / SHARED_OUTPUT_DIR / slug).resolve()


def ensure_project_dirs(root: Path, slug: str) -> tuple[Path, Path]:
    in_dir, out_dir = project_in_dir(root, slug), project_out_dir(root, slug)
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    return in_dir, out_dir


# --------------------------------------------------------------------------
# Tworzenie / nazwa
# --------------------------------------------------------------------------

def create_project(
    root: Path,
    title: str = "",
    *,
    slug: str | None = None,
    created: str | None = None,
    activate: bool = True,
) -> Project:
    """Tworzy projekt: unikalny slug → katalogi in/out → wpis w rejestrze → sidecar.

    ``slug`` można wymusić; inaczej liczony z ``title``. ``created`` domyślnie dzisiaj
    (parametr dla determinizmu testów)."""
    base = slug if slug else (title or DEFAULT_PROJECT)
    final_slug = unique_slug(root, base)
    created = created or date.today().isoformat()
    proj = Project(slug=final_slug, title=(title or final_slug), created=created)

    ensure_project_dirs(root, final_slug)
    data = load_registry(root)
    data["projects"].append(asdict(proj))
    if activate or not data.get("active"):
        data["active"] = final_slug
    save_registry(root, data)
    write_sidecar(root, proj)
    return proj


def derive_project_name(hypothesis: str = "", query: str = "", *, llm_fn=None, max_words: int = 6) -> str:
    """Tytuł projektu (HUMAN, nie slug). Priorytet: hipoteza → LLM(query) → słowa z query.

    Zwraca '' gdy nic nie ma (caller użyje DEFAULT_PROJECT). ``llm_fn`` to wstrzyknięta
    funkcja ``str->str`` (np. wywołanie OpenRouter) — moduł sam NIE woła sieci."""
    hypothesis = (hypothesis or "").strip()
    if hypothesis:
        return hypothesis
    query = (query or "").strip()
    if not query:
        return ""
    if llm_fn is not None:
        try:
            proposed = (llm_fn(query) or "").strip()
            if proposed:
                return proposed
        except Exception:
            pass  # LLM best-effort — fallback poniżej
    return " ".join(query.split()[:max_words])


# --------------------------------------------------------------------------
# Sidecar (projekt.json w katalogu wejściowym — wędruje radar→konwerter)
# --------------------------------------------------------------------------

def write_sidecar(root: Path, proj: Project) -> Path:
    in_dir = project_in_dir(root, proj.slug)
    in_dir.mkdir(parents=True, exist_ok=True)
    path = in_dir / SIDECAR_FILE
    path.write_text(json.dumps(asdict(proj), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def read_sidecar(root: Path, slug: str) -> Project | None:
    path = project_in_dir(root, slug) / SIDECAR_FILE
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get("slug"):
        return None
    return Project(slug=data["slug"], title=data.get("title", ""), created=data.get("created", ""))
