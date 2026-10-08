"""Strażnik DOC-003: cykl życia kontenera i statusy odprawy w README i SPECYFIKACJI
zgadzają się z enumami (kolejność = kolejność procesu). Nowy status w kodzie bez
aktualizacji dokumentacji = czerwony test, nie zły model procesu u czytelników."""
import re
from pathlib import Path

import pytest

from app.models.enums import ContainerStatus, CustomsStatus

ROOT = Path(__file__).resolve().parents[2]
DOCS = [ROOT / "README.md", ROOT / "docs" / "SPECYFIKACJA.md"]


def _chains(text: str) -> list[list[str]]:
    """Łańcuchy `A → B → C` w backtickach."""
    chains = (re.findall(r"[A-Z_]+", c) for c in re.findall(r"`([A-Z_ →]+→[A-Z_ →]+)`", text))
    return [c for c in chains if len(c) > 1]


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_container_lifecycle_matches_enum(doc):
    expected = [s.value for s in ContainerStatus]
    chains = [c for c in _chains(doc.read_text(encoding="utf-8")) if c[0] == expected[0]]
    assert chains, f"{doc.name}: brak łańcucha statusów kontenera"
    assert chains[0] == expected, f"{doc.name}: {chains[0]} ≠ {expected}"


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_customs_statuses_all_documented(doc):
    text = doc.read_text(encoding="utf-8")
    chain = next((c for c in _chains(text) if c[0] == CustomsStatus.BRAK.value), None)
    assert chain, f"{doc.name}: brak łańcucha statusów odprawy"
    missing = [s.value for s in CustomsStatus if s.value not in chain and f"`{s.value}`" not in text]
    assert not missing, f"{doc.name}: brak statusów odprawy {missing}"
    main_path = [s.value for s in CustomsStatus if s is not CustomsStatus.REWIZJA]
    assert chain == main_path, f"{doc.name}: {chain} ≠ {main_path}"
