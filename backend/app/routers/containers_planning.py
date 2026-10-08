"""Planowanie dat: wysyłka/potwierdzenie planu, kolizje paczek, propozycja awizacji,
widok kolejki (grupowanie po dacie awizacji) i konfiguracja UI bufora ETA."""
import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..app_settings import get_setting
from ..config import settings
from ..database import get_db
from ..deps import Editors as editors
from ..deps import PlanConfirmers as plan_confirmers
from ..deps import Viewer as viewer
from ..deps import ViewerOrSales as viewer_or_sales
from ..deps import check_container_access, scope_containers
from ..holidays import is_free_day
from ..models import Container, PlanningStatus, User, Warehouse, today_pl
from ..planning import confirm_plan, send_to_forwarder
from ..schemas import ContainerOut, QueueDay
from .containers_common import (
    _LOAD,
    _enum_filter,
    calendar_overrides_map,
    daily_limits_map,
    get_container_checked,
    to_out,
    transport_job_conflicts,
)

# sub-router bez prefiksu — podpinany w routers/containers.py (prefiks /api, tag kolejka)
router = APIRouter()


class PlanSendIn(BaseModel):
    container_ids: list[int] = Field(min_length=1)


@router.post("/containers/plan/send")
def send_plan(body: PlanSendIn, db: Session = Depends(get_db), user: User = editors):
    """Wysyła propozycje dat do spedycji — zamraża je i oznacza jako oczekujące.

    Zadeklarowany PRZED /containers/{container_id}, by "plan" nie trafiło w {id}.
    """
    containers = db.scalars(select(Container)
                            .options(selectinload(Container.forwarder))
                            .where(Container.id.in_(body.container_ids))).all()
    if not containers:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono kontenerów.")
    for c in containers:
        check_container_access(user, c)

    sent, no_forwarder, skipped = 0, [], []
    for c in containers:
        if not c.forwarder_id:
            # bez spedytora nie ma komu wysłać — zgłaszamy zamiast po cichu pomijać
            no_forwarder.append(c.container_no)
            continue
        if c.planning_status == PlanningStatus.POTWIERDZONE:
            skipped.append(c.container_no)
            continue
        send_to_forwarder(db, c, user)
        sent += 1
    db.commit()
    return {"sent": sent, "no_forwarder": no_forwarder, "skipped": skipped}


class PlanConfirmIn(BaseModel):
    delivery_date: datetime.date


@router.get("/containers/plan/pending", response_model=list[ContainerOut])
def pending_plan(db: Session = Depends(get_db), user: User = viewer_or_sales):
    """Kontenery czekające na potwierdzenie daty — lista dla modułu spedycji.

    Zadeklarowany PRZED /containers/{container_id}, by "plan" nie trafiło w {id}.
    """
    query = (select(Container).options(*_LOAD)
             .where(Container.planning_status == PlanningStatus.WYSLANE)
             .order_by(Container.notify_date, Container.id))
    return [to_out(c, user) for c in db.scalars(scope_containers(query, user)).all()]


@router.post("/containers/{container_id}/plan/confirm", response_model=ContainerOut)
def confirm_plan_endpoint(container_id: int, body: PlanConfirmIn,
                          db: Session = Depends(get_db), user: User = plan_confirmers):
    """Potwierdzenie daty przez zalogowaną spedycję (portal).

    Role jak przy PATCH notify_date plus spedytor: endpoint zapisuje datę dostawy,
    więc nie może być szerszy niż zwykła edycja. Izolacja: get_container_checked.
    """
    container = get_container_checked(db, container_id, user)
    confirm_plan(db, container, body.delivery_date, confirmed_by=user)
    db.commit()
    return to_out(get_container_checked(db, container_id, user), user)


@router.get("/containers/transport-conflicts")
def containers_transport_conflicts(
    db: Session = Depends(get_db), user: User = viewer_or_sales,
    date_from: datetime.date | None = None, date_to: datetime.date | None = None,
):
    """Ostrzeżenia kolejki: to samo zlecenie transportowe rozjeżdża się tego samego
    dnia do różnych magazynów (jedna ciężarówka nie dostarczy w dwa miejsca)."""
    today = today_pl()
    date_from = date_from or today - datetime.timedelta(days=3)
    date_to = date_to or today + datetime.timedelta(days=28)
    return {"conflicts": transport_job_conflicts(db, user, date_from, date_to)}


@router.get("/containers/{container_id}/suggest-notify-date")
def suggest_notify_date(container_id: int, db: Session = Depends(get_db),
                        user: User = viewer):
    """#50: propozycja daty awizacji — pierwszy dzień roboczy (kalendarz magazynu)
    po ETA+bufor z wolnym slotem (used < limit); bez limitu, gdy brak magazynu."""
    container = get_container_checked(db, container_id, user)
    try:
        buffer_days = int(get_setting(db, "warehouse_eta_buffer_days") or 3)
    except ValueError:
        buffer_days = 3
    base = (container.eta or today_pl()) + datetime.timedelta(days=buffer_days)
    warehouse = container.warehouse
    country = warehouse.country if warehouse else "PL"
    horizon = base + datetime.timedelta(days=60)  # ponytail: 60 dni wystarczy; brak slotu = 409
    wh_ids = [warehouse.id] if warehouse else []
    limits = daily_limits_map(db, wh_ids, base, horizon)
    overrides = calendar_overrides_map(db, wh_ids, base, horizon)
    used_by_day: dict[datetime.date, int] = {}
    if warehouse:
        rows = db.execute(
            select(Container.notify_date, func.count(Container.id))
            .where(Container.warehouse_id == warehouse.id,
                   Container.notify_date >= base, Container.notify_date <= horizon,
                   Container.is_transit.is_(False),
                   Container.status.notin_(Container.FINISHED),
                   Container.planning_status == PlanningStatus.POTWIERDZONE)
            .group_by(Container.notify_date)).all()
        used_by_day = dict(rows)
    day = base
    while day <= horizon:
        free = is_free_day(day, country)
        if warehouse:
            working = overrides.get((warehouse.id, day))
            if working is not None:
                free = not working
        if not free:
            limit = (limits.get((warehouse.id, day), warehouse.default_daily_limit)
                     if warehouse else None)
            if limit is None or used_by_day.get(day, 0) < limit:
                return {"date": day.isoformat(),
                        "eta": container.eta.isoformat() if container.eta else None,
                        "buffer_days": buffer_days}
        day += datetime.timedelta(days=1)
    raise HTTPException(status.HTTP_409_CONFLICT,
                        "Brak wolnego terminu w ciągu 60 dni od ETA + bufor.")


# --- widok kolejki (grupowanie po dacie awizacji) ---

@router.get("/queue", response_model=list[QueueDay])
def queue_view(
    db: Session = Depends(get_db),
    user: User = viewer_or_sales,
    date_from: datetime.date | None = None,
    date_to: datetime.date | None = None,
    warehouse_id: int | None = None,
    transit: bool | None = None,
    planning: str | None = None,
):
    today = today_pl()
    date_from = date_from or today - datetime.timedelta(days=3)
    date_to = date_to or today + datetime.timedelta(days=21)

    query = (select(Container).options(*_LOAD)
             .where(Container.notify_date >= date_from, Container.notify_date <= date_to)
             .order_by(Container.notify_date, Container.id))
    query = scope_containers(query, user)
    if warehouse_id is not None:
        query = query.where(Container.warehouse_id == warehouse_id)
    # None = bez filtra (kompatybilność wsteczna); zakładki kolejki wysyłają jawne false
    if transit is not None:
        query = query.where(Container.is_transit.is_(transit))
    # filtr sekcji planowania (kolejka wysyła PROPOZYCJA / WYSLANE / POTWIERDZONE)
    query = _enum_filter(query, Container.planning_status, planning, PlanningStatus)
    containers = db.scalars(query).all()

    warehouse = db.get(Warehouse, warehouse_id) if warehouse_id else None
    by_day: dict[datetime.date, list[Container]] = {}
    for c in containers:
        by_day.setdefault(c.notify_date, []).append(c)

    # limity i wyjątki kalendarza dla całego okna — dwa zapytania zamiast 2 na każdy dzień
    wh_ids = [warehouse.id] if warehouse else []
    limits = daily_limits_map(db, wh_ids, date_from, date_to)
    overrides = calendar_overrides_map(db, wh_ids, date_from, date_to)

    days = []
    day = date_from
    while day <= date_to:
        items = by_day.get(day, [])
        country = warehouse.country if warehouse else "PL"
        free = is_free_day(day, country)
        if warehouse:
            working = overrides.get((warehouse.id, day))
            if working is not None:
                free = not working
        limit = (limits.get((warehouse.id, day), warehouse.default_daily_limit)
                 if warehouse else None)
        # do limitu liczymy wyłącznie terminy uzgodnione ze spedycją — propozycja
        # i wysyłka czekająca na odpowiedź nie rezerwują slotu rozładunkowego
        used = sum(1 for c in items
                   if c.status not in Container.FINISHED and not c.is_transit
                   and c.planning_status == PlanningStatus.POTWIERDZONE)
        days.append(QueueDay(
            day=day, is_free_day=free, limit=limit, used=used,
            over_limit=limit is not None and used > limit,
            containers=[to_out(c, user) for c in items]))
        day += datetime.timedelta(days=1)
    return days


@router.get("/ui-config")
def ui_config(db: Session = Depends(get_db), user: User = viewer_or_sales):
    """Drobna konfiguracja UI dla zalogowanych (ustawienia admina czytane przez front)."""
    try:
        buffer_days = int(get_setting(db, "warehouse_eta_buffer_days") or 3)
    except ValueError:
        buffer_days = 3
    # max_upload_mb: front odrzuca za duży plik PRZED wysłaniem (zamiast 413 po minutach uploadu)
    return {"warehouse_eta_buffer_days": buffer_days, "max_upload_mb": settings.max_upload_mb}
