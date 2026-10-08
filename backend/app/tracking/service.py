"""Tracking kontenerów: definicja „śledzonego" (mapa) + reset danych po zmianie numeru.

Zewnętrzny provider trackingu kontenerów został usunięty — pozycje statków daje AIS (ais.py),
oś zdarzeń: timeline.py (zdarzenia w bazie + ręczne statusy)."""
import datetime

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from ..audit import record
from ..models import AuditLog, Container, ContainerStatus, TrackingEvent


def _filled(column):
    return func.length(func.trim(func.coalesce(column, ""))) > 0


# TRACKED = kontenery pokazywane na mapie (tracking_map): numer kontenera + numer RF
# (definicja użytkownika „śledzonego").
TRACKED = and_(_filled(Container.container_no), _filled(Container.rf_number))


# pola nanoszone dawniej przez tracking (audyt note "tracking:*") — parser wartości z audytu
_TRACKED_FIELDS = (
    ("etd", lambda v: datetime.date.fromisoformat(v) if v else None),
    ("status", ContainerStatus),
    ("vessel", lambda v: v or ""),
)


def _value_before_tracking(db: Session, container_id: int, field: str):
    """Wartość pola sprzed ciągu ostatnich zmian z trackingu (note "tracking:*").
    Zwraca (True, stara_wartość) albo (False, None), gdy ostatnia zmiana nie była z
    trackingu — wtedy pole ustawił człowiek i nie wolno go ruszać."""
    notes = db.execute(
        select(AuditLog.note, AuditLog.old_value).where(
            AuditLog.entity_type == "containers", AuditLog.entity_id == container_id,
            AuditLog.field == field).order_by(AuditLog.id.desc())).all()
    found, before = False, None
    for note, old_value in notes:
        if not (note or "").startswith("tracking:"):
            break
        found, before = True, old_value
    return found, before


def reset_tracking(db: Session, container: Container, user) -> None:
    """Zmiana numeru kontenera (np. poprawka literówki): zdarzenia, ETD, status i statek
    z trackingu starego numeru przestają być prawdą. Kasuje oś zdarzeń, cofa pola do
    stanu sprzed trackingu (tylko te, których od tamtej pory nie zmienił człowiek)
    i zeruje tracked_at."""
    note = "zmiana numeru kontenera: reset danych trackingu"
    dropped = db.query(TrackingEvent).filter(
        TrackingEvent.container_id == container.id).delete(synchronize_session=False)
    if dropped:
        record(db, entity_type="containers", entity_id=container.id,
               field="tracking_events", old_value=dropped, new_value=0, user=user, note=note)
    for field, parse in _TRACKED_FIELDS:
        found, before = _value_before_tracking(db, container.id, field)
        if not found:
            continue
        value = parse(before)
        current = getattr(container, field)
        if getattr(current, "value", current) == getattr(value, "value", value):
            continue
        record(db, entity_type="containers", entity_id=container.id, field=field,
               old_value=getattr(current, "value", current),
               new_value=getattr(value, "value", value), user=user, note=note)
        setattr(container, field, value)
    container.tracked_at = None
    container.tracking_error = ""
