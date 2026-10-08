"""Święta backendu == snapshot, który sprawdza też frontend (holidays.parity.test.ts).

frontend/src/holidays.ts to ręczne lustro app/holidays.py — zmiana świąt po jednej stronie
bez drugiej (i bez snapshotu) wywala któryś z dwóch testów.
"""
import json
from pathlib import Path

from app.holidays import holidays

SNAPSHOT = Path(__file__).resolve().parents[2] / "frontend" / "src" / "holidays.snapshot.json"


def test_holidays_match_frontend_snapshot():
    snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert set(snap) == {"PL", "PT"}
    for country, years in snap.items():
        for year, days in years.items():
            assert sorted(d.isoformat() for d in holidays(int(year), country)) == days, (country, year)
