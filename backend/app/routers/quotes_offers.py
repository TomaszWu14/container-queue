"""Wyceny (RFQ): oferty spedycji i rozstrzygnięcie zlecenia.

Zmiana ceny (Q55/Q56), historia oferty (Q47), złożenie wyceny, wybór zwycięzcy (Q39/Q40),
anulowanie i wznowienie zlecenia. Router bez prefiksu — prefiks /api i tag nadaje
quotes.router, który go dołącza.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..audit import record
from ..database import get_db
from ..deps import (
    Editors as editors,
)
from ..deps import (
    ViewerNoPurchasing as viewer_np,
)
from ..models import (
    Carrier,
    QuoteStatus,
    Role,
    TransportJobStatus,
    User,
    utcnow,
)
from ..notifications import forwarder_users, notify
from ..schemas import (
    CancelJobIn,
    ChooseQuoteIn,
    PriceRevisionIn,
    QuoteRevisionOut,
    QuoteSubmitIn,
    TransportJobOut,
)
from .quotes_core import (
    _get_job,
    _job_out,
    _logistics_admins,
    _score_quotes,
    _snapshot_quote,
)

router = APIRouter()


@router.post("/transport-jobs/{job_id}/price-change", response_model=TransportJobOut)
def revise_price(job_id: int, body: PriceRevisionIn,
                 db: Session = Depends(get_db), user: User = viewer_np):
    """Q55: każda zaproszona spedycja może zgłosić pilną zmianę ceny; zmiana czeka na
    akceptację logistyki (Q56), zanim zastąpi cenę oferty."""
    if user.role != Role.forwarder or user.forwarder_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tylko spedytor może zgłosić zmianę ceny.")
    job = _get_job(db, job_id, user)
    if job.status not in (TransportJobStatus.WYSLANE, TransportJobStatus.ZLECONE):
        raise HTTPException(status.HTTP_409_CONFLICT, "Zmiana ceny możliwa tylko dla aktywnego zlecenia.")
    quote = next((q for q in job.quotes if q.forwarder_id == user.forwarder_id), None)
    if quote is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Brak zaproszenia do wyceny.")
    if quote.submitted_at is None:
        # nie ma czego korygować, jeśli spedycja nie złożyła jeszcze oferty
        raise HTTPException(status.HTTP_409_CONFLICT, "Najpierw złóż wycenę.")
    # ponowne zgłoszenie tej samej (jeszcze nieakceptowanej) zmiany nie robi nic
    if body.revised_amount == quote.revised_amount and body.revised_note == quote.revised_note:
        return _job_out(job, user)
    prev = quote.amount
    quote.revised_amount = body.revised_amount  # niepuste = oczekuje na akceptację logistyki
    quote.revised_note = body.revised_note
    quote.revised_at = utcnow()
    record(db, entity_type="quotes", entity_id=quote.id, field="revised_amount",
           old_value=str(prev), new_value=f"{body.revised_amount} {quote.currency}",
           user=user, note=f"pilna zmiana ceny — {quote.forwarder.name}")
    _snapshot_quote(db, quote, "zgłoszenie zmiany", user,
                    amount=body.revised_amount, note=body.revised_note)
    db.commit()
    # pilny alert do logistyki (dawna cena → nowa cena, do akceptacji)
    notify(db, _logistics_admins(db), kind="order",
           title=f"⚠ Pilna zmiana ceny (do akceptacji) — {job.number}",
           body=f"{quote.forwarder.name}: {prev} → {body.revised_amount} "
                f"{quote.currency}."
                f"{' Powód: ' + body.revised_note if body.revised_note else ''}")
    db.commit()
    return _job_out(_get_job(db, job.id, user), user)


@router.post("/transport-jobs/{job_id}/quotes/{quote_id}/approve-price",
             response_model=TransportJobOut)
def approve_price_revision(job_id: int, quote_id: int,
                           db: Session = Depends(get_db), user: User = editors):
    """Q56: logistyka akceptuje zgłoszoną zmianę ceny — nowa cena zastępuje ofertę."""
    job = _get_job(db, job_id, user)
    if job.status not in (TransportJobStatus.WYSLANE, TransportJobStatus.ZLECONE):
        raise HTTPException(status.HTTP_409_CONFLICT, "Zlecenie nie jest aktywne.")
    quote = next((q for q in job.quotes if q.id == quote_id), None)
    if quote is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono oferty.")
    if quote.revised_amount is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Brak oczekującej zmiany ceny do akceptacji.")
    old = quote.amount
    # nowa cena zastępuje ofertę; wyczyszczenie danych rewizji kończy stan „oczekuje"
    quote.amount = quote.revised_amount
    quote.revised_amount = None
    quote.revised_note = ""
    quote.revised_at = None
    record(db, entity_type="quotes", entity_id=quote.id, field="amount",
           old_value=str(old), new_value=f"{quote.amount} {quote.currency}",
           user=user, note=f"zaakceptowano zmianę ceny — {quote.forwarder.name}")
    _snapshot_quote(db, quote, "akceptacja", user, note="akceptacja zmiany ceny")
    db.commit()
    notify(db, forwarder_users(db, quote.forwarder_id), kind="order",
           title=f"Zmiana ceny zaakceptowana — {job.number}",
           body=f"Logistyka zaakceptowała nową cenę {quote.amount} {quote.currency}.")
    db.commit()
    return _job_out(_get_job(db, job.id, user), user)


@router.get("/transport-jobs/{job_id}/quotes/{quote_id}/history",
            response_model=list[QuoteRevisionOut])
def quote_history(job_id: int, quote_id: int,
                  db: Session = Depends(get_db), user: User = viewer_np):
    """Historia wersji oferty (Q47) — logistyka dla dowolnej oferty, spedytor tylko własnej."""
    job = _get_job(db, job_id, user)
    quote = next((q for q in job.quotes if q.id == quote_id), None)
    if quote is None or (user.role == Role.forwarder
                         and quote.forwarder_id != user.forwarder_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono oferty.")
    return [QuoteRevisionOut(
        id=r.id, amount=r.amount, currency=r.currency, note=r.note, kind=r.kind,
        created_by_login=r.created_by.login if r.created_by else None,
        created_at=r.created_at) for r in quote.revisions]


@router.post("/transport-jobs/{job_id}/quote", response_model=TransportJobOut)
def submit_quote(job_id: int, body: QuoteSubmitIn,
                 db: Session = Depends(get_db), user: User = viewer_np):
    """Spedytor podaje cenę dla swojego zaproszenia."""
    if user.role != Role.forwarder or user.forwarder_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tylko spedytor może wyceniać.")
    job = _get_job(db, job_id, user)
    # Q36: oferty przyjmujemy aż do wyboru zwycięzcy — po terminie też (termin jest
    # informacyjny, mierzony w KPI); blokujemy dopiero gdy zlecenie nie jest już WYSLANE
    if job.status != TransportJobStatus.WYSLANE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Zlecenie nie przyjmuje już wycen.")
    quote = next((q for q in job.quotes if q.forwarder_id == user.forwarder_id), None)
    if quote is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Brak zaproszenia do wyceny.")
    if body.carrier_id is not None and not db.get(Carrier, body.carrier_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono armatora.")
    revision_kind = "korekta" if quote.submitted_at else "wycena"   # kolejne złożenie = korekta
    quote.amount = body.amount
    quote.currency = body.currency
    quote.valid_until = body.valid_until
    quote.note = body.note
    quote.carrier_id = body.carrier_id
    quote.etd = body.etd
    quote.eta = body.eta
    quote.transit_time_days = body.transit_time_days
    quote.no_equipment = body.no_equipment
    quote.can_roll_booking = body.can_roll_booking
    quote.status = QuoteStatus.WYCENIONA
    quote.submitted_at = utcnow()
    record(db, entity_type="quotes", entity_id=quote.id, field="amount",
           old_value=None, new_value=f"{body.amount} {body.currency}", user=user,
           note=f"wycena zlecenia {job.number}")
    _snapshot_quote(db, quote, revision_kind, user, note=body.note)
    db.commit()
    notify(db, _logistics_admins(db), kind="order",
           title=f"Wycena — {job.number}",
           body=f"{quote.forwarder.name}: {body.amount} {body.currency}")
    db.commit()
    return _job_out(_get_job(db, job.id, user), user)


@router.post("/transport-jobs/{job_id}/choose", response_model=TransportJobOut)
def choose_quote(job_id: int, body: ChooseQuoteIn,
                 db: Session = Depends(get_db), user: User = editors):
    """Wybór zwycięskiej oferty — pozostałe zostają odrzucone; powiadomienia do spedycji."""
    job = _get_job(db, job_id, user)
    winner = next((q for q in job.quotes if q.id == body.quote_id), None)
    if winner is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono oferty.")
    if winner.status != QuoteStatus.WYCENIONA:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ta oferta nie ma jeszcze ceny.")
    # Q40: wybór oferty gorszej niż najlepiej oceniona w rankingu wymaga uzasadnienia
    # (oferty o równie wysokim wyniku są współrekomendowane — nie wymagają powodu)
    scores, top = _score_quotes(job.quotes)
    if top is not None and scores.get(winner.id, -1) < scores[top] and not body.reason.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Wybór oferty innej niż rekomendowana wymaga uzasadnienia.")
    for q in job.quotes:
        if q.id == winner.id:
            q.status = QuoteStatus.WYBRANA
        elif q.submitted_at:
            q.status = QuoteStatus.ODRZUCONA
        else:
            q.status = QuoteStatus.WYGASLA   # nie wyceniono w terminie — wygasło, nie odrzucono
    job.chosen_quote_id = winner.id
    job.chosen_at = utcnow()
    job.status = TransportJobStatus.ZLECONE
    record(db, entity_type="transport_jobs", entity_id=job.id, field="chosen_quote",
           old_value=None, new_value=f"{winner.forwarder.name} {winner.amount} {winner.currency}",
           user=user, note=f"wybrano ofertę do zlecenia {job.number}"
                          + (f" — {body.reason.strip()}" if body.reason.strip() else ""))
    db.commit()
    # zwycięzca: gratulacje + prośba o dane agenta (wiersz 16/17)
    notify(db, forwarder_users(db, winner.forwarder_id), kind="order",
           title=f"Wygrana wycena — {job.number}",
           body=f"Twoja oferta {winner.amount} {winner.currency} została wybrana. "
                f"Uzupełnij dane agenta (imię i nazwisko, telefon, firma) na swoim koncie.")
    for q in job.quotes:
        if q.id == winner.id:
            continue
        if q.submitted_at:  # oferta odrzucona (wpłynęła, ale nie wygrała)
            notify(db, forwarder_users(db, q.forwarder_id), kind="order",
                   title=f"Wynik wyceny — {job.number}",
                   body="Dziękujemy za ofertę. Tym razem wybrano inną spedycję.")
        else:  # brak wyceny w terminie — oferta wygasła
            notify(db, forwarder_users(db, q.forwarder_id), kind="order",
                   title=f"Wygaśnięcie zapytania — {job.number}",
                   body="Zapytanie o wycenę zostało zamknięte (brak oferty w terminie).")
    # wiersz 16: brak numeru przesyłki po wyborze → przypomnienie do logistyki
    if not job.shipment_number.strip():
        notify(db, _logistics_admins(db), kind="order",
               title=f"Uzupełnij numer przesyłki — {job.number}",
               body="Zlecenie zostało przydzielone spedycji, ale brakuje numeru przesyłki. "
                    "Dodaj go w szczegółach zlecenia.")
    db.commit()
    return _job_out(_get_job(db, job.id, user), user)


@router.post("/transport-jobs/{job_id}/cancel", response_model=TransportJobOut)
def cancel_job(job_id: int, body: CancelJobIn,
               db: Session = Depends(get_db), user: User = editors):
    """Anulowanie zlecenia z obowiązkowym powodem — także zlecenia już przydzielonego
    (wiersz 20). Zaproszone spedycje dostają powiadomienie z powodem."""
    job = _get_job(db, job_id, user)
    if job.status == TransportJobStatus.ANULOWANE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Zlecenie jest już anulowane.")
    prev = job.status
    job.status = TransportJobStatus.ANULOWANE
    job.cancel_reason = body.reason
    job.cancelled_at = utcnow()
    job.chosen_quote_id = None   # anulowane zlecenie nie ma zwycięzcy (raporty/eksport)
    job.chosen_at = None
    for q in job.quotes:
        q.status = QuoteStatus.ODRZUCONA
    record(db, entity_type="transport_jobs", entity_id=job.id, field="status",
           old_value=prev.value, new_value="ANULOWANE", user=user,
           note=f"anulowano zlecenie: {body.reason}")
    db.commit()
    # powiadom spedycje, które już zobaczyły zlecenie (wysłane/przydzielone)
    if prev in (TransportJobStatus.WYSLANE, TransportJobStatus.ZLECONE):
        for q in job.quotes:
            notify(db, forwarder_users(db, q.forwarder_id), kind="order",
                   title=f"Anulowano zlecenie — {job.number}",
                   body=f"Zlecenie zostało anulowane. Powód: {body.reason}")
        db.commit()
    return _job_out(_get_job(db, job.id, user), user)


@router.post("/transport-jobs/{job_id}/reopen", response_model=TransportJobOut)
def reopen_job(job_id: int, db: Session = Depends(get_db), user: User = editors):
    """Wznowienie anulowanego zlecenia (Q58) — wraca do szkicu z tymi samymi kontenerami
    i spedycjami, do ponownej wysyłki. Czyści dane rozstrzygnięcia i anulowania."""
    job = _get_job(db, job_id, user)
    if job.status != TransportJobStatus.ANULOWANE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Wznowić można tylko anulowane zlecenie.")
    job.status = TransportJobStatus.SZKIC
    job.cancel_reason = ""
    job.cancelled_at = None
    job.chosen_quote_id = None
    job.chosen_at = None
    job.sent_at = None
    job.response_deadline = None
    # wyczyść dane rozstrzygnięcia poprzedniego cyklu (agent, numer przesyłki)
    job.agent_name = job.agent_phone = job.agent_company = ""
    job.agent_submitted_at = None
    job.shipment_number = ""
    for q in job.quotes:
        q.status = QuoteStatus.ZAPYTANIE
        q.amount = None
        q.submitted_at = None
        q.revised_amount = None
        q.revised_note = ""
        q.revised_at = None
        # również dane oferty z poprzedniego cyklu, by nie wyciekły do nowej wyceny
        q.carrier_id = None
        q.etd = q.eta = None
        q.transit_time_days = None
        q.valid_until = None
        q.note = ""
        q.no_equipment = q.can_roll_booking = False
    record(db, entity_type="transport_jobs", entity_id=job.id, field="status",
           old_value="ANULOWANE", new_value="SZKIC", user=user, note="wznowiono zlecenie")
    db.commit()
    return _job_out(_get_job(db, job.id, user), user)
