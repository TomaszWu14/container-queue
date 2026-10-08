"""Strażnik DOC-005: każde pole `Settings` ma wiersz w docs/ZMIENNE-SRODOWISKOWE.md."""
from pathlib import Path

from app.config import Settings

ENV_DOC = Path(__file__).resolve().parents[2] / "docs" / "ZMIENNE-SRODOWISKOWE.md"


def test_every_settings_field_documented():
    assert ENV_DOC.exists(), f"brak pliku {ENV_DOC}"
    text = ENV_DOC.read_text(encoding="utf-8")
    missing = [name.upper() for name in Settings.model_fields
               if f"`{name.upper()}`" not in text]
    assert not missing, f"dopisz do docs/ZMIENNE-SRODOWISKOWE.md: {', '.join(missing)}"
