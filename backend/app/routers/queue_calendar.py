"""Limity dzienne i kalendarz pracy per magazyn — wydzielone z containers.py.

Endpointy pod tym samym prefiksem /api (URL bez zmian): /limits, /calendar.
Samodzielny seam: zależy tylko od _checked_warehouse (dostęp do spółki magazynu).
"""
import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import record, record_changes, record_created
from ..database import get_db
from ..deps import Editors as editors
from ..deps import ViewerOrSales as viewer_or_sales
from ..deps import get_scoped, scope_containers
from ..models import CalendarDay, Container, DailyLimit, User, Warehouse, today_pl
from ..schemas import CalendarDayIn, CalendarDayOut, DailyLimitIn, DailyLimitOut

router = APIRouter(prefix="/api", tags=["kolejka"])


def _checked_warehouse(db: Session, user: User, warehouse_id: int) -> Warehouse:
    """Magazyn z kontrolą dostępu do spółki (odczyt limitów/kalendarza per magazyn)."""
    return get_scoped(db, Warehouse, warehouse_id, user)


@router.get("/limits", response_model=list[DailyLimitOut])
def list_limits(warehouse_id: int, date_from: datetime.date, date_to: datetime.date,
                db: Session = Depends(get_db), user: User = viewer_or_sales):
    _checked_warehouse(db, user, warehouse_id)   # nie zdradzamy limitów magazynów obcych spółek
    return db.scalars(select(DailyLimit).where(
        DailyLimit.warehouse_id == warehouse_id,
        DailyLimit.day >= date_from, DailyLimit.day <= date_to)).all()


@router.put("/limits", response_model=DailyLimitOut)
def set_limit(body: DailyLimitIn, db: Session = Depends(get_db), user: User = editors):
    _checked_warehouse(db, user, body.warehouse_id)  # jedna reguła dostępu (jak w GET)
    existing = db.scalar(select(DailyLimit).where(
        DailyLimit.warehouse_id == body.warehouse_id, DailyLimit.day == body.day))
    if existing:
        record(db, entity_type="daily_limits", entity_id=existing.id, field="limit",
               old_value=existing.limit, new_value=body.limit, user=user)
        existing.limit = body.limit
        db.commit()
        return existing
    entry = DailyLimit(**body.model_dump())
    db.add(entry)
    db.flush()
    record(db, entity_type="daily_limits", entity_id=entry.id, field="limit",
           old_value=None, new_value=body.limit, user=user)
    db.commit()
    return entry


@router.get("/calendar", response_model=list[CalendarDayOut])
def list_calendar(warehouse_id: int, db: Session = Depends(get_db), user: User = viewer_or_sales):
    _checked_warehouse(db, user, warehouse_id)   # kalendarz pracy tylko magazynów w zasięgu
    return db.scalars(select(CalendarDay).where(
        CalendarDay.warehouse_id == warehouse_id).order_by(CalendarDay.day)).all()


@router.put("/calendar", response_model=CalendarDayOut)
def set_calendar_day(body: CalendarDayIn, db: Session = Depends(get_db), user: User = editors):
    _checked_warehouse(db, user, body.warehouse_id)  # jedna reguła dostępu (jak w GET)
    existing = db.scalar(select(CalendarDay).where(
        CalendarDay.warehouse_id == body.warehouse_id, CalendarDay.day == body.day))
    if existing:
        record_changes(db, existing, {"is_working": body.is_working, "note": body.note}, user,
                       note=f"magazyn {body.warehouse_id}, {body.day}")
        db.commit()
        return existing
    entry = CalendarDay(**body.model_dump())
    db.add(entry)
    record_created(db, entry, user, label=f"{body.day} {'pracujący' if body.is_working else 'wolny'}",
                   note=f"magazyn {body.warehouse_id}")
    db.commit()
    return entry


@router.get("/calendar/year")
def calendar_year(rok: int = Query(ge=2000, le=2100),
                  db: Session = Depends(get_db), user: User = viewer_or_sales):
    """Widok roczny kalendarza: liczba kontenerów per dzień awizacji × magazyn.

    Ten sam zbiór co /api/queue w widoku miesięcznym (notify_date, scope_containers),
    ale jednym GROUP BY zamiast rekordów. warehouse=None → „Bez magazynu".
    """
    query = (select(Container.notify_date, Warehouse.name, func.count(Container.id))
             .select_from(Container)
             .outerjoin(Warehouse, Container.warehouse_id == Warehouse.id)
             .where(Container.notify_date >= datetime.date(rok, 1, 1),
                    Container.notify_date <= datetime.date(rok, 12, 31))
             .group_by(Container.notify_date, Warehouse.name)
             .order_by(Container.notify_date))
    rows = db.execute(scope_containers(query, user)).all()
    return {"year": rok, "today": today_pl().isoformat(),
            "days": [{"day": d.isoformat(), "warehouse": wh, "count": n} for d, wh, n in rows]}
