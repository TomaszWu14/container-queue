"""RUN_BACKGROUND_JOBS=false — instancja wtórna (drugi serwer na wspólnej bazie)
serwuje API, ale nie startuje pętli tła (bez podwójnych alertów/SMS-ów)."""
import asyncio

from fastapi.testclient import TestClient

from app.config import settings
from app.database import engine
from app.main import app


def test_secondary_instance_starts_without_background_tasks(monkeypatch, _db_template):
    monkeypatch.setattr(settings, "run_background_jobs", False)
    created: list = []
    original = asyncio.create_task

    def spy(coro, **kwargs):
        created.append(getattr(coro, "__name__", str(coro)))
        return original(coro, **kwargs)

    monkeypatch.setattr(asyncio, "create_task", spy)
    # Baza jak w fixture `client` (dispose puli + szablon po bootstrapie), a nie własny
    # drop_all na wspólnym pliku bez dispose(): jako jedyny test robił DDL na połączeniach
    # zostawionych przez poprzedni test (i ewentualny zrzut applog_loop z wątku to_thread,
    # którego cancel nie zatrzymuje) — zależność od kolejności. bootstrap() woła i tak lifespan.
    engine.dispose()
    with engine.raw_connection() as raw:
        _db_template.backup(raw.driver_connection)
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
    # żadna pętla DOMENOWA nie wystartowała (create_task może być wołany przez
    # starlette wewnętrznie — filtrujemy po nazwach naszych pętli). applog_loop jest
    # wyjątkiem świadomym: bufor dziennika jest per-proces, więc nawet instancja
    # wtórna musi sama zrzucać swój bufor do bazy (patrz main.lifespan).
    loops = [name for name in created if name.endswith("_loop") and name != "applog_loop"]
    assert loops == []
    assert "applog_loop" in created
