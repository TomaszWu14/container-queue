"""Obieg wymiany z agencją po wysłaniu faktur: potwierdzenie odbioru, wersje draftu SAD,
decyzja. Jedno wejście dla operatora (router) i automatu (n8n, PR 4) — `source`."""
import hashlib
import pathlib
import secrets

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import audit
from ..config import settings
from ..models import (DECISIONS, SOURCES, AgencyAck, Attachment, Container, DocumentType, InvoiceBatch,
                      SadDraft, User, utcnow)
from ..notifications import container_watchers, notify
from . import sad_compare, sad_ours, sad_parse

DOC_TYPE = "Draft SAD"


def _check_source(source: str) -> None:
    if source not in SOURCES:
        raise ValueError(f"nieznane źródło: {source}")


def acknowledge(db: Session, batch: InvoiceBatch, user: User | None, source: str) -> AgencyAck:
    _check_source(source)
    ack = db.get(AgencyAck, batch.id)
    if ack is not None:
        return ack
    ack = AgencyAck(batch_id=batch.id, acked_at=utcnow(), source=source,
                    acked_by_id=user.id if user else None)
    db.add(ack)
    audit.record(db, entity_type="containers", entity_id=batch.container_id, field="agency_ack",
                 old_value=None, new_value=source, user=user,
                 note=f"agencja potwierdziła odbiór faktur (paczka #{batch.id})")
    return ack


def _doc_type(db: Session) -> DocumentType:
    # kafelek SAD-DRAFT (kod przy typie, migracja tile001); nazwa — gdy kodu jeszcze nikt nie nadał
    doc_type = (db.scalar(select(DocumentType).where(DocumentType.tile_code == "SAD_DRAFT"))
                or db.scalar(select(DocumentType).where(DocumentType.name == DOC_TYPE)))
    if doc_type is None:
        doc_type = DocumentType(name=DOC_TYPE, is_active=True, is_required=False, tile_code="SAD_DRAFT")
        db.add(doc_type)
        db.flush()
    return doc_type


def _commit_with_file(db: Session, stored: str, content: bytes) -> None:
    """Jak forwarding_files.commit_with_file (moduł domenowy nie importuje routerów, ARCH-001):
    plik przed commitem, sprzątany gdy commit padnie."""
    uploads = pathlib.Path(settings.uploads_dir)
    uploads.mkdir(parents=True, exist_ok=True)
    path = uploads / stored
    path.write_bytes(content)
    try:
        db.commit()
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _check_name(filename: str) -> None:
    if not filename or pathlib.PurePath(filename.replace("\\", "/")).name != filename:
        raise ValueError(f"nazwa pliku ze ścieżką: {filename!r}")


def _attachment(db: Session, batch: InvoiceBatch, filename: str, content: bytes,
                content_type: str, user: User | None) -> Attachment:
    stored = f"{batch.container_id}_{secrets.token_hex(8)}_{filename}"
    attachment = Attachment(container_id=batch.container_id, filename=filename, stored_name=stored,
                            content_type=content_type, size=len(content),
                            uploaded_by_id=user.id if user else None,
                            document_type_id=_doc_type(db).id)
    db.add(attachment)
    db.flush()
    return attachment


def newest_batch(db: Session, container_id: int) -> InvoiceBatch | None:
    return db.scalars(select(InvoiceBatch).where(InvoiceBatch.container_id == container_id)
                      .order_by(InvoiceBatch.id.desc())).first()


def _by_sha(db: Session, batch_id: int, digest: str) -> SadDraft | None:
    return db.scalar(select(SadDraft).where(SadDraft.batch_id == batch_id,
                                            SadDraft.sha256 == digest))


def add_draft(db: Session, batch: InvoiceBatch, filename: str, content: bytes,
              user: User | None, source: str) -> tuple[SadDraft, bool]:
    """Nowa wersja draftu SAD; ten sam plik ponownie (np. ponowienie automatu) → istniejąca
    wersja bez duplikatu. Przyjęcie draftu = także potwierdzenie odbioru. `filename` — już
    bezpieczna nazwa (wołający: routers.forwarding_files.safe_filename), bez ścieżki."""
    _check_source(source)
    _check_name(filename)
    batch_id = batch.id
    digest = hashlib.sha256(content).hexdigest()
    existing = _by_sha(db, batch_id, digest)
    if existing is not None:
        return existing, False
    acknowledge(db, batch, user, source)
    version = (db.scalar(select(func.max(SadDraft.version))
                         .where(SadDraft.batch_id == batch_id)) or 0) + 1
    attachment = _attachment(db, batch, filename, content, "application/pdf", user)
    stored = attachment.stored_name
    draft = SadDraft(batch_id=batch_id, version=version, attachment_id=attachment.id,
                     sha256=digest, source=source, created_by_id=user.id if user else None)
    db.add(draft)
    audit.record(db, entity_type="containers", entity_id=batch.container_id, field="sad_draft",
                 old_value=None, new_value=f"v{version}", user=user,
                 note=f"draft SAD v{version} od agencji ({source}, {filename})")
    # §4 pkt 20: draft z poczty (automat) przychodził po cichu — logistyka/agencja dostaje dzwonek
    container = db.get(Container, batch.container_id)
    if container is not None:
        notify(db, container_watchers(db, container), kind="customs",
               title=f"Draft SAD v{version} przy {container.container_no}",
               body=f"{filename} ({'z poczty' if source == 'automation' else 'wgrany ręcznie'})",
               container_id=container.id, exclude_user_id=user.id if user else None)
    try:
        _commit_with_file(db, stored, content)
    except IntegrityError as exc:
        # wyścig na uq_sad_drafts_batch_{version,sha} (dwa równoległe wgrania / ponowienie
        # automatu): ten sam plik → wersja zwycięzcy; inny plik → operator odświeża
        db.rollback()
        existing = _by_sha(db, batch_id, digest)
        if existing is not None:
            return existing, False
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Równolegle wgrano inną wersję draftu — odśwież i spróbuj ponownie.") from exc
    return draft, True


def _draft(db: Session, batch: InvoiceBatch, draft_id: int) -> SadDraft:
    draft = db.get(SadDraft, draft_id)
    if draft is None or draft.batch_id != batch.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie ma takiego draftu SAD w tej paczce.")
    return draft


def decide(db: Session, batch: InvoiceBatch, draft_id: int, decision: str, comment: str,
           user: User) -> SadDraft:
    draft = _draft(db, batch, draft_id)
    if decision not in DECISIONS or decision == "pending":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Decyzja: accepted albo rejected.")
    comment = (comment or "").strip()
    if decision == "rejected" and not comment:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Przy „do poprawy” wpisz, co agencja ma poprawić.")
    newest = db.scalar(select(func.max(SadDraft.version)).where(SadDraft.batch_id == batch.id))
    if draft.version != newest:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Jest nowsza wersja draftu (v{newest}) — oceń najnowszą.")
    old = draft.decision
    draft.decision, draft.comment = decision, comment[:1000]
    draft.decided_by_id, draft.decided_at = user.id, utcnow()
    audit.record(db, entity_type="containers", entity_id=batch.container_id,
                 field="sad_decision", old_value=old, new_value=decision, user=user,
                 note=f"draft SAD v{draft.version}: {decision}" + (f" — {comment}" if comment else ""))
    db.commit()
    return draft


def _file(draft: SadDraft, attachment: Attachment | None = None) -> str:
    path = pathlib.Path(settings.uploads_dir) / (attachment or draft.attachment).stored_name
    if not path.is_file():
        raise HTTPException(status.HTTP_410_GONE,
                            "Plik draftu SAD zniknął z serwera — wgraj go ponownie.")
    return str(path)


def _outcome(summary: dict | None) -> str | None:
    if not summary:
        return None
    return (f"grupy CN {summary['ok']}/{summary['groups']} zgodne, różnice {summary['diff']}, "
            f"do sprawdzenia {summary['manual']}")


def _parsed(draft: SadDraft) -> dict:
    """Odczyt wersji: z XML, gdy dołączony (zastępuje PDF), inaczej z PDF; zapamiętany w `parsed`
    i odświeżany po zmianie PARSER_VERSION albo źródła. Strony podglądu zawsze z PDF."""
    parsed = draft.parsed
    if parsed and parsed.get("v") == sad_parse.PARSER_VERSION and (
            parsed.get("layout") == sad_parse.XML_LAYOUT) == bool(draft.xml_attachment_id):
        return parsed
    pdf = _file(draft)
    if draft.xml_attachment is not None:
        xml = sad_parse.parse_xml(pathlib.Path(_file(draft, draft.xml_attachment)).read_bytes())
        if xml is None:              # plik przyjęty przy wgraniu — tu tylko po ręcznej podmianie
            raise HTTPException(status.HTTP_410_GONE, "XML draftu SAD jest nieczytelny.")
        parsed = {**xml, "pages": sad_parse.page_count(pdf)}
    else:
        parsed = sad_parse.parse_file(pdf)
    draft.parsed = parsed
    return parsed


def attach_xml(db: Session, batch: InvoiceBatch, draft_id: int, filename: str, content: bytes,
               user: User | None, source: str) -> tuple[SadDraft, bool]:
    """XML z WinSAD do istniejącej wersji draftu (agencja dosyła go po PDF). Ten sam plik ponownie
    → bez zmian; inny XML do wersji, która już ma XML → 409 (poprawka = nowa wersja draftu).
    Kontener z XML musi zgadzać się z odczytem PDF — łapie pomyłkę „XML od innego zgłoszenia”."""
    _check_source(source)
    _check_name(filename)
    draft = _draft(db, batch, draft_id)
    digest = hashlib.sha256(content).hexdigest()
    if draft.xml_sha256 == digest:
        return draft, False
    if draft.xml_attachment_id is not None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Draft v{draft.version} ma już XML — poprawka od agencji to nowa wersja draftu.")
    xml = sad_parse.parse_xml(content)
    if xml is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "To nie jest XML draftu SAD z WinSAD (oczekiwany eksport SADUE).")
    pdf = _parsed(draft)
    if pdf.get("container") and xml["container"] and pdf["container"] != xml["container"]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"XML dotyczy kontenera {xml['container']}, a draft v{draft.version} "
                            f"— {pdf['container']}. Sprawdź, czy to właściwy plik.")
    attachment = _attachment(db, batch, filename, content, "application/xml", user)
    draft.xml_attachment_id, draft.xml_sha256 = attachment.id, digest
    draft.parsed = {**xml, "pages": pdf.get("pages", 0)}
    audit.record(db, entity_type="containers", entity_id=batch.container_id, field="sad_draft_xml",
                 old_value=None, new_value=f"v{draft.version}", user=user,
                 note=f"XML draftu SAD v{draft.version} ({source}, {filename}"
                      + (f", zgłoszenie {xml['sad_no']}" if xml.get("sad_no") else "") + ")")
    _commit_with_file(db, attachment.stored_name, content)
    return draft, True


def compare_draft(db: Session, batch: InvoiceBatch, draft_id: int, user: User | None) -> dict:
    """Porównanie wersji draftu z paczką. Draft czytany raz (`_parsed`: XML albo PDF); nasza strona zawsze z bieżących pozycji; wynik zapisany w `comparison`
    (PR 3: rozbieżności do szkicu odpowiedzi „Do poprawy”). Audyt (OBS-003) tylko przy
    zmianie wyniku — ponowne „Porównaj” bez zmian nie zaśmieca historii kontenera."""
    draft = _draft(db, batch, draft_id)
    parsed = _parsed(draft)
    comparison = {**sad_compare.compare(sad_ours.batch_side(db, batch), parsed),
                  "at": utcnow().isoformat()}
    old = _outcome((draft.comparison or {}).get("summary"))
    new = _outcome(comparison["summary"])
    if new != old:
        audit.record(db, entity_type="containers", entity_id=batch.container_id,
                     field="sad_compare", old_value=old, new_value=new, user=user,
                     note=f"porównanie draftu SAD v{draft.version} z fakturami")
    draft.comparison = comparison
    db.commit()
    return {"draft_id": draft.id, "version": draft.version, "pages": parsed.get("pages", 0),
            **comparison}


def page_png(db: Session, batch: InvoiceBatch, draft_id: int, page: int) -> bytes:
    path = _file(_draft(db, batch, draft_id))
    if not 1 <= page <= sad_parse.page_count(path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie ma takiej strony draftu.")
    return sad_parse.page_png(path, page - 1)


def _name(db: Session, user_id: int | None) -> str | None:
    user = db.get(User, user_id) if user_id else None
    return (user.full_name or user.login) if user else None


def _data_from(draft: SadDraft) -> str | None:
    """Skąd dane porównania: „xml”, „pdf” (wstępnie, do nadejścia XML) albo None (jeszcze nie czytano)."""
    if not draft.parsed:
        return None
    return "xml" if draft.parsed.get("layout") == sad_parse.XML_LAYOUT else "pdf"


def state(db: Session, batch: InvoiceBatch) -> dict:
    ack = db.get(AgencyAck, batch.id)
    drafts = db.scalars(select(SadDraft).where(SadDraft.batch_id == batch.id)
                        .order_by(SadDraft.version.desc())).all()
    return {
        "ack": None if ack is None else {"at": ack.acked_at.isoformat(), "source": ack.source,
                                         "by": _name(db, ack.acked_by_id)},
        "drafts": [{"id": d.id, "version": d.version, "attachment_id": d.attachment_id,
                    "filename": d.attachment.filename, "source": d.source,
                    "xml_attachment_id": d.xml_attachment_id,
                    "xml_filename": d.xml_attachment.filename if d.xml_attachment else None,
                    "data_from": _data_from(d),
                    "decision": d.decision, "comment": d.comment,
                    "created_at": d.created_at.isoformat(),
                    "decided_at": d.decided_at.isoformat() if d.decided_at else None,
                    "decided_by": _name(db, d.decided_by_id),
                    "summary": (d.comparison or {}).get("summary")} for d in drafts],
    }
