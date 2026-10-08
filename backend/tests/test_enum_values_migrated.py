"""Audyt DB-001: każda wartość natywnego enuma PG używana przez modele musi pojawić się
w jakiejś migracji (CREATE TYPE albo ALTER TYPE … ADD VALUE). Inaczej na świeżym PG
zapis tej wartości daje 500 (`invalid input value for enum`), a SQLite w testach tego nie widzi."""
import pathlib

import sqlalchemy as sa

from app.database import Base
import app.models  # noqa: F401  (rejestruje tabele)

VERSIONS = pathlib.Path(__file__).resolve().parents[1] / "migrations" / "versions"
# w bazie VARCHAR (migracja e4f5a6b7c8d9), w modelu natywny Enum — rozjazd typu, nie brak wartości
_VARCHAR_IN_DB = {("ports", "category"), ("orders", "main_mode"), ("orders", "sea_service")}


def test_every_native_enum_value_is_created_by_a_migration():
    text = "\n".join(p.read_text(encoding="utf-8") for p in VERSIONS.glob("*.py"))
    missing = set()
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if (table.name, column.name) in _VARCHAR_IN_DB:
                continue
            if isinstance(column.type, sa.Enum) and column.type.native_enum:
                for value in column.type.enums:
                    if f"'{value}'" not in text and f'"{value}"' not in text:
                        missing.add(f"{column.type.name}.{value}")
    assert not missing, f"brak migracji dodającej wartości enuma: {sorted(missing)}"
