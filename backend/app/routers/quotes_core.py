"""Wyceny (RFQ) — wspólny rdzeń: ładowanie zleceń, izolacja, serializacja i ranking ofert.

Wydzielone z routers/quotes.py (limit 500 linii/plik). Endpointy: quotes.py (obieg
zlecenia), quotes_offers.py (oferty i rozstrzygnięcie), quotes_stats.py (statystyki/eksport).
"""
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..audit import record
from ..deps import check_container_access, company_filter_ids, scope_containers
from ..models import (
    Container,
    Order,
    Quote,
    QuoteRevision,
    QuoteStatus,
    Role,
    SupplierContact,
    TransportJob,
    TransportJobContainer,
    TransportJobStatus,
    User,
    utcnow,
)
from ..notifications import notify
from ..order_numbers import split_order_numbers
from ..schemas import JobKpi, TransportJobOut

# eager-load relacji kontenera używanych w _job_out — bez tego N+1 przy liście zleceń
_CONTAINER = selectinload(TransportJob.items).selectinload(TransportJobContainer.container)
_LOAD = (
    _CONTAINER.selectinload(Container.order).selectinload(Order.supplier_contact),
    _CONTAINER.selectinload(Container.supplier),
    _CONTAINER.selectinload(Container.warehouse),
    selectinload(TransportJob.quotes).selectinload(Quote.forwarder),
    selectinload(TransportJob.quotes).selectinload(Quote.carrier),
)
# statusy widoczne dla spedytora (potwierdzone/wysłane przez nas)
_VISIBLE_TO_FORWARDER = (TransportJobStatus.WYSLANE, TransportJobStatus.ZLECONE)


def _next_number(db: Session) -> str:
    year = utcnow().year   # spójnie z created_at (UTC), by rok numeracji się nie rozjeżdżał
    count = db.scalar(select(func.count(TransportJob.id)).where(
        TransportJob.number.like(f"TJ-{year}-%"))) or 0
    return f"TJ-{year}-{count + 1:04d}"


def _has_transit_number(order_numbers: str | None) -> bool:
    return any(tok.startswith("47") for tok in split_order_numbers(order_numbers))


def ensure_transit_quote(db: Session, container: Container, user: User) -> None:
    """Tranzyt (numer zamówienia od 47): oznacz is_transit + auto-SZKIC wyceny + alert spedycji.

    Idempotentne: nie tworzy drugiego zlecenia, jeśli kontener był już w JAKIMKOLWIEK
    zleceniu — także anulowanym (anulowanie to decyzja logistyki; powrót przez „Wznów”).
    """
    if not _has_transit_number(container.order_numbers):
        return
    if not container.is_transit:
        record(db, entity_type="containers", entity_id=container.id, field="is_transit",
               old_value=False, new_value=True, user=user, note="auto: numer tranzytowy 47…")
        container.is_transit = True
    # jakiekolwiek zlecenie (też anulowane) już obejmuje ten kontener? -> nie duplikuj
    exists = db.scalar(select(TransportJobContainer.id)
                       .where(TransportJobContainer.container_id == container.id).limit(1))
    if exists:
        db.commit()
        return
    job = TransportJob(number=_next_number(db), status=TransportJobStatus.SZKIC,
                       note="auto: tranzyt (numer 47…)", created_by_id=user.id)
    job.items = [TransportJobContainer(container_id=container.id)]
    db.add(job)
    db.flush()
    from ..notifications import acme_team
    notify(db, acme_team(db), kind="quote",
           title=f"Tranzyt do wyceny: {container.container_no}",
           body=f"Auto-utworzono zlecenie {job.number} (SZKIC) — uzupełnij i wyślij zapytanie.")
    db.commit()


def _logistics_admins(db: Session) -> list[User]:
    return list(db.scalars(select(User).where(
        User.is_active, User.role.in_((Role.logistics, Role.admin)))))


# lekki load do statystyk/eksportu — tylko oferty (bez kontenerów/dostawców)
_STATS_LOAD = (selectinload(TransportJob.quotes).selectinload(Quote.forwarder),
               selectinload(TransportJob.items))


def _winning_quote(job: TransportJob) -> Quote | None:
    """Zwycięska oferta zlecenia (wybrana przez logistykę)."""
    return next((q for q in job.quotes if q.id == job.chosen_quote_id), None)


def _snapshot_quote(db: Session, quote: Quote, kind: str, user: User,
                    amount=None, note: str = "") -> None:
    """Zapis wersji oferty do historii (Q47)."""
    db.add(QuoteRevision(
        quote_id=quote.id, amount=quote.amount if amount is None else amount,
        currency=quote.currency, note=note, kind=kind, created_by_id=user.id))


def _deadline_passed(job: TransportJob) -> bool:
    """Czy minął termin odpowiedzi (tylko dla wysłanych, jeszcze nierozstrzygniętych)."""
    return bool(job.status == TransportJobStatus.WYSLANE
                and job.response_deadline and utcnow() > job.response_deadline)


def _quote_out(q: Quote, expired_window: bool = False) -> dict:
    # oferta bez ceny po terminie prezentowana jako „wygasła" (bez zapisu do bazy)
    status = q.status
    if status == QuoteStatus.ZAPYTANIE and expired_window:
        status = QuoteStatus.WYGASLA
    return {
        "id": q.id, "forwarder_id": q.forwarder_id,
        "forwarder_name": q.forwarder.name if q.forwarder else None,
        "status": status, "amount": q.amount, "currency": q.currency,
        "valid_until": q.valid_until, "note": q.note,
        "carrier_id": q.carrier_id,
        "carrier_name": q.carrier.name if q.carrier else None,
        "etd": q.etd, "eta": q.eta, "transit_time_days": q.transit_time_days,
        "no_equipment": q.no_equipment, "can_roll_booking": q.can_roll_booking,
        "submitted_at": q.submitted_at,
        "revised_amount": q.revised_amount, "revised_note": q.revised_note,
        "revised_at": q.revised_at,
    }


# wagi rankingu ważonego ofert (Q39): cena / transit time / niezawodność
_W_PRICE, _W_TRANSIT, _W_RELIABILITY = 0.60, 0.25, 0.15


def _score_quotes(quotes: list[Quote]) -> tuple[dict[int, int], int | None]:
    """Ranking ważony ofert z ceną (Q39). Zwraca {quote_id: score 0-100} i id najlepszej.

    Punktacja: cena (im taniej, tym lepiej), transit time (im krócej, tym lepiej),
    niezawodność (kara za brak sprzętu, bonus za możliwość rolowania). Normalizowane
    względem najlepszej oferty w danym zleceniu."""
    priced = [q for q in quotes if q.amount is not None]
    if not priced:
        return {}, None
    min_price = min(float(q.amount) for q in priced)
    transits = [q.transit_time_days for q in priced if q.transit_time_days is not None]
    min_transit = min(transits) if transits else None
    scores: dict[int, int] = {}
    for q in priced:
        price_s = min_price / float(q.amount) if q.amount else 0.0
        # brak danych = neutralnie (0.5); transit 0 dni jest najlepszy (nie „brak")
        transit_s = (min_transit / q.transit_time_days
                     if q.transit_time_days else (1.0 if q.transit_time_days == 0 else 0.5))
        reliability = 1.0 - (0.5 if q.no_equipment else 0.0) + (0.1 if q.can_roll_booking else 0.0)
        reliability = max(0.0, min(1.0, reliability))
        total = _W_PRICE * price_s + _W_TRANSIT * transit_s + _W_RELIABILITY * reliability
        scores[q.id] = round(total * 100)
    top = max(scores, key=lambda qid: (scores[qid], -qid))  # remis → niższe id (wcześniejsza oferta)
    return scores, top


def _response_rate(responded: int, invited: int) -> int:
    return round(responded * 100 / invited) if invited else 0


def _quote_response_stats(quotes) -> tuple[int, int, int]:
    """(zaproszone, odpowiedziane, % odpowiedzi) z listy ofert — jedna definicja KPI."""
    invited = len(quotes)
    responded = sum(1 for q in quotes if q.submitted_at)
    return invited, responded, _response_rate(responded, invited)


def _job_kpi(job: TransportJob, passed: bool) -> JobKpi:
    invited, responded, rate = _quote_response_stats(job.quotes)
    expired = sum(1 for q in job.quotes
                  if q.status == QuoteStatus.ZAPYTANIE and passed) if passed else 0
    return JobKpi(invited=invited, responded=responded, expired=expired,
                  response_rate=rate, deadline_passed=passed)


def _supplier_contact(container) -> SupplierContact | None:
    """Kontakt do dostawcy z zamówienia kontenera (Q34 — widoczny dla spedycji)."""
    order = getattr(container, "order", None) if container else None
    return getattr(order, "supplier_contact", None) if order else None


def _job_container(it, show_contact: bool) -> dict:
    """Kontener zlecenia; kontakt dostawcy tylko gdy wolno (logistyka / zwycięzca, Q34)."""
    c = it.container
    contact = _supplier_contact(c) if show_contact else None
    return {
        "container_id": it.container_id,
        "container_no": c.container_no if c else "",
        "supplier_name": c.supplier.name if c and c.supplier else None,
        "supplier_contact_name": contact.full_name if contact else None,
        "supplier_contact_email": contact.email if contact else None,
        "supplier_contact_phone": contact.phone if contact else None,
        "order_numbers": c.order_numbers if c else "",
        "warehouse_name": c.warehouse.name if c and c.warehouse else None,
        "eta": c.eta if c else None,
        "notify_date": c.notify_date if c else None,
    }


def _forwarder_view(mine, passed: bool) -> tuple[list, dict | None, str, JobKpi]:
    """Spedytor widzi tylko własną ofertę — nigdy cen konkurencji, SCFI ani liczby odpowiedzi."""
    quotes = [_quote_out(mine, passed)] if mine else []
    my_quote = _quote_out(mine, passed) if mine else None
    return quotes, my_quote, "", JobKpi(deadline_passed=passed)   # SCFI: nie kotwiczymy ceny


def _logistics_view(job: TransportJob, passed: bool) -> tuple[list, None, str, JobKpi]:
    """Logistyka: wszystkie oferty od najtańszej z rankingiem ważonym (Q39) i KPI."""
    scores, top = _score_quotes(job.quotes)
    best = scores[top] if top is not None else None
    quotes = [_quote_out(q, passed) for q in sorted(
        job.quotes, key=lambda q: (q.amount is None, q.amount or 0))]
    for qd in quotes:
        qd["score"] = scores.get(qd["id"])
        # rekomendowane = wszystkie o najlepszym wyniku (spójnie z regułą wyboru bez powodu)
        qd["recommended"] = qd["id"] in scores and scores[qd["id"]] == best
    return quotes, None, job.scfi_index, _job_kpi(job, passed)


def _job_out(job: TransportJob, user: User) -> TransportJobOut:
    """CODE-004: maskowanie per rola w _forwarder_view/_logistics_view i _job_container."""
    passed = _deadline_passed(job)
    is_forwarder = user.role == Role.forwarder
    mine = (next((q for q in job.quotes if q.forwarder_id == user.forwarder_id), None)
            if is_forwarder else None)
    # numer przesyłki, dane agenta i kontakt dostawcy widzi logistyka oraz WYŁĄCZNIE
    # zwycięska spedycja — nie przegrani/rywale (ochrona PII dostawcy, Q34)
    show_ship_agent = (not is_forwarder) or bool(mine and mine.id == job.chosen_quote_id)
    containers = [_job_container(it, show_ship_agent) for it in job.items]
    quotes, my_quote, scfi, kpi = (_forwarder_view(mine, passed) if is_forwarder
                                   else _logistics_view(job, passed))
    agent = ({"shipment_number": job.shipment_number, "agent_name": job.agent_name,
              "agent_phone": job.agent_phone, "agent_company": job.agent_company,
              "agent_submitted_at": job.agent_submitted_at} if show_ship_agent else
             {"shipment_number": "", "agent_name": "", "agent_phone": "", "agent_company": "",
              "agent_submitted_at": None})
    return TransportJobOut(
        id=job.id, number=job.number, status=job.status,
        pickup_location=job.pickup_location, delivery_location=job.delivery_location,
        note=job.note, created_at=job.created_at, sent_at=job.sent_at,
        response_hours=job.response_hours, response_deadline=job.response_deadline,
        scfi_index=scfi, **agent,
        cancel_reason=job.cancel_reason, cancelled_at=job.cancelled_at,
        chosen_quote_id=job.chosen_quote_id,
        container_count=len(job.items), kpi=kpi,
        containers=containers, quotes=quotes, my_quote=my_quote)


def _unrestricted(user: User) -> bool:
    """Widzi kontenery wszystkich spółek i magazynów (admin, logistyk z view_all bez listy magazynów)."""
    return company_filter_ids(user) is None and not (
        user.role == Role.logistics and user.allowed_warehouse_ids)


def _scope_jobs(query, user: User):
    """Ogranicza zapytanie o zlecenia do zakresu użytkownika (bez tego company-scoped logistyk
    widziałby RFQ/KPI/ceny wszystkich firm). Zlecenie widać tylko, gdy WSZYSTKIE jego kontenery
    są w zakresie (scope_containers: spółka + allowed_warehouse_ids) — oferty i ceny dotyczą
    całego zlecenia, więc samo ukrycie cudzych kontenerów nadal ujawniałoby ceny innej spółki."""
    if _unrestricted(user):
        return query
    visible = scope_containers(select(Container.id), user)
    items = select(TransportJobContainer.job_id)
    return query.where(
        TransportJob.id.in_(items.where(TransportJobContainer.container_id.in_(visible))),
        TransportJob.id.not_in(items.where(TransportJobContainer.container_id.not_in(visible))))


def _job_in_company_scope(job: TransportJob, user: User) -> bool:
    """Ta sama reguła co _scope_jobs dla pojedynczego zlecenia (check_container_access)."""
    if _unrestricted(user):
        return True
    if not job.items:
        return False
    try:
        for it in job.items:
            check_container_access(user, it.container)
    except HTTPException:
        return False
    return True


def _get_job(db: Session, job_id: int, user: User) -> TransportJob:
    # w wycenach uczestniczy tylko logistyka/admin oraz zaproszone spedycje —
    # magazyn i inne role nie mają wglądu (inaczej wyciek cen/SCFI/KPI/agenta)
    if user.role not in (Role.admin, Role.logistics, Role.forwarder):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono zlecenia.")
    job = db.scalar(select(TransportJob).options(*_LOAD).where(TransportJob.id == job_id))
    if not job:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono zlecenia.")
    if user.role == Role.forwarder:
        invited = any(q.forwarder_id == user.forwarder_id for q in job.quotes)
        if not invited or job.status not in _VISIBLE_TO_FORWARDER:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono zlecenia.")
    elif not _job_in_company_scope(job, user):
        # logistyk przypisany do spółki nie widzi zleceń innych firm
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono zlecenia.")
    return job
