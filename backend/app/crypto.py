"""Symetryczne szyfrowanie wrażliwych wartości w DB (cache MSAL z refresh tokenem).

Klucz: DATA_ENCRYPTION_KEY — osobny od SECRET_KEY, żeby rotacja klucza JWT nie psuła
danych i wyciek jednego sekretu nie kompromitował obu zastosowań (audyt SEC-017). Bez niego
(zgodność wstecz) klucz wyprowadzany z SECRET_KEY. Odczyt próbuje obu kluczy, więc wartości
zapisane przed ustawieniem DATA_ENCRYPTION_KEY dalej się odszyfrowują; nowy zapis idzie już
kluczem danych. Fernet = AES-128-CBC + HMAC. Format z prefiksem 'enc:' pozwala rozpoznać
i płynnie zmigrować istniejące wartości plaintext (odczyt bez prefiksu zwraca surowy tekst).
"""
from __future__ import annotations

import base64
import hashlib

from .config import settings

_PREFIX = "enc:"


def _key(secret: str) -> bytes:
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())


def _fernet():
    """MultiFernet: szyfruje pierwszym kluczem (danych, a bez niego z SECRET_KEY),
    odszyfrowuje dowolnym z listy."""
    from cryptography.fernet import Fernet, MultiFernet
    secrets = dict.fromkeys(s for s in (settings.data_encryption_key, settings.secret_key) if s)
    return MultiFernet([Fernet(_key(s)) for s in secrets])


def encrypt(text: str) -> str:
    if not text:
        return text
    token = _fernet().encrypt(text.encode()).decode()
    return _PREFIX + token


def decrypt(value: str) -> str:
    if not value or not value.startswith(_PREFIX):
        return value                      # zgodność wstecz z plaintext
    return _fernet().decrypt(value[len(_PREFIX):].encode()).decode()
