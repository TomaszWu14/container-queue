"""CODE-007: szerokie `except` nie połykają błędu bez śladu — przyczyna (ślad stosu)
trafia do logu, a ruff pilnuje tego w CI (BLE001 = połknięty wyjątek, B904 = zgubiony
łańcuch przy `raise` w `except`)."""
import logging
import pathlib
import tomllib

PYPROJECT = pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml"


def _traced(caplog, logger_name: str) -> bool:
    return any(r.name == logger_name and r.exc_info for r in caplog.records)


class _BrokenDb:
    def scalar(self, _stmt):
        raise RuntimeError("baza niedostępna")


def test_ruff_blocks_blind_except_and_lost_exception_chain():
    lint = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["tool"]["ruff"]["lint"]
    assert "B" in lint["select"] and "B904" not in lint["ignore"]
    assert "BLE" in lint["select"] and "BLE001" not in lint["ignore"]


def test_system_panel_metric_failure_is_logged(caplog):
    from app.routers import system
    with caplog.at_level(logging.WARNING, logger="app.routers.system"):
        assert system._safe_scalar(_BrokenDb(), "SELECT 1") is None
    assert _traced(caplog, "app.routers.system")


def test_system_panel_dir_size_failure_is_logged(caplog, monkeypatch, tmp_path):
    from app.routers import system

    def _denied(self, _pattern):
        raise PermissionError("brak dostępu")
    monkeypatch.setattr(pathlib.Path, "rglob", _denied)
    with caplog.at_level(logging.WARNING, logger="app.routers.system"):
        assert system._dir_size_mb(str(tmp_path)) is None
    assert _traced(caplog, "app.routers.system")


def test_backup_verify_missing_table_is_logged(caplog, tmp_path):
    from app import backup_verify
    url = f"sqlite:///{tmp_path / 'dump.db'}"
    with caplog.at_level(logging.WARNING, logger="app.backup_verify"):
        assert backup_verify._count_rows(url, ["nie_ma_tabeli"]) == {"nie_ma_tabeli": None}
    assert _traced(caplog, "app.backup_verify")


def test_analytics_unreadable_file_is_logged(caplog):
    from app.analytics import ingest
    with caplog.at_level(logging.WARNING, logger="app.analytics.ingest"):
        report = ingest.parse_issues(b"\x00 to nie jest xlsx", "zuzycie.xlsx")
    assert report.errors == ["Nie udało się odczytać pliku"]   # komunikat dla użytkownika bez zmian
    assert _traced(caplog, "app.analytics.ingest")

