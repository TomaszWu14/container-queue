"""DATA-007: kontrole jakości danych (10 plików SQL z audytu) uruchamiane skryptem, tylko do odczytu.

SQL jest PostgreSQL-owy (array_agg, regexp), więc tu sprawdzamy: że pliki są czystym SELECT,
że runner ustawia sesję read-only i timeout przed czymkolwiek, dzieli pliki na instrukcje,
zbiera wyniki i błędy per instrukcja, a poza Postgresem odmawia (kod 2)."""
import re

import pytest

from scripts import data_quality

WRITE_WORDS = re.compile(r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|"
                         r"vacuum|call|do|set)\b", re.IGNORECASE)


def test_all_checks_present_and_select_only():
    files = data_quality.check_files()
    assert [f.name[:7] for f in files] == [f"data_{i:02d}" for i in range(1, 11)]
    for path in files:
        statements = data_quality.statements(path.read_text(encoding="utf-8"))
        assert statements, path.name
        for sql in statements:
            assert re.match(r"^\s*(select|with)\b", sql, re.IGNORECASE), (path.name, sql[:60])
            assert not WRITE_WORDS.search(re.sub(r"'[^']*'", "''", sql)), (path.name, sql[:60])


def test_statements_split_skips_comments():
    sql = "-- opis; z średnikiem\nSELECT 1;\n\n-- druga\nSELECT 'a;b'\nFROM t;\n"
    assert data_quality.statements(sql) == ["SELECT 1", "SELECT 'a;b'\nFROM t"]


def test_describe_reads_goal_and_expected_result():
    goal, expected = data_quality.describe(data_quality.check_files()[0].read_text(encoding="utf-8"))
    assert goal.startswith("DATA-01") and expected.startswith("(a) 0 wierszy")


class _Cursor:
    def __init__(self, log, results):
        self.log, self.results, self.description = log, results, None
        self._rows = []

    def execute(self, sql):
        self.log.append(sql)
        outcome = self.results.pop(0) if sql.lstrip().upper().startswith(("SELECT", "WITH")) else None
        if isinstance(outcome, Exception):
            raise outcome
        if outcome is not None:
            self.description = [(name,) for name in outcome[0]]
            self._rows = outcome[1]

    def fetchmany(self, n):
        return self._rows[:n]

    def fetchall(self):
        return self._rows

    def close(self):
        pass


class _Conn:
    def __init__(self, results):
        self.log, self.results, self.commits, self.rollbacks = [], list(results), 0, 0

    def cursor(self):
        return _Cursor(self.log, self.results)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_run_is_read_only_and_collects_results(tmp_path):
    (tmp_path / "data_01_a.sql").write_text("-- DATA-A. Cel: a.\n-- Oczekiwany wynik: 0.\n"
                                            "SELECT 1 AS x;\nSELECT 2 AS y;\n", encoding="utf-8")
    (tmp_path / "data_02_b.sql").write_text("-- DATA-B. Cel: b.\nSELECT zla FROM brak;\n",
                                            encoding="utf-8")
    conn = _Conn([(["x"], [(1,), (2,)]), (["y"], []), RuntimeError("relation brak does not exist")])
    report = data_quality.run(conn, sorted(tmp_path.glob("*.sql")), limit=1)
    assert conn.log[0] == "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"
    assert conn.log[1].startswith("SET statement_timeout")
    first, second, broken = report
    assert (first["file"], first["rows"], first["columns"], first["sample"]) == (
        "data_01_a.sql", 2, ["x"], [[1]])
    assert first["goal"] == "DATA-A. Cel: a." and first["expected"] == "0."
    assert second["rows"] == 0 and broken["error"].startswith("RuntimeError")
    assert conn.rollbacks >= 1          # błąd jednej instrukcji nie blokuje kolejnych


def test_refuses_non_postgres(capsys, monkeypatch):
    monkeypatch.setattr(data_quality.settings, "database_url", "sqlite:///./x.db")
    assert data_quality.main([]) == 2
    assert "PostgreSQL" in capsys.readouterr().out


@pytest.mark.parametrize("rows,fail,code", [(0, True, 0), (3, False, 0), (3, True, 1)])
def test_exit_code_for_findings(rows, fail, code):
    report = [{"file": "f.sql", "statement": 1, "rows": rows, "error": ""}]
    assert data_quality.exit_code(report, fail_on_findings=fail) == code
