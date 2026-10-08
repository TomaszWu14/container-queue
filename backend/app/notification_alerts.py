"""Alerty per kontener: demurrage, tracking (ETA/dryf AIS/postój/port docelowy),
przeciągająca się odprawa celna i braki dokumentów przed ETA.

Importuj przez app.notifications (re-eksport) — moduł sam importuje rdzeń z
app.notifications, więc wejście prosto tutaj zamknęłoby cykl importu."""
from .models import pl_midnight_utc, today_pl
import datetime
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .app_settings import get_setting
from .config import settings
from .models import (
    Container,
    CustomsStatus,
    DocumentStatus,
    Notification,
    TrackingEvent,
    utcnow,
)
from .notifications import (
    company_watchers,
    container_watchers,
    customs_agency_users,
    notify,
    notify_aboard,
)


# --- alerty demurrage ---

def _arrival_map(db: Session, container_ids: list[int]) -> dict[int, datetime.datetime]:
    """Najwcześniejsze faktyczne przybycie (DISCHARGE/ARRIVE, nie-estymowane) per kontener,
    jednym zapytaniem GROUP BY — zamiast osobnego SELECT-a na każdy kontener (N+1)."""
    if not container_ids:
        return {}
    rows = db.execute(
        select(TrackingEvent.container_id, func.min(TrackingEvent.occurred_at))
        .where(TrackingEvent.container_id.in_(container_ids),
               TrackingEvent.event_code.in_(("DISCHARGE", "ARRIVE")),
               TrackingEvent.is_estimated.is_(False),
               TrackingEvent.occurred_at.is_not(None))
        .group_by(TrackingEvent.container_id)).all()
    return {cid: occurred for cid, occurred in rows}


def _free_days(container: Container, carrier_days: dict[int, int | None]) -> int:
    """Dni wolne: ręcznie przy kontenerze → u armatora (słownik) → domyślna (decyzja 2026-09-28).
    Pusty wpis nie wycisza alertu — armator liczy swoje dni tak czy siak."""
    if container.demurrage_free_days is not None:
        return container.demurrage_free_days
    carrier = carrier_days.get(container.carrier_id) if container.carrier_id else None
    return carrier if carrier is not None else settings.demurrage_default_free_days


def _carrier_days(db: Session, containers: Sequence[Container]) -> dict[int, int | None]:
    from .models import Carrier
    ids = {c.carrier_id for c in containers if c.carrier_id}
    return dict(db.execute(select(Carrier.id, Carrier.demurrage_free_days)
                           .where(Carrier.id.in_(ids))).all()) if ids else {}


def demurrage_deadlines(db: Session,
                        containers: Sequence[Container]) -> dict[int, datetime.date | None]:
    """Termin demurrage dla wielu kontenerów naraz: data przybycia (wyładunek/przybycie
    z trackingu, inaczej ETA) + dni wolne. Jedno zapytanie o zdarzenia zamiast N."""
    arrivals = _arrival_map(db, [c.id for c in containers])
    carrier_days = _carrier_days(db, containers)   # jedno zapytanie zamiast N
    result: dict[int, datetime.date | None] = {}
    for container in containers:
        free_days = _free_days(container, carrier_days)
        arrival = arrivals.get(container.id)
        # zakończony (DOSTARCZONY/ZREALIZOWANY) — demurrage już nie biegnie
        arrival_date = (None if container.status in Container.FINISHED
                        else arrival.date() if arrival else container.eta)
        result[container.id] = (
            arrival_date + datetime.timedelta(days=free_days)
            if arrival_date else None)
    return result


def demurrage_window(db: Session, container: Container) \
        -> tuple[datetime.date, int, datetime.date, bool] | None:
    """(start, wolne_dni, deadline, szacowane) — okno demurrage do osi czasu.

    start = faktyczne przybycie (DISCHARGE/ARRIVE) albo ETA (wtedy szacowane=True).
    Kwoty nie liczymy — stawka armatora nie jest nigdzie przechowywana."""
    arrival = _arrival_map(db, [container.id]).get(container.id)
    free_days = _free_days(container, _carrier_days(db, [container]))
    start = arrival.date() if arrival else container.eta
    if start is None:
        return None
    return start, free_days, start + datetime.timedelta(days=free_days), arrival is None


def demurrage_deadline(db: Session, container: Container) -> datetime.date | None:
    """Termin demurrage pojedynczego kontenera (cienki wrapper na wersję zbiorczą)."""
    return demurrage_deadlines(db, [container])[container.id]


def check_demurrage_alerts(db: Session, today: datetime.date | None = None) -> int:
    """Wysyła alert, gdy do końca demurrage zostało <= DEMURRAGE_ALERT_DAYS.

    Jeden alert na kontener i dzień (deduplikacja po istniejącym powiadomieniu).
    """
    today = today or today_pl()
    sent = 0
    active = db.scalars(select(Container).where(
        Container.status.notin_(Container.FINISHED))).all()
    deadlines = demurrage_deadlines(db, active)   # jedno zapytanie zamiast N
    for container in active:
        deadline = deadlines[container.id]
        if deadline is None:
            continue
        days_left = (deadline - today).days
        if days_left > settings.demurrage_alert_days:
            continue
        already = db.scalar(select(Notification).where(
            Notification.kind == "demurrage",
            Notification.container_id == container.id,
            Notification.created_at >= pl_midnight_utc(today)))
        if already:
            continue
        if days_left >= 0:
            title = f"Demurrage: {container.container_no} — zostały {days_left} dni (do {deadline})"
        else:
            title = f"Demurrage: {container.container_no} — termin minął {deadline}!"
        sent += notify(db, container_watchers(db, container), kind="demurrage",
                       title=title, container_id=container.id)
    db.commit()
    return sent


# --- alerty trackingu: przekroczone ETA + dryf ETA statku z AIS ---

def check_tracking_alerts(db: Session, today: datetime.date | None = None) -> int:
    """Milestone'y trackingowe (in-app + e-mail + Teams przez notify()).

    1. Kontener przed przybyciem przekroczył ETA (wczoraj) — okno jednodniowe
       + deduplikacja per kontener i dzień (job biegnie kilka razy dziennie).
    2. ETA statku z AIS późniejsze od ETA kontenerów na pokładzie o próg
       tracking_eta_alert_days — alerty per statek idą przez notify_aboard: każdy
       odbiorca widzi tylko kontenery swojej spółki/spedytora/agencji."""
    from .models import TrackedVessel
    from .tracking.ais import format_container_list, group_by_vessel
    today = today or today_pl()
    # dedup po realnym czasie zapisu powiadomień (created_at = utcnow), nie po
    # parametrze today — inaczej testowe „dziś" z przyszłości omija deduplikację
    midnight = pl_midnight_utc()
    sent = 0

    # 1) ETA minęło wczoraj, kontener wciąż przed przybyciem (W_PORCIE/ODPRAWA/
    #    AWIZOWANY już przypłynęły — „brak potwierdzenia przybycia" byłoby fałszem).
    #    Job biegnie co 6 h i przy restarcie → dedup per kontener i dzień.
    overdue = db.scalars(select(Container).where(
        Container.status.in_(Container.ACTIVE_PRE_ARRIVAL),
        Container.eta == today - datetime.timedelta(days=1),
        Container.atd.is_(None))).all()
    for container in overdue:
        if db.scalar(select(Notification.id).where(
                Notification.kind == "eta_overdue",
                Notification.container_id == container.id,
                Notification.created_at >= midnight)):
            continue
        title = (f"ETA minęło: {container.container_no} — planowane "
                 f"{container.eta}, brak potwierdzenia przybycia")
        sent += notify(db, container_watchers(db, container), kind="eta_overdue",
                       title=title, container_id=container.id)

    # 2) dryf ETA per statek (AIS) — alert per zakres odbiorców (spółka/spedytor/
    #    agencja) z listą tylko ich kontenerów; dedup per statek, odbiorca i dzień
    aboard_by_vessel = group_by_vessel(db.scalars(select(Container).where(
        Container.vessel != "",
        Container.status.notin_(Container.FINISHED))).all())
    vessels = db.scalars(select(TrackedVessel).where(
        TrackedVessel.ais_eta.is_not(None))).all()
    for vessel in vessels:
        def drift_alert(group, vessel=vessel):
            etas = [c.eta for c in group if c.eta]
            if not etas:
                return None
            drift = (vessel.ais_eta.date() - min(etas)).days
            if drift < settings.tracking_eta_alert_days:
                return None
            return (f"Dryf ETA: {vessel.name} wg AIS przybędzie {vessel.ais_eta.date()} "
                    f"— {drift} dni po ETA kontenerów: {format_container_list(group)}", "")
        sent += notify_aboard(db, aboard_by_vessel.get(vessel.name, []), kind="eta_drift",
                              render=drift_alert, since=midnight)
    # 3) statek stoi przy porcie > prog (kotwica/reda) z kontenerami na pokladzie
    #    — tylko ze świeżym sygnałem AIS: near_port czyści wyłącznie nowa pozycja,
    #    więc statek, który zniknął z AIS, „stałby" wiecznie i alarmował codziennie
    stuck_cutoff = utcnow() - datetime.timedelta(hours=settings.ais_anchor_alert_hours)
    seen_cutoff = utcnow() - datetime.timedelta(hours=settings.ais_stale_hours)
    for vessel in db.scalars(select(TrackedVessel).where(
            TrackedVessel.near_port != "",
            TrackedVessel.near_port_since.is_not(None),
            TrackedVessel.near_port_since <= stuck_cutoff,
            TrackedVessel.last_seen >= seen_cutoff)).all():
        hours = int((utcnow() - vessel.near_port_since).total_seconds() // 3600)
        sent += notify_aboard(
            db, aboard_by_vessel.get(vessel.name, []), kind="vessel_stuck", since=midnight,
            render=lambda group, v=vessel, h=hours: (
                f"Statek {v.name} stoi przy {v.near_port} juz {h} h "
                f"(ryzyko demurrage) - kontenery: {format_container_list(group)}", ""))
    # 4) statek wszedł w geofence portu DOCELOWEGO (near_port == cel z AIS Destination)
    #    — raz per statek+port i odbiorcę (dedup po stałym tytule, bez okna czasowego)
    from .tracking.geo import GEOFENCE_NM, PORT_COORDS, haversine_nm, locate_destination
    for vessel in db.scalars(select(TrackedVessel).where(
            TrackedVessel.near_port != "")).all():
        dest = locate_destination(vessel.destination)
        port_xy = PORT_COORDS.get(vessel.near_port)
        if (dest is None or port_xy is None
                or haversine_nm(*port_xy, *dest) > GEOFENCE_NM):
            continue
        # tytuł stały (bez listy kontenerów — ta zmienia się w czasie i psułaby dedup)
        title = f"Statek {vessel.name} w porcie docelowym {vessel.near_port}"
        sent += notify_aboard(
            db, aboard_by_vessel.get(vessel.name, []), kind="dest_port", unique_title=True,
            render=lambda group, t=title: (
                t, f"Kontenery na pokładzie: {format_container_list(group)}. "
                   f"Sprawdź statusy i odprawę."))
    db.commit()
    return sent


# --- alerty przeciągającej się odprawy celnej ---

def check_customs_alerts(db: Session, today: datetime.date | None = None) -> int:
    """Alert, gdy odprawa jest ZLECONA/REWIZJA dłużej niż CUSTOMS_ALERT_DAYS od zlecenia.

    Jeden alert na kontener i dzień (deduplikacja po istniejącym powiadomieniu).
    Powiadamiani: nasi pracownicy (logistyka spółki + admini) oraz agencja celna.
    """
    today = today or today_pl()
    threshold = settings.customs_alert_days
    sent = 0
    pending = db.scalars(select(Container).where(
        Container.customs_status.in_((CustomsStatus.ZLECONA, CustomsStatus.REWIZJA)),
        Container.customs_assigned_at.is_not(None))).all()
    for container in pending:
        days = (today - container.customs_assigned_at.date()).days
        if days < threshold:
            continue
        already = db.scalar(select(Notification).where(
            Notification.kind == "customs-delay",
            Notification.container_id == container.id,
            Notification.created_at >= pl_midnight_utc(today)))
        if already:
            continue
        agency = container.customs_agency_rel.name if container.customs_agency_rel else \
            (container.customs_agency or "—")
        title = (f"Odprawa {container.container_no}: {days} dni bez zamknięcia "
                 f"(agencja {agency})")
        recipients = company_watchers(db, container.company_id) \
            + customs_agency_users(db, container.customs_agency_id)
        sent += notify(db, recipients, kind="customs-delay",
                       title=title, container_id=container.id)
    db.commit()
    return sent


def check_docs_alerts(db: Session, today: datetime.date | None = None) -> int:
    """Przypomnienie o brakach w checkliście dokumentów N dni przed ETA.

    Kontener w obiegu celnym (agencja lub status odprawy ≠ BRAK), jeszcze nie
    WYSLANE, ETA ≤ dziś+N (próg `docs_reminder_days` z ustawień admina) i braki
    wymaganych typów → dzwonek do obserwatorów spółki. Raz dziennie per kontener."""
    from .routers.customs import missing_document_types_batch
    today = today or today_pl()
    try:
        # ustawienie admina ma pierwszeństwo; brak → env DOCS_ETA_DAYS (domyślnie 5)
        days = int(get_setting(db, "docs_reminder_days") or settings.docs_eta_days)
    except ValueError:
        days = settings.docs_eta_days
    horizon = today + datetime.timedelta(days=days)
    candidates = db.scalars(select(Container).where(
        Container.eta.is_not(None), Container.eta <= horizon,
        Container.document_status != DocumentStatus.WYSLANE,
        (Container.customs_agency_id.is_not(None))
        | (Container.customs_status != CustomsStatus.BRAK))).all()
    gaps = missing_document_types_batch(db, candidates)
    sent = 0
    for container in candidates:
        missing = gaps[container.id]
        if not missing:
            continue
        already = db.scalar(select(Notification).where(
            Notification.kind == "docs-missing",
            Notification.container_id == container.id,
            Notification.created_at >= pl_midnight_utc(today)))
        if already:
            continue
        sent += notify(db, company_watchers(db, container.company_id), kind="docs-missing",
                       title=f"Braki dokumentów {container.container_no} "
                             f"(ETA {container.eta}): {', '.join(missing)}",
                       container_id=container.id)
    db.commit()
    return sent
