"""BUILD-003: przy kilku workerach uvicorna (WEB_CONCURRENCY>1) pętle tła prowadzi JEDEN proces.

Lider = proces trzymający sesyjny `pg_try_advisory_lock(LEADER_KEY)` na własnym, długo
żyjącym połączeniu (osobny silnik bez puli — nie zajmuje miejsca w puli żądań). Pozostałe
procesy co `retry_s` próbują przejąć rolę: gdy lider zakończy się albo zerwie połączenie,
Postgres zwalnia jego locki i następny proces startuje pętle. Przy każdej próbie lider
sprawdza, czy jego połączenie żyje — po zerwaniu oddaje rolę i zatrzymuje pętle.

Zadania dalej biorą per-przebieg `jobs.job_lock`, więc krótkie okno dwóch liderów (zerwanie
wykryte dopiero przy kolejnym sprawdzeniu) nie daje równoległego przebiegu tego samego joba.
Pętle per proces (`jobs.PER_PROCESS_JOBS`, zrzut applog) biegną w każdym workerze.
SQLite (dev/testy, jeden proces): zawsze lider. Kontrakt: docs/JEDNA-INSTANCJA.md.
"""
import asyncio
import logging
from collections.abc import Callable

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from .config import settings
from .jobs import lock_key

logger = logging.getLogger(__name__)

LEADER_KEY = lock_key("__leader__")
RETRY_S = 30.0


class Leadership:
    """Rola lidera pętli tła w tym procesie (acquire/release z wątku — blokujące I/O)."""

    def __init__(self, url: str | None = None) -> None:
        self._url = url or settings.database_url
        self._engine = None
        self._conn = None

    def _is_postgres(self) -> bool:
        return self._url.startswith("postgresql")

    def _connect(self):
        if self._engine is None:
            self._engine = create_engine(self._url, poolclass=NullPool)
        return self._engine.connect()

    def _alive(self) -> bool:
        try:
            self._conn.execute(text("SELECT 1"))
            self._conn.commit()
            return True
        except Exception:  # noqa: BLE001 — zerwane połączenie = lock już zwolniony przez PG
            logger.warning("Połączenie lidera pętli tła zerwane — oddaję rolę")
            self._close()
            return False

    def _close(self) -> None:
        try:
            self._conn.close()
        except Exception:  # noqa: BLE001 — zamykamy martwe połączenie
            logger.debug("Zamknięcie połączenia lidera nie powiodło się", exc_info=True)
        self._conn = None

    def acquire(self) -> bool:
        """True = ten proces jest (albo właśnie został) liderem."""
        if not self._is_postgres():
            return True
        if self._conn is not None and self._alive():
            return True
        conn = self._connect()
        try:
            got = bool(conn.execute(text("SELECT pg_try_advisory_lock(:k)"),
                                    {"k": LEADER_KEY}).scalar())
            conn.commit()   # lock sesyjny przeżywa commit; bez tego „idle in transaction”
        except Exception:
            conn.close()
            raise
        if got:
            self._conn = conn
        else:
            conn.close()
        return got

    def release(self) -> None:
        if self._conn is None:
            return
        try:
            self._conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LEADER_KEY})
            self._conn.commit()
        except Exception:  # noqa: BLE001 — i tak zamykamy sesję, co zwalnia lock
            logger.debug("pg_advisory_unlock nie powiódł się — zamykam sesję", exc_info=True)
        self._close()


async def _stop(tasks: list[asyncio.Task]) -> None:
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def leader_loop(start: Callable[[], list[asyncio.Task]],
                      leadership: Leadership | None = None, retry_s: float = RETRY_S) -> None:
    """Startuje pętle tła (`start()`), gdy ten proces zostanie liderem; zatrzymuje je, gdy
    rolę straci. Przy anulowaniu (koniec lifespan) zatrzymuje pętle i zwalnia lock."""
    lead = leadership or Leadership()
    tasks: list[asyncio.Task] = []
    try:
        while True:
            try:
                is_leader = await asyncio.to_thread(lead.acquire)
            except Exception:  # noqa: BLE001 — baza chwilowo niedostępna: spróbuj później
                logger.exception("Wybór lidera pętli tła nie powiódł się — ponowię")
                is_leader = bool(tasks)
            if is_leader and not tasks:
                logger.info("Ten proces prowadzi pętle tła (lider)")
                tasks = start()
            elif not is_leader and tasks:
                logger.warning("Proces stracił rolę lidera — zatrzymuję pętle tła")
                await _stop(tasks)
                tasks = []
            await asyncio.sleep(retry_s)
    finally:
        await _stop(tasks)
        await asyncio.to_thread(lead.release)
