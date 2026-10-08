"""Strażnik spójności dev-shimu (`ensure_new_columns`) z migracjami Alembica.

Produkcja migruje przez `alembic upgrade head`. Dev na SQLite migracji nie uruchamia —
polega na `ensure_new_columns()` w `app/db_bootstrap.py`, który ręcznie ALTER-uje istniejące
tabele. To dwa niezależne, ręcznie utrzymywane opisy tego samego schematu, więc cicho
się rozjeżdżają: kolumna dodana tylko migracją nigdy nie trafi do istniejącej bazy dev,
a `Base.metadata.create_all()` jej nie doda — create_all tworzy wyłącznie brakujące
tabele, nigdy nie zmienia istniejących.

Tak powstał błąd `carriers.is_active`: migracja c7d8e9f0a1b2 dodała kolumnę, wpisu
w shimie zabrakło, więc każda baza dev z tabelą `carriers` sprzed migracji zwracała
`GET /api/carriers -> 500 (no such column: carriers.is_active)`.

Test czyta AST `app/db_bootstrap.py` zamiast wykonywać funkcję, bo słowniki `ddl`/`extra_tables`
są lokalne dla `ensure_new_columns()` i nie da się ich zaimportować.
"""
import ast
import pathlib

import pytest

BACKEND = pathlib.Path(__file__).resolve().parents[1]
MAIN_PY = BACKEND / "app" / "db_bootstrap.py"
MIGRATIONS = BACKEND / "migrations" / "versions"


def _dict_literal(node: ast.AST) -> dict:
    """Zwraca {klucz: <cokolwiek>} z literału dict; wartości nieistotne — liczą się klucze."""
    out = {}
    if isinstance(node, ast.Dict):
        for key, value in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                out[key.value] = _dict_literal(value) if isinstance(value, ast.Dict) else True
    return out


def _shim_coverage() -> dict[str, set[str]]:
    """{tabela: {kolumny}} obsługiwane przez ensure_new_columns()."""
    tree = ast.parse(MAIN_PY.read_text(encoding="utf-8"))
    func = next((n for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef) and n.name == "ensure_new_columns"), None)
    assert func is not None, "nie znaleziono ensure_new_columns() w app/db_bootstrap.py"

    coverage: dict[str, set[str]] = {}
    for stmt in ast.walk(func):
        if not isinstance(stmt, ast.Assign) or not isinstance(stmt.targets[0], ast.Name):
            continue
        target = stmt.targets[0].id
        if target == "ddl":
            # `ddl` dotyczy wyłącznie tabeli containers (ALTER TABLE containers ...)
            coverage.setdefault("containers", set()).update(_dict_literal(stmt.value))
        elif target == "extra_tables":
            for table, columns in _dict_literal(stmt.value).items():
                coverage.setdefault(table, set()).update(columns if isinstance(columns, dict) else ())
    assert coverage, "nie udało się odczytać ddl/extra_tables z ensure_new_columns()"
    return coverage


def _migration_add_columns() -> list[tuple[str, str, str]]:
    """[(tabela, kolumna, plik_migracji)] dla każdego op.add_column w migracjach."""
    found = []
    for path in sorted(MIGRATIONS.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "add_column" and len(node.args) >= 2):
                continue
            table, column = node.args[0], node.args[1]
            if not (isinstance(table, ast.Constant) and isinstance(table.value, str)):
                continue
            # sa.Column("nazwa", ...) — nazwa kolumny to pierwszy argument
            if isinstance(column, ast.Call) and column.args and isinstance(column.args[0], ast.Constant):
                found.append((table.value, column.args[0].value, path.name))
    dropped = _migration_dropped_columns()
    return [f for f in found if f[:2] not in dropped]


def _migration_dropped_columns() -> set[tuple[str, str]]:
    """(tabela, kolumna) usunięte później w upgrade() przez batch_alter_table(...).drop_column —
    takiej kolumny shim dev już nie potrzebuje (np. attachments.client_visible, nocust001)."""
    dropped = set()
    for path in sorted(MIGRATIONS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        upgrade = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "upgrade"), None)
        for with_node in ast.walk(upgrade) if upgrade else ():
            if not isinstance(with_node, ast.With):
                continue
            ctx = with_node.items[0].context_expr
            if not (isinstance(ctx, ast.Call) and getattr(ctx.func, "attr", "") == "batch_alter_table"
                    and ctx.args and isinstance(ctx.args[0], ast.Constant)):
                continue
            for call in ast.walk(with_node):
                if (isinstance(call, ast.Call) and getattr(call.func, "attr", "") == "drop_column"
                        and call.args and isinstance(call.args[0], ast.Constant)):
                    dropped.add((ctx.args[0].value, call.args[0].value))
    return dropped


def test_migrations_contain_add_column():
    """Sanity: gdyby parser przestał cokolwiek znajdować, test poniżej byłby pusto-zielony."""
    assert len(_migration_add_columns()) > 20


@pytest.mark.parametrize("table,column,migration", _migration_add_columns(),
                         ids=lambda v: v if isinstance(v, str) else str(v))
def test_every_migration_column_is_in_dev_shim(table, column, migration):
    """Każda kolumna dodana migracją musi mieć wpis w ensure_new_columns().

    Inaczej: produkcja (alembic) ją dostanie, a istniejące bazy dev nie — i pierwszy
    SELECT po tej kolumnie wywali 500. Jeśli ten test świeci na czerwono po dodaniu
    migracji, dopisz kolumnę do `ddl` (dla containers) lub `extra_tables` w app/db_bootstrap.py.
    """
    coverage = _shim_coverage()
    assert column in coverage.get(table, set()), (
        f"Migracja {migration} dodaje {table}.{column}, ale ensure_new_columns() o tym "
        f"nie wie — istniejące bazy dev nie dostaną tej kolumny i poleci 500 "
        f"(no such column: {table}.{column}). Dopisz wpis w app/db_bootstrap.py."
    )
