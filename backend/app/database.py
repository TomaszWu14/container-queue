from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


def engine_options(database_url: str) -> dict:
    """Opcje silnika zależne od backendu bazy.

    SQLite (dev/testy): jedno połączenie współdzielone między wątkami TestClienta.
    PostgreSQL (produkcja): jawnie strojona pula — bez tego SQLAlchemy używa domyślnych
    5+10=15 połączeń, a synchroniczne handlery FastAPI biegną w threadpoolu (~40 wątków),
    więc pod obciążeniem żądania czekają na wolne połączenie aż do pool_timeout.
    pool_pre_ping odrzuca martwe połączenia (np. po restarcie Postgresa/proxy).
    """
    if database_url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {
        "pool_pre_ping": True,
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_timeout": settings.db_pool_timeout,
        "pool_recycle": settings.db_pool_recycle,
    }


engine = create_engine(settings.database_url, **engine_options(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
