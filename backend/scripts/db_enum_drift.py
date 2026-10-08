"""Strażnik dryfu natywnych ENUM-ów: wartości enumów w modelach vs typy w PostgreSQL.

compare_metadata() (db_drift.py) NIE porównuje wartości enumów — to osobne sprawdzenie.
Baza musi być zbudowana `alembic upgrade head`. Tylko odczyt. Kod wyjścia 1 = rozjazd.
    DATABASE_URL=postgresql+psycopg2://... python scripts/db_enum_drift.py   (z backend/)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import Enum, create_engine, text  # noqa: E402

import app.main  # noqa: F401,E402 — rejestruje wszystkie modele (kolejność importów)
from app.config import settings  # noqa: E402
from app.database import Base  # noqa: E402


def main() -> int:
    engine = create_engine(settings.database_url)
    db_enums: dict[str, set[str]] = {}
    with engine.connect() as conn:
        for typname, label in conn.execute(text(
                "select t.typname, e.enumlabel from pg_type t join pg_enum e on e.enumtypid = t.oid")):
            db_enums.setdefault(typname, set()).add(label)
        # kolumny, które w bazie NIE są natywnym enumem (np. VARCHAR) — rozjazd typu kolumny
        # pilnuje db_drift.py (modify_type w baseline), tu sprawdzamy tylko wartości enumów
        plain_cols = set(conn.execute(text(
            "select table_name, column_name from information_schema.columns "
            "where table_schema = current_schema() and data_type <> 'USER-DEFINED'")).all())
    engine.dispose()

    seen: set[str] = set()
    problems = 0
    for table in Base.metadata.sorted_tables:
        for col in table.columns:
            t = col.type
            if not isinstance(t, Enum) or not t.native_enum or t.name in seen:
                continue
            if (table.name, col.name) in plain_cols:
                print(f"pomijam {table.name}.{col.name}: w bazie nie jest enumem "
                      f"(typ kolumny pilnuje db_drift.py)")
                continue
            seen.add(t.name)
            db_vals = db_enums.get(t.name)
            if db_vals is None:
                print(f"BRAK TYPU w bazie: {t.name} ({table.name}.{col.name})")
                problems += 1
                continue
            missing, extra = set(t.enums) - db_vals, db_vals - set(t.enums)
            if missing or extra:
                problems += 1
                print(f"{t.name} ({table.name}.{col.name}): brak w bazie={sorted(missing)} "
                      f"nadmiarowe w bazie={sorted(extra)}")
    print(f"Sprawdzono {len(seen)} typów enum, rozjazdów: {problems}")
    if problems:
        print("Dopisz migrację ALTER TYPE ... ADD VALUE dla brakujących wartości.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
