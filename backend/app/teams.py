"""MS Teams: wysyłka karty na webhook kanału + ostatni wynik dla panelu Integracje.

Microsoft wycofuje stare Incoming Webhooki (Office 365 Connectors) na rzecz Workflows
(„Post to a channel when a webhook request is received”). Workflows przyjmują tylko
Adaptive Card w kopercie `message/attachments` — ten sam format obsługują też stare
webhooki, więc jedna karta działa w obu. Błąd HTTP rzuca wyjątek (log w notifications._run)
i trafia do `status_detail()`, żeby nieudana wysyłka nie była cicha.
"""
import datetime
import threading

import httpx

LEGACY_HOST = "webhook.office.com"   # Office 365 Connector — do migracji na Workflows

_lock = threading.Lock()
# ostatni wynik w tym procesie (bez tabeli — diagnostyka, nie audyt)
_last: dict = {"at": None, "error": ""}


def card(title: str, body: str) -> dict:
    return {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.4",
                "msteams": {"width": "Full"},
                "body": [
                    {"type": "TextBlock", "text": f"[TIMPORYE] {title}",
                     "weight": "Bolder", "size": "Medium", "wrap": True},
                    {"type": "TextBlock", "text": body or title, "wrap": True},
                ],
            },
        }],
    }


def _record(error: str) -> None:
    with _lock:
        _last["at"] = datetime.datetime.now(datetime.UTC)
        _last["error"] = error


def post(url: str, title: str, body: str) -> None:
    try:
        response = httpx.post(url, json=card(title, body), timeout=15)
        response.raise_for_status()
        # stary webhook odpowiada 200 z treścią „1”; inna treść przy 200 = odrzucona karta
        if LEGACY_HOST in url and response.text.strip() not in ("", "1"):
            raise RuntimeError(f"Teams odrzucił kartę: {response.text[:200]}")
    except Exception as exc:
        _record(f"{type(exc).__name__}: {exc}"[:300])
        raise
    _record("")


def status_detail(url: str) -> tuple[str, datetime.datetime | None]:
    """Opis do panelu Integracje: rodzaj webhooka + wynik ostatniej wysyłki."""
    kind = "webhook (stary connector — przejdź na Workflows)" if LEGACY_HOST in url \
        else "Workflows webhook"
    with _lock:
        at, error = _last["at"], _last["error"]
    if at is None:
        return f"{kind} · brak wysyłek od startu", None
    return (f"{kind} · błąd: {error}" if error else f"{kind} · ok"), at
