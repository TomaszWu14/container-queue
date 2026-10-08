"""Audyt AI-002: limit równoległych wywołań LLM, krótszy timeout asystenta, limit per użytkownik."""
import threading
import time

import pytest

from app import llm
from app.config import settings
from app.routers import assistant

from .conftest import login
from .test_assistant import _seed


class _Resp:
    def raise_for_status(self):
        pass

    def json(self):
        return {"message": {"content": "ok"}}


@pytest.fixture
def fake_ollama(monkeypatch):
    """httpx.post Ollamy zamockowany: trzyma slot, dopóki test nie zwolni `release`."""
    seen, started, release = [], threading.Event(), threading.Event()

    def post(url, json, timeout):
        seen.append(timeout)
        started.set()
        release.wait(5)
        return _Resp()
    monkeypatch.setattr(settings, "ollama_url", "http://ollama:11434")
    monkeypatch.setattr(settings, "llm_wait_s", 0.05)
    monkeypatch.setattr(llm.httpx, "post", post)
    yield seen, started, release
    release.set()


def test_second_parallel_call_gets_fast_busy(fake_ollama):
    seen, started, release = fake_ollama
    t = threading.Thread(target=llm.chat, args=("m", "pierwsze"))
    t.start()
    assert started.wait(2)
    t0 = time.monotonic()
    with pytest.raises(llm.LLMBusy, match="zajęty"):
        llm.chat("m", "drugie")
    assert time.monotonic() - t0 < 1   # szybka odmowa, nie czekanie na model
    release.set()
    t.join(2)
    assert llm.chat("m", "po zwolnieniu") == "ok"   # slot wrócił


def test_timeout_from_settings(fake_ollama, monkeypatch):
    seen, _, release = fake_ollama
    release.set()
    monkeypatch.setattr(settings, "llm_timeout_s", 42.0)
    llm.chat("m", "x")
    llm.chat("m", "x", timeout=settings.ollama_timeout)   # OCR vision: własny, dłuższy
    assert seen == [42.0, settings.ollama_timeout]


def test_assistant_busy_returns_503(client, db_session, fake_ollama):
    _seed(db_session)
    assert llm._slots.acquire(timeout=1)   # ktoś inny właśnie pyta model
    try:
        r = client.post("/api/assistant/ask", headers=login(client),
                        json={"question": "status MSCU1234567"})
    finally:
        llm._slots.release()
    assert r.status_code == 503 and "zajęty" in r.json()["detail"]


def test_assistant_per_user_limit_429(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "ollama_url", "")
    monkeypatch.setattr(settings, "assistant_rate_limit_per_minute", 2)
    monkeypatch.setattr(assistant, "ask_limiter", assistant.ApiRateLimiter())
    hdr = login(client)
    codes = [client.post("/api/assistant/ask", headers=hdr, json={"question": "hej"}).status_code
             for _ in range(3)]
    assert codes == [200, 200, 429]
