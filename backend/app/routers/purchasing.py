"""Dział zakupów — status zakupowy kontenera.

Rola `purchasing` widzi kolejkę/zamówienia/spedycję swojej spółki, ale edytować
może WYŁĄCZNIE `purchasing_status` (jedyny endpoint zapisu poniżej). Reszta pól
kontenera jest poza jej zasięgiem, bo generyczny PUT wymaga roli edytora
(admin/logistics). Zakres firmowy egzekwuje `get_scoped` (fundament D1).
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ..audit import record_changes
from ..database import get_db
from ..deps import PurchasingReaders as purchasing_side
from ..deps import get_scoped
from ..models import Container, PurchasingStatus, User
from ..notifications import company_watchers, notify
from ..schemas import ContainerOut, PurchasingStatusIn
from .containers import _LOAD, to_out

router = APIRouter(prefix="/api/purchasing", tags=["zakupy"])


_LABEL = {
    PurchasingStatus.BRAK: "brak",
    PurchasingStatus.DO_ZAMOWIENIA: "do zamówienia",
    PurchasingStatus.ZAMOWIONE: "zamówione",
    PurchasingStatus.POTWIERDZONE: "potwierdzone",
    PurchasingStatus.ZREALIZOWANE: "zrealizowane",
    PurchasingStatus.WSTRZYMANE: "wstrzymane",
}


@router.put("/containers/{container_id}/status", response_model=ContainerOut,
            status_code=status.HTTP_200_OK)
def set_purchasing_status(container_id: int, body: PurchasingStatusIn,
                          db: Session = Depends(get_db), user: User = purchasing_side):
    """Zmiana statusu zakupowego. Zakres firmowy pilnuje get_scoped (403/404 poza spółką)."""
    container = get_scoped(db, Container, container_id, user, options=_LOAD)
    record_changes(db, container, {"purchasing_status": body.purchasing_status}, user,
                   note="zmiana statusu zakupów")
    notify(db, company_watchers(db, container.company_id), kind="order",
           title=f"Zakupy {container.container_no}: {_LABEL[body.purchasing_status]}",
           body="", container_id=container.id, exclude_user_id=user.id)
    db.commit()
    return to_out(container, user)
