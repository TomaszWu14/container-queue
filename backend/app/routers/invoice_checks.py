"""Wynik kontroli dokumentu faktury wg profilu dostawcy (etap 3): jednostki, wagi netto,
suma pozycji ↔ faktura, CI ↔ PL, CI ↔ zamówienie SAP; zgodność z kontenerem i akcje bramki
(przypnij PO, przenieś dokument). Dostęp jak moduł faktur."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..database import get_db
from ..deps import PurchasingReaders as purchasing_readers
from ..deps import Editors as editors
from ..deps import get_scoped, scope_containers
from .containers_common import get_container_checked
from .forwarding import uploads_dir
from .invoices import _stored
from ..invoices.checks import job_checks
from ..invoices.conformity import has_copy, job_conformity
from ..invoices.orders_link import orders_to_link
from ..invoices.relocate import copy_job, move_job
from ..models import Container, InvoiceBatch, InvoiceDocKind, InvoiceJob, InvoiceJobStatus, User

router = APIRouter(prefix="/api", tags=["faktury"])


def _job(db: Session, job_id: int, user: User) -> tuple[InvoiceJob, int | None]:
    job = get_scoped(db, InvoiceJob, job_id, user)   # deps: przez paczkę → kontener
    container = db.get(Container, job.batch.container_id)
    return job, container.company_id if container else None


@router.get("/invoice-jobs/{job_id}/checks")
def get_job_checks(job_id: int, db: Session = Depends(get_db),
                   user: User = purchasing_readers) -> dict:
    job, company_id = _job(db, job_id, user)
    return job_checks(db, job, company_id)


@router.get("/invoice-jobs/{job_id}/conformity")
def get_job_conformity(job_id: int, db: Session = Depends(get_db),
                       user: User = purchasing_readers) -> dict:
    """Zgodność dokumentu z kontenerem paczki: status ok / uncertain / conflict + sygnały."""
    job, company_id = _job(db, job_id, user)
    return job_conformity(db, job, company_id)


@router.post("/invoice-jobs/{job_id}/link-orders")
def link_orders(job_id: int, db: Session = Depends(get_db),
                user: User = purchasing_readers) -> list[str]:
    """Świadome przypięcie zamówień z faktury do kontenera paczki (decyzja człowieka).
    Zamówienia z innym kontenerem pomija — przepinanie to nie ta akcja."""
    job, company_id = _job(db, job_id, user)
    linked = []
    for order in orders_to_link(db, job, company_id):
        order.container_id = job.batch.container_id
        audit.record(db, entity_type="sap_orders", entity_id=order.id, field="container_id",
                     old_value=None, new_value=order.container_id, user=user,
                     note=f"z faktury {job.invoice_number or job.filename}")
        linked.append(order.order_number)
    db.commit()
    return linked


def _check_movable(db: Session, job: InvoiceJob, target: Container) -> None:
    """§4 pkt 18: nie w trakcie cięcia/OCR (zaślepka zniknie, przeniesienie przepadnie) i nie
    do kontenera, który ten dokument już ma (dubel)."""
    if job.status == InvoiceJobStatus.uploaded:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Dokument jest jeszcze przetwarzany — spróbuj za chwilę.")
    if has_copy(db, job, target):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Kontener {target.container_no} ma już ten dokument.")


class MoveIn(BaseModel):
    container_id: int


@router.post("/invoice-jobs/{job_id}/move")
def move_invoice_job(job_id: int, body: MoveIn, db: Session = Depends(get_db),
                     user: User = purchasing_readers) -> dict:
    """„Wrzuć do X”: dokument w złym kontenerze → właściwy (ta sama spółka)."""
    job, company_id = _job(db, job_id, user)
    target = get_container_checked(db, body.container_id, user)
    if target.company_id != company_id or target.id == job.batch.container_id:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Dokument można przenieść tylko do innego kontenera tej samej spółki.")
    _check_movable(db, job, target)
    batch = move_job(db, job, target, user)
    db.commit()
    return {"container_id": target.id, "container_no": target.container_no, "batch_id": batch.id}


@router.post("/invoice-jobs/{job_id}/copy")
def copy_invoice_job(job_id: int, body: MoveIn, db: Session = Depends(get_db),
                     user: User = purchasing_readers) -> dict:
    """„Dodaj też do X”: faktura na kilka kontenerów — tylko do kontenera z jej treści."""
    job, company_id = _job(db, job_id, user)
    target = get_container_checked(db, body.container_id, user)
    also_in = {c["id"]: c for c in job_conformity(db, job, company_id)["also_in"]}
    if target.id not in also_in or also_in[target.id]["has_copy"]:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Dokument można dodać tylko do innego kontenera wymienionego na nim, "
                            "który jeszcze go nie ma.")
    _check_movable(db, job, target)
    stored = _stored(target.id, job.filename)
    copy = copy_job(db, job, target, user, uploads_dir(), stored)
    try:
        db.commit()
    except Exception:   # §4 pkt 36: plik kopii skopiowany przed commitem — bez sieroty
        (uploads_dir() / stored).unlink(missing_ok=True)
        raise
    return {"job_id": copy.id, "container_id": target.id, "container_no": target.container_no}


_REPORT_KINDS = (InvoiceDocKind.invoice, InvoiceDocKind.proforma, InvoiceDocKind.packing_list)
_REPORT_STATUSES = (InvoiceJobStatus.extracted, InvoiceJobStatus.confirmed, InvoiceJobStatus.packing_list)


@router.get("/invoice-conformity/report")
def conformity_report(limit: int = Query(default=300, ge=1, le=1000),
                      db: Session = Depends(get_db), user: User = editors) -> dict:
    """Jednorazowy przegląd wstecz (spec 2026-10-01, PR 4): ostatnie dokumenty paczek faktur,
    które nie są zgodne z kontenerem — do ręcznego przejrzenia, nic nie przenosimy samo.
    ponytail: liczone na żądanie dla `limit` najnowszych; przy tysiącach dokumentów —
    zapis statusu przy ekstrakcji i filtr w SQL."""
    query = (select(InvoiceJob, Container).join(InvoiceBatch, InvoiceJob.batch_id == InvoiceBatch.id)
             .join(Container, InvoiceBatch.container_id == Container.id)
             .where(InvoiceJob.doc_kind.in_(_REPORT_KINDS), InvoiceJob.status.in_(_REPORT_STATUSES))
             .order_by(InvoiceJob.id.desc()).limit(limit))
    rows, checked = [], 0
    for job, container in db.execute(scope_containers(query, user)).all():
        checked += 1
        result = job_conformity(db, job, container.company_id)
        if result["status"] == "ok":
            continue
        rows.append({"job_id": job.id, "container_id": container.id,
                     "container_no": container.container_no, "filename": job.filename,
                     "invoice_number": job.invoice_number, "doc_kind": job.doc_kind.value,
                     "confirmed": job.status == InvoiceJobStatus.confirmed,
                     "status": result["status"], "signals": result["signals"],
                     "overage": result["overage"], "move_to": result["move_to"],
                     "ack": result["ack"]})
    rows.sort(key=lambda r: r["status"] != "conflict")   # sprzeczne na górze
    return {"checked": checked, "rows": rows}
