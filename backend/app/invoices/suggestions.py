"""Auto-propozycje podpięcia dokumentów z pipeline'u faktur do kontenerów (W5 #31).

Po przetworzeniu paczki: w tekście każdej części szukamy numerów kontenerów
(ISO 6346 z cyfrą kontrolną); numer istniejący w spółce → propozycja podpięcia
(status proposed). Nic nie kopiujemy — dopiero akceptacja człowieka tworzy Attachment.
"""
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import iso6346
from ..models import AttachmentSuggestion, Container, InvoiceBatch, SuggestionStatus

# wzorzec ISO 6346 w tekście dokumentu (właściciel + kategoria U/J/Z + 6 cyfr + kontrolna)
CONTAINER_NO_RE = re.compile(r"\b[A-Z]{3}[UJZ]\d{7}\b")


def found_container_numbers(text: str) -> list[str]:
    """Numery kontenerów z tekstu — tylko z poprawną cyfrą kontrolną (OCR-owe
    przekłamania jednej cyfry odpadają same)."""
    seen, out = set(), []
    for match in CONTAINER_NO_RE.findall((text or "").upper()):
        if match in seen:
            continue
        seen.add(match)
        if iso6346.validate(match)[0]:
            out.append(match)
    return out


def propose_for_batch(db: Session, batch: InvoiceBatch, company_id: int) -> int:
    """Tworzy propozycje dla wszystkich części paczki. Zwraca liczbę nowych.
    Idempotentne per (job, kontener) — ponowna ekstrakcja nie dubluje propozycji."""
    created = 0
    for job in batch.jobs:
        numbers = set(found_container_numbers(job.text_excerpt))
        if job.container_no:
            numbers.add(job.container_no.upper())
        if not numbers:
            continue
        containers = db.scalars(select(Container).where(
            Container.company_id == company_id,
            Container.id != batch.container_id,   # §4 pkt 11: własny kontener paczki = dubel faktury
            Container.container_no.in_(sorted(numbers)))).all()
        if not containers:
            continue
        existing = set(db.execute(select(AttachmentSuggestion.container_id).where(
            AttachmentSuggestion.job_id == job.id)).scalars())
        for container in containers:
            if container.id in existing:
                continue
            db.add(AttachmentSuggestion(job_id=job.id, container_id=container.id,
                                        doc_kind=job.doc_kind.value,
                                        status=SuggestionStatus.proposed))
            created += 1
    return created
