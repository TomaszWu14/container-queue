"""#49 — ujednolicony przegląd audytu: kto/co/kiedy zmienił, przekrojowo po WSZYSTKICH
encjach (audit_log zbiera ślad ze wszystkich modułów). Tylko admin — to wrażliwy,
firmo-przekrojowy widok; historię pojedynczej encji dają endpointy per moduł (np.
/api/containers/{id}/history)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..deps import AdminOnly as admins
from ..models import AuditLog, User

router = APIRouter(prefix="/api/audit", tags=["audyt"])


@router.get("")
def list_audit(entity_type: str | None = Query(default=None, max_length=40),
               entity_id: int | None = Query(default=None),
               user_id: int | None = Query(default=None),
               field: str | None = Query(default=None, max_length=60),
               q: str | None = Query(default=None, max_length=120),
               limit: int = Query(default=100, le=500),
               db: Session = Depends(get_db), user: User = admins) -> list[dict]:
    query = (select(AuditLog).options(selectinload(AuditLog.user))
             .order_by(AuditLog.created_at.desc()))
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        query = query.where(AuditLog.entity_id == entity_id)
    if user_id is not None:
        query = query.where(AuditLog.user_id == user_id)
    if field:
        query = query.where(AuditLog.field == field)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(AuditLog.old_value.ilike(like)
                            | AuditLog.new_value.ilike(like) | AuditLog.note.ilike(like))
    return [{
        "id": a.id, "entity_type": a.entity_type, "entity_id": a.entity_id,
        "field": a.field, "old_value": a.old_value, "new_value": a.new_value,
        "note": a.note, "user_login": a.user.login if a.user else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    } for a in db.scalars(query.limit(limit)).all()]
