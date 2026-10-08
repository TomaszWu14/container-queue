"""Alerty zbiorcze i digesty: prognoza przeładowania magazynu, pilne palety DLT,
poranny digest logistyki, tygodniowy digest zakupów, stęchłe importy master data.

Importuj przez app.notifications (re-eksport) — moduł sam importuje rdzeń z
app.notifications, więc wejście prosto tutaj zamknęłoby cykl importu."""
from .models import PL_TZ, pl_midnight_utc, today_pl
import datetime
import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .app_settings import get_setting
from .config import settings
from .models import (
    Container,
    DocumentStatus,
    Notification,
    Role,
    User,
    WatchedContainer,
    utcnow,
)
from .notifications import company_watchers, notify, acme_team

logger = logging.getLogger(__name__)


def check_forecast_alerts(db: Session, today: datetime.date | None = None) -> int:
    """Alert o przewidywanym przekroczeniu limitu rozładunków magazynu.

    Okno: N dni w przód (`forecast_alert_days`, domyślnie 7). Liczba aktywnych
    kontenerów z notify_date w danym dniu > limit (nadpisanie DailyLimit albo
    default magazynu) → dzwonek do obserwatorów spółki właściciela magazynu.
    Reguła jak w kolejce: limit łącznie dla wszystkich spółek, bez tranzytów
    (is_transit nie liczy się do limitu). Dedup raz dziennie per magazyn+data
    (po tytule w dzisiejszych powiadomieniach)."""
    from .models import DailyLimit, Warehouse
    today = today or today_pl()
    try:
        days = int(get_setting(db, "forecast_alert_days") or 7)
    except ValueError:
        days = 7
    horizon = today + datetime.timedelta(days=days)
    rows = db.execute(
        select(Container.warehouse_id, Container.notify_date, func.count(Container.id))
        .where(Container.status.not_in(Container.FINISHED),
               Container.is_transit.is_(False),
               Container.warehouse_id.is_not(None),
               Container.notify_date.is_not(None),
               Container.notify_date >= today, Container.notify_date <= horizon)
        .group_by(Container.warehouse_id, Container.notify_date)).all()
    if not rows:
        return 0
    warehouse_ids = {wid for wid, _, _ in rows}
    warehouses = {w.id: w for w in db.scalars(
        select(Warehouse).where(Warehouse.id.in_(warehouse_ids)))}
    overrides = {(wid, day): limit for wid, day, limit in db.execute(
        select(DailyLimit.warehouse_id, DailyLimit.day, DailyLimit.limit)
        .where(DailyLimit.warehouse_id.in_(warehouse_ids),
               DailyLimit.day >= today, DailyLimit.day <= horizon)).all()}
    sent = 0
    for wid, day, count in rows:
        warehouse = warehouses.get(wid)
        if not warehouse:
            continue
        limit = overrides.get((wid, day), warehouse.default_daily_limit)
        if limit is None or count <= limit:
            continue
        title = (f"Prognoza: {warehouse.name} {day} — {count} rozładunków "
                 f"przy limicie {limit}")
        already = db.scalar(select(Notification).where(
            Notification.kind == "forecast-overload",
            Notification.title == title,
            Notification.created_at >= pl_midnight_utc(today)))
        if already:
            continue
        sent += notify(db, company_watchers(db, warehouse.company_id),
                       kind="forecast-overload", title=title)
    db.commit()
    return sent


def check_pallet_urgent_alerts(db: "Session") -> int:
    """Powiadamia zespół Acme o produktach oznaczonych 'pilne' w analizie wywołań.
    Cichnie, gdy Power BI nieskonfigurowane. Zwraca liczbę odbiorców (0 = brak alertu)."""
    from .pallets_cache import get_analysis
    from .powerbi import is_configured
    if not is_configured():
        return 0
    try:
        items, _, _, _ = get_analysis(db)
    except Exception:  # noqa: BLE001
        logger.exception("Alert palet: nie udało się pobrać analizy wywołań")
        return 0
    urgent = [i for i in items if i.get("pilne")]
    if not urgent:
        return 0
    # dedup: pierwszy przebieg idzie zaraz po starcie — bez tego każdy redeploy = nowa paczka
    window = datetime.timedelta(hours=settings.pallet_alert_interval_hours)
    if db.scalar(select(Notification.id).where(
            Notification.kind == "pallet_urgent",
            Notification.created_at >= utcnow() - window).limit(1)):
        return 0
    produkty = ", ".join(i["produkt"] for i in urgent[:20])
    if len(urgent) > 20:
        produkty += f" (+{len(urgent) - 20})"
    return notify(db, acme_team(db), kind="pallet_urgent",
                  title=f"Palety do pilnego wywołania: {len(urgent)}", body=produkty)


def _dlt_low_stock_lines(db: Session) -> list[str]:
    """Produkty DLT z zapasem poniżej celu (dni_zapasu < cel) — do porannego digestu.
    Puste, gdy Power BI nieskonfigurowane albo analiza padła (best-effort)."""
    from .pallets_cache import get_analysis
    from .powerbi import is_configured
    if not is_configured():
        return []
    try:
        items, _, _, _ = get_analysis(db)
    except Exception:  # noqa: BLE001
        logger.exception("Digest: nie udało się pobrać analizy DLT")
        return []
    low = [i for i in items
           if i.get("dni_zapasu") is not None and i.get("cel_dni") is not None
           and i["dni_zapasu"] < i["cel_dni"]]
    low = low or [i for i in items if i.get("pilne")]
    def days(i):
        d = i.get("dni_zapasu")
        return f"{d:.0f} dni" if d is not None else "brak danych"
    return [f"{i['produkt']} — zapas {days(i)}" for i in low[:15]]


def check_daily_digest_alerts(db: Session, now: datetime.datetime | None = None) -> int:
    """Poranny digest (#24): jeden mail per spółka do logistyki — dzisiejsze dostawy,
    opóźnienia, braki dokumentów przed ETA, niskie zapasy DLT, nieprzeczytane noty.

    Okno wysyłki: godzina DIGEST_HOUR czasu polskiego. Dedup per user po
    Notification(kind='daily_digest') z dzisiejszą datą. Wyłączalny w matrycy reguł."""
    from zoneinfo import ZoneInfo

    from .models import Company
    from .routers.customs import missing_document_types_batch
    now = now or utcnow()
    local = now.replace(tzinfo=datetime.UTC).astimezone(ZoneInfo("Europe/Warsaw"))
    if local.hour != settings.digest_hour:
        return 0
    today = local.date()   # doba PL (data UTC między 00:00 a 02:00 PL to jeszcze wczoraj)
    midnight = pl_midnight_utc(today)
    already = set(db.scalars(select(Notification.user_id).where(
        Notification.kind == "daily_digest",
        Notification.created_at >= midnight)))
    dlt_lines = _dlt_low_stock_lines(db)
    sent = 0
    for company in db.scalars(select(Company).where(Company.is_active)):
        users = [u for u in db.scalars(select(User).where(
            User.is_active, User.role == Role.logistics,
            User.company_id == company.id)) if u.id not in already]
        if not users:
            continue
        active = db.scalars(select(Container).where(
            Container.company_id == company.id,
            Container.status.notin_(Container.FINISHED))).all()
        deliveries = [c for c in active if c.notify_date == today]
        delayed = [c for c in active if c.eta and c.eta < today and c.atd is None]
        horizon = today + datetime.timedelta(days=7)
        soon = [c for c in active if c.eta and c.eta <= horizon
                and c.document_status != DocumentStatus.WYSLANE]
        gaps = missing_document_types_batch(db, soon)   # ARCH-006: wsadowo, nie per kontener
        docs_missing = [f"{c.container_no}: {', '.join(gaps[c.id])}" for c in soon if gaps[c.id]]
        sections: list[str] = []

        def section(header: str, lines: list[str]) -> None:
            if lines:
                shown = lines[:15]
                if len(lines) > 15:
                    shown.append(f"...i {len(lines) - 15} więcej")
                sections.append(header + "\n" + "\n".join(f"- {li}" for li in shown))  # noqa: B023 — wywoływana od razu w tej iteracji

        section(f"Dzisiejsze dostawy ({len(deliveries)}):",
                [f"{c.container_no} — {c.warehouse.name if c.warehouse else '—'}"
                 for c in deliveries])
        section(f"Opóźnione (ETA minęło, {len(delayed)}):",
                [f"{c.container_no} — ETA {c.eta}" for c in delayed])
        section(f"Braki dokumentów przed ETA ({len(docs_missing)}):", docs_missing)
        if not sections:
            continue  # pusty dzień spółki = bez maila (wspólna sekcja DLT sama nie wystarcza)
        section(f"Zapasy DLT poniżej celu ({len(dlt_lines)}):", dlt_lines)
        title = f"Poranny przegląd {company.name} — {today}"
        for user in users:
            unread = db.scalar(select(func.count(Notification.id)).where(
                Notification.user_id == user.id, Notification.is_read.is_(False)))
            body = "\n\n".join(sections)
            if unread:
                body += f"\n\nNieprzeczytane powiadomienia: {unread}"
            sent += notify(db, [user], kind="daily_digest", title=title, body=body)
    db.commit()
    return sent


def check_weekly_digest_alerts(db: Session, now: datetime.datetime | None = None) -> int:
    """Poniedziałkowy digest dla działu zakupów: obserwowane kontenery z notify_date/ETA
    w tym tygodniu. Okno wysyłki: poniedziałek 8:00-9:00 czasu PL (stałe niezależnie od
    DST). Dedup per user po istniejącym Notification(kind='weekly_digest', container_id=None,
    created_at >= polska północ dziś)."""
    now = now or utcnow()
    local = now.replace(tzinfo=datetime.UTC).astimezone(PL_TZ)
    if local.weekday() != 0 or local.hour != 8:
        return 0
    today = local.date()
    already = set(db.scalars(select(Notification.user_id).where(
        Notification.kind == "weekly_digest",
        Notification.container_id.is_(None),
        Notification.created_at >= pl_midnight_utc(today))))
    week_end = today + datetime.timedelta(days=7)
    sent = 0
    users = db.scalars(select(User).where(
        User.is_active, User.role == Role.purchasing)).all()
    for user in users:
        if user.id in already:
            continue
        containers = list(db.scalars(
            select(Container).join(
                WatchedContainer, WatchedContainer.container_id == Container.id)
            .where(WatchedContainer.user_id == user.id,
                   (Container.notify_date.between(today, week_end))
                   | (Container.eta.between(today, week_end)))
            .order_by(Container.notify_date)))
        if not containers:
            continue
        shown = containers[:15]
        lines = [f"{c.container_no} — {c.notify_date or c.eta}" for c in shown]
        if len(containers) > len(shown):
            lines.append(f"...i {len(containers) - len(shown)} więcej")
        sent += notify(db, [user], kind="weekly_digest",
                       title=f"Tygodniowy przegląd obserwowanych kontenerów ({len(containers)})",
                       body="\n".join(lines))
    db.commit()
    return sent


def check_stale_import_alerts(db: Session, today: datetime.date | None = None) -> int:
    """Alert o stęchłych importach master data (#17): typ starszy niż STALE_IMPORT_DAYS.

    Raz dziennie (dedup po Notification kind='stale-import' z dzisiaj), do adminów
    i logistyki — tych samych osób, które pracują z master data (Editors)."""
    from .master_quality import import_freshness
    today = today or today_pl()
    already = db.scalar(select(Notification).where(
        Notification.kind == "stale-import",
        Notification.created_at >= pl_midnight_utc(today)))
    if already:
        return 0
    stale = [f for f in import_freshness(db) if f["stale"]]
    if not stale:
        return 0
    lines = [f"{f['type'].upper()}: "
             + (f"{f['age_days']} dni temu" if f["age_days"] is not None else "nigdy")
             for f in stale]
    recipients = list(db.scalars(select(User).where(
        User.is_active, User.role.in_((Role.admin, Role.logistics)))))
    sent = notify(db, recipients, kind="stale-import",
                  title=f"Stęchłe importy master data: {len(stale)} "
                        f"(próg {settings.stale_import_days} dni)",
                  body="\n".join(lines))
    db.commit()
    return sent
