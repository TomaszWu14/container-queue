"""Faktury (CIPL) przy kontenerze: PDF → ekstrakcja → weryfikacja → Excel do pobrania.

Cały pipeline jest lokalny (app/invoices). Upload zapisuje pliki; cięcie, OCR i ekstrakcję
robi pętla tła (ARCH-004, invoices/ingest.py — 202 i dokumenty „uploaded”, front odpytuje),
a bez pętli tła na instancji — od razu w żądaniu (201). Excel zapisujemy jako
zwykły `Attachment` — pobieranie leci istniejącym /api/attachments/{id}/download.
Dostęp: admin, logistyka, zakupy (spedytor/magazyn/agencja widzą tylko gotowy Excel
w załącznikach kontenera).
"""
import logging
import pathlib
import secrets

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .. import audit
from ..config import settings
from ..database import get_db
from ..deps import PurchasingReaders as purchasing_readers
from ..deps import get_scoped
from ..document_gate import digest, duplicate_reason
from ..exports import XLSX_MIME
from ..invoices import conformity, ingest, ml, ocr, pipeline, profiles
from ..invoices.excel import build_workbook
from ..invoices.matching import reset_match, resolve_chosen_refs
from ..models import (
    INVOICE_LIKE_KINDS,
    AgencyAck,
    Attachment,
    Container,
    InvoiceBatch,
    InvoiceDocKind,
    InvoiceItem,
    InvoiceJob,
    InvoiceJobStatus,
    SadDraft,
    Supplier,
    User,
    utcnow,
)
from ..schemas import InvoiceBatchOut, InvoiceJobDetailOut, InvoiceJobOut, InvoiceReviewIn
from .containers import _check_company_fks, get_container_checked
from .forwarding import read_upload_capped, safe_filename, uploads_dir
from .forwarding_files import commit_with_file

router = APIRouter(prefix="/api", tags=["faktury"])
logger = logging.getLogger(__name__)


def _job_out(job: InvoiceJob, detail: bool = False, items_count: int | None = None) -> InvoiceJobOut:
    out = (InvoiceJobDetailOut if detail else InvoiceJobOut).model_validate(job)
    if items_count is None:
        items_count = sum(1 for item in job.items if not item.skipped)
    out.items_count = items_count
    return out


def _item_counts(db: Session, batches: list[InvoiceBatch]) -> dict[int, int]:
    """Aktywne pozycje per dokument JEDNYM zapytaniem GROUP BY dla wszystkich paczek —
    lista nie ładuje setek wierszy pozycji tylko po to, żeby je policzyć."""
    job_ids = [job.id for batch in batches for job in batch.jobs]
    if not job_ids:
        return {}
    rows = db.execute(select(InvoiceItem.job_id, func.count())
                      .where(InvoiceItem.job_id.in_(job_ids), InvoiceItem.skipped.is_(False))
                      .group_by(InvoiceItem.job_id)).all()
    return {job_id: n for job_id, n in rows}


def _batches_out(db: Session, batches: list[InvoiceBatch]) -> list[InvoiceBatchOut]:
    item_counts = _item_counts(db, batches)
    result = []
    for batch in batches:
        out = InvoiceBatchOut.model_validate(batch)
        counts = pipeline.batch_counts(batch)
        out.total, out.confirmed, out.errors = counts["total"], counts["confirmed"], counts["errors"]
        # „gotowe” = wszystkie faktury zatwierdzone (stan dokumentów); kolumna batch.ready
        # mówi tylko, czy wygenerowany Excel jest aktualny
        out.ready = counts["ready"]
        out.excel_current = bool(batch.attachment_id) and bool(batch.ready)
        out.jobs = [_job_out(job, items_count=item_counts.get(job.id, 0)) for job in batch.jobs]
        out.supplier_name = batch.supplier.name if batch.supplier else None
        out.attachment_filename = batch.attachment.filename if batch.attachment else None
        result.append(out)
    return result


def _batch_out(db: Session, batch: InvoiceBatch) -> InvoiceBatchOut:
    return _batches_out(db, [batch])[0]


def _batches(db: Session, container_id: int) -> list[InvoiceBatch]:
    return db.scalars(select(InvoiceBatch)
                      .options(selectinload(InvoiceBatch.attachment),
                               selectinload(InvoiceBatch.supplier))
                      .where(InvoiceBatch.container_id == container_id)
                      .order_by(InvoiceBatch.created_at.desc(), InvoiceBatch.id.desc())).all()


# nazwa pliku na dysku/w bazie (String(255)): prefiks + skrócona nazwa oryginału; części po
# cięciu dostają sufiks „_docN_kind.pdf”, więc zostawiamy na to zapas


def _safe_filename(filename: str) -> str:
    return safe_filename(filename, "faktura.pdf")


def _stored(container_id: int, filename: str) -> str:
    return f"inv_{container_id}_{secrets.token_hex(8)}_{_safe_filename(filename)}"


def _page_count(content: bytes) -> int:
    import io

    from pypdf import PdfReader
    return len(PdfReader(io.BytesIO(content)).pages)


def _validate_pdf(name: str, content: bytes) -> int:
    """Liczba stron albo 422 — wołane w threadpoolu (pypdf parsuje cały plik)."""
    try:
        pages = _page_count(content)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"„{name}” — nie udało się otworzyć PDF.") from exc
    if pages > settings.invoice_pdf_max_pages:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"„{name}” ma {pages} stron — limit {settings.invoice_pdf_max_pages}.")
    return pages


@router.post("/containers/{container_id}/invoice-batches", response_model=InvoiceBatchOut,
             status_code=201)
def upload_invoices(container_id: int, response: Response,
                          pdf: list[UploadFile] = File(...),
                          supplier_id: int | None = Form(default=None),
                          db: Session = Depends(get_db), user: User = purchasing_readers):
    container = get_container_checked(db, container_id, user)
    supplier = _resolve_supplier(db, container, supplier_id)
    uploads = uploads_dir()
    saved: list[tuple[str, str, bytes]] = []
    skipped: list[str] = []
    seen: set[str] = set()
    for upload in pdf:
        name = _safe_filename(upload.filename or "faktura.pdf")
        if not name.lower().endswith(".pdf"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"„{name}” — wymagany plik PDF.")
        content = read_upload_capped(upload, settings.max_upload_mb, label="Faktura")
        # dubel pomija TEN plik, nie całe wgranie — folder zamówienia idzie dalej (§4 pkt 14–16)
        sha = digest(content)
        dup = "powtórzony w tym wgraniu" if sha in seen else duplicate_reason(db, container_id, content, uploads)
        seen.add(sha)
        if dup is not None:
            skipped.append(f"{name} ({dup})")
            continue
        saved.append((name, _stored(container_id, name), content))
    if skipped and not saved:
        raise HTTPException(status.HTTP_409_CONFLICT, "Nic nowego — " + "; ".join(skipped))
    if not saved:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Brak plików.")
    # cięcie + OCR + ekstrakcja to sekundy–minuty CPU na stronę: w tle (202, front odpytuje)
    batch, queued = _ingest(db, container, supplier, saved, uploads, user)
    if queued:
        response.status_code = status.HTTP_202_ACCEPTED
    out = _batch_out(db, batch)
    out.skipped = skipped
    return out


def _ingest(db: Session, container: Container, supplier: Supplier | None,
            saved: list[tuple[str, str, bytes]], uploads: pathlib.Path,
            user: User) -> tuple[InvoiceBatch, bool]:
    """Paczka z wgranych PDF-ów → (paczka, czy w kolejce tła). W kolejce: tylko pliki
    i zaślepki `uploaded` (ingest.process_pending), inaczej pełne przetworzenie w żądaniu."""
    page_counts = [_validate_pdf(name, content) for name, _, content in saved]
    written: list[pathlib.Path] = []
    queued = ingest.in_background()
    try:
        files = []
        for (name, stored, content), pages in zip(saved, page_counts, strict=True):
            path = uploads / stored
            path.write_bytes(content)
            written.append(path)
            files.append((name, stored, pages))
        batch = InvoiceBatch(container_id=container.id, supplier=supplier, created_by_id=user.id)
        db.add(batch)
        if queued:
            ingest.queue_files(batch, files, uploads)
            db.commit()
            db.refresh(batch)
        else:
            batch = ingest.ingest_files(db, batch, container, files, uploads, user, written)
    except BaseException:
        # nic nie zapisaliśmy w bazie → nie zostawiamy osieroconych plików w uploads
        db.rollback()
        for path in written:
            path.unlink(missing_ok=True)
        raise
    return batch, queued


def _resolve_supplier(db: Session, container: Container, supplier_id: int | None) -> Supplier | None:
    if supplier_id is None:
        supplier_id = container.supplier_id
    if supplier_id is None:
        return None
    # ta sama reguła izolacji co przy tworzeniu kontenera (dostawca musi należeć do jego spółki)
    _check_company_fks(db, container.company_id, supplier_id, None, None)
    return db.get(Supplier, supplier_id)


@router.get("/containers/{container_id}/invoice-batches", response_model=list[InvoiceBatchOut])
def list_invoice_batches(container_id: int, db: Session = Depends(get_db), user: User = purchasing_readers):
    get_container_checked(db, container_id, user)
    return _batches_out(db, _batches(db, container_id))


def _get_batch(db: Session, batch_id: int, user: User) -> InvoiceBatch:
    # izolacja per spółka / rola centralnie w deps (InvoiceBatch.container_id → kontener)
    return get_scoped(db, InvoiceBatch, batch_id, user)


def _get_job(db: Session, job_id: int, user: User) -> tuple[InvoiceJob, Container]:
    job = get_scoped(db, InvoiceJob, job_id, user)   # deps: przez paczkę → kontener
    return job, db.get(Container, job.batch.container_id)


@router.delete("/invoice-batches/{batch_id}", status_code=204)
def delete_batch(batch_id: int, db: Session = Depends(get_db), user: User = purchasing_readers):
    """Usuwa paczkę z dokumentami i plikami części; gotowy Excel (załącznik) zostaje."""
    batch = _get_batch(db, batch_id, user)
    if any(ingest.is_processing(job) for job in batch.jobs):   # wyścig z pętlą tła na plikach
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Paczka jest właśnie przetwarzana — poczekaj chwilę i spróbuj ponownie.")
    # spec 2026-10-06 §4 pkt 7: kaskada w bazie kasowała wersje draftów SAD, decyzje i potwierdzenie
    # agencji (pliki zostawały jako zwykłe załączniki) — paczka z odpowiedzią agencji jest chroniona
    if db.scalar(select(func.count(SadDraft.id)).where(SadDraft.batch_id == batch.id))             or db.scalar(select(func.count()).select_from(AgencyAck).where(AgencyAck.batch_id == batch.id)):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Paczka ma potwierdzenie albo draft SAD od agencji — nie usuwamy jej "
                            "(historia odprawy). Popraw dokumenty w paczce albo dodaj nową wersję draftu.")
    names = {job.stored_name for job in batch.jobs} | {job.source_name for job in batch.jobs}
    audit.record(db, entity_type="containers", entity_id=batch.container_id,
                 field="invoice_batch", old_value=f"paczka {batch.id}", new_value=None, user=user)
    db.delete(batch)
    db.commit()
    # §4 pkt 34: pliki dopiero po commicie — nieudany zapis nie zostawia wierszy bez plików
    for name in names - {""}:
        (uploads_dir() / name).unlink(missing_ok=True)


@router.get("/invoice-jobs/{job_id}", response_model=InvoiceJobDetailOut)
def get_invoice_job(job_id: int, db: Session = Depends(get_db), user: User = purchasing_readers):
    job, _ = _get_job(db, job_id, user)
    return _job_out(job, detail=True)


@router.put("/invoice-jobs/{job_id}/review", response_model=InvoiceJobDetailOut)
def review_invoice_job(job_id: int, body: InvoiceReviewIn,
                       db: Session = Depends(get_db), user: User = purchasing_readers):
    """Zapis poprawek operatora (+ opcjonalne zatwierdzenie). Zatwierdzony dokument
    można dalej poprawiać — wraca do 'extracted', Excel trzeba wygenerować ponownie."""
    job, container = _get_job(db, job_id, user)
    if job.status not in (InvoiceJobStatus.extracted, InvoiceJobStatus.confirmed):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Dokument nie ma pozycji do weryfikacji (błąd ekstrakcji lub packing lista).")
    by_id = {item.id: item for item in job.items}
    changed = False   # tylko REALNA zmiana unieważnia gotowy Excel (ponowny zapis bez zmian — nie)
    for incoming in body.items:
        item = by_id.get(incoming.id)
        if item is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Pozycja {incoming.id} nie należy do dokumentu.")
        if incoming.master_ref is not None and incoming.master_ref.strip() != item.master_ref:
            # ręczna zmiana REF unieważnia poprzednie dopasowanie (i jego nazwę/CN/SENT) —
            # resolve_chosen_refs niżej dogrywa nowe, jeśli REF istnieje w master
            reset_match(item, incoming.master_ref.strip())
            changed = True
        for field in ("qty", "amount", "weight_net", "weight_gross"):
            value = getattr(incoming, field)
            if value is not None and value.strip() != getattr(item, field):   # pominięte = bez zmian
                setattr(item, field, value.strip())
                changed = True
        if incoming.skipped is not None and incoming.skipped != item.skipped:
            item.skipped = incoming.skipped
            changed = True
    if body.invoice_number is not None and body.invoice_number.strip() != job.invoice_number:
        job.invoice_number = body.invoice_number.strip()
        changed = True
    resolve_chosen_refs(db, job, container.company_id)
    was_confirmed = job.status == InvoiceJobStatus.confirmed
    if body.confirm:
        ok, message = pipeline.confirm_job(job)
        if ok:   # bramka zgodności z dostawą (spec 2026-10-01): sprzeczna nie, niepewna z powodem
            db.flush()
            result = conformity.job_conformity(db, job, container.company_id)
            message = conformity.confirm_gate(result, body.conformity_reason)
            ok = not message
        if not ok:
            db.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, message)
        if result["status"] == conformity.UNCERTAIN and not result["ack"]:
            conformity.store_ack(job, body.conformity_reason or "", user.login, utcnow().isoformat())
            audit.record(db, entity_type="containers", entity_id=container.id,
                         field="invoice_conformity_ack", old_value=None,
                         new_value=job.invoice_number or job.filename, user=user,
                         note=(body.conformity_reason or "").strip()[:500])
        audit.record(db, entity_type="containers", entity_id=container.id, field="invoice_confirm",
                     old_value=None, new_value=job.invoice_number or job.filename, user=user)
        # W5 #34: rozjazd faktura↔zamówienie ponad tolerancję → alert do działu zakupów
        try:
            from ..invoices.compare import invoice_vs_order
            from ..notifications import notify, purchasing_users
            report = invoice_vs_order(db, job, container, settings.invoice_tolerance_pct)
            if report["exceeded"]:
                detail = (f"kwota faktury {report['invoice_total']} vs zamówienie "
                          f"{report['po_total']} (różnica {report['diff_pct']}%)"
                          if report["diff_pct"] is not None
                          else f"rozjazdy ilości: {report['mismatches']} poz.")
                notify(db, purchasing_users(db, container.company_id), kind="invoice-mismatch",
                       title=f"Rozjazd faktury {job.invoice_number or job.filename} "
                             f"({container.container_no})",
                       body=detail, container_id=container.id, exclude_user_id=user.id)
        except Exception:  # noqa: BLE001 — alert pomocniczy nie może blokować zatwierdzenia
            logger.warning("porównanie faktura↔zamówienie nie powiodło się", exc_info=True)
    elif was_confirmed:
        job.status = InvoiceJobStatus.extracted
    if changed or was_confirmed != (job.status == InvoiceJobStatus.confirmed):
        # zmiana pozycji albo zbioru zatwierdzonych dokumentów = Excel do wygenerowania ponownie
        job.updated_at = utcnow()
        _unready(job.batch)
    db.commit()
    if body.confirm:
        ml.schedule_training()   # nowe przykłady (dostawca + REF → REF master) dla sugestii
    db.refresh(job)
    return _job_out(job, detail=True)


def _unready(batch: InvoiceBatch) -> None:
    batch.ready = False
    batch.updated_at = utcnow()


@router.post("/invoice-jobs/{job_id}/ignore", response_model=InvoiceJobDetailOut)
def ignore_invoice_job(job_id: int, db: Session = Depends(get_db), user: User = purchasing_readers):
    """Dokument rozpoznany jako faktura, którym nie jest (certyfikat, list przewozowy bez
    markera, duplikat) — wyłączany z paczki; nie liczy się do gotowości ani do Excela.
    doc_kind zostaje: pomyłkę cofa POST /reprocess („Przywróć”), a klasyfikator ML nie uczy
    się na nim (pominięta „faktura” to nie przykład typu „inne”)."""
    job, container = _get_job(db, job_id, user)
    if job.status == InvoiceJobStatus.confirmed:
        raise HTTPException(status.HTTP_409_CONFLICT, "Zatwierdzonego dokumentu nie można pominąć.")
    if job.status == InvoiceJobStatus.ignored:
        raise HTTPException(status.HTTP_409_CONFLICT, "Dokument jest już pominięty.")
    if job.doc_kind == InvoiceDocKind.other:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ten dokument i tak nie wchodzi do paczki.")
    if job.status == InvoiceJobStatus.uploaded:   # zaślepka = cały niepocięty zestaw
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Zestaw nie jest jeszcze pocięty na dokumenty — poczekaj na przetworzenie.")
    job.items = []
    job.status = InvoiceJobStatus.ignored
    job.error = ""
    job.updated_at = utcnow()
    _unready(job.batch)
    audit.record(db, entity_type="containers", entity_id=container.id, field="invoice_ignore",
                 old_value=None, new_value=job.invoice_number or job.filename, user=user)
    db.commit()
    db.refresh(job)
    return _job_out(job, detail=True)


@router.post("/invoice-jobs/{job_id}/reprocess", response_model=InvoiceJobDetailOut)
def reprocess_invoice_job(job_id: int, db: Session = Depends(get_db), user: User = purchasing_readers):
    """Ponowna ekstrakcja (np. po dopisaniu mapy kolumn u dostawcy) — dla dokumentów
    z błędem, jeszcze niezatwierdzonych albo pominiętych („Przywróć” cofa /ignore)."""
    job, container = _get_job(db, job_id, user)
    if job.status == InvoiceJobStatus.confirmed:
        raise HTTPException(status.HTTP_409_CONFLICT, "Zatwierdzonego dokumentu nie ponawiamy.")
    if ingest.requeue(job):   # niepocięty zestaw z błędem → z powrotem do kolejki tła
        _unready(job.batch)
        audit.record(db, entity_type="containers", entity_id=container.id, field="invoice_requeue",
                     old_value=None, new_value=job.filename, user=user)
        db.commit()
        db.refresh(job)
        return _job_out(job, detail=True)
    if job.status == InvoiceJobStatus.uploaded:
        raise HTTPException(status.HTTP_409_CONFLICT, "Zestaw czeka w kolejce — przetworzy się sam.")
    restored = job.status == InvoiceJobStatus.ignored
    if job.doc_kind == InvoiceDocKind.packing_list:
        # pominięta packing lista wraca do paczki (znów daje wagi) — bez ekstrakcji pozycji
        if not restored:
            raise HTTPException(status.HTTP_409_CONFLICT, "Packing lista nie ma pozycji do ponowienia.")
        job.status = InvoiceJobStatus.packing_list
        job.updated_at = utcnow()
    elif job.doc_kind not in INVOICE_LIKE_KINDS:
        raise HTTPException(status.HTTP_409_CONFLICT, "To nie jest faktura.")
    else:
        job.items = []
        ocr.forget(str(uploads_dir() / job.stored_name))   # ponowienie = OCR naprawdę od nowa
        pipeline.process_job(db, job, profiles.resolve(job.batch.supplier), container.company_id,
                             uploads_dir(), {})
    _unready(job.batch)
    if restored:
        audit.record(db, entity_type="containers", entity_id=container.id, field="invoice_restore",
                     old_value=None, new_value=job.invoice_number or job.filename, user=user)
    db.commit()
    db.refresh(job)
    return _job_out(job, detail=True)


@router.post("/invoice-batches/{batch_id}/export", response_model=InvoiceBatchOut)
def export_batch(batch_id: int, partial: bool = False,
                 db: Session = Depends(get_db), user: User = purchasing_readers):
    """Excel z zatwierdzonych dokumentów paczki. 409 dopóki nie wszystkie zatwierdzone
    (chyba że `partial` — wtedy to, co już jest). Ponowny eksport nadpisuje plik."""
    batch = _get_batch(db, batch_id, user)
    counts = pipeline.batch_counts(batch)
    done = [j for j in batch.jobs if j.doc_kind in INVOICE_LIKE_KINDS
            and j.status == InvoiceJobStatus.confirmed]
    if not done or (not counts["ready"] and not partial):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Paczka niegotowa — zatwierdzono {counts['confirmed']}/{counts['total']} faktur.")
    # bramka zgodności: dane SAP mogły się zmienić po zatwierdzeniu; PL też (wagi)
    for job in [*done, *(j for j in batch.jobs if j.doc_kind == InvoiceDocKind.packing_list)]:
        result = conformity.job_conformity(db, job, batch.container.company_id)
        if result["status"] == conformity.CONFLICT:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"{job.filename}: {conformity.conflict_message(result)}")
    import io
    buf = io.BytesIO()
    build_workbook(done).save(buf)
    content = buf.getvalue()
    filename = f"faktury_{batch.container.container_no}_{batch.id}.xlsx"
    attachment = batch.attachment
    old_stored = None
    if attachment is None:
        attachment = Attachment(container_id=batch.container_id, filename=filename,
                                stored_name=_stored(batch.container_id, filename),
                                content_type=XLSX_MIME, uploaded_by_id=user.id)
        db.add(attachment)
        batch.attachment = attachment
    else:
        # ponowny eksport = nowy plik: w załącznikach widać, kto i kiedy go wygenerował;
        # §4 pkt 35: pod nową nazwą — stary plik znika dopiero po udanym commicie
        attachment.uploaded_by_id = user.id
        attachment.created_at = utcnow()
        old_stored, attachment.stored_name = attachment.stored_name, _stored(batch.container_id, filename)
    attachment.filename = filename
    attachment.size = len(content)
    batch.ready = True   # Excel odpowiada bieżącemu stanowi (także częściowy) — do następnej edycji
    batch.updated_at = utcnow()
    audit.record(db, entity_type="containers", entity_id=batch.container_id, field="invoice_excel",
                 old_value=None, new_value=filename, user=user,
                 note=f"{len(done)} faktur, {sum(1 for j in done for i in j.items if not i.skipped)} pozycji")
    commit_with_file(db, uploads_dir() / attachment.stored_name, content)
    if old_stored:
        (uploads_dir() / old_stored).unlink(missing_ok=True)
    db.refresh(batch)
    return _batch_out(db, batch)
