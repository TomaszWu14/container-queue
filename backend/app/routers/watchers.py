"""„Śledzone przez…": kto, kiedy i dlaczego obserwuje kontener / statek.

Widoczność jednym miejscem (`_watchers_out`): role wewnętrzne widzą wszystkich
obserwujących (także magazyn), pozostałe tylko własny wpis — nazwiska i powody
pracowników nie wychodzą do spedytora/agencji. Zakres zasobu: get_container_checked /
get_vessel_visible (nie powielamy reguł izolacji)."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import ViewerOrSales as viewer_or_sales
from ..models import Role, User, WatchedContainer, WatchedVessel, utcnow
from ..schemas import WatchIn
from ..security import shares_company_scope
from .containers_common import get_container_checked

router = APIRouter(prefix="/api", tags=["obserwowanie"])

INTERNAL_ROLES = (Role.admin, Role.logistics, Role.purchasing, Role.warehouse)


def can_see_watcher(viewer: User, target: User) -> bool:
    """Czy viewer widzi obserwującego/awatar targetu — jedna reguła dla /watchers, mapy i awatarów."""
    if target.id == viewer.id:
        return True
    if viewer.role not in INTERNAL_ROLES:
        return False
    return shares_company_scope(viewer, target)


def _watchers_out(db: Session, model, target_col, target_id: int, user: User) -> dict:
    rows = db.execute(
        select(model, User).join(User, User.id == model.user_id)
        .where(target_col == target_id)
        .order_by(model.created_at.asc().nulls_first(), model.id)).all()
    rows = [(w, u) for w, u in rows if can_see_watcher(user, u)]
    return {
        "watching": any(u.id == user.id for _, u in rows),
        "watchers": [{"user_id": u.id, "name": u.full_name or u.login, "reason": w.reason,
                      "created_at": w.created_at.isoformat() if w.created_at else None,
                      "has_avatar": u.has_avatar}
                     for w, u in rows],
    }


def watchers_by_target(db: Session, model, target_col, target_ids: list[int],
                       user: User) -> dict[int, list[dict]]:
    """Obserwujący wielu obiektów naraz (mapa, lista statków) — jedno zapytanie, ta sama reguła."""
    if not target_ids:
        return {}
    rows = db.execute(
        select(target_col, User).join(User, User.id == model.user_id)
        .where(target_col.in_(target_ids))
        .order_by(model.created_at.asc().nulls_first(), model.id)).all()
    out: dict[int, list[dict]] = {}
    for target_id, u in rows:
        if can_see_watcher(user, u):
            out.setdefault(target_id, []).append(
                {"user_id": u.id, "name": u.full_name or u.login, "has_avatar": u.has_avatar})
    return out


@router.get("/containers/{container_id}/watchers")
def container_watchers(container_id: int, db: Session = Depends(get_db),
                       user: User = viewer_or_sales):
    get_container_checked(db, container_id, user)
    return _watchers_out(db, WatchedContainer, WatchedContainer.container_id,
                         container_id, user)


@router.get("/tracking/vessels/{vessel_id}/watchers")
def vessel_watchers(vessel_id: int, db: Session = Depends(get_db), user: User = viewer_or_sales):
    from .tracking import get_vessel_visible
    get_vessel_visible(db, vessel_id, user)
    return _watchers_out(db, WatchedVessel, WatchedVessel.vessel_id, vessel_id, user)


@router.post("/tracking/vessels/{vessel_id}/watch")
def toggle_vessel_watch(vessel_id: int, body: WatchIn | None = None,
                        db: Session = Depends(get_db), user: User = viewer_or_sales):
    """Toggle gwiazdki statku — jak kontener: drugi POST zdejmuje obserwację."""
    from .tracking import get_vessel_visible
    get_vessel_visible(db, vessel_id, user)
    existing = db.scalar(select(WatchedVessel).where(
        WatchedVessel.user_id == user.id, WatchedVessel.vessel_id == vessel_id))
    if existing:
        db.delete(existing)
        watching = False
    else:
        db.add(WatchedVessel(user_id=user.id, vessel_id=vessel_id,
                             reason=(body.reason.strip() if body else ""),
                             created_at=utcnow()))
        watching = True
    db.commit()
    return {"watching": watching}
