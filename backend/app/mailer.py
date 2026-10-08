"""Wysyłka maili awizacji: Microsoft Graph (M365) / SMTP / konsola.

Wszystkie implementacje są SYNCHRONICZNE i rzucają wyjątek przy błędzie — wynik
trafia do AvizoMailLog (avizo_workflow), więc błąd dostawy nie ginie w logach.
Wybór: MAIL_BACKEND=graph|smtp|console (puste → smtp przy SMTP_HOST, inaczej console).
"""
import datetime
import logging
import time
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Protocol

import httpx
from sqlalchemy import select

from .config import settings

logger = logging.getLogger(__name__)

GRAPH_SCOPE = ["https://graph.microsoft.com/.default"]
RETRY_DELAYS = (1, 4, 16)   # s między próbami → 4 próby łącznie
_sleep = time.sleep          # podmieniane w testach


@dataclass
class Mail:
    to: list[str]
    subject: str
    html: str
    text: str
    cc: list[str] = field(default_factory=list)
    reply_to: str = ""


class MailSender(Protocol):
    name: str

    def send(self, mail: Mail) -> None: ...


CONSOLE_BODY_ENVS = ("dev", "development", "test", "local")


class ConsoleMailSender:
    """Dev/testy/brak konfiguracji: log zamiast wysyłki; `outbox` do asercji w testach."""
    name = "console"

    def __init__(self) -> None:
        self.outbox: list[Mail] = []

    def send(self, mail: Mail) -> None:
        if settings.environment.lower() in ("production", "prod"):
            # produkcja bez poczty = twardy błąd (log maili „failed”), nie ciche „sent”
            raise RuntimeError("Poczta nie jest skonfigurowana (MAIL_BACKEND / SMTP_HOST) — "
                               "mail NIE został wysłany.")
        self.outbox.append(mail)
        if settings.environment.lower() in CONSOLE_BODY_ENVS:
            # dev/E2E: link z maila na stdout (poza logowaniem — filtr maskuje tam tokeny)
            print(f"--- MAIL (console) → {', '.join(mail.to)}: {mail.subject}\n{mail.text}")
        # poza dev/test (np. staging po HTTP) treść z linkami-tokenami i adresy NIE mogą trafić
        # do logów Dockera (audyt OBS-004) — tylko temat i liczba adresatów
        logger.warning("MAIL_BACKEND=console — mail NIE wysłany: %s (adresatów: %d)",
                       mail.subject, len(mail.to))


class SmtpMailSender:
    name = "smtp"

    def send(self, mail: Mail) -> None:
        from .notifications import _smtp_send   # synchronicznie — chcemy znać wynik
        message = MIMEMultipart("alternative")
        message["Subject"] = mail.subject
        message["From"] = settings.smtp_from
        message["To"] = ", ".join(mail.to)
        if mail.cc:
            message["Cc"] = ", ".join(mail.cc)
        if mail.reply_to:
            message["Reply-To"] = mail.reply_to
        message.attach(MIMEText(mail.text, "plain", "utf-8"))
        message.attach(MIMEText(mail.html, "html", "utf-8"))
        _smtp_send(message, mail.to + mail.cc, timeout=20)


_graph_app = None   # ConfidentialClientApplication — trzyma cache tokenu między wysyłkami


def graph_app(tenant_id: str, client_id: str, client_secret: str):
    """Aplikacja MSAL (client credentials); trzymaj instancję — ma cache tokenu."""
    import msal
    return msal.ConfidentialClientApplication(
        client_id, authority=f"https://login.microsoftonline.com/{tenant_id}",
        client_credential=client_secret)


def graph_token(app) -> str:
    """Token Graph (app-only) — wspólne dla maili i SharePointa. Sekret nie trafia do błędu."""
    result = app.acquire_token_for_client(scopes=GRAPH_SCOPE)
    if "access_token" not in result:
        raise RuntimeError(f"Graph: brak tokenu ({result.get('error')}: "
                           f"{result.get('error_description', '')[:200]})")
    return result["access_token"]


def graph_configured() -> bool:
    s = settings
    return all(v.strip() for v in (s.ms_tenant_id, s.ms_client_id, s.ms_client_secret,
                                    s.mail_sender))


class GraphMailSender:
    """POST /users/{MAIL_SENDER}/sendMail z tokenem aplikacji (client credentials).
    Uprawnienie Mail.Send (Application) ograniczone Application Access Policy do jednej skrzynki."""
    name = "graph"

    def _token(self) -> str:
        global _graph_app
        if _graph_app is None:
            _graph_app = graph_app(settings.ms_tenant_id, settings.ms_client_id,
                                   settings.ms_client_secret)
        return graph_token(_graph_app)

    def send(self, mail: Mail) -> None:
        if not graph_configured():
            raise RuntimeError("Graph nie jest skonfigurowany (MS_TENANT_ID, MS_CLIENT_ID, "
                               "MS_CLIENT_SECRET, MAIL_SENDER).")
        message = {
            "subject": mail.subject,
            "body": {"contentType": "HTML", "content": mail.html},
            "toRecipients": [{"emailAddress": {"address": a}} for a in mail.to],
            "ccRecipients": [{"emailAddress": {"address": a}} for a in mail.cc],
        }
        if mail.reply_to:
            message["replyTo"] = [{"emailAddress": {"address": mail.reply_to}}]
        response = httpx.post(
            f"https://graph.microsoft.com/v1.0/users/{settings.mail_sender}/sendMail",
            headers={"Authorization": f"Bearer {self._token()}"},
            json={"message": message, "saveToSentItems": True}, timeout=30)
        if response.status_code != 202:
            raise RuntimeError(f"Graph sendMail HTTP {response.status_code}: {response.text[:300]}")


_console = ConsoleMailSender()   # jedna instancja — outbox przeżywa między wywołaniami


def backend_name() -> str:
    return (settings.mail_backend or ("smtp" if settings.smtp_host else "console")).lower()


def status_detail(db) -> tuple[bool, str, datetime.datetime | None]:
    """Panel Integracje: (gotowe?, opis, czas ostatniej wysyłki) dla maili awizacji.
    Graph bez kompletu MS_* / MAIL_SENDER = wyłączone — tak samo jak przy wysyłce."""
    from .models import AvizoMailLog
    name = backend_name()
    if name == "graph":
        ready = graph_configured()
        detail = f"graph · {settings.mail_sender}" if ready else \
            "graph · brak MS_TENANT_ID/MS_CLIENT_ID/MS_CLIENT_SECRET/MAIL_SENDER"
    else:
        ready = name == "smtp" and bool(settings.smtp_host.strip())
        detail = f"{name} (bez M365)"
    try:
        last = db.scalars(select(AvizoMailLog).order_by(AvizoMailLog.id.desc()).limit(1)).first()
    except Exception:  # noqa: BLE001 — panel diagnostyczny nie może paść na braku tabeli
        logger.warning("status maili awizacji: odczyt ostatniej wysyłki padł", exc_info=True)
        db.rollback()
        last = None
    if last is None:
        return ready, detail, None
    result = f"błąd: {last.error[:200]}" if last.status == "failed" else "ok"
    return ready, f"{detail} · ostatnia: {last.backend} {result}", last.sent_at


def get_sender() -> MailSender:
    name = backend_name()
    if name == "graph":
        return GraphMailSender()
    if name == "smtp":
        return SmtpMailSender()
    return _console


def send_with_retry(sender: MailSender, mail: Mail) -> tuple[int, str]:
    """Zwraca (liczba prób, błąd | ""). Nie rzuca — wynik idzie do logu maili."""
    error = ""
    for attempt in range(1, len(RETRY_DELAYS) + 2):
        try:
            sender.send(mail)
            return attempt, ""
        except Exception as exc:  # noqa: BLE001 — każdy błąd dostawy ponawiamy
            error = f"{type(exc).__name__}: {exc}"[:1000]
            logger.warning("Wysyłka maila awizacji, próba %s nieudana: %s", attempt, error)
            if attempt <= len(RETRY_DELAYS):
                _sleep(RETRY_DELAYS[attempt - 1])
    return len(RETRY_DELAYS) + 1, error
