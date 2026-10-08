"""Powiadomienia: in-app (baza) + e-mail (SMTP) + Teams/Slack (webhook) + n8n.

Kanały zewnętrzne są opcjonalne — włączają się po skonfigurowaniu SMTP_HOST /
TEAMS_WEBHOOK_URL / AUTOMATION_WEBHOOK_URL i nigdy nie blokują operacji (błędy tylko do logów).
"""
import atexit
import datetime
import hashlib
import hmac
import json
import logging
import smtplib
from concurrent.futures import ThreadPoolExecutor
from email import encoders
from email.message import Message as MIMEMessage
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx
from sqlalchemy import delete, event, select
from sqlalchemy.orm import Session

from . import teams
from .config import settings
from .models import (
    Container,
    Notification,
    NotificationRule,
    Role,
    User,
    WatchedContainer,
    utcnow,
)

logger = logging.getLogger(__name__)

# Znane typy zdarzeń (wiersze matrycy reguł w Administracji). Nowy kind w kodzie
# dopisz też tutaj — inaczej nie da się go wyłączyć w matrycy.
NOTIFY_KINDS = [
    "avizo", "carrier", "complaint", "complaint_deadline", "complaint_draft",
    "complaint_reminder", "customs", "customs-delay", "daily_digest", "demurrage",
    "dest_port", "docs-missing", "driver", "eta", "eta_drift", "eta_overdue",
    "excel-sync", "file", "forecast-overload", "freight_approval", "freight_decision", "gate", "dlt", "mention", "message",
    "order", "pallet_urgent", "planned", "port_congestion", "status", "system",
    # "system-error" (applog.py, dziennik serwera): admini, TYLKO dzwonek — pisany
    # bezpośrednio jako wiersz Notification (bez notify()), więc reguły e-mail/Teams
    # z matrycy i tak nic by nie wysłały; reguła admin×dzwonek wyłącza alert (applog._alert).
    "system-error",
    "tracking", "tracking_error", "vessel", "vessel_port", "vessel_stuck",
    "weekly_digest",
]
NOTIFY_CHANNELS = ("bell", "email", "teams")


def kind_rules(db: Session, kind: str) -> dict[tuple[str, str], bool]:
    """Reguły matrycy dla jednego kindu: {(rola|'*', kanał): enabled}."""
    return {(r.role, r.channel): r.enabled for r in db.scalars(
        select(NotificationRule).where(NotificationRule.kind == kind))}

# Wysyłka kanałami zewnętrznymi (SMTP/Teams) POZA ścieżką żądania. Handlery FastAPI są
# synchroniczne (threadpool Starlette), a SMTP+Teams wołane inline potrafią zablokować
# odpowiedź nawet do ~30s (wolny/niedostępny serwer). Tu tylko I/O sieciowe — bez sesji
# DB (rekordy Notification zapisuje synchronicznie `notify`), więc offload jest bezpieczny.
# Best-effort: wyjątki tylko do logów, nigdy nie wracają do żądania.
_dispatch = ThreadPoolExecutor(max_workers=4, thread_name_prefix="notify")
atexit.register(_dispatch.shutdown, wait=False)


def _run(fn, *args, **kwargs) -> None:
    try:
        fn(*args, **kwargs)
    except Exception:  # noqa: BLE001 — kanał nie może wywrócić operacji
        logger.exception("Wysyłka w tle nie powiodła się: %s", getattr(fn, "__name__", fn))


def _submit(fn, *args, **kwargs) -> None:
    """Zleca wysyłkę do puli w tle. Gdy pula zamknięta (shutdown przy zamykaniu procesu),
    wykonuje synchronicznie — pojedyncze zdarzenie nie może zginąć po cichu."""
    try:
        _dispatch.submit(_run, fn, *args, **kwargs)
    except RuntimeError:
        _run(fn, *args, **kwargs)


# Kanały zewnętrzne z notify() dopiero PO commicie sesji: mail/Teams/n8n o czymś, czego
# commit nie zapisał (błąd DB, wyjątek dalej w żądaniu), to fałszywy alarm — a w zadaniach
# w tle wycofany wiersz Notification (dedup) oznaczał ponowną wysyłkę w kolejnym cyklu.
_PENDING = "notify_pending"


def _after_commit(db: Session, fn, *args) -> None:
    db.info.setdefault(_PENDING, []).append((fn, args))


@event.listens_for(Session, "after_commit")
def _dispatch_pending(session: Session) -> None:
    for fn, args in session.info.pop(_PENDING, []):
        _run(fn, *args)


@event.listens_for(Session, "after_transaction_end")
def _drop_pending(session: Session, transaction) -> None:
    # koniec transakcji głównej bez commita (rollback/close) — wysyłki przepadają razem
    # z wierszami Notification; po commicie lista jest już pusta (after_commit był pierwszy)
    if transaction.parent is None:
        session.info.pop(_PENDING, None)


def _smtp_conf(channel: str) -> tuple[str, int, str, str, str]:
    """Konfiguracja SMTP dla kanału: 'invite' (skrzynka example.com) lub 'main' (Resend).
    Kanał 'invite' bez ustawionego hosta spada na główny SMTP (nic się nie psuje)."""
    if channel == "invite" and settings.invite_smtp_host:
        return (settings.invite_smtp_host, settings.invite_smtp_port,
                settings.invite_smtp_user, settings.invite_smtp_password,
                settings.invite_smtp_from or settings.invite_smtp_user)
    return (settings.smtp_host, settings.smtp_port, settings.smtp_user,
            settings.smtp_password, settings.smtp_from)


def _smtp_send(message: MIMEMessage, recipients: list[str], timeout: int,
               channel: str = "main") -> None:
    """Połączenie SMTP + STARTTLS + opcjonalny login + wysyłka dla wybranego kanału."""
    host, port, user, password, sender = _smtp_conf(channel)
    with smtplib.SMTP(host, port, timeout=timeout) as smtp:
        try:
            smtp.starttls()
        except smtplib.SMTPNotSupportedError:
            pass  # lokalny serwer testowy bez TLS
        if user:
            smtp.login(user, password)
        smtp.sendmail(sender, recipients, message.as_string())


def _send_email(recipients: list[str], title: str, body: str) -> None:
    if not settings.smtp_host or not recipients:
        return
    message = MIMEText(body, "plain", "utf-8")
    message["Subject"] = f"[TIMPORYE] {title}"
    message["From"] = settings.smtp_from
    # odbiorcy w Bcc — nie ujawniamy adresów pracowników sobie nawzajem
    message["To"] = settings.smtp_from
    # wysyłka w tle — nie blokuje żądania; błędy trafiają do logów w _run
    _submit(_smtp_send, message, recipients, timeout=15)


def send_html_email(recipients: list[str], subject: str, html: str,
                    reply_to: str = "", channel: str = "main",
                    attachments: list[tuple[str, bytes, str]] | None = None) -> None:
    """Wysyłka wiadomości HTML (np. kolejka dnia do spedycji) przez wybrany kanał SMTP.
    channel='invite' → skrzynka example.com (jeśli skonfigurowana), inaczej główny SMTP."""
    host, _, _, _, sender = _smtp_conf(channel)
    if not host:
        raise RuntimeError("SMTP nie jest skonfigurowany (SMTP_HOST).")
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = sender
    # adresaci tylko w kopercie SMTP (nie w nagłówku To) — nie ujawniamy listy odbiorców
    message["To"] = sender
    if reply_to:
        message["Reply-To"] = reply_to
    message.attach(MIMEText(html, "html", "utf-8"))
    for filename, content, mime in (attachments or []):
        maintype, _, subtype = mime.partition("/")
        part = MIMEBase(maintype, subtype)
        part.set_payload(content)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=filename)
        message.attach(part)
    # walidacja (SMTP skonfigurowany?) już się wykonała synchronicznie powyżej, więc
    # wywołujący nadal dostaje natychmiastowy błąd konfiguracji; samą wysyłkę robimy w tle
    _submit(_smtp_send, message, recipients, timeout=20, channel=channel)


def send_password_reset(email: str, full_name: str, link: str, minutes: int) -> None:
    """Wysyła link resetu hasła. Podnosi wyjątek, gdy SMTP nieskonfigurowany —
    wywołujący łapie go (best-effort), by endpoint nie zdradzał istnienia konta."""
    from .mail_html import esc
    name = esc(full_name or "")
    subject = "Reset hasła / Password reset — Kolejka (TIMPORYE)"
    html = f"""
      <div style="font-family:Segoe UI,Arial,sans-serif;color:#1c2733;max-width:520px">
        <h2 style="color:#10263f">Reset hasła / Password reset</h2>
        <p>Cześć {name}, / Hi {name},</p>
        <p><b>PL:</b> Otrzymaliśmy prośbę o zresetowanie hasła do Twojego konta w aplikacji
           <b>Kolejka</b>. Kliknij poniższy przycisk, aby ustawić nowe hasło.</p>
        <p><b>EN:</b> We received a request to reset the password for your <b>Kolejka</b>
           account. Click the button below to set a new password.</p>
        <p style="margin:22px 0">
          <a href="{esc(link)}" style="background:#0b5fff;color:#fff;text-decoration:none;
             padding:12px 22px;border-radius:8px;font-weight:600;display:inline-block">
             Ustaw nowe hasło / Set new password</a>
        </p>
        <p style="color:#64748b;font-size:0.9em">Link jest ważny przez {minutes} min i można go
           użyć tylko raz. Jeśli to nie Ty — zignoruj tę wiadomość.<br>
           The link is valid for {minutes} min and can be used only once. If this wasn't you,
           ignore this message.</p>
      </div>"""
    send_html_email([email], subject, html)


def send_user_invite(email: str, full_name: str, login: str,
                     temp_password: str, base_url: str) -> None:
    """Zaproszenie nowego użytkownika: login + hasło tymczasowe (jednorazowe) +
    prośba o zalogowanie i ustawienie własnego hasła. Podnosi wyjątek, gdy SMTP
    nieskonfigurowany — wywołujący łapie go (best-effort)."""
    from .mail_html import esc
    name = esc(full_name or "")
    link = f"{base_url.rstrip('/')}/" if base_url else ""
    button = f"""
        <p style="margin:22px 0">
          <a href="{esc(link)}" style="background:#0b5fff;color:#fff;text-decoration:none;
             padding:12px 22px;border-radius:8px;font-weight:600;display:inline-block">
             Zaloguj się / Log in</a>
        </p>""" if link else ""
    subject = "Zaproszenie do aplikacji Kolejka (TIMPORYE) / Invitation"
    html = f"""
      <div style="font-family:Segoe UI,Arial,sans-serif;color:#1c2733;max-width:520px">
        <h2 style="color:#10263f">Witaj w aplikacji Kolejka / Welcome to Kolejka</h2>
        <p>Cześć {name}, / Hi {name},</p>
        <p><b>PL:</b> Założono dla Ciebie konto w aplikacji <b>Kolejka</b>. Zaloguj się
           poniższymi danymi, a przy pierwszym logowaniu ustawisz własne hasło.</p>
        <p><b>EN:</b> An account was created for you in <b>Kolejka</b>. Log in with the
           credentials below; you will set your own password on first login.</p>
        <table style="margin:14px 0;border-collapse:collapse">
          <tr><td style="padding:4px 10px;color:#64748b">Login</td>
              <td style="padding:4px 10px"><b>{esc(login)}</b></td></tr>
          <tr><td style="padding:4px 10px;color:#64748b">Hasło tymczasowe / Temp password</td>
              <td style="padding:4px 10px"><b>{esc(temp_password)}</b></td></tr>
        </table>{button}
        <p style="color:#64748b;font-size:0.9em">Hasło tymczasowe działa tylko do pierwszej
           zmiany. / The temporary password works only until you change it.</p>
      </div>"""
    # zaproszenia idą osobnym kanałem (skrzynka example.com), nie przez Resend
    send_html_email([email], subject, html, channel="invite")


def _teams_post(url: str, title: str, body: str) -> None:
    # Adaptive Card (Workflows + stary webhook); wynik trafia do panelu Integracje
    teams.post(url, title, body)


def _send_teams(title: str, body: str) -> None:
    if not settings.teams_webhook_url:
        return
    # wysyłka w tle — nie blokuje żądania; błędy trafiają do logów w _run
    _submit(_teams_post, settings.teams_webhook_url, title, body)


def sign_payload(body: bytes, secret: str) -> str:
    """Podpis treści webhooka (HMAC-SHA256, format jak w GitHubie) — n8n weryfikuje go
    przed wykonaniem workflow, żeby triggera nie odpalił ktokolwiek znający adres."""
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _n8n_post(url: str, payload: dict) -> None:
    # serializujemy raz i wysyłamy dokładnie te bajty, które podpisaliśmy — inaczej
    # podpis nie zgadzałby się po stronie n8n (separatory/kolejność kluczy)
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    headers = {"Content-Type": "application/json"}
    if settings.automation_webhook_secret:
        headers["X-Timporye-Signature"] = sign_payload(body, settings.automation_webhook_secret)
    httpx.post(url, content=body, headers=headers, timeout=15)


def send_automation_event(kind: str, title: str, body: str = "", **fields) -> None:
    """Zdarzenie do n8n (trigger workflow). Puste AUTOMATION_WEBHOOK_URL = kanał wyłączony.

    Best-effort jak pozostałe kanały: wysyłka w tle, błędy tylko do logów — padnięty
    n8n nie może wywrócić operacji w panelu.
    """
    if not settings.automation_webhook_url:
        return
    payload = {"event": kind, "title": title, "body": body,
               "sent_at": utcnow().isoformat(), **fields}
    _submit(_n8n_post, settings.automation_webhook_url, payload)


def notify(db: Session, users: list[User], *, kind: str, title: str, body: str = "",
           container_id: int | None = None, exclude_user_id: int | None = None,
           ignore_watch_only: bool = False, broadcast: bool = True) -> int:
    """Tworzy powiadomienia in-app i wysyła kanały zewnętrzne (po commicie sesji, rollback
    = brak wysyłki). Zwraca liczbę odbiorców.

    Respektuje matrycę reguł (NotificationRule): brak wiersza = kanał włączony.
    Dzwonek wyłączony, e-mail włączony → rekord Notification powstaje jako
    przeczytany (bez badge'a), żeby deduplikacja alertów dziennych nie pękła.
    ignore_watch_only=True (np. @wzmianka) pomija filtr „tylko obserwowane".
    broadcast=False: bez Teams/n8n (wariant per user tego samego zdarzenia — kanał wspólny raz)."""
    rules = kind_rules(db, kind)

    def enabled(role: str, channel: str) -> bool:
        return rules.get((role, channel), True)

    recipients = [u for u in users
                  if u.is_active and u.id != exclude_user_id]
    # tryb "tylko obserwowane": user z flagą dostaje powiadomienie o kontenerze
    # tylko jeśli go obserwuje (gwiazdka); powiadomienia bez container_id (np. digest)
    # przechodzą zawsze.
    if ignore_watch_only:
        pass
    elif container_id is not None and any(u.watch_only_notifications for u in recipients):
        watcher_ids = {u.id for u in recipients if u.watch_only_notifications}
        watching = set(db.scalars(select(WatchedContainer.user_id).where(
            WatchedContainer.container_id == container_id,
            WatchedContainer.user_id.in_(watcher_ids))))
        recipients = [u for u in recipients
                      if not u.watch_only_notifications or u.id in watching]
    seen: set[int] = set()
    emails: list[str] = []
    count = 0
    for user in recipients:
        if user.id in seen:
            continue
        seen.add(user.id)
        bell = enabled(user.role.value, "bell")
        mail = bool(user.email) and enabled(user.role.value, "email")
        if not bell and not mail:
            continue  # oba kanały wyłączone dla tej roli — pomijamy odbiorcę
        db.add(Notification(user_id=user.id, kind=kind, title=title, body=body,
                            container_id=container_id, is_read=not bell))
        if mail:
            emails.append(user.email)
        count += 1
    if count:
        _after_commit(db, lambda: _send_email(emails, title, body))
    if count and broadcast:
        if enabled("*", "teams"):
            _after_commit(db, lambda: _send_teams(title, body))
        _after_commit(db, lambda: send_automation_event(
            kind, title, body, container_id=container_id, recipients=count))
    return count


def company_watchers(db: Session, company_id: int) -> list[User]:
    """Logistyka spółki + konta widzące wszystko + admini (admin widzi wszystko z definicji)."""
    return list(db.scalars(select(User).where(
        User.is_active,
        ((User.company_id == company_id) & (User.role == Role.logistics))
        | (User.role == Role.admin)
        | (User.view_all_companies & (User.role == Role.logistics)))))


def acme_team(db: Session) -> list[User]:
    """Centralny team Acme (transport): logistyka spółki ACME + admini.

    Acme obsługuje transport wszystkich spółek, więc musi dostać powiadomienie
    o każdym nowym zleceniu — także tych z view_all=False."""
    from .models import Company
    acme = db.scalar(select(Company).where(Company.code == "ACME"))
    if not acme:
        return []
    return list(db.scalars(select(User).where(
        User.is_active, User.company_id == acme.id,
        User.role.in_((Role.logistics, Role.admin)))))


def new_order_watchers(db: Session, company_id: int) -> list[User]:
    """Odbiorcy powiadomienia o nowym zleceniu: wyłącznie centralny team Acme
    (transport) oraz systemowi admini — bez teamu spółki zakładającej."""
    watchers = {u.id: u for u in acme_team(db)}
    for u in db.scalars(select(User).where(
            User.is_active, User.view_all_companies, User.role == Role.admin)):
        watchers[u.id] = u
    return list(watchers.values())


def purchasing_users(db: Session, company_id: int) -> list[User]:
    """Dział zakupów spółki — odbiorcy alertu o rozjeździe faktura↔zamówienie."""
    return list(db.scalars(select(User).where(
        User.is_active, User.role == Role.purchasing,
        (User.company_id == company_id) | User.view_all_companies)))


def forwarder_users(db: Session, forwarder_id: int | None) -> list[User]:
    if not forwarder_id:
        return []
    return list(db.scalars(select(User).where(
        User.is_active, User.role == Role.forwarder,
        User.forwarder_id == forwarder_id)))


def customs_agency_users(db: Session, customs_agency_id: int | None) -> list[User]:
    if not customs_agency_id:
        return []
    return list(db.scalars(select(User).where(
        User.is_active, User.role == Role.customs,
        User.customs_agency_id == customs_agency_id)))


def container_watchers(db: Session, container: Container) -> list[User]:
    return company_watchers(db, container.company_id) \
        + forwarder_users(db, container.forwarder_id) \
        + customs_agency_users(db, container.customs_agency_id)


def notify_aboard(db: Session, aboard: list[Container], *, kind: str, render,
                  since: datetime.datetime | None = None,
                  unique_title: bool = False) -> int:
    """Alert „per statek" rozdzielony wg zakresu odbiorców (izolacja spółek).

    Każdy użytkownik dostaje listę WYŁĄCZNIE kontenerów, których jest obserwatorem
    (container_watchers: spółka / spedytor / agencja) — bez numerów innych spółek,
    a obserwatorzy każdej spółki na pokładzie dostają swój alert. Odbiorcy z tym
    samym zbiorem widocznych kontenerów dostają jedno wspólne powiadomienie.

    render(grupa) -> (tytuł, treść) albo None (pomiń grupę, np. dryf poniżej progu).
    Dedup per użytkownik: since → miał już dziś `kind` dla któregoś ze swoich
    kontenerów; unique_title → miał już `kind` o tym samym tytule."""
    visible: dict[int, tuple[User, list[Container]]] = {}
    for c in sorted(aboard, key=lambda c: c.id):   # stała kotwica = najmniejsze id
        for user in container_watchers(db, c):
            seen = visible.setdefault(user.id, (user, []))[1]
            if not seen or seen[-1].id != c.id:
                seen.append(c)
    groups: dict[tuple[int, ...], tuple[list[Container], list[User]]] = {}
    for user, containers in visible.values():
        key = tuple(c.id for c in containers)
        groups.setdefault(key, (containers, []))[1].append(user)
    sent = 0
    for ids, (containers, users) in groups.items():
        rendered = render(containers)
        if rendered is None:
            continue
        title, body = rendered
        if since is not None or unique_title:
            query = select(Notification.user_id).where(
                Notification.kind == kind,
                Notification.user_id.in_([u.id for u in users]))
            if since is not None:
                query = query.where(Notification.container_id.in_(ids),
                                    Notification.created_at >= since)
            if unique_title:
                query = query.where(Notification.title == title)
            done = set(db.scalars(query))
            users = [u for u in users if u.id not in done]
        if users:
            sent += notify(db, users, kind=kind, title=title, body=body,
                           container_id=ids[0])
    return sent


def warehouse_users(db: Session, company_id: int,
                    warehouse_id: int | None = None) -> list[User]:
    """Magazynierzy spółki; jeśli podano magazyn — TYLKO przypisani do niego.

    Konta magazynu bez przypisanego magazynu i tak nie mają dostępu do kontenerów
    (fail-closed w scope_containers), więc nie powiadamiamy ich o dostawach."""
    query = select(User).where(
        User.is_active, User.role == Role.warehouse, User.company_id == company_id)
    users = list(db.scalars(query))
    if warehouse_id is not None:
        users = [u for u in users if u.warehouse_id == warehouse_id]
    return users


def purge_read_notifications(db: Session) -> int:
    """OBS-011: przeczytane powiadomienia starsze niż NOTIFICATION_RETENTION_DAYS.
    Nieprzeczytane zostają bez względu na wiek (user jeszcze ich nie widział)."""
    cutoff = utcnow() - datetime.timedelta(days=settings.notification_retention_days)
    n = db.execute(delete(Notification).where(
        Notification.is_read.is_(True), Notification.created_at < cutoff)).rowcount or 0
    db.commit()
    return n


# Alerty (checki z jobs.py) żyją w osobnych modułach; re-eksport na końcu pliku, bo te
# moduły importują rdzeń stąd (notify/*_watchers) — publiczne ścieżki bez zmian.
from .notification_alerts import (  # noqa: E402,F401
    _arrival_map,
    check_customs_alerts,
    check_demurrage_alerts,
    check_docs_alerts,
    check_tracking_alerts,
    demurrage_deadline,
    demurrage_deadlines,
    demurrage_window,
)
from .notification_digests import (  # noqa: E402,F401
    _dlt_low_stock_lines,
    check_daily_digest_alerts,
    check_forecast_alerts,
    check_pallet_urgent_alerts,
    check_stale_import_alerts,
    check_weekly_digest_alerts,
)
