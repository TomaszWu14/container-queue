"""Bramka wgrania dokumentu do kontenera (2026-10-06): czy PDF jest czytelny i czy dotyczy TEGO
kontenera. Reguła jak bramka faktur (decyzja 2026-10-01): inny numer kontenera = odrzucenie
z podpowiedzią, brak numeru / skan bez tekstu = „niepewny” (wpuszczamy z ostrzeżeniem).

Tylko warstwa tekstowa (bez OCR): pierwsze strony, a przy konflikcie cały dokument (§4 pkt 30)
— upload ma być szybki; numery kontenerów
z poprawną cyfrą kontrolną ISO 6346 (suggestions.found_container_numbers)."""
import hashlib
import io
import pathlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from .attachment_links import in_container
from .invoices.suggestions import found_container_numbers
from .models import Attachment, InvoiceBatch, InvoiceJob

OK, UNCERTAIN, CONFLICT, UNREADABLE = "ok", "uncertain", "conflict", "unreadable"
MAX_PAGES = 5          # numer kontenera bywa na 1. stronie; dalej certyfikaty/załączniki
MIN_TEXT = 30          # mniej znaków = skan bez warstwy tekstowej


def check_pdf(content: bytes, container_no: str) -> dict:
    """{status, message, found}: ok / uncertain (wpuść z ostrzeżeniem) / conflict / unreadable."""
    return check_pdf_text(content, container_no)[0]


def check_pdf_text(content: bytes, container_no: str) -> tuple[dict, str]:
    """Jak check_pdf + przeczytana warstwa tekstowa (poczekalnia dopasowuje po niej PO/fakturę
    — bez drugiego czytania PDF-a). Tekst pusty, gdy PDF nieczytelny."""
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            return _out(UNREADABLE, "PDF jest zaszyfrowany (hasło) — agencja i aplikacja go nie odczytają."), ""
        pages = len(reader.pages)
    except (PdfReadError, ValueError, OSError, KeyError):
        return _out(UNREADABLE, "Plik nie jest poprawnym PDF-em (uszkodzony albo inny format)."), ""
    if pages == 0:
        return _out(UNREADABLE, "PDF nie ma żadnej strony."), ""
    text = _text(content)
    if len(text.strip()) < MIN_TEXT:
        return _out(UNCERTAIN, "Skan bez warstwy tekstowej — numeru kontenera nie sprawdzono."), text
    found = found_container_numbers(text)
    own = (container_no or "").upper()
    if own and own in found:
        return _out(OK, "", found), text
    if found and own and pages > MAX_PAGES:
        # §4 pkt 30 (decyzja 29): konflikt na pierwszych stronach — czytamy CAŁY dokument;
        # nasz numer dalej (zbiorczy B/L, lista kontenerów na końcu) = dokument dotyczy nas
        text = _text(content, pages=None)
        found = found_container_numbers(text)
        if own in found:
            return _out(OK, "", found), text
    if found:
        return _out(CONFLICT, f"Dokument dotyczy kontenera {', '.join(found)}, nie {own} — "
                              f"wgraj go do właściwego kontenera.", found), text
    return _out(UNCERTAIN, f"W dokumencie nie ma numeru kontenera {own} — sprawdź, czy to właściwy plik."), text


def _text(content: bytes, pages: int | None = MAX_PAGES) -> str:
    import pdfplumber
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages[:pages])
    except Exception:  # noqa: BLE001 — pypdf otworzył, pdfplumber nie: traktuj jak skan
        return ""


def _out(status: str, message: str, found: list[str] | None = None) -> dict:
    return {"status": status, "message": message, "found": found or []}


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def find_duplicate(db: Session, container_id: int, content: bytes,
                   uploads: pathlib.Path) -> Attachment | None:
    """Ten sam plik już leży w załącznikach kontenera — też jako wspólny z innym (po skrócie, sha001). Dubel z pomyłkowego
    drugiego kliknięcia = odmowa z informacją."""
    hit = db.scalar(select(Attachment).where(in_container(container_id),
                                             Attachment.sha256 == digest(content)).limit(1))
    if hit is not None:
        return hit
    # wiersze sprzed sha001 (bez skrótu): porównanie treści, kandydaci po rozmiarze
    for att in db.scalars(select(Attachment).where(in_container(container_id),
                                                   Attachment.sha256.is_(None),
                                                   Attachment.size == len(content))):
        path = uploads / att.stored_name
        if path.is_file() and path.read_bytes() == content:
            return att
    return None


def find_batch_duplicate(db: Session, container_id: int, content: bytes,
                         uploads: pathlib.Path) -> InvoiceBatch | None:
    """Ten sam PDF już wgrany do paczki faktur kontenera — też przeniesiony/skopiowany z innej
    paczki (skrót zostaje z dokumentem, §4 pkt 17). Audyt 2026-10-06 #2: druga paczka = drugi
    OCR, Excel i mail."""
    in_container = (select(InvoiceJob.batch_id).join(InvoiceBatch, InvoiceJob.batch_id == InvoiceBatch.id)
                    .where(InvoiceBatch.container_id == container_id))
    batch_id = db.scalar(in_container.where(InvoiceJob.sha256 == digest(content)).limit(1))
    if batch_id is not None:
        return db.get(InvoiceBatch, batch_id)
    # dokumenty sprzed sha001: porównanie z oryginałem zestawu (`source_name`)
    legacy = db.execute(in_container.add_columns(InvoiceJob.source_name)
                        .where(InvoiceJob.sha256.is_(None), InvoiceJob.source_name != "").distinct()).all()
    for batch_id, name in legacy:
        path = uploads / name
        if path.is_file() and path.stat().st_size == len(content) and path.read_bytes() == content:
            return db.get(InvoiceBatch, batch_id)
    return None


def duplicate_reason(db: Session, container_id: int, content: bytes,
                     uploads: pathlib.Path) -> str | None:
    """Dubel w KTÓRYMKOLWIEK kanale kontenera — załączniki albo paczka faktur (§4 pkt 14):
    ten sam PDF wgrany raz jako plik, raz jako faktura, to nadal jeden dokument."""
    att = find_duplicate(db, container_id, content, uploads)
    if att is not None:
        return f"już jest w kontenerze jako „{att.filename}”, wgrany {att.created_at:%d.%m.%Y %H:%M}"
    batch = find_batch_duplicate(db, container_id, content, uploads)
    if batch is not None:
        return f"już jest w paczce faktur z {batch.created_at:%d.%m.%Y %H:%M}"
    return None
