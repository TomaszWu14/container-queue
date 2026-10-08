"""Strażnik łańcucha migracji Alembica.

Lekcja z awarii prod 2026-09-18: migracja portalu reużyła istniejący revision ID
(b7c8d9e0f1a2) → duplikat + wiele głów → `alembic upgrade head` padał i aplikacja
nie wstawała po deployu. Te testy blokują merge z zepsutym łańcuchem.
"""
import re
from pathlib import Path

VERSIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"


def _parse():
    revs: dict[str, str] = {}          # revision -> nazwa pliku
    downs: dict[str, list[str]] = {}   # revision -> lista down_revision
    dups: list[str] = []
    for path in sorted(VERSIONS.glob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        rev = re.search(r"^revision(?::\s*\w+)?\s*=\s*['\"]([^'\"]+)['\"]", text, re.M)
        assert rev, f"{path.name}: brak revision"
        rid = rev.group(1)
        if rid in revs:
            dups.append(f"{rid} ({revs[rid]} i {path.name})")
        revs[rid] = path.name
        down_match = re.search(r"^down_revision[^=]*=\s*(.+)$", text, re.M)
        raw = down_match.group(1) if down_match else "None"
        downs[rid] = re.findall(r"['\"]([^'\"]+)['\"]", raw)
    return revs, downs, dups


def test_revision_ids_are_unique():
    _, _, dups = _parse()
    assert not dups, f"Zduplikowane revision ID (to wysadza deploy!): {dups}"


def test_single_head():
    revs, downs, _ = _parse()
    referenced = {d for lst in downs.values() for d in lst}
    heads = [rid for rid in revs if rid not in referenced]
    assert len(heads) == 1, (
        f"Łańcuch migracji ma {len(heads)} głów: "
        f"{[(h, revs[h]) for h in heads]} — przenumeruj swoją migrację na koniec "
        "łańcucha (down_revision = aktualna głowa), nie rób merge-migracji."
    )


def test_down_revisions_exist():
    revs, downs, _ = _parse()
    missing = [(rid, d) for rid, lst in downs.items() for d in lst if d not in revs]
    assert not missing, f"down_revision wskazuje nieistniejące migracje: {missing}"
