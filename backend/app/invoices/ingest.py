"""Wczytanie paczki faktur: cięcie PDF-zestawu, OCR, ekstrakcja, propozycje podpięcia.

ARCH-004: te kroki to sekundy–minuty CPU na stronę (Tesseract do 90 s, model obrazowy Ollamy
do OLLAMA_TIMEOUT). Upload zapisuje pliki i dokumenty-zaślepki w stanie `uploaded`, a pętla
tła (jobs.py → `process_pending`) robi resztę; front odpytuje paczkę, dopóki coś jest
`uploaded`. Bez pętli tła na tej instancji (RUN_BACKGROUND_JOBS=false) albo przy
INVOICE_OCR_IN_BACKGROUND=false — wszystko w żądaniu, jak dotąd.

Zaślepka = dokument w stanie `uploaded` (cały wgrany plik); po udanym przebiegu nie zostaje
żaden dokument w tym stanie (process_job zawsze ustawia extracted/error).
"""
import datetime
import hashlib
import logging
import pathlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..config import settings
from ..models import (INVOICE_LIKE_KINDS, Container, InvoiceBatch, InvoiceDocKind, InvoiceJob,
                      InvoiceJobStatus, User, utcnow)
from . import pipeline, profiles, splitter

logger = logging.getLogger(__name__)


def in_background() -> bool:
    """Kolejka tylko tam, gdzie pętla tła ją obsłuży — inaczej dokumenty wisiałyby w `uploaded`."""
    return settings.invoice_ocr_in_background and settings.run_background_jobs


def page_texts(path: pathlib.Path) -> list[str] | None:
    """Tekst stron (rozpoznanie dostawcy + cięcie); None, gdy PDF nie daje się czytać —
    wtedy split_pdf spróbuje sam i split_or_whole weźmie cały plik."""
    try:
        return splitter.page_texts(str(path))
    except Exception:  # noqa: BLE001 — jak w split_or_whole
        logger.warning("faktury: tekst stron %s nieczytelny", path.name, exc_info=True)
        return None


def split_or_whole(path: pathlib.Path, pages: int, pl_marker: str = "",
                   texts: list[str] | None = None) -> list[dict]:
    """Części z splittera; gdy cięcie padnie (uszkodzony/zaszyfrowany PDF) — cały plik
    jako jedna część typu faktura. Nie blokuje uploadu: błąd pokaże się przy ekstrakcji."""
    try:
        parts = splitter.split_pdf(str(path), pl_marker, texts)
        if parts:
            return parts
    except Exception:  # noqa: BLE001 — każdy błąd biblioteki PDF to „dokument do ręcznej obsługi”
        logger.warning("faktury: cięcie %s nie powiodło się — cały plik jako faktura", path.name,
                       exc_info=True)
    return [{"kind": InvoiceDocKind.invoice, "page_from": 1, "page_to": max(pages, 1),
             "out_path": str(path), "text": ""}]


def ingest_files(db: Session, batch: InvoiceBatch, container: Container,
                 files: list[tuple[str, str, int]], uploads: pathlib.Path, user: User | None,
                 written: list[pathlib.Path]) -> InvoiceBatch:
    """Pliki (nazwa, nazwa na dysku, liczba stron) już leżą w uploads → dokumenty paczki
    z pozycjami. Dopisuje ścieżki części do `written` (sprzątanie przy błędzie). Commituje."""
    texts_by_file = [page_texts(uploads / stored) for _, stored, _ in files]
    supplier = batch.supplier
    if supplier is None:   # kontener bez dostawcy: słowa kluczowe aktywnych profili spółki
        supplier = profiles.detect_supplier(
            db, "\n".join(t for texts in texts_by_file for t in texts or []), container.company_id)
        batch.supplier = supplier
    profile = profiles.resolve(supplier)
    for (name, stored, pages), texts in zip(files, texts_by_file, strict=True):
        path = uploads / stored
        sha = hashlib.sha256(path.read_bytes()).hexdigest()   # skrót oryginału — bramka dubli (sha001)
        for part in split_or_whole(path, pages, profile.split_marker, texts):
            kind = part["kind"]
            out_path = pathlib.Path(part["out_path"])
            if out_path != path:
                written.append(out_path)
            job = InvoiceJob(filename=part_name(name, part) if out_path != path else name,
                             stored_name=out_path.name,
                             source_name=stored, sha256=sha, page_from=part["page_from"],
                             page_to=part["page_to"], doc_kind=kind,
                             text_excerpt=(part.get("text") or "")[:pipeline.TEXT_EXCERPT_CHARS])
            if kind == InvoiceDocKind.packing_list:
                job.status = InvoiceJobStatus.packing_list
            elif kind == InvoiceDocKind.other:
                job.status = InvoiceJobStatus.ignored
            batch.jobs.append(job)
    db.flush()
    # packing listy są już w paczce → faktury dostają wagi od razu; cache PL wspólny dla
    # wszystkich faktur paczki (jedno parsowanie/OCR każdej packing listy)
    pl_cache: dict = {}
    for job in batch.jobs:
        if job.doc_kind in INVOICE_LIKE_KINDS:
            pipeline.process_job(db, job, profile, container.company_id, uploads, pl_cache)
    # W5 #31: numery kontenerów w tekście części → propozycje podpięcia jako załącznik
    from . import suggestions
    suggestions.propose_for_batch(db, batch, container.company_id)
    audit.record(db, entity_type="containers", entity_id=container.id, field="invoice_batch",
                 old_value=None, new_value=f"{len(batch.jobs)} dokument(ów)", user=user,
                 note=f"faktury: {', '.join(name for name, _, _ in files)}")
    db.commit()
    db.refresh(batch)
    return batch


_PART_LABEL = {InvoiceDocKind.invoice: "faktura", InvoiceDocKind.proforma: "proforma",
               InvoiceDocKind.packing_list: "PL", InvoiceDocKind.other: "inne"}


def part_name(source: str, part: dict) -> str:
    """Nazwa części po cięciu zestawu: „<zestaw>_<typ>_s<od>-<do>.pdf” — agencja i lista plików
    nie dostają kilku dokumentów o nazwie całego zestawu (audyt 2026-10-06 #13)."""
    stem = pathlib.PurePath(source).stem[:80]
    label = _PART_LABEL.get(part["kind"], "inne")
    if part["kind"] == InvoiceDocKind.other and splitter.is_bill_of_lading(part.get("text") or ""):
        label = "BL"
    pages = (f"s{part['page_from']}" if part["page_from"] == part["page_to"]
             else f"s{part['page_from']}-{part['page_to']}")
    return f"{stem}_{label}_{pages}.pdf"


def queue_files(batch: InvoiceBatch, files: list[tuple[str, str, int]], uploads: pathlib.Path) -> None:
    """Zaślepka na każdy wgrany plik — cięcie, OCR i ekstrakcję zrobi `process_pending`."""
    for name, stored, pages in files:
        batch.jobs.append(InvoiceJob(filename=name, stored_name=stored, source_name=stored,
                                     sha256=hashlib.sha256((uploads / stored).read_bytes()).hexdigest(),
                                     page_from=1, page_to=max(pages, 1),
                                     doc_kind=InvoiceDocKind.invoice,
                                     status=InvoiceJobStatus.uploaded))


def _ingest_queued(db: Session, batch: InvoiceBatch, uploads: pathlib.Path) -> None:
    placeholders = [j for j in batch.jobs if j.status == InvoiceJobStatus.uploaded]
    files = [(j.filename, j.stored_name, j.page_to) for j in placeholders]
    for job in placeholders:
        batch.jobs.remove(job)   # delete-orphan: zaślepki zastępują części po cięciu
    container = db.get(Container, batch.container_id)
    user = db.get(User, batch.created_by_id) if batch.created_by_id else None
    written: list[pathlib.Path] = []
    try:
        ingest_files(db, batch, container, files, uploads, user, written)
    except BaseException:
        db.rollback()
        for path in written:
            path.unlink(missing_ok=True)
        raise


MAX_ATTEMPTS = 2   # przerwane przetwarzanie (restart, OOM) — jedna ponowna próba, potem błąd


def _mark_failed(db: Session, batch_id: int, reason: str) -> None:
    """Paczka nie przeszła w tle — zaślepki dostają błąd Z PRZYCZYNĄ (nie wracają do kolejki);
    użytkownik widzi, co się stało, i może kliknąć „Ponów” albo usunąć paczkę."""
    for job in db.scalars(select(InvoiceJob).where(
            InvoiceJob.batch_id == batch_id, InvoiceJob.status == InvoiceJobStatus.uploaded)):
        job.status = InvoiceJobStatus.error
        job.processing_started_at = None
        job.error = f"Nie udało się przetworzyć pliku w tle: {reason} — „Ponów” albo usuń paczkę."
    db.commit()


def _claim(db: Session, batch_id: int) -> bool:
    """Oznacza start przetwarzania (widoczny w UI od razu — osobny commit); False, gdy paczka
    była już przerwana MAX_ATTEMPTS razy — wtedy błąd zamiast kolejnej próby."""
    placeholders = list(db.scalars(select(InvoiceJob).where(
        InvoiceJob.batch_id == batch_id, InvoiceJob.status == InvoiceJobStatus.uploaded)))
    if any((j.attempts or 0) >= MAX_ATTEMPTS for j in placeholders):
        _mark_failed(db, batch_id, f"przerwane {MAX_ATTEMPTS}× (restart serwera albo za duży plik)")
        return False
    for job in placeholders:
        job.attempts = (job.attempts or 0) + 1
        job.processing_started_at = utcnow()
    db.commit()
    return True


def process_pending(db: Session) -> int:
    """Pętla tła: NAJSTARSZA paczka z zaślepkami (`uploaded`) → cięcie, OCR, ekstrakcja.
    Jedna paczka na przebieg — duży zestaw nie blokuje faktur innych kontenerów na cały
    przebieg (pętla wraca co 30 s). Zwraca 1, gdy coś przetworzono."""
    uploads = pathlib.Path(settings.uploads_dir)
    batch_id = db.scalar(select(InvoiceJob.batch_id).where(
        InvoiceJob.status == InvoiceJobStatus.uploaded).order_by(InvoiceJob.batch_id).limit(1))
    batch = db.get(InvoiceBatch, batch_id) if batch_id is not None else None
    if batch is None or not _claim(db, batch.id):
        return 0
    try:
        _ingest_queued(db, batch, uploads)
        return 1
    except Exception as exc:
        logger.exception("faktury w tle: paczka %s nie przetworzona", batch.id)
        _mark_failed(db, batch.id, (str(exc) or type(exc).__name__)[:200])
        return 0


STALE_MINUTES = 30   # „przetwarza” dłużej = uznajemy za przerwane (UI, health, usuwanie paczki)


def is_processing(job: InvoiceJob) -> bool:
    """Zaślepka właśnie liczona przez pętlę tła (start < STALE_MINUTES temu)."""
    started = job.processing_started_at
    return (job.status == InvoiceJobStatus.uploaded and started is not None
            and utcnow() - started < datetime.timedelta(minutes=STALE_MINUTES))


def requeue(job: InvoiceJob) -> bool:
    """„Ponów” na niepociętym zestawie (zaślepka z błędem): z powrotem do kolejki tła zamiast
    czytać cały zestaw jako jedną fakturę w żądaniu HTTP. False = to już pocięta część."""
    # attempts > 0 = zaślepka, która padła w pętli tła; jednostronicowa faktura po ekstrakcji
    # też ma stored_name == source_name, ale attempts 0 — jej „Ponów” to zwykła ekstrakcja
    if (job.stored_name != job.source_name or job.status != InvoiceJobStatus.error
            or not job.attempts):
        return False
    job.status, job.error, job.attempts, job.processing_started_at = (
        InvoiceJobStatus.uploaded, "", 0, None)
    return True
