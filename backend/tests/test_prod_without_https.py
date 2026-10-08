"""Audyt SEC-003 / N-03: instancja po HTTP, więc dziś musi mieć ENVIRONMENT≠production — a to
wyłącza fail-fast sekretów i odsłania /docs. ALLOW_INSECURE_HTTP zwalnia wyłącznie wymóg
SECURE_COOKIES; domyślne sekrety dalej blokują start produkcji."""
import pytest

from app import main
from app.config import settings

STRONG = "x" * 40


@pytest.fixture()
def prod(monkeypatch):
    for name, value in (("environment", "production"), ("secure_cookies", False),
                        ("secret_key", STRONG), ("admin_password", "Silne-Haslo-2026!"),
                        ("public_base_url", "http://192.0.2.10:81"), ("automation_api_token", ""),
                        ("bcrypt_rounds", 12)):
        monkeypatch.setattr(settings, name, value)
    return monkeypatch


def test_production_over_http_starts_with_explicit_flag(prod):
    prod.setattr(settings, "allow_insecure_http", True)
    main.validate_settings()   # bez wyjątku


def test_production_over_http_without_flag_still_blocked(prod):
    prod.setattr(settings, "allow_insecure_http", False)
    with pytest.raises(RuntimeError, match="SECURE_COOKIES"):
        main.validate_settings()


def test_flag_does_not_excuse_default_secrets(prod):
    prod.setattr(settings, "allow_insecure_http", True)
    prod.setattr(settings, "secret_key", "change-me-in-production")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        main.validate_settings()


def test_production_refuses_cheap_bcrypt(prod):
    """Testy jadą na koszcie 4 (szybkie CI); produkcja z kosztem < 12 nie wystartuje."""
    prod.setattr(settings, "allow_insecure_http", True)
    prod.setattr(settings, "bcrypt_rounds", 4)
    with pytest.raises(RuntimeError, match="BCRYPT_ROUNDS"):
        main.validate_settings()


def test_hash_uses_configured_rounds(monkeypatch):
    from app.security import hash_password, verify_password
    monkeypatch.setattr(settings, "bcrypt_rounds", 5)
    hashed = hash_password("Haslo-123!")
    assert hashed.startswith("$2b$05$") and verify_password("Haslo-123!", hashed)
