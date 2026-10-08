from sqlalchemy.orm import Session

from .models import AuditLog, User

# pola wrażliwe (dane osobowe): w audycie zapisujemy fakt zmiany, nie samą wartość (RODO)
_MASKED_FIELDS = {"driver_id_no", "driver_phone", "driver_name", "truck_no", "trailer_no"}
_MASK = "•••"


def _mask(field: str, value) -> str | None:
    if value is None:
        return None
    if field in _MASKED_FIELDS and str(value):
        return _MASK
    return str(value)


def record(db: Session, *, entity_type: str, entity_id: int, field: str,
           old_value, new_value, user: User | None, note: str = "") -> None:
    db.add(AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        field=field,
        old_value=_mask(field, old_value),
        new_value=_mask(field, new_value),
        note=note,
        user_id=user.id if user else None,
    ))


def record_changes(db: Session, obj, changes: dict, user: User | None, note: str = "") -> None:
    """Zapisuje w audycie każdą realną zmianę pola obiektu i nadaje nową wartość."""
    for field, new_value in changes.items():
        old_value = getattr(obj, field)
        old_cmp = getattr(old_value, "value", old_value)
        new_cmp = getattr(new_value, "value", new_value)
        if old_cmp == new_cmp:
            continue
        setattr(obj, field, new_value)
        record(db, entity_type=type(obj).__tablename__, entity_id=obj.id, field=field,
               old_value=old_cmp, new_value=new_cmp, user=user, note=note)


def record_created(db: Session, obj, user: User | None, label=None, note: str = "") -> None:
    """Wpis „utworzono” (OBS-003): flush nadaje id, nowa wartość = czytelna etykieta
    (domyślnie `name` obiektu) — w historii widać, CO powstało i kto to utworzył."""
    db.flush()
    record(db, entity_type=type(obj).__tablename__, entity_id=obj.id, field="created",
           old_value=None, new_value=label if label is not None else getattr(obj, "name", obj.id),
           user=user, note=note)
