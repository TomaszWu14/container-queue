"""Dokument faktury w złym kontenerze → właściwy (2b) albo także w drugim kontenerze z tej
samej faktury (PR 3) — spec 2026-10-01-bramka-dokument-dostawa.

Dokument (część PDF z pozycjami) trafia do najnowszej paczki kontenera docelowego — tam,
gdzie operator i tak składa Excel dla agencji; gdy kontener nie ma paczki, powstaje nowa.
Zatwierdzenie i potwierdzenie „niepewnej” nie przechodzą — w nowym kontenerze to nowa decyzja."""
import pathlib
import shutil

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from .. import audit
from ..models import Container, InvoiceBatch, InvoiceItem, InvoiceJob, InvoiceJobStatus, User, utcnow


def target_batch(db: Session, target: Container, source: InvoiceBatch, user: User) -> InvoiceBatch:
    batch = db.scalar(select(InvoiceBatch).where(InvoiceBatch.container_id == target.id)
                      .order_by(InvoiceBatch.created_at.desc(), InvoiceBatch.id.desc()).limit(1))
    if batch is None:
        batch = InvoiceBatch(container_id=target.id, created_by_id=user.id,
                             supplier_id=target.supplier_id or source.supplier_id)
        db.add(batch)
        db.flush()
    return batch


def _reset(job: InvoiceJob) -> None:
    if job.status == InvoiceJobStatus.confirmed:
        job.status = InvoiceJobStatus.extracted
    job.check_data = {k: v for k, v in (job.check_data or {}).items() if k != "conformity_ack"}
    job.updated_at = utcnow()


def _unready(*batches: InvoiceBatch) -> None:
    for batch in batches:
        batch.ready = False
        batch.updated_at = utcnow()


def move_job(db: Session, job: InvoiceJob, target: Container, user: User) -> InvoiceBatch:
    source = job.batch
    batch = target_batch(db, target, source, user)
    # source_name = PDF całej paczki źródłowej; jej usunięcie skasuje plik — nie wiążemy go;
    # sha256 zostaje: bramka dubli widzi dokument w nowym kontenerze (§4 pkt 17)
    job.batch, job.source_name = batch, ""
    _reset(job)
    _unready(source, batch)
    label = job.invoice_number or job.filename
    audit.record(db, entity_type="containers", entity_id=source.container_id, field="invoice_moved",
                 old_value=label, new_value=target.container_no, user=user)
    audit.record(db, entity_type="containers", entity_id=target.id, field="invoice_moved",
                 old_value=None, new_value=label, user=user, note=f"z paczki {source.id}")
    return batch


def _clone(row, skip: set[str]) -> dict:
    return {c.key: getattr(row, c.key) for c in inspect(row).mapper.column_attrs if c.key not in skip}


def copy_job(db: Session, job: InvoiceJob, target: Container, user: User,
             uploads: pathlib.Path, stored_name: str) -> InvoiceJob:
    """Faktura na kilka kontenerów (PR 3): ten sam dokument także w paczce kontenera X —
    własny plik i własne pozycje, bo Excel / SAD każdego kontenera edytuje się osobno
    (np. pominięcie pozycji, których nie ma w tym kontenerze)."""
    batch = target_batch(db, target, job.batch, user)
    shutil.copyfile(uploads / job.stored_name, uploads / stored_name)
    copy = InvoiceJob(**_clone(job, {"id", "batch_id", "stored_name", "source_name",
                                     "created_at", "updated_at"}),
                      batch=batch, stored_name=stored_name, source_name="")
    copy.items = [InvoiceItem(**_clone(i, {"id", "job_id"})) for i in job.items]
    _reset(copy)
    _unready(batch)
    db.add(copy)
    audit.record(db, entity_type="containers", entity_id=target.id, field="invoice_shared",
                 old_value=None, new_value=job.invoice_number or job.filename, user=user,
                 note=f"z kontenera {job.batch.container.container_no}")
    return copy
