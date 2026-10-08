"""Wyceny (RFQ): zlecenie transportowe = paczka kontenerów wysyłana spedycjom.

Obieg: logistyka tworzy zlecenie (SZKIC) z kontenerów i zaprasza spedycje →
wysyła (WYSLANE) → spedytorzy widzą TYLKO wysłane zlecenia, w których zostali
zaproszeni, i TYLKO swoją ofertę → podają cenę → logistyka porównuje i wybiera
zwycięzcę (ZLECONE). E-mail/in-app na każdym etapie.
"""
import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import record
from ..database import get_db
from ..date_pl import date_pl
from ..deps import (
    Editors as editors,
)
from ..deps import (
    ViewerNoPurchasing as viewer_np,
)
from ..deps import get_scoped
from ..models import (
    Container,
    Forwarder,
    Quote,
    QuoteStatus,
    Role,
    TransportJob,
    TransportJobContainer,
    TransportJobStatus,
    User,
    utcnow,
)
from ..notifications import forwarder_users, notify
from ..schemas import (
    AgentIn,
    JobUpdateIn,
    TransportJobCreate,
    TransportJobOut,
)
from . import quotes_offers, quotes_stats
from .quotes_core import (  # noqa: F401 — ensure_transit_quote: publiczny import z .quotes
    _LOAD,
    _VISIBLE_TO_FORWARDER,
    _get_job,
    _job_out,
    _logistics_admins,
    _next_number,
    _scope_jobs,
    _winning_quote,
    ensure_transit_quote,
)

router = APIRouter(prefix="/api", tags=["wyceny"])


@router.get("/transport-jobs", response_model=list[TransportJobOut])
def list_jobs(db: Session = Depends(get_db), user: User = viewer_np):
    query = select(TransportJob).options(*_LOAD).order_by(TransportJob.id.desc())
    if user.role == Role.forwarder:
        if user.forwarder_id is None:
            return []
        query = query.where(
            TransportJob.status.in_(_VISIBLE_TO_FORWARDER),
            TransportJob.quotes.any(Quote.forwarder_id == user.forwarder_id))
    elif user.role not in (Role.admin, Role.logistics):
        return []  # magazyn itp. nie uczestniczy w wycenach
    else:
        query = _scope_jobs(query, user)  # logistyk scoped-do-firmy widzi tylko swoje
    return [_job_out(j, user) for j in db.scalars(query).all()]


@router.get("/transport-jobs/{job_id}", response_model=TransportJobOut)
def get_job(job_id: int, db: Session = Depends(get_db), user: User = viewer_np):
    return _job_out(_get_job(db, job_id, user), user)


@router.post("/transport-jobs", response_model=TransportJobOut, status_code=201)
def create_job(body: TransportJobCreate, db: Session = Depends(get_db), user: User = editors):
    containers = []
    for cid in dict.fromkeys(body.container_ids):
        container = get_scoped(db, Container, cid, user)
        containers.append(container)
    if len({c.company_id for c in containers}) > 1:
        # oferty/ceny dotyczą całego zlecenia — mieszanie spółek ujawniałoby je drugiej spółce
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Zlecenie transportowe może obejmować kontenery tylko jednej spółki.")
    forwarders = []
    for fid in dict.fromkeys(body.forwarder_ids):
        fwd = db.get(Forwarder, fid)
        if not fwd or not fwd.is_active:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Spedytor {fid} nie istnieje.")
        forwarders.append(fwd)

    job = TransportJob(
        number=_next_number(db), status=TransportJobStatus.SZKIC,
        pickup_location=body.pickup_location, delivery_location=body.delivery_location,
        note=body.note, response_hours=body.response_hours, scfi_index=body.scfi_index,
        created_by_id=user.id)
    db.add(job)
    try:
        db.flush()   # tu wstawia się unikalny number — równoległy create → 409, nie 500
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Konflikt numeracji zlecenia — spróbuj ponownie.") from None
    for c in containers:
        db.add(TransportJobContainer(job_id=job.id, container_id=c.id))
    for f in forwarders:
        db.add(Quote(job_id=job.id, forwarder_id=f.id, status=QuoteStatus.ZAPYTANIE))
    record(db, entity_type="transport_jobs", entity_id=job.id, field="created",
           old_value=None, new_value=job.number, user=user,
           note=f"{len(containers)} kont., {len(forwarders)} spedycji")
    db.commit()
    return _job_out(_get_job(db, job.id, user), user)


@router.post("/transport-jobs/{job_id}/send", response_model=TransportJobOut)
def send_job(job_id: int, db: Session = Depends(get_db), user: User = editors):
    """Publikacja zlecenia — od teraz zaproszone spedycje je widzą i mogą wyceniać."""
    job = _get_job(db, job_id, user)
    if job.status != TransportJobStatus.SZKIC:
        raise HTTPException(status.HTTP_409_CONFLICT, "Zlecenie zostało już wysłane.")
    job.status = TransportJobStatus.WYSLANE
    job.sent_at = utcnow()
    job.response_deadline = job.sent_at + datetime.timedelta(hours=job.response_hours)
    record(db, entity_type="transport_jobs", entity_id=job.id, field="status",
           old_value="SZKIC", new_value="WYSLANE", user=user,
           note=f"wysłano do wyceny (termin {job.response_hours}h)")
    db.commit()
    deadline_txt = f"{date_pl(job.response_deadline, time=True)} UTC"
    for q in job.quotes:
        recipients = forwarder_users(db, q.forwarder_id)
        notify(db, recipients, kind="order",
               title=f"Zapytanie o wycenę — zlecenie {job.number}",
               body=f"Otrzymałeś zapytanie o wycenę transportu ({len(job.items)} kont.). "
                    f"Termin odpowiedzi: {deadline_txt}. Zaloguj się, aby podać cenę.")
    db.commit()
    return _job_out(_get_job(db, job.id, user), user)


@router.patch("/transport-jobs/{job_id}", response_model=TransportJobOut)
def update_job(job_id: int, body: JobUpdateIn,
               db: Session = Depends(get_db), user: User = editors):
    """Edycja terminu/SCFI (przed rozstrzygnięciem), danych odbioru/dostawy i numeru
    przesyłki. Zmiana danych już wysłanego/zleconego zlecenia alarmuje spedycje (wiersz 19)."""
    job = _get_job(db, job_id, user)
    if job.status == TransportJobStatus.ANULOWANE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Zlecenie zostało anulowane.")
    # termin i SCFI mają sens tylko do rozstrzygnięcia; numer przesyłki dochodzi zwykle później
    if body.response_hours is not None or body.scfi_index is not None:
        if job.status == TransportJobStatus.ZLECONE:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "Zlecenie jest już zlecone — nie zmieniasz terminu/SCFI.")
        if body.response_hours is not None:
            job.response_hours = body.response_hours
            if job.sent_at:  # przelicz termin od momentu wysłania
                job.response_deadline = job.sent_at + datetime.timedelta(hours=body.response_hours)
        if body.scfi_index is not None:
            job.scfi_index = body.scfi_index
    # zmiany istotne dla spedycji (miejsce odbioru/dostawy, notatka, nr przesyłki) → alert
    changed: list[str] = []
    for attr, value, label in (
        ("pickup_location", body.pickup_location, "miejsce odbioru"),
        ("delivery_location", body.delivery_location, "miejsce dostawy"),
        ("note", body.note, "uwagi"),
        ("shipment_number", body.shipment_number, "numer przesyłki"),
    ):
        if value is not None and value != getattr(job, attr):
            setattr(job, attr, value)
            changed.append(label)
    record(db, entity_type="transport_jobs", entity_id=job.id, field="deadline",
           old_value=None,
           new_value=f"{job.response_hours}h / SCFI {job.scfi_index or '—'} / "
                     f"przesyłka {job.shipment_number or '—'}",
           user=user, note="edycja terminu/SCFI/nr przesyłki")
    db.commit()
    # wiersz 19: powiadom zainteresowane spedycje o zmianie w wysłanym/zleconym zleceniu
    if changed and job.status in (TransportJobStatus.WYSLANE, TransportJobStatus.ZLECONE):
        if job.status == TransportJobStatus.ZLECONE:
            won = _winning_quote(job)
            targets = [won] if won else []
        else:
            targets = list(job.quotes)
        for q in targets:
            notify(db, forwarder_users(db, q.forwarder_id), kind="order",
                   title=f"Zmiana w zleceniu — {job.number}",
                   body=f"Zaktualizowano: {', '.join(changed)}. Sprawdź szczegóły zlecenia.")
        db.commit()
    return _job_out(_get_job(db, job.id, user), user)


@router.post("/transport-jobs/{job_id}/agent", response_model=TransportJobOut)
def submit_agent(job_id: int, body: AgentIn, db: Session = Depends(get_db), user: User = viewer_np):
    """Wygrywająca spedycja podaje dane agenta (imię/nazwisko, telefon, firma)
    oraz numer przesyłki (Q49)."""
    if user.role != Role.forwarder or user.forwarder_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tylko spedytor może podać agenta.")
    job = _get_job(db, job_id, user)
    winner = _winning_quote(job)
    if job.status != TransportJobStatus.ZLECONE or winner is None \
            or winner.forwarder_id != user.forwarder_id:
        # agenta podaje wyłącznie zwycięska spedycja po rozstrzygnięciu
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tylko zwycięska spedycja po wyborze oferty.")
    # pusty numer przesyłki nie kasuje już wpisanego
    new_ship = body.shipment_number or job.shipment_number
    # ponowne przesłanie tych samych danych nie robi nic (bez spamu do logistyki)
    if (body.agent_name, body.agent_phone, body.agent_company, new_ship) == (
            job.agent_name, job.agent_phone, job.agent_company, job.shipment_number):
        return _job_out(job, user)
    job.agent_name = body.agent_name
    job.agent_phone = body.agent_phone
    job.agent_company = body.agent_company
    job.shipment_number = new_ship
    job.agent_submitted_at = utcnow()
    record(db, entity_type="transport_jobs", entity_id=job.id, field="agent",
           old_value=None, new_value=f"{body.agent_name} ({body.agent_company})",
           user=user, note=f"agent od spedycji {winner.forwarder.name}")
    db.commit()
    # wiersz 17: info od spedycji z agentem → do logistyki
    notify(db, _logistics_admins(db), kind="order",
           title=f"Agent spedycji — {job.number}",
           body=f"{winner.forwarder.name}: {body.agent_name}"
                f"{' · ' + body.agent_phone if body.agent_phone else ''}"
                f"{' · ' + body.agent_company if body.agent_company else ''}")
    db.commit()
    return _job_out(_get_job(db, job.id, user), user)


# oferty/rozstrzygnięcie i statystyki żyją w osobnych modułach; dołączone na końcu,
# więc kolejność tras (i prefiks /api, tag „wyceny”) jest taka jak przed podziałem
router.include_router(quotes_offers.router)
router.include_router(quotes_stats.router)
