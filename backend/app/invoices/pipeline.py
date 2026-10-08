"""Orkiestracja jednego dokumentu: ekstrakcja → wagi z packing listy → dopasowanie →
pozycje; oraz zatwierdzanie (ambiguous blokuje, unmatched nie) i stan paczki."""
import logging
import pathlib
import re

from sqlalchemy.orm import Session

from ..models import (
    INVOICE_LIKE_KINDS,
    InvoiceBatch,
    InvoiceDocKind,
    InvoiceJob,
    InvoiceJobStatus,
    InvoiceMatchStatus,
    utcnow,
)
from . import extractor, ocr, packing_list
from .matching import build_items
from .profiles import DocProfile

logger = logging.getLogger(__name__)

# ile znaków tekstu dokumentu trzymamy jako dane treningowe klasyfikatora typu
TEXT_EXCERPT_CHARS = 4000


def _packing_list(pl: InvoiceJob, uploads: pathlib.Path, cache: dict,
                  pl_map: dict | None = None) -> tuple[str, dict, dict]:
    """(tekst 1–2 stron, mapa wag, mapa ilości) packing listy — liczone raz per paczka (cache po pliku),
    bo każda faktura paczki pyta o te same PL, a OCR skanu PL to sekundy."""
    if pl.stored_name not in cache:
        # JEDNO parsowanie (tekst + tabele; OCR skanu raz) — osobne page_texts + parse_pdf
        # czytałoby każdą stronę PL dwa razy
        doc = extractor.parse_pdf(str(uploads / pl.stored_name), pl_map)
        cache[pl.stored_name] = (doc.raw_text, packing_list.weight_map_from_items(doc.items),
                                 packing_list.qty_map_from_items(doc.items))
    return cache[pl.stored_name]


def weight_map_for(batch: InvoiceBatch, invoice_number: str, uploads: pathlib.Path,
                   cache: dict | None = None, pl_map: dict | None = None) -> dict:
    return pl_maps_for(batch, invoice_number, uploads, cache, pl_map)[0]


def pl_maps_for(batch: InvoiceBatch, invoice_number: str, uploads: pathlib.Path,
                cache: dict | None = None, pl_map: dict | None = None) -> tuple[dict, dict]:
    """(wagi, ilości) z packing list paczki: najpierw PL, których tekst zawiera numer TEJ
    faktury; żadna nie pasuje → unia wszystkich PL paczki (fallback)."""
    pls = [j for j in batch.jobs if j.doc_kind == InvoiceDocKind.packing_list
           and j.status != InvoiceJobStatus.ignored]   # pominięta PL nie daje wag
    if not pls:
        return {}, {}
    cache = {} if cache is None else cache
    parsed = [(pl, *_packing_list(pl, uploads, cache, pl_map)) for pl in pls]
    matched = [entry for entry in parsed if _mentions(entry[1], invoice_number)]
    if not matched and len(parsed) > 1:
        # kilka PL, żadna nie wymienia tej faktury: unia dałaby wagi CUDZYCH pozycji
        return {}, {}
    weights: dict = {}
    qtys: dict = {}
    for _, _, weight_map, qty_map in (matched or parsed):
        weights.update(weight_map)
        qtys.update(qty_map)
    return weights, qtys


def _mentions(text: str, invoice_number: str) -> bool:
    """„FV/1” w tekście PL, ale nie jako fragment „FV/10” — granice po obu stronach."""
    if not invoice_number:
        return False
    return re.search(rf"(?<![\w/-]){re.escape(invoice_number)}(?![\w/-])", text) is not None


def process_job(db: Session, job: InvoiceJob, profile: DocProfile | None,
                company_id: int | None, uploads: pathlib.Path,
                pl_cache: dict | None = None) -> InvoiceJobStatus:
    """Ekstrakcja + dopasowanie. Nie commituje — wołający decyduje o granicy transakcji.
    `profile` = profiles.resolve(dostawca paczki) — mapy CI/PL i rodzaj REF.
    `pl_cache` współdzielony między fakturami jednej paczki (patrz _packing_list)."""
    profile = profile or DocProfile()
    path = str(uploads / job.stored_name)
    try:
        doc = extractor.parse_pdf(path, profile.ci_map)
    except Exception as exc:  # uszkodzony PDF, zaszyfrowany itd. — dokument, nie 500
        logger.warning("faktura %s: ekstrakcja padła: %s", job.filename, exc, exc_info=True)
        job.status = InvoiceJobStatus.error
        job.error = f"Nie udało się odczytać pliku: {str(exc)[:200]}"
        return job.status
    job.text_excerpt = doc.raw_text[:TEXT_EXCERPT_CHARS]
    job.ocr_used = doc.ocr_used
    if not doc.items:
        job.status = InvoiceJobStatus.error
        if not doc.raw_text.strip():
            job.error = ("Nie udało się odczytać pliku — PDF bez warstwy tekstowej (skan), a OCR "
                         + ("nie rozpoznał tekstu." if ocr.is_available()
                            else "jest niedostępny (brak tesseract na serwerze)."))
        else:
            job.error = ("Nie udało się odczytać tabeli pozycji — nierozpoznany układ kolumn "
                         "(ustaw mapę kolumn u dostawcy)" + (" lub słaba jakość skanu." if doc.ocr_used else "."))
        return job.status
    meta = extractor.header_meta(doc.raw_text)
    try:
        weight_map, pl_qty = pl_maps_for(job.batch, doc.invoice_number, uploads, pl_cache,
                                         profile.pl_map)
    except Exception as exc:  # waga to dane pomocnicze — błąd nie wywraca faktury
        logger.warning("faktura %s: wagi z packing listy: %s", job.filename, exc, exc_info=True)
        weight_map, pl_qty = {}, {}
    # dane kontroli (checks.py), których nie da się odtworzyć z pozycji: suma z faktury
    # i ilości per REF z packing listy
    job.check_data = {"doc_total": doc.total_net or "", "pl_qty": pl_qty, "charges": doc.charges}
    job.items = build_items(db, doc.items, company_id, weight_map,
                            supplier_id=job.batch.supplier_id if job.batch else None,
                            ref_kind=profile.ref_kind)
    job.invoice_number = doc.invoice_number[:80]
    job.container_no = meta["container_no"][:20]
    job.delivery_terms = meta["delivery_terms"]
    job.status = InvoiceJobStatus.extracted
    job.error = ""
    job.updated_at = utcnow()
    return job.status


def confirm_job(job: InvoiceJob) -> tuple[bool, str]:
    """Zatwierdzić można tylko dokument po udanej ekstrakcji, z aktywnymi pozycjami
    i bez niejednoznacznych dopasowań."""
    if job.status not in (InvoiceJobStatus.extracted, InvoiceJobStatus.confirmed):
        return False, "Dokument nie jest gotowy do zatwierdzenia (brak udanej ekstrakcji)."
    active = [item for item in job.items if not item.skipped]
    if not active:
        return False, "Brak pozycji do zatwierdzenia."
    if not (job.invoice_number or "").strip():
        return False, "Uzupełnij numer faktury — bez niego kolumna „Nr faktury” w Excelu byłaby pusta."
    if any(item.match_status == InvoiceMatchStatus.ambiguous for item in active):
        return False, "Rozstrzygnij niejednoznaczne pozycje (X/X1) przed zatwierdzeniem."
    job.status = InvoiceJobStatus.confirmed
    job.updated_at = utcnow()
    return True, ""


def batch_counts(batch: InvoiceBatch) -> dict:
    """Pominięty (ignored) dokument nie liczy się do gotowości — zachowuje jednak swój
    doc_kind, żeby „Przywróć” (ponowna ekstrakcja) mogło go cofnąć do paczki."""
    invoice_like = [j for j in batch.jobs if j.doc_kind in INVOICE_LIKE_KINDS
                    and j.status != InvoiceJobStatus.ignored]
    confirmed = [j for j in invoice_like if j.status == InvoiceJobStatus.confirmed]
    errors = [j for j in invoice_like if j.status == InvoiceJobStatus.error]
    return {"total": len(invoice_like), "confirmed": len(confirmed), "errors": len(errors),
            "ready": bool(invoice_like) and len(confirmed) == len(invoice_like)}
