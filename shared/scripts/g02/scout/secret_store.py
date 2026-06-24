"""Szyfrowanie sekretów w spoczynku przez Windows DPAPI (CryptProtectData).

Zero zależności (ctypes → crypt32). Klucz szyfrujący jest powiązany z KONTEM
użytkownika Windows i NIGDZIE nie jest zapisywany — skopiowany plik/ZIP jest
bezużyteczny na innej maszynie/koncie. Wartości zaszyfrowane mają prefiks
``dpapi:`` + base64. Odczyt jest przezroczysty: wartości bez prefiksu = plaintext,
więc paczki z jawnymi kluczami (np. testowa) działają bez zmian.

Świadomie NIE jest to ochrona przed właścicielem na jego maszynie (DPAPI tego
nie zapewnia) — celem jest uniemożliwienie odczytania kluczy z skopiowanego
``konwerter.env``. Hasło aplikacji (przenośne szyfrowanie) to osobny, cięższy
wariant — tu wybrano DPAPI: zero hasła, zero zależności.
"""

from __future__ import annotations

import base64
import os

PREFIX = "dpapi:"


def dpapi_available() -> bool:
    """True tylko na Windows z dostępnym crypt32."""
    if os.name != "nt":
        return False
    try:
        import ctypes

        ctypes.WinDLL("crypt32")
        return True
    except Exception:
        return False


def is_protected(value: str) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)


def _dpapi(data: bytes, *, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    fn.restype = wintypes.BOOL
    fn.argtypes = [
        ctypes.POINTER(DATA_BLOB),
        wintypes.LPCWSTR,
        ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(DATA_BLOB),
    ]
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    blob_out = DATA_BLOB()
    if not fn(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
        raise OSError(ctypes.get_last_error(), "DPAPI operation failed")
    try:
        out_ptr = ctypes.cast(blob_out.pbData, ctypes.c_void_p)
        return ctypes.string_at(out_ptr, blob_out.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(blob_out.pbData, ctypes.c_void_p))


def protect(value: str) -> str:
    """Zaszyfruj string → ``dpapi:<base64>``. Pusty lub już zaszyfrowany — bez zmian."""
    if not value or is_protected(value):
        return value
    blob = _dpapi(value.encode("utf-8"), protect=True)
    return PREFIX + base64.b64encode(blob).decode("ascii")


def unprotect(value: str) -> str:
    """Odszyfruj ``dpapi:<base64>`` → plaintext. Wartość bez prefiksu zwracana bez
    zmian. Gdy odszyfrowanie zawiedzie (inna maszyna/konto, uszkodzone dane) —
    zwraca wartość wejściową (aplikacja zgłosi potem błąd autoryzacji, nie wysypie się)."""
    if not is_protected(value):
        return value
    try:
        blob = base64.b64decode(value[len(PREFIX):])
        return _dpapi(blob, protect=False).decode("utf-8")
    except Exception:
        return value


def decrypt_if_protected(value: str) -> str:
    return unprotect(value)
