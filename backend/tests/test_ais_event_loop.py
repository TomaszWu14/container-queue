"""AIS: praca na bazie kolektora (handle_message → commit, geofence → notify_aboard) nie może
blokować event loopa — wolna baza wstrzymywała całą aplikację (wszystkie żądania async)."""
import asyncio
import sys
import threading
import time
import types

from app.tracking import ais


class _FakeWs:
    def __init__(self):
        self.sent = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def send(self, _data):
        return None

    async def recv(self):
        if not self.sent:
            self.sent = True
            return "{}"
        await asyncio.sleep(10)


class _FakeDb:
    closed_in = None

    def close(self):
        _FakeDb.closed_in = threading.current_thread().name


def test_run_session_db_work_off_event_loop(monkeypatch):
    monkeypatch.setitem(sys.modules, "websockets",
                        types.SimpleNamespace(connect=lambda _url: _FakeWs()))
    threads: list[str] = []
    ticks = [0]
    during: list[int] = []
    monkeypatch.setattr(ais, "_prepare_session",
                        lambda _db, _pref, _rot: (threads.append("prep") or {}, {}, False))

    def slow_handle(_db, _raw, _wanted):
        threads.append(threading.current_thread().name)
        start = ticks[0]
        time.sleep(0.3)        # wolny commit / notify_aboard
        during.append(ticks[0] - start)
        return True

    monkeypatch.setattr(ais, "handle_message", slow_handle)

    async def scenario():
        async def ticker():
            while True:
                await asyncio.sleep(0.01)
                ticks[0] += 1

        task = asyncio.create_task(ticker())
        positions = await ais.run_session(_FakeDb, 0.5)
        task.cancel()
        return positions

    positions = asyncio.run(scenario())
    assert positions is True
    db_threads = [t for t in threads if t != "prep"]
    assert db_threads and all(t.startswith("ais-db") for t in db_threads), threads
    assert _FakeDb.closed_in and _FakeDb.closed_in.startswith("ais-db")
    # pętla żyła w trakcie 0,3 s „wolnej bazy” (inline = 0 ticków)
    assert during and during[0] >= 3, during
