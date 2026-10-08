"""DB-007: pomocnik ograniczeń CHECK dla słowników tekstowych (VARCHAR bez natywnego enuma).

Modele deklarują CHECK-i (create_all: SQLite w testach/dev), a migracja chk001 zakłada te same
wyrażenia na PostgreSQL (NOT VALID + VALIDATE). Zgodność pilnuje test_db_check_constraints.
"""
from collections.abc import Iterable

from sqlalchemy import CheckConstraint

__all__ = ["in_check"]


def in_check(table: str, column: str, values: Iterable[str], *,
             nullable: bool = False) -> CheckConstraint:
    """`kolumna IN (...)` (z `IS NULL OR` dla kolumn opcjonalnych), nazwa ck_<tabela>_<kolumna>."""
    listed = ", ".join(f"'{v}'" for v in values)
    expr = f"{column} IN ({listed})"
    if nullable:
        expr = f"{column} IS NULL OR {expr}"
    return CheckConstraint(expr, name=f"ck_{table}_{column}")
