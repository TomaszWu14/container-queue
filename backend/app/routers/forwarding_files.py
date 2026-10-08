"""Spedycja: załączniki kontenera (upload/lista/pobranie) oraz
wspólne helpery uploadu (katalog, bezpieczna nazwa, limit rozmiaru) używane w wielu routerach.

Router bez prefiksu — prefiks /api i tag nadaje forwarding.router, który go dołącza.
Helpery są nadal importowalne z .forwarding.
"""
import pathlib
import secrets

from fastapi import APIRouter, Depends, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..audit import record_changes
from ..config import settings
from ..database import get_db
from ..deps import NonWarehouseViewers as non_warehouse
from ..deps import Viewer as viewer
from ..deps import forwarder_may_see, get_scoped
from .. import audit
from ..models import (
    Attachment,
    AttachmentSuggestion,
    Container,
    DocumentStatus,
    DocumentType,
    SuggestionStatus,
    User,
)
from .. import attachment_rules as rules
from ..attachment_links import add_link, containers_of, in_container
from ..document_gate import CONFLICT, UNCERTAIN, UNREADABLE, check_pdf, digest, duplicate_reason
from ..document_tiles import sad_customs_target
from ..invoices import sad_drafts as sad_flow
from ..notifications import container_watchers, notify
from ..schemas import AttachmentOut
from .containers import get_container_checked
from .containers_common import CUSTOMS_EDITORS, sync_status_from_customs

router = APIRouter()


def uploads_dir() -> pathlib.Path:
    path = pathlib.Path(settings.uploads_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def commit_with_file(db: Session, path: pathlib.Path, content: bytes) -> None:
    """Zapis pliku PRZED commitem (wiersz nigdy nie wskazuje na brakujący plik);
    gdy commit padnie — plik jest sprzątany (bez osieroconych plików)."""
    path.write_bytes(content)
    try:
        db.commit()
    except IntegrityError as exc:   # uq_attachments_container_sha: równoległe wgranie tego samego
        db.rollback()
        path.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_409_CONFLICT, "Ten plik właśnie trafił do kontenera.") from exc
    except Exception:
        path.unlink(missing_ok=True)
        raise


_FILENAME_KEEP = 120


def safe_filename(filename: str | None, fallback: str = "plik") -> str:
    r"""Nazwa pliku od klienta: bez ścieżki (także windowsowej „\”, zip-slip), rdzeń
    przycięty do 120 znaków + rozszerzenie (≤8) — z prefiksem stored_name mieści się
    w String(255)."""
    name = pathlib.PurePath((filename or "").replace("\\", "/")).name or fallback
    stem, suffix = pathlib.PurePath(name).stem, pathlib.PurePath(name).suffix[:8]
    return (stem[:_FILENAME_KEEP] + suffix) if len(name) > _FILENAME_KEEP + len(suffix) else name


def read_upload_capped(file: UploadFile, max_mb: int, label: str = "Plik") -> bytes:
    """Wczytuje upload z twardym limitem — bez buforowania całego pliku w pamięci (anty-OOM)."""
    max_bytes = max_mb * 1024 * 1024
    if file.size is not None and file.size > max_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            f"{label} przekracza {max_mb} MB.")
    content = file.file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            f"{label} przekracza {max_mb} MB.")
    return content


@router.get("/containers/{container_id}/attachments", response_model=list[AttachmentOut])
def list_attachments(container_id: int, db: Session = Depends(get_db), user: User = viewer):
    container = get_container_checked(db, container_id, user)
    attachments = db.scalars(select(Attachment)
                             .options(selectinload(Attachment.uploaded_by),
                                      selectinload(Attachment.document_type))
                             .where(in_container(container_id))
                             .order_by(Attachment.created_at)).all()
    return _outs(db, [a for a in attachments if forwarder_may_see(a, user)], container, user)


def _outs(db: Session, attachments: list[Attachment], container: Container,
          user: User) -> list[AttachmentOut]:
    """Lista z oznaczeniem wspólnych plików: `shared_with` = pozostałe kontenery pliku;
    w kontenerze powiązanym `owner_container_no` i tylko „Odepnij” (usuwa/podmienia właściciel)."""
    numbers = containers_of(db, [a.id for a in attachments])
    result = []
    for attachment in attachments:
        out = _out(db, attachment, container, user)
        names = numbers.get(attachment.id, [])
        out.shared_with = [no for no in names if no != container.container_no]
        if attachment.container_id != container.id:
            link = next(li for li in attachment.links if li.container_id == container.id)
            out.owner_container_no = names[0] if names else None
            out.can_delete = out.can_replace = False
            out.can_unlink = user.role not in rules.PARTNER_ROLES or link.created_by_id == user.id
        result.append(out)
    return result


def _as_sad_draft(db: Session, container: Container, document_type: DocumentType | None,
                  filename: str, content: bytes, user: User) -> AttachmentOut | None:
    """§4 pkt 22: „Draft SAD” z kafelka/zwykłego wgrania = nowa wersja w obiegu draftu paczki
    (porównanie, decyzja, historia), a nie luźny plik obok niego. Bez paczki faktur — None."""
    if document_type is None or document_type.tile_code != "SAD_DRAFT":
        return None
    batch = sad_flow.newest_batch(db, container.id)
    if batch is None:
        return None
    if container.document_status == DocumentStatus.BRAK:   # obieg BRAK→ZALACZONE jak przy pliku
        record_changes(db, container, {"document_status": DocumentStatus.ZALACZONE},
                       user, note="pierwszy otypowany dokument")
    draft, _ = sad_flow.add_draft(db, batch, filename, content, user, "manual")
    return _out(db, db.get_one(Attachment, draft.attachment_id), container, user)


def _out(db: Session, attachment: Attachment, container: Container, user: User) -> AttachmentOut:
    out = AttachmentOut.model_validate(attachment)
    out.uploaded_by_login = attachment.uploaded_by.login if attachment.uploaded_by else None
    out.document_type_name = attachment.document_type.name if attachment.document_type else None
    for key, value in rules.flags(db, attachment, container, user).items():
        setattr(out, key, value)
    return out


def allowed_extensions() -> set[str]:
    return {e.strip().lower() for e in settings.allowed_upload_extensions.split(",") if e.strip()}


@router.post("/containers/{container_id}/attachments", response_model=AttachmentOut,
             status_code=201)
def upload_attachment(container_id: int, file: UploadFile,
                            document_type_id: int | None = Form(default=None),
                            replaces_id: int | None = Form(default=None),
                            replace_reason: str = Form(default="", max_length=500),
                            db: Session = Depends(get_db), user: User = non_warehouse):
    container = get_container_checked(db, container_id, user)
    # „Podmień” (spec 2026-10-06 §4 pkt 3): stary plik znika w TEJ SAMEJ transakcji co nowy —
    # nieudane usunięcie nie zostawia dwóch plików; po wysłaniu do agencji wymagany powód
    old = None
    if replaces_id is not None:
        old = get_scoped(db, Attachment, replaces_id, user)
        if old.container_id != container_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono pliku do podmiany.")
        block = rules.removal_block(db, old, user)
        if block:
            raise HTTPException(*block)
        if rules.is_sent(container) and not replace_reason.strip():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, rules.REASON_REQUIRED)
    document_type = None
    if document_type_id is not None:
        document_type = db.get(DocumentType, document_type_id)
        if not document_type or not document_type.is_active:
            raise HTTPException(status.HTTP_404_NOT_FOUND,
                                "Nie znaleziono aktywnego typu dokumentu.")
    extension = pathlib.Path(file.filename or "").suffix.lstrip(".").lower()
    if extension == "zip":   # rozpakowuje POST …/archive (front kieruje tam ZIP-y)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Archiwum ZIP jest rozpakowywane — wgraj je przez „Dokumenty”.")
    if extension not in allowed_extensions():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Niedozwolony typ pliku „.{extension or '?'}”. "
            f"Dozwolone: {', '.join(sorted(allowed_extensions()))}.")
    content = read_upload_capped(file, settings.max_upload_mb)
    if document_type is None and old is not None:
        document_type = old.document_type   # podmiana zachowuje typ (kafelek, checklista)
    gate = check_pdf(content, container.container_no) if extension == "pdf" else None
    if gate and gate["status"] == UNREADABLE:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, gate["message"])
    if gate and gate["status"] == CONFLICT:   # jak bramka faktur: inny kontener = odrzucenie
        raise HTTPException(status.HTTP_409_CONFLICT, gate["message"])
    duplicate = duplicate_reason(db, container_id, content, uploads_dir())
    if duplicate is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Ten plik {duplicate}.")
    safe = safe_filename(file.filename)
    draft_out = _as_sad_draft(db, container, document_type, safe, content, user)         if old is None and extension == "pdf" else None
    if draft_out is not None:
        return draft_out
    stored_name = f"{container_id}_{secrets.token_hex(8)}_{safe}"
    attachment = Attachment(
        container_id=container_id, filename=safe,
        stored_name=stored_name, content_type=file.content_type or "",
        size=len(content), sha256=digest(content), uploaded_by_id=user.id,
        document_type=document_type)   # relacja od razu (forwarder_may_see przed flushem)
    db.add(attachment)
    old_path = _remove(db, old, user, replace_reason.strip(), replaced_by=attachment) \
        if old is not None else None
    # pierwszy otypowany dokument przesuwa obieg BRAK→ZALACZONE (nie cofa WYSLANE)
    if document_type and container.document_status == DocumentStatus.BRAK:
        record_changes(db, container, {"document_status": DocumentStatus.ZALACZONE},
                       user, note="pierwszy otypowany dokument")
    # SAD-PZ → ODPRAWIONY, SAD-PW → ZWOLNIONY (kafelki dokumentów, spec 2026-10-01) — do przodu;
    # tylko role, które same mogą zmienić status odprawy (spedytor/zakupy wgrywają plik bez automatu)
    customs_target = sad_customs_target(container, document_type)
    customs_skipped = customs_target is not None and user.role not in CUSTOMS_EDITORS
    if customs_target is not None and document_type is not None and user.role in CUSTOMS_EDITORS:
        code = (document_type.tile_code or "").replace("_", "-")
        record_changes(db, container, {"customs_status": customs_target}, user,
                       note=f"automatycznie z wgranego {code}")
        sync_status_from_customs(db, container, user)
    # spec 2026-10-06 §4 pkt 10: wgranie też w historii kontenera (dotąd tylko usunięcie)
    audit.record(db, entity_type="containers", entity_id=container_id, field="attachment_upload",
                 old_value=None, new_value=attachment.filename, user=user,
                 note=document_type.name if document_type else "")
    # nazwa pliku w tytule — spedytor dostaje tylko pliki, które sam może zobaczyć (CMR/własne)
    notify(db, [u for u in container_watchers(db, container) if forwarder_may_see(attachment, u)],
           kind="file",
           title=f"Nowy plik przy {container.container_no}: {attachment.filename}",
           container_id=container_id, exclude_user_id=user.id)
    # plik dopiero przy commicie; rollback/błąd po drodze = brak osieroconego pliku
    commit_with_file(db, uploads_dir() / stored_name, content)
    if old_path is not None:
        old_path.unlink(missing_ok=True)   # po commicie: rollback nie zostawi wiersza bez pliku
    out = AttachmentOut.model_validate(attachment)
    out.uploaded_by_login = user.login
    out.document_type_name = document_type.name if document_type else None
    if gate and gate["status"] == UNCERTAIN:
        out.gate_warning = gate["message"]
    elif customs_skipped:   # §4 pkt 50: SAD-PZ/PW od roli bez prawa do statusu odprawy — powiedz to
        out.gate_warning = "Plik zapisany; status odprawy zmieni logistyka albo agencja celna."
    for key, value in rules.flags(db, attachment, container, user).items():
        setattr(out, key, value)
    return out


@router.get("/attachments/{attachment_id}/download")
def download_attachment(attachment_id: int, db: Session = Depends(get_db),
                        user: User = viewer):
    # izolacja w deps: kontener-rodzic (404 także gdy usunięty) + reguła spedytora (CMR/własne)
    attachment = get_scoped(db, Attachment, attachment_id, user)
    path = uploads_dir() / attachment.stored_name
    if not path.is_file():
        raise HTTPException(status.HTTP_410_GONE, "Plik został usunięty z dysku.")
    # nie ufamy Content-Type podanemu przy uploadzie — wymuszamy pobranie jako załącznik
    return FileResponse(path, filename=attachment.filename,
                        media_type="application/octet-stream")


@router.delete("/attachments/{attachment_id}", status_code=204)
def delete_attachment(attachment_id: int, db: Session = Depends(get_db),
                      user: User = non_warehouse) -> Response:
    """Pomyłka przy wgraniu: partnerzy tylko własne pliki; po wysłaniu do agencji / po odprawie
    nie usuwamy (tylko „Podmień” z powodem) — attachment_rules. Wpis w historii kontenera."""
    attachment = get_scoped(db, Attachment, attachment_id, user)
    block = rules.removal_block(db, attachment, user)
    if block:
        raise HTTPException(*block)
    container = get_container_checked(db, attachment.container_id, user)
    if rules.is_sent(container):
        raise HTTPException(status.HTTP_409_CONFLICT, rules.SENT_DELETE)
    path = _remove(db, attachment, user)
    db.flush()
    if container.document_status == DocumentStatus.ZALACZONE and not db.scalar(
            select(Attachment.id).where(Attachment.container_id == container.id,
                                        Attachment.document_type_id.is_not(None)).limit(1)):
        record_changes(db, container, {"document_status": DocumentStatus.BRAK}, user,
                       note="usunięto ostatni otypowany dokument")
    db.commit()
    path.unlink(missing_ok=True)   # po commicie: rollback nie zostawi wiersza bez pliku
    return Response(status_code=204)


def _remove(db: Session, attachment: Attachment, user: User, reason: str = "",
            replaced_by: Attachment | None = None) -> pathlib.Path:
    """Usunięcie wiersza (bez commitu) z wpisem w historii; zwraca ścieżkę pliku do skasowania
    PO commicie. Propozycje OCR wracają do „proposed” (§4 pkt 13 — można je przyjąć ponownie)."""
    for suggestion in db.scalars(select(AttachmentSuggestion)
                                 .where(AttachmentSuggestion.attachment_id == attachment.id)):
        suggestion.attachment_id = None
        suggestion.status = SuggestionStatus.proposed
        suggestion.decided_by_id = suggestion.decided_at = None
    audit.record(db, entity_type="containers", entity_id=attachment.container_id,
                 field="attachment_replace" if replaced_by else "attachment_delete",
                 old_value=attachment.filename, new_value=replaced_by.filename if replaced_by else None,
                 user=user, note=reason)
    if replaced_by is not None:   # wspólny plik: podmiana działa wszędzie — powiązania za nowym wierszem
        for link in list(attachment.links):
            link.attachment = replaced_by
    path = uploads_dir() / attachment.stored_name
    db.delete(attachment)
    return path



class LinkIn(BaseModel):
    container_id: int


def _linked_in(db: Session, container_id: int, attachment_id: int,
               user: User) -> tuple[Container, Attachment]:
    """Plik widoczny w kontenerze (własny albo wspólny) — inaczej 404."""
    container = get_container_checked(db, container_id, user)
    attachment = get_scoped(db, Attachment, attachment_id, user)
    if attachment.container_id != container_id and not any(
            link.container_id == container_id for link in attachment.links):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono pliku w kontenerze.")
    return container, attachment


@router.post("/containers/{container_id}/attachments/{attachment_id}/link",
             response_model=AttachmentOut, status_code=201)
def link_attachment(container_id: int, attachment_id: int, body: LinkIn,
                    db: Session = Depends(get_db), user: User = non_warehouse):
    """Dokument zbiorczy (decyzja 24): ten sam plik także w innym kontenerze tej samej spółki."""
    _, attachment = _linked_in(db, container_id, attachment_id, user)
    target = get_container_checked(db, body.container_id, user)
    owner = db.get_one(Container, attachment.container_id)
    if target.company_id != owner.company_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Wspólny plik tylko dla kontenerów tej samej spółki.")
    present = target.id == owner.id or any(li.container_id == target.id for li in attachment.links)         or (attachment.sha256 is not None and db.scalar(select(Attachment.id).where(
            in_container(target.id), Attachment.sha256 == attachment.sha256).limit(1)))
    if present:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Ten plik już jest w {target.container_no}.")
    add_link(db, attachment, target, user)
    db.commit()
    return _outs(db, [attachment], target, user)[0]


@router.delete("/containers/{container_id}/attachments/{attachment_id}/link", status_code=204)
def unlink_attachment(container_id: int, attachment_id: int, db: Session = Depends(get_db),
                      user: User = non_warehouse) -> Response:
    """Odepnij wspólny plik od kontenera powiązanego (plik zostaje u właściciela)."""
    container, attachment = _linked_in(db, container_id, attachment_id, user)
    link = next((li for li in attachment.links if li.container_id == container_id), None)
    if link is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "To plik tego kontenera — użyj „Usuń”.")
    if user.role in rules.PARTNER_ROLES and link.created_by_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Możesz odpiąć tylko powiązania dodane przez siebie.")
    for cid in (container_id, attachment.container_id):
        audit.record(db, entity_type="containers", entity_id=cid, field="attachment_unlink",
                     old_value=attachment.filename, new_value=None, user=user,
                     note=f"odpięty od {container.container_no}")
    db.delete(link)
    db.commit()
    return Response(status_code=204)
