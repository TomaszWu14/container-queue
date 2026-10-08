"""Checklista kontroli przyjęcia kontenera (W11 #72).

- słownik punktów kontroli w panelu admina (nazwa, aktywny),
- wynik per kontener: OK / NOK / UWAGA + notatka (karta rozładunku),
- wyniki widoczne na karcie kontenera; NOK sugeruje w UI utworzenie reklamacji.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..audit import record, record_changes, record_created
from ..database import get_db
from ..deps import (
    AdminOnly as admin_only,
)
from ..deps import (
    Viewer as viewer,
)
from ..deps import (
    WarehouseOrEditors as checkers,
)
from ..deps import get_scoped
from ..models import ChecklistPoint, ChecklistResult, Container, User, utcnow
from ..schemas import (
    ChecklistPointIn,
    ChecklistPointOut,
    ChecklistPutIn,
    ChecklistResultOut,
)

router = APIRouter(prefix="/api", tags=["checklista"])


# --- słownik punktów kontroli (panel admina) ---

@router.get("/checklist-points", response_model=list[ChecklistPointOut])
def list_points(active_only: bool = False, db: Session = Depends(get_db),
                user: User = viewer):
    query = select(ChecklistPoint).order_by(ChecklistPoint.sort_order, ChecklistPoint.name)
    if active_only:
        query = query.where(ChecklistPoint.is_active)
    return db.scalars(query).all()


@router.post("/checklist-points", response_model=ChecklistPointOut, status_code=201)
def create_point(body: ChecklistPointIn, db: Session = Depends(get_db),
                 user: User = admin_only):
    if db.scalar(select(ChecklistPoint).where(ChecklistPoint.name == body.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Taki punkt kontroli już istnieje.")
    point = ChecklistPoint(**body.model_dump())
    db.add(point)
    record_created(db, point, user)
    db.commit()
    return point


@router.patch("/checklist-points/{point_id}", response_model=ChecklistPointOut)
def update_point(point_id: int, body: ChecklistPointIn,
                 db: Session = Depends(get_db), user: User = admin_only):
    point = db.get(ChecklistPoint, point_id)
    if not point:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono punktu kontroli.")
    record_changes(db, point, body.model_dump(exclude_unset=True), user)
    db.commit()
    return point


# --- wynik kontroli per kontener ---

def _container_checked(db: Session, container_id: int, user: User) -> Container:
    return get_scoped(db, Container, container_id, user)


def _checklist_out(db: Session, container_id: int) -> list[ChecklistResultOut]:
    results = {r.point_id: r for r in db.scalars(
        select(ChecklistResult).options(selectinload(ChecklistResult.checked_by))
        .where(ChecklistResult.container_id == container_id))}
    # punkty aktywne + nieaktywne z istniejącym wynikiem (historia nie znika)
    points = db.scalars(select(ChecklistPoint)
                        .order_by(ChecklistPoint.sort_order, ChecklistPoint.name)).all()
    out = []
    for point in points:
        result = results.get(point.id)
        if not point.is_active and not result:
            continue
        out.append(ChecklistResultOut(
            point_id=point.id, name=point.name,
            result=result.result if result else None,
            note=result.note if result else "",
            checked_by_login=(result.checked_by.login
                              if result and result.checked_by else None),
            checked_at=result.checked_at if result else None))
    return out


@router.get("/containers/{container_id}/checklist",
            response_model=list[ChecklistResultOut])
def get_checklist(container_id: int, db: Session = Depends(get_db), user: User = viewer):
    _container_checked(db, container_id, user)
    return _checklist_out(db, container_id)


@router.put("/containers/{container_id}/checklist",
            response_model=list[ChecklistResultOut])
def put_checklist(container_id: int, body: ChecklistPutIn,
                  db: Session = Depends(get_db), user: User = checkers):
    """Upsert wyników podanych punktów (pozostałe zostają bez zmian)."""
    _container_checked(db, container_id, user)
    existing = {r.point_id: r for r in db.scalars(select(ChecklistResult).where(
        ChecklistResult.container_id == container_id))}
    for item in body.items:
        point = db.get(ChecklistPoint, item.point_id)
        if not point:
            raise HTTPException(status.HTTP_404_NOT_FOUND,
                                f"Nie znaleziono punktu kontroli {item.point_id}.")
        row = existing.get(item.point_id)
        old = (row.result, row.note) if row else (None, None)
        if old != (item.result, item.note.strip()[:2000]):
            record(db, entity_type="containers", entity_id=container_id, field="checklist",
                   old_value=old[0], new_value=item.result, user=user,
                   note=f"{point.name}: {item.note.strip()}"[:500])
        if row:
            row.result = item.result
            row.note = item.note.strip()[:2000]
            row.checked_by_id = user.id
            row.checked_at = utcnow()
        else:
            db.add(ChecklistResult(
                container_id=container_id, point_id=item.point_id,
                result=item.result, note=item.note.strip()[:2000],
                checked_by_id=user.id))
    db.commit()
    return _checklist_out(db, container_id)
