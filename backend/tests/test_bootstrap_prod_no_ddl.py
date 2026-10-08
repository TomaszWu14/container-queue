"""BUILD-002 / ARCH-005: na produkcji schemat pochodzi wyłącznie z `alembic upgrade head`.

bootstrap() nie może tam wołać create_all ani dev-shimu ensure_new_columns — tylko seedy.
"""
import logging

import pytest

from app import db_bootstrap


def _boom(*_a, **_kw):
    raise AssertionError("DDL przy starcie na produkcji")


@pytest.mark.parametrize("env", ["production", "prod", "Production"])
def test_bootstrap_on_production_skips_ddl(monkeypatch, caplog, env):
    monkeypatch.setattr(db_bootstrap.settings, "environment", env)
    monkeypatch.setattr(db_bootstrap, "ensure_new_columns", _boom)
    monkeypatch.setattr(db_bootstrap.Base.metadata, "create_all", _boom)
    with caplog.at_level(logging.INFO, logger=db_bootstrap.__name__):
        db_bootstrap.bootstrap()   # seedy idempotentne — schemat już jest z conftest
    assert any("DDL pominięty" in r.getMessage() for r in caplog.records)


def test_alembic_head_mismatch_logs_error(monkeypatch, caplog):
    # testowa baza SQLite nie ma alembic_version → niezgodność z głową → ERROR, bez wyjątku
    with caplog.at_level(logging.ERROR, logger=db_bootstrap.__name__):
        db_bootstrap.check_alembic_head()
    assert any("różni się od głowy" in r.getMessage() for r in caplog.records)


def test_bootstrap_in_dev_still_runs_ddl(monkeypatch):
    calls = []
    monkeypatch.setattr(db_bootstrap.settings, "environment", "dev")
    monkeypatch.setattr(db_bootstrap, "ensure_new_columns", lambda: calls.append("shim"))
    db_bootstrap.bootstrap()
    assert calls == ["shim"]
