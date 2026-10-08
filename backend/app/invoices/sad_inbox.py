"""Skrzynka draftów SAD dla automatu (n8n ← skrypt Outlooka na komputerze 24/7, docs/SAD-Z-POCZTY.md).

Automat nie zna paczki faktur — dostaje tylko plik z maila agencji. Kontener czytamy z samego
pliku (PDF: odczyt WinSAD / ogólny, XML: eksport SADUE) i trafiamy w najnowszą paczkę faktur
tego kontenera w zakresie konta automatu (deps.scope_containers — te same reguły co dla ludzi):
- PDF → nowa wersja draftu (ten sam plik ponownie = bez duplikatu) + porównanie z fakturami,
- XML → dołącza do najnowszej wersji draftu (agencja przysyła go po PDF) + nowe porównanie.
Odpowiedź mówi, co się stało, żeby n8n mógł zgłosić człowiekowi przypadki „nie rozpoznano”."""
import pathlib
import tempfile

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import scope_containers
from ..models import Container, InvoiceBatch, SadDraft, User
from . import sad_drafts as flow
from . import sad_parse


def _read(filename: str, content: bytes) -> tuple[str, dict]:
    if filename.lower().endswith(".xml"):
        parsed = sad_parse.parse_xml(content)
        if parsed is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "To nie jest XML draftu SAD z WinSAD (oczekiwany eksport SADUE).")
        return "xml", parsed
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Draft SAD: oczekiwany PDF albo XML.")
    with tempfile.TemporaryDirectory() as tmp:          # odczyt PDF (pdfplumber/OCR) chce ścieżki
        path = pathlib.Path(tmp) / "draft.pdf"
        path.write_bytes(content)
        return "pdf", sad_parse.parse_file(str(path))


def _batch(db: Session, container_no: str, user: User) -> InvoiceBatch:
    query = (select(InvoiceBatch).join(Container, InvoiceBatch.container_id == Container.id)
             .where(Container.container_no == container_no))
    batches = db.scalars(scope_containers(query, user).order_by(InvoiceBatch.id.desc())).all()
    if len({b.container_id for b in batches}) > 1:   # §4 pkt 21: ten numer w dwóch spółkach
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Kontener {container_no} jest w kilku spółkach — wgraj draft ręcznie "
                            f"przy właściwej paczce faktur.")
    batch = batches[0] if batches else None
    if batch is None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Kontener {container_no}: brak paczki faktur — wgraj faktury, potem ponów.")
    return batch


def receive(db: Session, filename: str, content: bytes, user: User) -> dict:
    kind, parsed = _read(filename, content)
    container_no = (parsed.get("container") or "").replace(" ", "").upper()
    if not container_no:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Nie odczytano numeru kontenera z draftu — wgraj ręcznie przy paczce faktur.")
    batch = _batch(db, container_no, user)
    if kind == "pdf":
        draft, created = flow.add_draft(db, batch, filename, content, user, "automation")
    else:
        newest = db.scalars(select(SadDraft).where(SadDraft.batch_id == batch.id)
                            .order_by(SadDraft.version.desc())).first()
        if newest is None:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"Kontener {container_no}: XML przed PDF — brak wersji draftu, ponów później.")
        draft, created = flow.attach_xml(db, batch, newest.id, filename, content, user, "automation")
    comparison = flow.compare_draft(db, batch, draft.id, user) if created else None
    return {"kind": kind, "created": created, "container": container_no, "batch_id": batch.id,
            "draft_id": draft.id, "version": draft.version, "sad_no": parsed.get("sad_no"),
            "summary": (comparison or {}).get("summary")}
