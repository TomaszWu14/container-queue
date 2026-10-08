"""A4+A8 — wysyłka e-mail/Teams poza ścieżką żądania.

Potwierdza, że kanały zewnętrzne (SMTP, Teams) są zlecane do puli w tle (inny wątek),
że wyjątki w tle nie wracają do wywołującego, ORAZ że synchroniczna walidacja
konfiguracji SMTP jest zachowana (endpoint nadal od razu wie, że SMTP nie działa).
"""
import threading

import pytest

from app import notifications as N


def _wait(event: threading.Event, timeout: float = 3.0) -> None:
    assert event.wait(timeout), "zadanie w tle nie wystartowało w oczekiwanym czasie"


def test_submit_runs_in_background_and_swallows_errors():
    done = threading.Event()
    box: dict[str, str] = {}

    def boom():
        box["thread"] = threading.current_thread().name
        done.set()
        raise RuntimeError("kanał padł")

    # nie może rzucić mimo wyjątku w środku (best-effort)
    N._submit(boom)
    _wait(done)
    assert box["thread"].startswith("notify")


def test_send_email_offloads_smtp(monkeypatch):
    done = threading.Event()
    box: dict[str, object] = {}
    monkeypatch.setattr(N.settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(N.settings, "smtp_from", "x@example.com")

    def fake_smtp(message, recipients, timeout, channel="main"):
        box["thread"] = threading.current_thread().name
        box["recipients"] = list(recipients)
        done.set()

    monkeypatch.setattr(N, "_smtp_send", fake_smtp)
    caller = threading.current_thread().name
    N._send_email(["a@example.com"], "Tytuł", "treść")
    _wait(done)
    assert box["thread"] != caller and box["thread"].startswith("notify")
    assert box["recipients"] == ["a@example.com"]


def test_send_email_noop_without_host(monkeypatch):
    monkeypatch.setattr(N.settings, "smtp_host", "")
    called = []
    monkeypatch.setattr(N, "_smtp_send", lambda *a, **k: called.append(1))
    N._send_email(["a@example.com"], "t", "b")
    assert called == []


def test_send_html_email_offloads_when_configured(monkeypatch):
    done = threading.Event()
    box: dict[str, str] = {}
    monkeypatch.setattr(N.settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(N.settings, "smtp_from", "x@example.com")

    def fake_smtp(message, recipients, timeout, channel="main"):
        box["thread"] = threading.current_thread().name
        done.set()

    monkeypatch.setattr(N, "_smtp_send", fake_smtp)
    N.send_html_email(["a@example.com"], "S", "<b>hi</b>")
    _wait(done)
    assert box["thread"].startswith("notify")


def test_send_html_email_raises_when_unconfigured(monkeypatch):
    # walidacja MUSI zostać synchroniczna — endpoint od razu wie, że SMTP nie działa
    monkeypatch.setattr(N.settings, "smtp_host", "")
    monkeypatch.setattr(N.settings, "invite_smtp_host", "")
    with pytest.raises(RuntimeError):
        N.send_html_email(["a@example.com"], "S", "x")


def test_password_reset_offloads(monkeypatch):
    done = threading.Event()
    box: dict[str, str] = {}
    monkeypatch.setattr(N.settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(N.settings, "smtp_from", "x@example.com")

    def fake_smtp(message, recipients, timeout, channel="main"):
        box["thread"] = threading.current_thread().name
        done.set()

    monkeypatch.setattr(N, "_smtp_send", fake_smtp)
    N.send_password_reset("u@example.com", "Jan", "https://x/reset?t=1", 30)
    _wait(done)
    assert box["thread"].startswith("notify")


def test_send_teams_offloads(monkeypatch):
    done = threading.Event()
    box: dict[str, str] = {}
    monkeypatch.setattr(N.settings, "teams_webhook_url", "https://hook.example.com")

    def fake_post(url, title, body):
        box["thread"] = threading.current_thread().name
        done.set()

    monkeypatch.setattr(N, "_teams_post", fake_post)
    N._send_teams("tytuł", "treść")
    _wait(done)
    assert box["thread"].startswith("notify")
