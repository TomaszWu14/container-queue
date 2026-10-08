"""Lokalny LLM przez Ollamę (własny serwer) — żadne dane nie wychodzą do chmury.

Wspólny klient dla warstwy OCR (model obrazowy) i asystenta wiedzy (model tekstowy).
Pusty `OLLAMA_URL` = funkcje AI wyłączone. Ollama nie ma uwierzytelniania, a do modelu idą
skany faktur i fakty z systemu — dlatego adres musi być wewnętrzny (AI-006, `url_problem`).

Obserwowalność (audyt AI-004): każde wywołanie modelu trafia do dziennika serwera
(applog → job_runs, panel Administracja → Logi → Zadania, job „llm”) jako metryka BEZ
treści: cel:model, czas, sukces/błąd, rozmiary promptu i odpowiedzi, tokeny z Ollamy.
"""
import ipaddress
import logging
import threading
import time
from urllib.parse import urlsplit

import httpx

from .config import settings

logger = logging.getLogger(__name__)

BUSY_MSG = "Asystent jest zajęty — spróbuj za chwilę"
# audyt AI-002: Ollama na CPU i tak liczy po kolei — równoległe wywołania tylko trzymają
# wątki serwera i RAM. ponytail: limit per proces uvicorn; kilka workerów → kolejka zadań
_slots = threading.BoundedSemaphore(settings.llm_max_concurrency)


class LLMBusy(RuntimeError):
    """Wszystkie sloty LLM zajęte dłużej niż czas oczekiwania."""


class LLMUnavailable(RuntimeError):
    """OLLAMA_URL pusty albo odrzucony (`url_problem`) — nic nie wysyłamy."""


# nazwa usługi Dockera (bez kropki), localhost i domeny, które z definicji nie są publiczne
_INTERNAL_SUFFIXES = (".localhost", ".internal", ".local", ".lan", ".home.arpa")


def is_internal_host(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        name = host.lower().rstrip(".")
        return "." not in name or name.endswith(_INTERNAL_SUFFIXES)
    return ip.is_private or ip.is_loopback or ip.is_link_local


def url_problem(url: str) -> str | None:
    """Powód odrzucenia adresu Ollamy albo None. Bez DNS (deterministycznie): host spoza
    sieci Dockera/firmowej wymaga świadomego OLLAMA_ALLOW_REMOTE=true."""
    try:
        parts = urlsplit(url.strip())
        host, _port = parts.hostname, parts.port   # port: ValueError przy złym numerze
    except ValueError:
        return "nieprawidłowy adres"
    if parts.scheme not in ("http", "https") or not host:
        return "wymagany adres http(s)://host:port"
    if settings.ollama_allow_remote or is_internal_host(host):
        return None
    return (f"host {host} spoza sieci wewnętrznej — dane (skany faktur) opuściłyby serwer; "
            "użyj nazwy usługi Dockera / adresu prywatnego albo świadomie OLLAMA_ALLOW_REMOTE=true")


def is_configured() -> bool:
    return bool(settings.ollama_url) and url_problem(settings.ollama_url) is None


def _sizes(prompt: str, images: list[str] | None, answer: str | None, data: dict) -> str:
    """Opis wywołania bez treści: rozmiary i tokeny (prompt_eval_count/eval_count Ollamy)."""
    parts = [f"prompt {len(prompt)} zn."]
    if images:
        parts.append(f"obrazy {len(images)}")
    if answer is not None:
        parts.append(f"odp. {len(answer)} zn.")
    if "prompt_eval_count" in data or "eval_count" in data:
        parts.append(f"tokeny: we {data.get('prompt_eval_count', 0)}, wy {data.get('eval_count', 0)}")
    return ", ".join(parts)


def _error(exc: Exception) -> str:
    """Klasa błędu i kod HTTP — bez komunikatu (mógłby zawierać fragment odpowiedzi)."""
    if isinstance(exc, httpx.HTTPStatusError):
        return f"{type(exc).__name__} HTTP {exc.response.status_code}"
    return type(exc).__name__


def _record(name: str, started_at, start: float, ok: bool, detail: str) -> None:
    from . import applog   # ponytail: import w funkcji (applog ciągnie modele i bazę)
    duration_ms = int((time.perf_counter() - start) * 1000)
    logger.info("LLM %s: %s, %d ms — %s", name, "ok" if ok else "BŁĄD", duration_ms, detail)
    try:
        applog.record_job(job="llm", fn=name, started_at=started_at, duration_ms=duration_ms,
                          ok=ok, detail=detail)
    except Exception:  # noqa: BLE001 — metryka nie może zepsuć odpowiedzi modelu
        logger.exception("Zapis metryki LLM nie powiódł się")


def chat(model: str, prompt: str, *, system: str = "", images: list[str] | None = None,
         json_mode: bool = False, timeout: float | None = None, wait: float | None = None,
         purpose: str = "") -> str:
    """Jedna tura czatu → treść odpowiedzi. `images` = PNG w base64 (modele obrazowe).

    `timeout` — limit wywołania (domyślnie LLM_TIMEOUT_S), `wait` — ile czekać na wolny
    slot (domyślnie LLM_WAIT_S); potem `LLMBusy` zamiast wiszenia wątku w kolejce.
    `purpose` — etykieta w metryce (np. „assistant”, „ocr_vision”)."""
    from .models import utcnow
    if not is_configured():
        raise LLMUnavailable("Lokalny model AI nie jest skonfigurowany (OLLAMA_URL).")
    messages = [{"role": "system", "content": system}] if system else []
    user = {"role": "user", "content": prompt}
    if images:
        user["images"] = images
    messages.append(user)
    body = {"model": model, "messages": messages, "stream": False,
            # 4 GB RAM: model zwalniany po 5 min bezczynności, mały kontekst = mniej pamięci
            "keep_alive": "5m", "options": {"temperature": 0, "num_ctx": 4096}}
    if json_mode:
        body["format"] = "json"
    if not _slots.acquire(timeout=settings.llm_wait_s if wait is None else wait):
        raise LLMBusy(BUSY_MSG)   # odmowa przed wywołaniem — to nie jest wywołanie modelu
    name = f"{purpose or 'chat'}:{model}"[:120]
    started_at, start = utcnow(), time.perf_counter()
    try:
        try:
            resp = httpx.post(settings.ollama_url.rstrip("/") + "/api/chat", json=body,
                              timeout=settings.llm_timeout_s if timeout is None else timeout)
        finally:
            _slots.release()
        resp.raise_for_status()
        data = resp.json()
        answer = data.get("message", {}).get("content", "")
    except Exception as exc:
        _record(name, started_at, start, False, f"{_error(exc)}; {_sizes(prompt, images, None, {})}")
        raise
    _record(name, started_at, start, True, _sizes(prompt, images, answer, data))
    return answer
