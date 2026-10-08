"""A3 — strojenie puli połączeń.

Test potwierdza problem/zachowanie bez żywego Postgresa: sprawdzamy opcje silnika
budowane dla adresu PostgreSQL (jawna pula) oraz to, że SQLite pozostaje nietknięty.
Silnika PG nie łączymy — weryfikujemy tylko konfigurację (create_engine jest leniwe).
"""
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

from app.config import settings
from app.database import engine_options


def test_sqlite_options_untouched():
    opts = engine_options("sqlite:///./x.db")
    assert opts == {"connect_args": {"check_same_thread": False}}
    # brak parametrów puli QueuePool dla SQLite (używa domyślnego dla plikowej bazy)
    assert "pool_size" not in opts


def test_postgres_options_tune_pool():
    opts = engine_options("postgresql+psycopg2://u:p@db:5432/x")
    assert opts["pool_pre_ping"] is True
    assert opts["pool_size"] == settings.db_pool_size
    assert opts["max_overflow"] == settings.db_max_overflow
    assert opts["pool_timeout"] == settings.db_pool_timeout
    assert opts["pool_recycle"] == settings.db_pool_recycle


def test_postgres_defaults_exceed_sqlalchemy_baseline():
    # regresja: pula musi być większa niż domyślne 5+10=15, inaczej strojenie jest no-opem
    assert settings.db_pool_size + settings.db_max_overflow > 15


def test_engine_built_with_pool_for_postgres():
    # silnik faktycznie przyjmuje opcje (bez łączenia) — QueuePool z naszym rozmiarem
    eng = create_engine("postgresql+psycopg2://u:p@db:5432/x",
                        **engine_options("postgresql+psycopg2://u:p@db:5432/x"))
    assert isinstance(eng.pool, QueuePool)
    assert eng.pool.size() == settings.db_pool_size
