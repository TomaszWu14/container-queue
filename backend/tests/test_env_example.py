"""Strażnik DOC-007: `.env.example` wymienia każde pole `Settings`, które ustawia operator.

Nowe pole w backend/app/config.py bez linii `NAZWA=` w .env.example = czerwony test. Pola
czysto wewnętrzne trafiają świadomie do INTERNAL (z powodem). Działa też w drugą stronę:
zmienna w szablonie, której nic nie czyta, to martwy wpis (np. usunięty SYNC_API_TOKEN)."""
import re
from pathlib import Path

from app.config import Settings

ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"

# pola Settings, których operator NIE ustawia — każde z powodem
INTERNAL = {
    "app_version": "SHA commita wstrzykiwany w obrazie (build arg SOURCE_COMMIT)",
    "build_time": "data builda wstrzykiwana w obrazie",
    "ml_train_in_background": "False tylko w testach (trening synchroniczny)",
}
# zmienne w szablonie spoza Settings — czytane przez compose albo skrypty
NON_SETTINGS = {
    "POSTGRES_PASSWORD": "docker-compose*.yml składa z niego DATABASE_URL",
    "BACKUP_KEEP": "backend/scripts/backup.sh",
}
# pola z sekretem: w szablonie wolno tylko pustą wartość albo jawną atrapę
SECRET_RE = re.compile(r"(PASSWORD|SECRET|TOKEN|API_KEY|SECRET_KEY|DSN)$")
PLACEHOLDERS = {"", "change-me-in-production", "admin123", "zmien-mnie"}


def _entries() -> dict[str, str]:
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^([A-Z][A-Z0-9_]*)=(.*)$", line)   # zakomentowane warianty pomijamy
        if m:
            out[m.group(1)] = m.group(2).split(" #")[0].strip()
    return out


def test_every_operator_setting_listed():
    names = _entries()
    missing = [f.upper() for f in Settings.model_fields
               if f not in INTERNAL and f.upper() not in names]
    assert not missing, f"dopisz do .env.example: {', '.join(missing)}"


def test_no_stale_entries():
    fields = {f.upper() for f in Settings.model_fields}
    stale = sorted(n for n in _entries() if n not in fields and n not in NON_SETTINGS)
    assert not stale, f"zmienne w .env.example, których nic nie czyta: {', '.join(stale)}"


def test_internal_list_is_current():
    assert set(INTERNAL) <= set(Settings.model_fields)


def test_no_real_secrets_in_template():
    leaked = [n for n, v in _entries().items() if SECRET_RE.search(n) and v not in PLACEHOLDERS]
    assert not leaked, f"w .env.example tylko puste wartości/atrapy sekretów: {', '.join(leaked)}"


def test_template_values_valid_and_equal_code_defaults():
    # literówka w wartości (np. „tak” w polu bool) wywaliłaby start aplikacji z szablonu, a wartość
    # inna niż w kodzie po cichu zmienia zachowanie (było: ACCESS_TOKEN_MINUTES=60 zamiast 120)
    template, defaults = Settings(_env_file=ENV_EXAMPLE), Settings(_env_file=None)
    drift = [f.upper() for f in Settings.model_fields
             if getattr(template, f) != getattr(defaults, f)]
    assert not drift, f"wartość w .env.example ≠ domyślna w config.py: {', '.join(drift)}"
