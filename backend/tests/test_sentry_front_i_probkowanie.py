"""OBS-010: próbkowanie transakcji Sentry z konfiguracji (SENTRY_TRACES_RATE, domyślnie 5%)
i błędy JS z beaconu /api/client-error jako osobne zdarzenia Sentry — grupowane po nazwie
i komunikacie, z tagiem source=frontend, po maskowaniu. Bez SENTRY_DSN: nic nie wychodzi."""
import sentry_sdk

from app import redaction
from app.config import Settings, settings

DSN = "https://public@o0.ingest.example.invalid/1"   # atrapa — sentry_sdk.init podmieniony


def test_traces_rate_default_and_configurable(monkeypatch):
    assert Settings(_env_file=None).sentry_traces_rate == 0.05
    seen = {}
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: seen.update(kw))
    monkeypatch.setattr(settings, "sentry_dsn", DSN)
    monkeypatch.setattr(settings, "sentry_traces_rate", 0.2)
    redaction.init_sentry()
    assert seen["traces_sample_rate"] == 0.2
    assert seen["send_default_pii"] is False and seen["before_send"] is redaction._sentry_before_send


def test_init_skipped_without_dsn(monkeypatch):
    called = []
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: called.append(kw))
    monkeypatch.setattr(settings, "sentry_dsn", "")
    redaction.init_sentry()
    assert called == []


def _capture(monkeypatch):
    events = []

    def capture_message(message, level=None, scope=None, **kw):
        events.append({"message": message, "level": level, "tags": kw.get("tags", {}),
                       "fingerprint": kw.get("fingerprint", []), "extra": kw.get("extras", {})})

    monkeypatch.setattr(sentry_sdk, "capture_message", capture_message)
    return events


def test_client_error_beacon_goes_to_sentry_as_frontend_event(client, monkeypatch):
    events = _capture(monkeypatch)
    monkeypatch.setattr(settings, "sentry_dsn", DSN)
    token = "abcdefghijklmnopqrstuvwxyz123456"
    r = client.post("/api/client-error", json={
        "name": "TypeError", "message": "x is undefined (jan.kowalski@firma.pl)",
        "stack": "at QueuePage (index.js:1:2)", "url": f"http://panel/dostawa/{token}"})
    assert r.status_code == 202
    [event] = events
    assert event["message"].startswith("[frontend] TypeError: x is undefined")
    assert event["level"] == "error" and event["tags"]["source"] == "frontend"
    assert event["fingerprint"][:2] == ["frontend", "TypeError"]
    assert token not in str(event) and "jan.kowalski@firma.pl" not in str(event)
    assert "QueuePage" in event["extra"]["stack"]


def test_client_error_without_dsn_is_not_sent(client, monkeypatch):
    events = _capture(monkeypatch)
    monkeypatch.setattr(settings, "sentry_dsn", "")
    assert client.post("/api/client-error", json={
        "name": "Error", "message": "boom", "stack": "", "url": "http://panel/"}).status_code == 202
    assert events == []
