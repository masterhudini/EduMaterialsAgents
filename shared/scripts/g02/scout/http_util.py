"""Odporny na throttling klient HTTP (stdlib only).

Jeden helper dla wszystkich zapytań JSON/XML Scouta: ponawia 429 i 5xx oraz
bledy sieci z exponential backoff + jitter, honoruje naglowek Retry-After,
ma cap prob. Wzorzec przeniesiony z modulu 2 (mathpix_client._request_with_retry).
Wywolujacy decyduje, czy terminalny blad ma sie propagowac (rdzen: OpenAlex)
czy degradowac do pustego (best-effort: providery)."""

from __future__ import annotations

import random
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable

# Status, ktore PONAWIAMY (przejsciowe). 404 i 4xx (poza 429) NIE ponawiamy.
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})

# Pacing per-host (P4): rozsuwa zapytania do tego samego hosta, by NIE wpasc w 429
# (zwlaszcza na wspoldzielonym IP uczelni). ~3 zapytania/s/host. Reaktywny retry
# zostaje jako siatka bezpieczenstwa; pacing zmniejsza liczbe trafien w limit.
DEFAULT_MIN_INTERVAL = 0.34
# Safety cap for server Retry-After. Some APIs return multi-hour values; a desktop
# job should retry shortly instead of appearing frozen for half a day.
DEFAULT_MAX_RETRY_AFTER = 60.0
_pace_lock = threading.Lock()
_last_call: dict[str, float] = {}

# Bezpiecznik 1 — GOVERNOR prędkości: globalny (konfigurowalny) min-odstęp per host.
# Domyślnie DEFAULT_MIN_INTERVAL; run_student nadpisuje z konfiguracji
# (HTTP_MIN_INTERVAL_SECONDS). Pojedyncza liczba — proste, jawne, wersjonowane.
_min_interval = DEFAULT_MIN_INTERVAL


def set_min_interval(seconds: float) -> None:
    """Ustaw globalny min-odstęp pacingu (per host). 0 = bez pacingu."""
    global _min_interval
    try:
        _min_interval = max(0.0, float(seconds))
    except (TypeError, ValueError):
        pass


def pace(url: str, min_interval: float = DEFAULT_MIN_INTERVAL) -> None:
    """Odczekaj, by od ostatniego zapytania do TEGO hosta minelo >= min_interval.
    Rezerwuje slot pod lockiem, spi poza lockiem (rozne hosty sie nie blokuja)."""
    if min_interval <= 0:
        return
    try:
        host = urllib.parse.urlsplit(url).netloc or url
    except Exception:  # noqa: BLE001
        return
    with _pace_lock:
        now = time.monotonic()
        target = max(now, _last_call.get(host, 0.0) + min_interval)
        _last_call[host] = target
        wait = target - now
    if wait > 0:
        time.sleep(wait)

# Hook (per-watek) wolany przy KAZDYM ponowieniu - pozwala pokazac je w logu
# Przebiegu, bez przeplatania `progress` przez caly stos wywolan HTTP.
_local = threading.local()


class HttpBudgetExceeded(RuntimeError):
    """Przebieg przekroczył twardy limit zapytań HTTP (HTTP_MAX_CALLS_PER_RUN).
    Podnoszony, by ZATRZYMAĆ runaway (nieskończona ekspansja/retry), nie zawiesić apki."""


def reset_run_budget(max_calls: int | None) -> None:
    """Bezpiecznik 2 — wyzeruj licznik zapytań dla BIEŻĄCEGO przebiegu (wątku) i ustaw
    twardy limit. ``max_calls`` ≤ 0 / None = bez limitu (licznik tylko zlicza). Woła
    run_student na starcie; licznik jest THREAD-LOCAL, więc przebiegi się nie mieszają."""
    _local.http_calls = 0
    _local.http_max = int(max_calls) if max_calls and int(max_calls) > 0 else 0


def http_calls_made() -> int:
    """Ile realnych zapytań HTTP wykonano w bieżącym przebiegu (wątku)."""
    return int(getattr(_local, "http_calls", 0))


def _tick() -> None:
    """Zlicz jedno realne zapytanie; przekroczenie limitu → HttpBudgetExceeded."""
    count = int(getattr(_local, "http_calls", 0)) + 1
    _local.http_calls = count
    cap = int(getattr(_local, "http_max", 0))
    if cap and count > cap:
        raise HttpBudgetExceeded(
            f"Przekroczono budżet HTTP przebiegu ({cap} zapytań) — przerwano, by nie zapętlić."
        )


def set_retry_hook(fn: "Callable[[int, Exception, float], None] | None") -> None:
    """Zainstaluj (dla biezacego watku) callback ponowien: fn(attempt, exc, delay).
    None = wylacz. Job ustawia go u siebie, zeby emitowac zdarzenie `retry`."""
    _local.hook = fn


def _emit_retry(attempt: int, exc: Exception, delay: float) -> None:
    fn = getattr(_local, "hook", None)
    if fn is not None:
        try:
            fn(attempt, exc, delay)
        except Exception:  # noqa: BLE001 - log nie moze wywrocic pobierania
            pass


def parse_retry_after(value: str | None) -> float | None:
    """Naglowek Retry-After: liczba sekund albo data HTTP. Zwraca sekundy (>=0)
    albo None, gdy brak/niepoprawny."""
    if not value:
        return None
    raw = str(value).strip()
    if raw.isdigit():
        return float(raw)
    try:
        when = parsedate_to_datetime(raw)
        if when is None:
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return max(0.0, (when - datetime.now(when.tzinfo)).total_seconds())
    except (TypeError, ValueError):
        return None


def _backoff(attempt: int, base_delay: float, max_delay: float) -> float:
    """Exponential backoff + pelny jitter (random w [0, base]) - rozprasza ponowienia."""
    return min(max_delay, base_delay * (2 ** attempt)) + random.uniform(0.0, base_delay)


def request_with_retry(
    url: str,
    *,
    headers: dict | None = None,
    data: bytes | None = None,
    method: str = "GET",
    timeout: float = 15.0,
    max_attempts: int = 4,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    max_retry_after: float | None = DEFAULT_MAX_RETRY_AFTER,
    opener: Callable | None = None,
    sleep: Callable[[float], None] | None = None,
) -> bytes:
    """Pobierz URL z odpornoscia na throttling. Ponawia 429/5xx (honorujac
    Retry-After) i bledy sieci, z backoff+jitter, do `max_attempts` prob. 404 i
    inne 4xx -> natychmiastowy raise (bez ponawiania). `max_retry_after`
    ogranicza absurdalnie dlugie Retry-After, zeby UI nie zamarzal na godziny.
    Po wyczerpaniu prob podnosi ostatni wyjatek. opener/sleep wstrzykiwalne
    (testy)."""
    opener_is_default = opener is None
    opener = opener or urllib.request.urlopen
    sleep = sleep or time.sleep
    if opener_is_default:  # realny ruch (nie test z wstrzyknietym openerem) -> pacing per-host
        pace(url, _min_interval)
    attempts = max(1, int(max_attempts))
    last_exc: Exception | None = None
    for attempt in range(attempts):
        _tick()  # bezpiecznik 2: licz KAŻDĄ próbę (retry też) → przekroczenie zatrzymuje przebieg
        try:
            req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
            with opener(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code in RETRY_STATUS and attempt < attempts - 1:
                ra = parse_retry_after(exc.headers.get("Retry-After") if exc.headers else None)
                if ra is not None:
                    delay = min(ra, max_retry_after) if max_retry_after is not None else ra
                else:
                    delay = _backoff(attempt, base_delay, max_delay)
                _emit_retry(attempt, exc, delay)
                sleep(delay)
                continue
            raise  # 404/4xx albo wyczerpane proby
        except Exception as exc:  # noqa: BLE001 - sieć/timeout/itp.
            last_exc = exc
            if attempt < attempts - 1:
                delay = _backoff(attempt, base_delay, max_delay)
                _emit_retry(attempt, exc, delay)
                sleep(delay)
                continue
            raise
    if last_exc:
        raise last_exc
    raise RuntimeError("request_with_retry: brak proby")
