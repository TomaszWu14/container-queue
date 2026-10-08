"""Masowe akcje kolejki (pasek zaznaczenia): zmiana statusu i magazynu rozładunku.

Jedno żądanie zamiast N — ale każda pozycja przechodzi DOKŁADNIE tę samą ścieżkę co
pojedyncza zmiana: izolacja przez get_container_checked (get_scoped) per id, walidacja
przejść statusów, audyt (record) i kontrola limitu dnia. Błędy pojedynczych kontenerów nie
przerywają reszty — wracają w `failed`, poprawne zmiany są zapisywane jednym commitem.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import Editors as editors
from ..deps import WarehouseOrEditors as warehouse_or_editors
from ..models import ContainerStatus, User
from ..schemas import StatusChange
from .containers_common import _notify_new_delivery, get_container_checked
from .containers_write import apply_status, apply_warehouse

# sub-router bez prefiksu — podpinany w routers/containers.py PRZED /containers/{id}/…
router = APIRouter()

_MAX_IDS = 500


class BulkStatusIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=_MAX_IDS)
    status: ContainerStatus
    note: str = ""


class BulkWarehouseIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=_MAX_IDS)
    name: str = Field(min_length=1, max_length=160)


class BulkFailure(BaseModel):
    id: int
    detail: str


class BulkResult(BaseModel):
    ok: list[int]        # zmienione lub już w docelowym stanie (bez zmian = też sukces)
    failed: list[BulkFailure]


def _run(db: Session, ids: list[int], user: User, apply) -> tuple[BulkResult, list]:
    ok, failed, changed = [], [], []
    for cid in dict.fromkeys(ids):   # bez duplikatów, kolejność zachowana
        try:
            container = get_container_checked(db, cid, user)   # 404 = brak dostępu / nie istnieje
            if apply(container):
                changed.append(container)
            ok.append(cid)
        except HTTPException as exc:
            failed.append(BulkFailure(id=cid, detail=str(exc.detail)))
    db.commit()
    return BulkResult(ok=ok, failed=failed), changed


@router.post("/containers/bulk/status", response_model=BulkResult)
def bulk_status(body: BulkStatusIn, db: Session = Depends(get_db),
                user: User = warehouse_or_editors):
    change = StatusChange(status=body.status, note=body.note)
    result, _ = _run(db, body.ids, user, lambda c: apply_status(db, c, change, user))
    return result


@router.post("/containers/bulk/warehouse", response_model=BulkResult)
def bulk_warehouse(body: BulkWarehouseIn, db: Session = Depends(get_db), user: User = editors):
    result, changed = _run(db, body.ids, user, lambda c: apply_warehouse(db, c, body.name, user))
    for container in changed:
        _notify_new_delivery(db, container, user)   # Q66: (prze)przypisano magazyn — jak pojedynczo
    return result
