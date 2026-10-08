"""Cykl planowania dostawy — jedyne miejsce z regułą zamrożenia daty.

`Container.notify_date` jest jednocześnie planowaną datą dostawy i kluczem dnia
w kolejce. Żeby ETA z API nie przestawiała w tle terminu uzgodnionego ze spedycją,
automatyczne przeliczanie działa wyłącznie na nietkniętej propozycji. Wszędzie
indziej zmiana ETA jedynie podnosi alert — decyzję o przeplanowaniu podejmuje człowiek.
"""
import datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .audit import record, record_changes
from .models import Container, DailyLimit, PlanningStatus, Warehouse, today_pl, utcnow

# domyślne wyprzedzenie: rozładunek planujemy 4 dni po przypłynięciu
PLAN_LEAD_DAYS = 4


def proposed_date(eta: datetime.date) -> datetime.date:
    """Domyślna data dostawy wyliczona z ETA."""
    return eta + datetime.timedelta(days=PLAN_LEAD_DAYS)


def transit_days_for(port, month: int) -> int | None:
    """Transit time portu dla danego miesiąca.

    Kolejność: wartość sezonowa z `port.transit_rows` → `port.transit_time_days`
    (wartość domyślna, gdy miesiąca brak — np. dane klienta kończą się na wrześniu)
    → None, gdy port nie ma żadnej liczby.
    """
    if port is None:
        return None
    for row in port.transit_rows:
        if row.month == month:
            return row.days
    return port.transit_time_days


def estimated_eta(container: Container) -> datetime.date | None:
    """D12: fallback ETA dla kontenera bez ETA z trackingu (AIS) — ETD +
    transit time portu w miesiącu wypłynięcia. Tylko do wyświetlenia jako „szacunek”:
    nie zapisuje `eta` ani nie rusza planowania (to dalej stała PLAN_LEAD_DAYS)."""
    if container.eta or not container.etd:
        return None
    days = transit_days_for(container.port, container.etd.month)
    return None if days is None else container.etd + datetime.timedelta(days=days)


def send_to_forwarder(db: Session, container: Container, user) -> None:
    """Zamraża plan i oznacza go jako wysłany do spedycji.

    Zdjęcie ETA (`planning_eta_at_send`) jest punktem odniesienia dla alertu
    „ETA przesunięta o X dni". Commit należy do wołającego.
    """
    container.planning_status = PlanningStatus.WYSLANE
    container.planning_sent_at = utcnow()
    container.planning_eta_at_send = container.eta
    record(db, entity_type="containers", entity_id=container.id, field="planning_status",
           old_value=None, new_value=PlanningStatus.WYSLANE.value, user=user,
           note="wysłano plan do spedycji")


def confirm_plan(db: Session, container: Container, day: datetime.date, confirmed_by,
                 note: str = "potwierdzenie planu przez spedycję") -> None:
    """Spedycja uzgodniła datę. `confirmed_by` = None przy potwierdzeniu tokenem.

    Wołane z obu dróg wejścia (portal i publiczny formularz), żeby reguła istniała
    w jednym miejscu. Commit należy do wołającego.
    """
    # publiczny link tokenowy nie wygasa natychmiast — bez tego progu dałoby się nim
    # przestawić dostawę na dowolny dzień, także wstecz
    if day < today_pl():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Data dostawy nie może być z przeszłości.")
    changes = {"planning_status": PlanningStatus.POTWIERDZONE}
    if container.notify_date != day:
        # uzgodniona data jest ręczna: automat ETA nie może jej ruszyć nawet po resecie
        changes["notify_date"] = day
        changes["notify_date_manual"] = True
    record_changes(db, container, changes, user=confirmed_by, note=note)
    # kto uzgodnił — osobny wpis, bo pole jest poza record_changes
    record(db, entity_type="containers", entity_id=container.id,
           field="planning_confirmed_by_id", old_value=str(container.planning_confirmed_by_id),
           new_value=str(confirmed_by.id) if confirmed_by else None, user=confirmed_by, note=note)
    container.planning_confirmed_at = utcnow()
    container.planning_confirmed_by_id = confirmed_by.id if confirmed_by else None
    record_if_over_limit(db, container, confirmed_by)


def record_if_over_limit(db: Session, container: Container, user) -> None:
    """Ślad „kto zignorował limit”: zapis ponad dzienny limit magazynu przechodzi
    (ostrzeżenie, nie blokada), ale zostawia wpis w audycie. Liczy jak kolejka:
    tylko uzgodnione (POTWIERDZONE), niezakończone, bez tranzytów."""
    db.flush()   # synchronizuje FK z relacją (POST /warehouse przypisuje relację)
    # magazyn po FK, nie przez relację: PATCH zmienia sam warehouse_id, a załadowana
    # relacja container.warehouse wskazywałaby jeszcze stary magazyn
    wh = db.get(Warehouse, container.warehouse_id) if container.warehouse_id else None
    day = container.notify_date
    if (wh is None or day is None or container.is_transit
            or container.status in Container.FINISHED
            or container.planning_status != PlanningStatus.POTWIERDZONE):
        return
    override = db.scalar(select(DailyLimit.limit).where(
        DailyLimit.warehouse_id == wh.id, DailyLimit.day == day))
    limit = wh.default_daily_limit if override is None else override
    used = db.scalar(select(func.count(Container.id)).where(
        Container.warehouse_id == wh.id, Container.notify_date == day,
        Container.status.notin_(Container.FINISHED), Container.is_transit.isnot(True),
        Container.planning_status == PlanningStatus.POTWIERDZONE)) or 0
    if limit is not None and used > limit:
        record(db, entity_type="containers", entity_id=container.id, field="daily_limit",
               old_value=limit, new_value=used, user=user,
               note=f"przekroczono limit dzienny {wh.name} {day.isoformat()}: {used}/{limit}")


def reset_plan(db: Session, container: Container, user, note: str) -> None:
    """Cofa plan do propozycji i czyści ślad potwierdzenia.

    Wołane, gdy ktoś zmienia datę uzgodnioną ze spedycją: inaczej rekord dalej
    udawałby uzgodniony i wciąż zajmowałby slot w dziennym limicie. Kasujemy też
    zdjęcie ETA — nowa data wymaga nowej rundy wysyłki, a stare zdjęcie dawałoby
    fałszywy alert „ETA przesunięta o X dni".
    """
    record_changes(db, container, {"planning_status": PlanningStatus.PROPOZYCJA},
                   user=user, note=note)
    # ślad „kto uzgodnił poprzednią datę" musi przeżyć reset — inaczej spór jest nierozstrzygalny
    record(db, entity_type="containers", entity_id=container.id,
           field="planning_confirmed_by_id", old_value=str(container.planning_confirmed_by_id),
           new_value=None, user=user, note=note)
    container.planning_confirmed_at = None
    container.planning_confirmed_by_id = None
    container.planning_sent_at = None
    container.planning_eta_at_send = None


def eta_shift_days(container: Container) -> int | None:
    """O ile dni ETA przesunęła się od zamrożenia planu. None = brak zdjęcia ETA.

    Dodatnia wartość = statek spóźniony względem stanu z chwili wysyłki do spedycji.
    """
    if not container.planning_eta_at_send or not container.eta:
        return None
    return (container.eta - container.planning_eta_at_send).days
