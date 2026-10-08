"""Sprzątacz osieroconych plików w uploads (spec dokumenty-dostaw §4 pkt 37).

Plik bez wiersza w bazie zostaje po przerwanym wgraniu / starym błędzie zapisu. Ostrożnie:
- tylko znane wzorce nazw z wgrywania dokumentów (inne pliki — awatary, zdjęcia, wzory,
  modele ML — nie są ruszane),
- tylko starsze niż doba (wgranie w toku albo kolejka OCR nie traci pliku),
- nie kasujemy, tylko przenosimy do `_osierocone/` — w razie pomyłki plik da się przywrócić.
ponytail: pełny listing katalogu raz na dobę; przy setkach tysięcy plików — indeks w bazie."""
import datetime
import logging
import pathlib
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import Attachment, FreightInvoice, InvoiceJob

logger = logging.getLogger(__name__)
QUARANTINE = "_osierocone"
MIN_AGE = datetime.timedelta(hours=24)

# wzorzec nazwy → skąd wiadomo, że plik jest w użyciu
_ATTACHMENT = re.compile(r"^\d+_[0-9a-f]{16}_")        # załączniki kontenera (także drafty SAD)
_INVOICE = re.compile(r"^inv_\d+_[0-9a-f]{16}_")        # PDF paczki faktur i jego części _docN_
_FREIGHT = re.compile(r"^bl_[0-9a-f]{16}_")             # faktury transportowe (BL)


def _referenced(db: Session) -> set[str]:
    names = set(db.scalars(select(Attachment.stored_name)))
    for stored, source in db.execute(select(InvoiceJob.stored_name, InvoiceJob.source_name)):
        names.update((stored, source))
    names.update(db.scalars(select(FreightInvoice.stored_name)))
    return {n for n in names if n}


def quarantine_orphans(db: Session, now: datetime.datetime | None = None,
                       uploads: pathlib.Path | None = None) -> int:
    """Przenosi osierocone pliki dokumentów do uploads/_osierocone; zwraca ich liczbę."""
    uploads = uploads or pathlib.Path(settings.uploads_dir)
    if not uploads.is_dir():
        return 0
    cutoff = (now or datetime.datetime.now()).timestamp() - MIN_AGE.total_seconds()
    used = _referenced(db)
    moved = 0
    for path in uploads.iterdir():
        name = path.name
        if (not path.is_file() or name in used or path.stat().st_mtime > cutoff
                or not (_ATTACHMENT.match(name) or _INVOICE.match(name) or _FREIGHT.match(name))):
            continue
        target = uploads / QUARANTINE
        target.mkdir(exist_ok=True)
        path.replace(target / name)
        moved += 1
    if moved:
        logger.warning("sprzątacz plików: %d osieroconych przeniesiono do %s/", moved, QUARANTINE)
    return moved
