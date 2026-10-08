"""Audyt SEC-017: klucz szyfrowania danych w bazie oddzielony od SECRET_KEY (JWT).
DATA_ENCRYPTION_KEY szyfruje nowe wartości; stare (z klucza SECRET_KEY) dalej się czytają."""
import pytest
from cryptography.fernet import InvalidToken

from app import crypto
from app.config import settings

SECRET = '{"refresh":"abc123"}'


def test_rotating_secret_key_keeps_data_readable(monkeypatch):
    monkeypatch.setattr(settings, "data_encryption_key", "osobny-klucz-danych-0123456789abcdef")  # gitleaks:allow
    enc = crypto.encrypt(SECRET)
    monkeypatch.setattr(settings, "secret_key", "nowy-sekret-jwt-po-rotacji-0123456789")  # gitleaks:allow
    assert crypto.decrypt(enc) == SECRET


def test_legacy_values_readable_after_setting_data_key(monkeypatch):
    monkeypatch.setattr(settings, "data_encryption_key", "")
    legacy = crypto.encrypt(SECRET)                  # zapisane kluczem z SECRET_KEY
    monkeypatch.setattr(settings, "data_encryption_key", "osobny-klucz-danych-0123456789abcdef")  # gitleaks:allow
    assert crypto.decrypt(legacy) == SECRET


def test_data_key_value_not_readable_with_secret_key_alone(monkeypatch):
    monkeypatch.setattr(settings, "data_encryption_key", "osobny-klucz-danych-0123456789abcdef")  # gitleaks:allow
    enc = crypto.encrypt(SECRET)
    monkeypatch.setattr(settings, "data_encryption_key", "")
    with pytest.raises(InvalidToken):
        crypto.decrypt(enc)


def test_without_data_key_behaviour_unchanged(monkeypatch):
    monkeypatch.setattr(settings, "data_encryption_key", "")
    enc = crypto.encrypt(SECRET)
    assert enc.startswith("enc:") and crypto.decrypt(enc) == SECRET
