"""Usuwanie kontenerów (admin): pojedynczo i czyszczenie kolejki wraz z dziećmi."""
import datetime
import logging
import pathlib

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, event, select
from sqlalchemy.orm import Session

from ..audit import record
from ..database import get_db
from ..deps import AdminOnly as admins
from ..deps import get_company_by_code
from ..models import Container, ContainerStatus, User
from .containers_common import get_container_checked

# sub-router bez prefiksu — podpinany w routers/containers.py (prefiks /api, tag kolejka)
router = APIRouter()
# ten sam logger co przed podziałem routers/containers.py (filtry/alerty po nazwie)
logger = logging.getLogger(__package__ + ".containers")


def _unlink_after_commit(db: Session, paths: set[pathlib.Path]) -> None:
    """DB-012: pliki znikają z dysku dopiero po udanym commicie. Rollback (błąd FK,
    zerwane połączenie) przywraca wiersze — wtedy pliki zostają, a nasłuch jest zdejmowany,
    żeby kolejny commit tej sesji ich nie skasował."""
    if not paths:
        return

    def _unlink(_session) -> None:
        event.remove(db, "after_rollback", _forget)
        for path in paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:  # commit już jest — sierota na dysku zamiast 500 po fakcie
                logger.warning("nie udało się skasować pliku %s", path, exc_info=True)

    def _forget(_session) -> None:
        event.remove(db, "after_commit", _unlink)

    event.listen(db, "after_commit", _unlink, once=True)
    event.listen(db, "after_rollback", _forget, once=True)


def _delete_where(db: Session, model, condition) -> int:
    """DELETE w stylu 2.0 (ARCH-009) — jak dotychczasowe Query.delete(synchronize_session=False):
    bez synchronizacji obiektów sesji; zwraca liczbę skasowanych wierszy."""
    return db.execute(delete(model).where(condition),
                      execution_options={"synchronize_session": False}).rowcount


# Dzieci kontenera wyliczane z Base.metadata (każdy FK do containers.id), więc nowa
# tabela nie wraca z FK violation na Postgresie. NOT NULL FK = dane kontenera → kasowane;
# nullable FK (purchase_orders, notifications, sap_orders) = rekord własny → ODPINANY
# (container_id←NULL). Ręcznie obsłużone zostają tylko wnuki i pliki na dysku.
def _purge_containers(db: Session, ids: list[int]) -> int:
    """Usuwa kontenery o podanych id wraz z twardymi dziećmi (transport, tracking,
    wiadomości, załączniki, SMS-y, awizacje, reklamacje...). Zwraca liczbę usuniętych.
    Kolejność: dzieci → rodzic, by nie naruszyć FK (produkcja = Postgres, brak kaskad)."""
    from ..models import (
        Attachment,
        AttachmentSuggestion,
        Base,
        Complaint,
        ComplaintPhoto,
        ComplaintProblem,
        InvoiceBatch,
        InvoiceItem,
        InvoiceJob,
        UnloadPhoto,
    )
    from .forwarding import uploads_dir  # lokalnie: forwarding importuje containers
    if not ids:
        return 0
    files: set[pathlib.Path] = set()  # kasowane po commicie (DB-012)
    # W5 #31: propozycje podpięcia (FK do jobów, załączników i kontenerów) — najpierw one
    suggestion_job_ids = [jid for (jid,) in db.execute(
        select(InvoiceJob.id).join(InvoiceBatch, InvoiceJob.batch_id == InvoiceBatch.id)
        .where(InvoiceBatch.container_id.in_(ids)))]
    suggestions = AttachmentSuggestion.container_id.in_(ids)
    if suggestion_job_ids:
        suggestions = suggestions | AttachmentSuggestion.job_id.in_(suggestion_job_ids)
    _delete_where(db, AttachmentSuggestion, suggestions)
    # faktury (CIPL): pozycje → dokumenty → paczki, zanim znikną załączniki (Excel) i kontener
    batch_ids = [bid for (bid,) in db.execute(
        select(InvoiceBatch.id).where(InvoiceBatch.container_id.in_(ids)))]
    if batch_ids:
        jobs = db.execute(select(InvoiceJob.id, InvoiceJob.stored_name, InvoiceJob.source_name)
                          .where(InvoiceJob.batch_id.in_(batch_ids))).all()
        job_ids = [jid for jid, _, _ in jobs]
        # pliki PDF dokumentów (oryginał + części po cięciu) — jak DELETE /invoice-batches
        uploads = uploads_dir()
        files.update(uploads / n for _, stored, source in jobs for n in (stored, source) if n)
        if job_ids:
            _delete_where(db, InvoiceItem, InvoiceItem.job_id.in_(job_ids))
            _delete_where(db, InvoiceJob, InvoiceJob.id.in_(job_ids))
        _delete_where(db, InvoiceBatch, InvoiceBatch.id.in_(batch_ids))
    # pliki załączników (CMR, SAD, dokumenty) i zdjęć z rozładunku (wiersze znikną w pętli
    # niżej) — RODO: kontener usunięty = jego pliki też, nie sieroty na dysku
    for model in (Attachment, UnloadPhoto):
        for (name,) in db.execute(select(model.stored_name)
                                  .where(model.container_id.in_(ids))):
            files.add(uploads_dir() / name)
    # wnuki: complaint_problems/photos FK complaints.id bez kaskady — muszą zniknąć
    # PRZED complaints, inaczej Postgres rzuca FK violation na kasowaniu reklamacji
    complaint_ids = [cid for (cid,) in db.execute(
        select(Complaint.id).where(Complaint.container_id.in_(ids)))]
    if complaint_ids:
        files.update(uploads_dir() / name for (name,) in db.execute(
            select(ComplaintPhoto.stored_name)
            .where(ComplaintPhoto.complaint_id.in_(complaint_ids))))
        for gm in (ComplaintProblem, ComplaintPhoto):
            _delete_where(db, gm, gm.complaint_id.in_(complaint_ids))
    # reversed(sorted_tables): dzieci przed rodzicami (invoice_batches przed attachments)
    for table in reversed(Base.metadata.sorted_tables):
        for column in table.columns:
            if any(fk.column.table.name == Container.__tablename__
                   for fk in column.foreign_keys):
                stmt = (table.update().values({column.name: None}) if column.nullable
                        else table.delete())
                db.execute(stmt.where(column.in_(ids)))
    deleted = _delete_where(db, Container, Container.id.in_(ids))
    _unlink_after_commit(db, files)
    return deleted


@router.delete("/containers/{container_id}", status_code=204)
def delete_container(container_id: int, db: Session = Depends(get_db), user: User = admins):
    """Usuwa pojedynczy kontener z kolejki (tylko admin). Uwaga: kolejka syncuje się
    z SharePointa — jeśli numer nadal jest w arkuszu, wróci przy najbliższym syncu."""
    container = get_container_checked(db, container_id, user)
    no = container.container_no
    record(db, entity_type="containers", entity_id=container.id, field="__deleted__",
           old_value=no, new_value=None, user=user, note="usunięto kontener")
    _purge_containers(db, [container.id])
    db.commit()
    logger.info("admin %s usunął kontener %s", user.login, no)


@router.delete("/containers")
def clear_queue(company_code: str | None = Query(default=None),
                confirm: bool = Query(default=False),
                before: datetime.date | None = Query(default=None),
                keep_statuses: list[ContainerStatus] = Query(default=[]),
                dry_run: bool = Query(default=False),
                db: Session = Depends(get_db), user: User = admins):
    """Czyści kolejkę (tylko admin) — do resetu przed wgraniem nowej do testów.
    Wymaga confirm=true (poza dry_run). `company_code` zawęża do jednej spółki; brak =
    wszystkie widoczne dla admina. `before` kasuje tylko kontenery z notify_date < before
    (kolejka grupuje po tym polu) — kontenery bez daty zostają. `keep_statuses` zachowuje
    podane statusy. `dry_run=true` tylko liczy, nic nie kasuje i nie wymaga confirm.
    Uwaga: sync z SharePointa odtworzy kontenery nadal obecne w arkuszu."""
    if not dry_run and not confirm:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Wymagane confirm=true — operacja kasuje kolejkę.")
    q = select(Container.id)
    if company_code:
        company = get_company_by_code(db, user, company_code)
        q = q.where(Container.company_id == company.id)
    if before:
        q = q.where(Container.notify_date.is_not(None), Container.notify_date < before)
    if keep_statuses:
        q = q.where(Container.status.notin_(keep_statuses))
    ids = [cid for (cid,) in db.execute(q)]
    if dry_run:
        return {"deleted": len(ids)}
    deleted = _purge_containers(db, ids)
    filter_note = ""
    if before or keep_statuses:
        parts = []
        if before:
            parts.append(f"przed {before}")
        if keep_statuses:
            parts.append(f"zachowano: {', '.join(keep_statuses)}")
        filter_note = f" ({', '.join(parts)})"
    record(db, entity_type="containers", entity_id=0, field="__queue_cleared__",
           old_value=str(deleted), new_value=company_code or "ALL", user=user,
           note=f"wyczyszczono kolejkę{filter_note}")
    db.commit()
    logger.warning("admin %s wyczyścił kolejkę (%s)%s: %d kontenerów",
                   user.login, company_code or "ALL", filter_note, deleted)
    return {"deleted": deleted}
