"""Spedycja: faktury transportowe BL (jedna faktura na zestaw kontenerów) i ich obieg
akceptacji (#42/#50).

Router bez prefiksu — prefiks /api i tag nadaje forwarding.router, który go dołącza.
"""
import datetime
import pathlib
import secrets

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..audit import record
from ..config import settings
from ..database import get_db
from ..deps import (
    AdminOnly as approvers,
)
from ..deps import (
    Editors as editors,
)
from ..deps import (
    PurchasingReaders as freight_readers,
)
from ..deps import (
    get_scoped,
    resolve_company_id,
    scope_company,
    scope_containers,
)
from ..models import (
    Container,
    Forwarder,
    FreightInvoice,
    FreightInvoiceContainer,
    Role,
    User,
    utcnow,
)
from ..notifications import company_watchers, notify
from .forwarding_files import (allowed_extensions, commit_with_file, read_upload_capped, safe_filename,
                               uploads_dir)

router = APIRouter()


class FreightInvoiceContainerOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    container_no: str


class FreightInvoiceOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    company_id: int
    bl_number: str
    invoice_number: str
    forwarder_id: int | None
    forwarder_name: str | None = None
    amount: float | None
    currency: str
    note: str
    filename: str
    has_file: bool = False
    amount_per_container: float | None = None
    uploaded_by_login: str | None = None
    created_at: datetime.datetime
    status: str = "NOWA"
    approved_by_login: str | None = None
    approved_at: datetime.datetime | None = None
    approval_note: str = ""
    containers: list[FreightInvoiceContainerOut] = []


def _freight_out(inv: FreightInvoice) -> FreightInvoiceOut:
    out = FreightInvoiceOut.model_validate(inv)
    out.forwarder_name = inv.forwarder.name if inv.forwarder else None
    out.uploaded_by_login = inv.uploaded_by.login if inv.uploaded_by else None
    out.approved_by_login = inv.approved_by.login if inv.approved_by else None
    out.has_file = bool(inv.stored_name)
    out.containers = [FreightInvoiceContainerOut(id=it.container.id,
                                                 container_no=it.container.container_no)
                      for it in inv.items if it.container]
    n = len(out.containers)
    # koszt frachtu na kontener — najczęściej potrzebna liczba przy BL wielo-kontenerowym
    out.amount_per_container = round(float(inv.amount) / n, 2) if inv.amount and n else None
    return out


_FREIGHT_OPTS = (selectinload(FreightInvoice.forwarder),
                 selectinload(FreightInvoice.uploaded_by),
                 selectinload(FreightInvoice.approved_by),
                 selectinload(FreightInvoice.items).selectinload(FreightInvoiceContainer.container))

# obieg akceptacji faktury transportowej (#42): stany i dozwolone przejścia
_FI_SUBMIT_FROM = {"NOWA", "ODRZUCONA"}     # zgłoszenie do akceptacji (twórca)
_FI_DECIDE_FROM = {"DO_AKCEPTACJI"}         # zatwierdzenie/odrzucenie (akceptujący)


@router.get("/freight-invoices", response_model=list[FreightInvoiceOut])
def list_freight_invoices(container_id: int | None = None,
                          db: Session = Depends(get_db), user: User = freight_readers):
    query = select(FreightInvoice).options(*_FREIGHT_OPTS).order_by(FreightInvoice.created_at.desc())
    query = scope_company(query, FreightInvoice.company_id, user)
    if container_id is not None:
        # zakładka „Koszty" szuflady kolejki: tylko faktury tego kontenera — dostęp do
        # kontenera sprawdzany jak wszędzie (get_scoped → 404, gdy poza zakresem usera)
        get_scoped(db, Container, container_id, user)
        query = query.where(FreightInvoice.items.any(FreightInvoiceContainer.container_id == container_id))
    return [_freight_out(inv) for inv in db.scalars(query).all()]


_ARCHIVES = {"zip", "7z", "rar"}


def _refuse_same_file(db: Session, company_id: int, content: bytes) -> None:
    """Ten sam plik faktury w spółce drugi raz → 409 (§4 pkt 31). Kandydaci po rozmiarze.
    ponytail: porównanie treści bez kolumny skrótu — faktur BL jest kilkadziesiąt w miesiącu;
    przy tysiącach — sha256 jak w attachments (sha001)."""
    for inv in db.scalars(select(FreightInvoice).where(FreightInvoice.company_id == company_id,
                                                        FreightInvoice.size == len(content),
                                                        FreightInvoice.stored_name != "")):
        path = uploads_dir() / inv.stored_name
        if path.is_file() and path.read_bytes() == content:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"Ten plik już jest jako faktura {inv.invoice_number or '—'} "
                                f"do BL {inv.bl_number or '—'}.")


@router.post("/freight-invoices", response_model=FreightInvoiceOut, status_code=201)
def create_freight_invoice(
        company_id: int = Form(...),
        container_ids: str = Form(...),   # CSV id kontenerów, np. "12,15,18"
        bl_number: str = Form(default=""),
        invoice_number: str = Form(default=""),
        forwarder_id: int | None = Form(default=None),
        amount: float | None = Form(default=None),
        currency: str = Form(default="EUR"),
        note: str = Form(default=""),
        file: UploadFile | None = None,
        db: Session = Depends(get_db), user: User = editors):
    resolve_company_id(db, user, company_id)
    try:
        ids = {int(x) for x in container_ids.split(",") if x.strip()}
    except ValueError:   # np. "12,abc" — błąd klienta, nie 500
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Nieprawidłowa lista kontenerów.") from None
    if not ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Wskaż co najmniej jeden kontener.")
    # kontenery muszą być w zasięgu użytkownika I należeć do spółki faktury (izolacja)
    scoped = db.scalars(scope_containers(
        select(Container).where(Container.id.in_(ids)), user)).all()
    found = {c.id: c for c in scoped}
    for cid in ids:
        if cid not in found:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Nie znaleziono kontenera {cid}.")
        if found[cid].company_id != company_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Kontener należy do innej spółki niż faktura.")
    if forwarder_id is not None and not db.get(Forwarder, forwarder_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono spedytora.")
    # §4 pkt 31: ta sama faktura (numer + BL) w spółce drugi raz = dubel kosztu frachtu
    if invoice_number.strip():
        twin = db.scalar(select(FreightInvoice).where(
            FreightInvoice.company_id == company_id,
            func.lower(FreightInvoice.invoice_number) == invoice_number.strip().lower(),
            func.lower(FreightInvoice.bl_number) == bl_number.strip().lower()).limit(1))
        if twin is not None:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"Faktura {twin.invoice_number} do BL {twin.bl_number or '—'} "
                                f"już jest (dodana {twin.created_at:%d.%m.%Y}).")

    stored_name = filename = content_type = ""
    size = 0
    if file is not None and file.filename:
        extension = pathlib.Path(file.filename).suffix.lstrip(".").lower()
        if extension in _ARCHIVES:   # §4 pkt 38: wspólna allowlista przepuszczała archiwa
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Faktura transportowa: wgraj sam dokument (PDF / skan), nie archiwum.")
        if extension not in allowed_extensions():
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Niedozwolony typ pliku „.{extension or '?'}”. "
                f"Dozwolone: {', '.join(sorted(allowed_extensions()))}.")
        content = read_upload_capped(file, settings.max_upload_mb, label="Faktura")
        _refuse_same_file(db, company_id, content)
        filename = safe_filename(file.filename)
        stored_name = f"bl_{secrets.token_hex(8)}_{filename}"
        content_type, size = file.content_type or "", len(content)

    invoice = FreightInvoice(
        company_id=company_id, bl_number=bl_number.strip(), invoice_number=invoice_number.strip(),
        forwarder_id=forwarder_id, amount=amount, currency=(currency or "EUR").upper()[:3],
        note=note.strip(), filename=filename, stored_name=stored_name,
        content_type=content_type, size=size, uploaded_by_id=user.id)
    invoice.items = [FreightInvoiceContainer(container_id=cid) for cid in ids]
    db.add(invoice)
    db.flush()
    record(db, entity_type="freight_invoices", entity_id=invoice.id, field="create",
           old_value=None, new_value=f"BL {bl_number or '—'} / {len(ids)} kontenerów",
           user=user, note="faktura transportowa BL")
    if stored_name:   # §4 pkt 33: plik i wiersz razem — błąd commitu sprząta plik
        commit_with_file(db, uploads_dir() / stored_name, content)
    else:
        db.commit()
    db.refresh(invoice)
    inv = db.scalar(select(FreightInvoice).options(*_FREIGHT_OPTS)
                    .where(FreightInvoice.id == invoice.id))
    return _freight_out(inv)


def _get_freight_checked(db: Session, invoice_id: int, user: User) -> FreightInvoice:
    # obrona w głąb: faktury transportowe tylko dla admin/logistyka/zakupy (jak freight_readers)
    if user.role not in (Role.admin, Role.logistics, Role.purchasing):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Brak uprawnień.")
    return get_scoped(db, FreightInvoice, invoice_id, user, options=_FREIGHT_OPTS)


@router.get("/freight-invoices/{invoice_id}/download")
def download_freight_invoice(invoice_id: int, db: Session = Depends(get_db),
                             user: User = freight_readers):
    inv = _get_freight_checked(db, invoice_id, user)
    if not inv.stored_name:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Faktura nie ma pliku.")
    path = uploads_dir() / inv.stored_name
    if not path.is_file():
        raise HTTPException(status.HTTP_410_GONE, "Plik został usunięty z dysku.")
    return FileResponse(path, filename=inv.filename or inv.stored_name,
                        media_type="application/octet-stream")


@router.delete("/freight-invoices/{invoice_id}", status_code=204)
def delete_freight_invoice(invoice_id: int, db: Session = Depends(get_db), user: User = editors):
    inv = _get_freight_checked(db, invoice_id, user)
    stored_name = inv.stored_name
    record(db, entity_type="freight_invoices", entity_id=inv.id, field="delete",
           old_value=f"BL {inv.bl_number or '—'}", new_value=None, user=user)
    db.delete(inv)  # items znikają kaskadą (cascade all, delete-orphan)
    db.commit()
    if stored_name:   # po commicie — nieudane usunięcie nie zostawia wiersza bez pliku
        (uploads_dir() / stored_name).unlink(missing_ok=True)


# --- obieg akceptacji faktury transportowej (#42) ---

class FreightDecisionIn(BaseModel):
    note: str = ""


def _fi_transition(db: Session, inv: FreightInvoice, user: User, new_status: str, note: str = "") -> None:
    old = inv.status
    inv.status = new_status
    if new_status in ("ZAAKCEPTOWANA", "ODRZUCONA"):
        inv.approved_by_id, inv.approved_at, inv.approval_note = user.id, utcnow(), note.strip()
    elif new_status == "DO_AKCEPTACJI":
        inv.approved_by_id, inv.approved_at, inv.approval_note = None, None, ""
    record(db, entity_type="freight_invoices", entity_id=inv.id, field="status",
           old_value=old, new_value=new_status, user=user, note=note.strip() or None)
    _fi_notify(db, inv, user, new_status, note.strip())


def _fi_notify(db: Session, inv: FreightInvoice, user: User, new_status: str, note: str) -> None:
    """#50 — zgłoszenie → admini spółki (zatwierdzający); decyzja → autor faktury.
    Kanały wg matrycy reguł (kindy freight_approval / freight_decision)."""
    label = f"BL {inv.bl_number or '—'} / {inv.invoice_number or '—'}"
    if new_status == "DO_AKCEPTACJI":
        admins = [u for u in company_watchers(db, inv.company_id) if u.role == Role.admin]
        notify(db, admins, kind="freight_approval", exclude_user_id=user.id,
               title=f"Faktura transportowa do akceptacji: {label}",
               body=f"Zgłosił: {user.full_name or user.login}")
    elif new_status in ("ZAAKCEPTOWANA", "ODRZUCONA") and inv.uploaded_by:
        verdict = "zaakceptowana" if new_status == "ZAAKCEPTOWANA" else "odrzucona"
        notify(db, [inv.uploaded_by], kind="freight_decision", exclude_user_id=user.id,
               title=f"Faktura transportowa {verdict}: {label}",
               body=note or f"Decyzja: {user.full_name or user.login}")


@router.post("/freight-invoices/{invoice_id}/submit", response_model=FreightInvoiceOut)
def submit_freight_invoice(invoice_id: int, db: Session = Depends(get_db), user: User = editors):
    """Zgłoszenie faktury do akceptacji (twórca / logistyka)."""
    inv = _get_freight_checked(db, invoice_id, user)
    if inv.status not in _FI_SUBMIT_FROM:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Nie można zgłosić faktury w stanie {inv.status}.")
    _fi_transition(db, inv, user, "DO_AKCEPTACJI")
    db.commit()
    db.expire(inv)   # relacja approved_by była wczytana jako None przed decyzją — odśwież
    return _freight_out(_get_freight_checked(db, invoice_id, user))


@router.post("/freight-invoices/{invoice_id}/approve", response_model=FreightInvoiceOut)
def approve_freight_invoice(invoice_id: int, body: FreightDecisionIn | None = None,
                            db: Session = Depends(get_db), user: User = approvers):
    """Zatwierdzenie do zapłaty (rozdzielenie obowiązków — zatwierdza admin, nie twórca)."""
    inv = _get_freight_checked(db, invoice_id, user)
    if inv.status not in _FI_DECIDE_FROM:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Faktura nie jest zgłoszona do akceptacji (stan {inv.status}).")
    _fi_transition(db, inv, user, "ZAAKCEPTOWANA", (body.note if body else ""))
    db.commit()
    db.expire(inv)   # relacja approved_by była wczytana jako None przed decyzją — odśwież
    return _freight_out(_get_freight_checked(db, invoice_id, user))


@router.post("/freight-invoices/{invoice_id}/reject", response_model=FreightInvoiceOut)
def reject_freight_invoice(invoice_id: int, body: FreightDecisionIn | None = None,
                           db: Session = Depends(get_db), user: User = approvers):
    """Odrzucenie faktury (z powodem); wraca do poprawy — twórca może zgłosić ponownie."""
    inv = _get_freight_checked(db, invoice_id, user)
    if inv.status not in _FI_DECIDE_FROM:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Faktura nie jest zgłoszona do akceptacji (stan {inv.status}).")
    _fi_transition(db, inv, user, "ODRZUCONA", (body.note if body else ""))
    db.commit()
    db.expire(inv)   # relacja approved_by była wczytana jako None przed decyzją — odśwież
    return _freight_out(_get_freight_checked(db, invoice_id, user))
