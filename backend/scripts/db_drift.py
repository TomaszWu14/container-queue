"""Strażnik dryfu schematu: modele SQLAlchemy vs baza zbudowana `alembic upgrade head`.

Znane różnice są w db_drift_baseline.txt (jedna na linię) i mogą tylko ubywać — jak
BASELINE w scripts/check_file_lengths.py:
  - różnica spoza baseline = błąd (model zmieniony bez migracji albo migracja bez modelu),
  - pozycja baseline, której już nie ma = błąd „usuń z baseline” (dryf naprawiony).
Tylko odczyt (compare_metadata to czysty diff). Kod wyjścia 1 = problem.
    DATABASE_URL=postgresql+psycopg2://... python scripts/db_drift.py   (z backend/)
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alembic.autogenerate import compare_metadata  # noqa: E402
from alembic.migration import MigrationContext  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402

import app.main  # noqa: F401,E402 — rejestruje wszystkie modele (kolejność importów)
from app.config import settings  # noqa: E402
from app.database import Base  # noqa: E402

BASELINE = Path(__file__).with_name("db_drift_baseline.txt")


def _flat(diff):
    for item in diff:
        if isinstance(item, list):
            yield from _flat(item)
        else:
            yield item


def describe(i) -> str:
    """Stabilna, jednolinijkowa postać różnicy (klucz porównania z baseline)."""
    kind = i[0]
    if kind in ("add_table", "remove_table"):
        return f"{kind} {i[1].name}"
    if kind in ("add_index", "remove_index"):
        cols = ",".join(c.name for c in i[1].columns)
        return f"{kind} {i[1].table.name}.{i[1].name} ({cols}){' unique' if i[1].unique else ''}"
    if kind in ("add_column", "remove_column"):
        return f"{kind} {i[2]}.{i[3].name} {i[3].type}"
    if kind in ("add_fk", "remove_fk"):
        cols = ",".join(c.name for c in i[1].columns)
        return f"{kind} {i[1].parent.name} ({cols}) -> {i[1].referred_table.name}"
    if kind in ("add_constraint", "remove_constraint"):
        table = i[1].table.name if getattr(i[1], "table", None) is not None else "?"
        return f"{kind} {table}.{i[1].name}"
    if kind.startswith("modify_"):
        return f"{kind} {i[2]}.{i[3]} {i[5]!r} -> {i[6]!r}"
    return f"{kind} {i[1:]}"


def current_drift() -> set[str]:
    logging.getLogger("alembic").setLevel(logging.WARNING)  # bez szumu INFO „Detected …”
    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True,
                                                     "compare_server_default": False})
        diff = compare_metadata(ctx, Base.metadata)
    engine.dispose()
    return {describe(i) for i in _flat(diff)}


def main() -> int:
    known = {ln.strip() for ln in BASELINE.read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.startswith("#")}
    now = current_drift()
    new, gone = sorted(now - known), sorted(known - now)
    for line in new:
        print(f"NOWA RÓŻNICA: {line}")
    for line in gone:
        print(f"NAPRAWIONE — usuń z baseline ({BASELINE.name}): {line}")
    print(f"Różnic: {len(now)} (w baseline: {len(known)}), nowych: {len(new)}, "
          f"do usunięcia z baseline: {len(gone)}")
    if new:
        print("Model i migracje się rozjechały — dopisz migrację (alembic revision --autogenerate).")
    return 1 if new or gone else 0


if __name__ == "__main__":
    sys.exit(main())
