"""Oś czasu kontenera: 4 źródła + etapy planowane w jednej chronologii."""
import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    AuditLog,
    Container,
    ContainerStatus,
    PurchaseOrder,
    TrackedVessel,
    TrackingEvent,
    VesselPortCall,
)
from ..schemas import TimelineEntryOut
from .ais import normalize_name

_STATUS_PL = {
    # etykiety = etapy procesu (numer · nazwa), jak w interfejsie
    "ZAPOWIEDZIANY": "1 · Planowanie zakupu", "W_PRODUKCJI": "2 · Produkcja / gotowość",
    "TRANSPORT_WSTEPNY": "3 · Transport wstępny", "W_TRANSPORCIE": "4 · Transport morski",
    "W_PORCIE": "4 · Port docelowy", "ODPRAWA": "8 · Odprawa celna", "AWIZOWANY": "9 · Awizowany",
    "W_DOSTAWIE": "9 · Dostawa krajowa", "DOSTARCZONY": "10 · Przyjęcie na magazyn",
    "ZREALIZOWANY": "10 · Rozliczone",
}
# statusy, przy których notify_date traktujemy jako pewną (nie "planned"/estimated)
# w osi czasu — UWAGA: to NIE jest to samo co Container.FINISHED (models.py), który
# nie obejmuje W_DOSTAWIE. Różne pojęcia: FINISHED = formalnie zakończony, tu = data
# awizacji jest już na tyle pewna, że nie warto jej dalej oznaczać jako szacunek.
_NOTIFY_DATE_CONFIRMED_STATUSES = {ContainerStatus.W_DOSTAWIE, ContainerStatus.DOSTARCZONY,
                                   ContainerStatus.ZREALIZOWANY}


def _dt(d: datetime.date) -> datetime.datetime:
    return datetime.datetime.combine(d, datetime.time.min)


def build_timeline(db: Session, container: Container,
                   hide_orders: bool = False) -> list[TimelineEntryOut]:
    """hide_orders: rola nie widzi numerów zamówień (hidden_fields) — bez wpisów „Zamówienie …"."""
    entries: list[TimelineEntryOut] = []

    # order — zamówienia z arkusza ETD podpięte do kontenera
    for po in [] if hide_orders else db.scalars(
            select(PurchaseOrder).where(PurchaseOrder.container_id == container.id)):
        if po.etd:
            entries.append(TimelineEntryOut(
                kind="order", code="PO_ETD",
                title=f"Zamówienie {po.order_no} — planowane wypłynięcie",
                location=po.port_of_departure, at=_dt(po.etd),
                estimated=True, source="etd-sheet"))

    # carrier — zdarzenia armatora
    events = db.scalars(select(TrackingEvent)
                        .where(TrackingEvent.container_id == container.id)
                        .order_by(TrackingEvent.occurred_at.asc().nulls_last(),
                                  TrackingEvent.id)).all()
    for ev in events:
        entries.append(TimelineEntryOut(
            kind="carrier", code=ev.event_code, title=ev.description,
            location=" · ".join(x for x in (ev.location, ev.vessel) if x),
            at=ev.occurred_at, estimated=ev.is_estimated, source=ev.source))

    # vessel — postoje portowe statku kontenera (geofence AIS)
    if container.vessel:
        vessel = db.scalar(select(TrackedVessel)
                           .where(TrackedVessel.name == normalize_name(container.vessel)))
        if vessel:
            for pc in db.scalars(select(VesselPortCall)
                                 .where(VesselPortCall.vessel_id == vessel.id)
                                 .order_by(VesselPortCall.arrived_at)):
                entries.append(TimelineEntryOut(
                    kind="vessel", code="PORT_ARRIVE",
                    title=f"Statek w porcie {pc.port}", location=pc.port,
                    at=pc.arrived_at, estimated=False, source="ais"))
                if pc.departed_at:
                    entries.append(TimelineEntryOut(
                        kind="vessel", code="PORT_DEPART",
                        title=f"Statek wyszedł z portu {pc.port}", location=pc.port,
                        at=pc.departed_at, estimated=False, source="ais"))

    # system — TYLKO zmiany statusu kontenera z audytu
    for a in db.scalars(select(AuditLog)
                        .where(AuditLog.entity_type == "containers",
                               AuditLog.entity_id == container.id,
                               AuditLog.field == "status")
                        .order_by(AuditLog.created_at)):
        label = _STATUS_PL.get(a.new_value or "", a.new_value or "?")
        entries.append(TimelineEntryOut(
            kind="system", code=f"STATUS_{a.new_value}",
            title=f"Status: {label}", location="",
            at=a.created_at, estimated=False, source="system"))

    # kamienie milowe / planned — logika przeniesiona 1:1 z osi w ContainerPage:
    # ETD tylko gdy brak zdarzenia DEPART (dublują się ze zdarzeniami przewoźnika)
    if container.etd and not any(e.event_code == "DEPART" for e in events):
        entries.append(TimelineEntryOut(
            kind="planned", code="ETD", title="ETD", location="",
            at=_dt(container.etd), estimated=False, source="system"))
    if container.atd:
        entries.append(TimelineEntryOut(
            kind="planned", code="ATD", title="Dostarczono (ATD)", location="",
            at=_dt(container.atd), estimated=False, source="system"))
    elif container.eta:
        entries.append(TimelineEntryOut(
            kind="planned", code="ETA", title="ETA", location="",
            at=_dt(container.eta), estimated=True, source="system"))
    if container.notify_date:
        entries.append(TimelineEntryOut(
            kind="planned", code="NOTIFY", title="Awizacja", location="",
            at=_dt(container.notify_date),
            estimated=container.status not in _NOTIFY_DATE_CONFIRMED_STATUSES,
            source="system"))

    # demurrage: koniec wolnych dni armatora (start = przybycie z trackingu albo ETA).
    # Kwoty nie pokazujemy — stawka armatora nie jest nigdzie w systemie przechowywana.
    from ..notifications import demurrage_window
    window = demurrage_window(db, container)
    if window is not None:
        start, free_days, deadline, estimated = window
        entries.append(TimelineEntryOut(
            kind="planned", code="DEMURRAGE",
            title=f"Koniec wolnych dni demurrage ({free_days} dni od {start})",
            location=f"{start} +{free_days}d",   # format neutralny językowo (ct-sub)
            at=_dt(deadline), estimated=estimated, source="system"))

    entries.sort(key=lambda e: (e.at is None, e.at or datetime.datetime.min))
    return entries
