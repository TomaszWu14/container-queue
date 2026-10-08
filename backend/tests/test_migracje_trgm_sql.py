"""Strażnik DB-002: indeksy pg_trgm w migracjach mają poprawny SQL i nie są cicho połykane.

trgm001 miał `CREATE INDEX ... ON t (kol gin_trgm_ops) USING gin` (USING po liście kolumn
= błąd składni Postgresa) w `try/except Exception`, więc na prod nie powstał żaden indeks.
"""
import ast
import pathlib
import re

VERSIONS = pathlib.Path(__file__).resolve().parents[1] / "migrations" / "versions"
# Znany historyczny błąd — naprawiony w trgm002; zastosowanych migracji się nie edytuje.
KNOWN_BROKEN = {"trgm001_wyszukiwarka_pg_trgm.py"}
_OK = re.compile(r"\bON\s+\S+\s+USING\s+gin\s*\(", re.IGNORECASE)


def _trgm_index_sql(path: pathlib.Path) -> list[str]:
    """Rekonstruuje SQL CREATE INDEX z gin_trgm_ops (f-stringi: wartości słownika _INDEXES)."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "gin_trgm_ops" in node.value:
            out.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            text = ast.unparse(node)
            if "CREATE INDEX" in text.upper():
                out.append(text)
    return out


def _check(path: pathlib.Path) -> list[str]:
    stmts = [s for s in _trgm_index_sql(path) if "CREATE INDEX" in s.upper()]
    src = path.read_text(encoding="utf-8")
    if "gin_trgm_ops" not in src:
        return []
    bad = [s for s in stmts if not _OK.search(s)]
    if not stmts:  # SQL składany z kawałków — nie da się zweryfikować, wymuś jawną postać
        bad.append("brak jawnego 'ON <tabela> USING gin (' w CREATE INDEX")
    return bad


def test_trgm001_to_znany_blad():
    """Sanity: detektor łapie historyczny błąd (inaczej wykluczenie niżej byłoby martwe)."""
    assert _check(VERSIONS / "trgm001_wyszukiwarka_pg_trgm.py")


def test_create_index_gin_trgm_ma_using_przed_kolumnami():
    bad = {p.name: e for p in sorted(VERSIONS.glob("*.py"))
           if p.name not in KNOWN_BROKEN and (e := _check(p))}
    assert not bad, f"CREATE INDEX z gin_trgm_ops: 'USING gin' musi być przed '(kolumna …)': {bad}"


def test_trgm002_nie_polyka_wyjatkow():
    tree = ast.parse((VERSIONS / "trgm002_indeksy_pg_trgm_poprawka.py").read_text(encoding="utf-8"))
    handlers = [h for h in ast.walk(tree) if isinstance(h, ast.ExceptHandler)]
    assert not handlers, "trgm002 ma zatrzymać migrację na błędzie SQL, nie łapać wyjątków"
    assert "begin_nested" not in ast.unparse(tree)
