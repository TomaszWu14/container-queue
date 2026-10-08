"""#13 — sloty awizacji: okna rozładunku magazynu z pojemnością.

Magazyn definiuje okna startu ("07:00,08:00,…") i ile kontenerów mieści jedno okno.
Zajętość liczymy na żywo z kontenerów (warehouse + dzień awizacji + slot_time) — bez
osobnej tabeli rezerwacji, więc zmiana daty/magazynu kontenera zwalnia slot sama."""
import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Container, Warehouse


def windows(warehouse: Warehouse | None) -> list[str]:
    if not warehouse or not warehouse.slot_windows:
        return []
    return sorted({w.strip() for w in warehouse.slot_windows.split(",") if w.strip()})


def free_slots(db: Session, warehouse: Warehouse | None, day: datetime.date | None,
               exclude_container_id: int | None = None) -> list[dict]:
    """[{time, free}] dla dnia; kontener `exclude` nie zajmuje własnego slotu (zmiana)."""
    wins = windows(warehouse)
    if not wins or day is None:
        return []
    q = (select(Container.slot_time, func.count())
         .where(Container.warehouse_id == warehouse.id, Container.notify_date == day,
                Container.slot_time.in_(wins))
         .group_by(Container.slot_time))
    if exclude_container_id is not None:
        q = q.where(Container.id != exclude_container_id)
    taken = dict(db.execute(q).all())
    cap = max(warehouse.slot_capacity or 1, 1)
    return [{"time": w, "free": cap - taken.get(w, 0)} for w in wins]


def lock_warehouse(db: Session, warehouse_id: int | None) -> None:
    """Serializuje rezerwacje slotów magazynu do końca transakcji (sprawdź + zapisz).

    ponytail: blokada wiersza Warehouse (SELECT … FOR UPDATE) — Postgres szereguje
    równoległe zatwierdzenia na ten sam magazyn, SQLite ignoruje FOR UPDATE (dev/testy,
    jeden writer i tak). Całomagazynowa, nie per okno — tabela rezerwacji z unikalnym
    (magazyn, dzień, okno, miejsce) dopiero gdy zatwierdzeń będzie tyle, że to zaboli."""
    if warehouse_id is not None:
        db.execute(select(Warehouse.id).where(Warehouse.id == warehouse_id).with_for_update())


def is_free(db: Session, warehouse: Warehouse | None, day: datetime.date | None,
            slot: str, container_id: int) -> bool:
    return any(s["time"] == slot and s["free"] > 0
               for s in free_slots(db, warehouse, day, exclude_container_id=container_id))
