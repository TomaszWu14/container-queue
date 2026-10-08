"""AI-006: Ollama nie ma uwierzytelniania, a do modelu idą skany faktur i fakty z systemu —
aplikacja wysyła je tylko pod adres w sieci wewnętrznej (usługa Dockera, localhost,
adres prywatny), chyba że administrator świadomie ustawi OLLAMA_ALLOW_REMOTE=true."""
import logging

import pytest

from app import llm
from app.config import settings
from app.invoices import ocr

INTERNAL = ["http://ollama:11434", "http://localhost:11434/", "http://127.0.0.1:11434",
            "http://10.1.2.3:11434", "http://192.168.0.5:11434", "http://172.18.0.4:11434",
            "http://[::1]:11434", "https://ollama.internal:11434", "http://llm-host.lan:11434"]
REMOTE = ["http://8.8.8.8:11434", "https://ollama.example.com", "http://llm.firma.pl:11434"]
BROKEN = ["ftp://ollama:11434", "ollama:11434", "file:///etc/passwd", "http://:11434"]


@pytest.mark.parametrize("url", INTERNAL)
def test_internal_hosts_accepted(monkeypatch, url):
    monkeypatch.setattr(settings, "ollama_url", url)
    assert llm.url_problem(url) is None
    assert llm.is_configured()


@pytest.mark.parametrize("url", REMOTE + BROKEN)
def test_remote_or_broken_url_disables_ai(monkeypatch, url):
    monkeypatch.setattr(settings, "ollama_url", url)
    monkeypatch.setattr(settings, "ocr_enabled", True)
    monkeypatch.setattr(settings, "ocr_vision_model", "qwen2.5vl:3b")
    assert llm.url_problem(url)
    assert not llm.is_configured()
    assert not ocr.vision_available()


def test_chat_refuses_remote_host_without_request(monkeypatch):
    monkeypatch.setattr(settings, "ollama_url", "http://8.8.8.8:11434")
    sent = []
    monkeypatch.setattr(llm.httpx, "post", lambda *a, **k: sent.append(a))
    with pytest.raises(llm.LLMUnavailable):
        llm.chat("qwen2.5:1.5b", "status MSKU7026499")
    assert sent == []


def test_allow_remote_is_explicit_opt_in(monkeypatch):
    monkeypatch.setattr(settings, "ollama_url", "https://ollama.example.com")
    monkeypatch.setattr(settings, "ollama_allow_remote", True)
    assert llm.url_problem(settings.ollama_url) is None and llm.is_configured()
    # zły schemat nie przechodzi nawet z opt-in
    assert llm.url_problem("ftp://ollama.example.com")


def test_validate_settings_warns_about_remote_ollama(monkeypatch, caplog):
    from app import main
    monkeypatch.setattr(settings, "ollama_url", "http://8.8.8.8:11434")
    with caplog.at_level(logging.WARNING, logger="app.main"):
        main.validate_settings()
    assert any("OLLAMA_URL" in r.getMessage() for r in caplog.records)


def test_validate_settings_quiet_for_docker_service(monkeypatch, caplog):
    from app import main
    monkeypatch.setattr(settings, "ollama_url", "http://ollama:11434")
    with caplog.at_level(logging.WARNING, logger="app.main"):
        main.validate_settings()
    assert not any("OLLAMA_URL" in r.getMessage() for r in caplog.records)


def test_validate_settings_warns_about_plain_http_remote_opt_in(monkeypatch, caplog):
    from app import main
    monkeypatch.setattr(settings, "ollama_url", "http://ollama.example.com:11434")
    monkeypatch.setattr(settings, "ollama_allow_remote", True)
    with caplog.at_level(logging.WARNING, logger="app.main"):
        main.validate_settings()
    assert any("bez szyfrowania" in r.getMessage() for r in caplog.records)
