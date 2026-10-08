"""Poczekalnia dokumentów — logika (moduł w routers/, bo składa istniejące ścieżki uploadu:
_ingest paczki faktur, unpack ZIP-a, helpery plików; ARCH-001 zabrania domenie importu routerów).
Spec 2026-10-06-dokumenty-dostaw §2 (decyzje 1, 2, 3, 4, 11, 12): jedno
„Dodaj dokumenty” → rozpakowanie ZIP → cięcie PDF splitterem faktur → typ części → bramki (dubel,
inny kontener, czytelność). Do dostawy NIC nie trafia przed `confirm` — wtedy CI/PI/PL idą do
paczki faktur (ta sama ścieżka co POST …/invoice-batches), reszta do załączników z typem."""
import mimetypes
import pathlib
import secrets

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import audit
from ..attachment_links import add_link, in_container
from ..audit import record_changes
from ..deps import forwarder_may_see, scope_containers
from ..document_gate import CONFLICT, OK, UNCERTAIN, UNREADABLE, check_pdf_text, digest, duplicate_reason
from ..document_tiles import sad_customs_target
from ..invoices import ingest, splitter
from ..invoices.extractor import extract_invoice_number
from ..invoices.orders_link import order_numbers
from ..models import (Attachment, Container, DocumentStatus, DocumentType, IntakeBatch, IntakeItem,
                      InvoiceBatch, InvoiceDocKind, InvoiceJob, SapOrder, User)
from ..order_numbers import container_order_numbers
from ..notifications import container_watchers, notify
from .archive_upload import _INVOICE_ROLES
from .containers import get_container_checked
from .containers_common import CUSTOMS_EDITORS, sync_status_from_customs
from .forwarding_files import uploads_dir
from .intake_unpack import MAIL_EXTS, expand
from .invoices import _ingest, _resolve_supplier, _stored, _validate_pdf

DUPLICATE = "duplicate"
INVOICE_TYPES = ("CI", "PI", "PL")
_KIND_TYPE = {InvoiceDocKind.invoice: "CI", InvoiceDocKind.proforma: "PI",
              InvoiceDocKind.packing_list: "PL"}
_SAME_UPLOAD = "powtórzony w tym wgraniu"


def receive(db: Session, container: Container, files: list[tuple[str, bytes]],
            user: User) -> tuple[IntakeBatch, list[str]]:
    """Wgranie do poczekalni → (paczka, pominięte z powodem). Pliki części leżą w uploads jako
    `intake_{batch}_{hex}_{nazwa}`; błąd po drodze sprząta je (bez sierot)."""
    entries, skipped = expand(files)
    if not entries:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Brak plików do wgrania." + (
            f" Pominięte: {'; '.join(skipped)}" if skipped else ""))
    batch = IntakeBatch(container_id=container.id, created_by_id=user.id)
    db.add(batch)
    db.flush()
    uploads = uploads_dir()
    written: list[pathlib.Path] = []
    seen: set[str] = set()
    try:
        for name, data in entries:
            for item, part in _parts(batch.id, name, data, uploads, written):
                _gate(db, item, part, container, user, seen, uploads)
                batch.items.append(item)
        audit.record(db, entity_type="containers", entity_id=container.id, field="intake_upload",
                     old_value=None, new_value=f"poczekalnia: {len(batch.items)} części", user=user,
                     note=", ".join(i.original_name for i in batch.items)[:500])
        db.commit()
    except BaseException:
        db.rollback()
        for path in written:
            path.unlink(missing_ok=True)
        raise
    db.refresh(batch)
    return batch, skipped


def _stored_name(batch_id: int, name: str) -> str:
    return f"intake_{batch_id}_{secrets.token_hex(8)}_{name}"


def _parts(batch_id: int, name: str, data: bytes, uploads: pathlib.Path,
           written: list[pathlib.Path]) -> list[tuple[IntakeItem, bytes]]:
    """Plik → części (pozycja poczekalni + bajty). PDF tnie splitter faktur (puste strony
    dołącza do poprzedniego dokumentu — decyzja 18); inne formaty = jedna część OTHER."""
    source = uploads / _stored_name(batch_id, name)
    source.write_bytes(data)
    written.append(source)
    is_mail = pathlib.PurePath(name).suffix.lower().lstrip(".") in MAIL_EXTS   # korespondencja (decyzja 8)
    whole = IntakeItem(stored_name=source.name, original_name=name, sha256=digest(data),
                       doc_type="MAIL" if is_mail else "OTHER")
    if not name.lower().endswith(".pdf"):
        return [(whole, data)]
    try:
        pages = _validate_pdf(name, data)
    except HTTPException as exc:   # uszkodzony / za długi PDF: część do odrzucenia, nie 422 wgrania
        whole.gate_status, whole.gate_message = UNREADABLE, str(exc.detail)
        return [(whole, data)]
    texts = ingest.page_texts(source)
    parts = ingest.split_or_whole(source, pages, "", texts)
    out = []
    for part in parts:
        path = pathlib.Path(part["out_path"])
        label = ingest.part_name(name, part) if len(parts) > 1 else name
        if path != source:
            written.append(path)
            final = uploads / _stored_name(batch_id, label)
            path.rename(final)
            written.append(final)
        else:
            final = source
        part_bytes = final.read_bytes()
        out.append((IntakeItem(stored_name=final.name, original_name=label, sha256=digest(part_bytes),
                               page_from=part["page_from"], page_to=part["page_to"], pages=pages,
                               doc_type=_doc_type(part)), part_bytes))
    if all(item.stored_name != source.name for item, _ in out):
        source.unlink(missing_ok=True)   # zestaw pocięty — w poczekalni zostają tylko części
    return out


def _doc_type(part: dict) -> str:
    if part["kind"] in _KIND_TYPE:
        return _KIND_TYPE[part["kind"]]
    # ponytail: SAD (draft/PZ/PW) i CMR bez detektora — OTHER, typ zmienia użytkownik (PATCH)
    return "BL" if splitter.is_bill_of_lading(part.get("text") or "") else "OTHER"


def _gate(db: Session, item: IntakeItem, data: bytes, container: Container, user: User,
          seen: set[str], uploads: pathlib.Path) -> None:
    """Zgodność kontenera (bez OCR) → wybór kontenera docelowego (decyzje 13, 14) → dubel
    liczony względem KOŃCOWEGO celu (w tym wgraniu i w obu kanałach kontenera)."""
    item.target_container_id = container.id
    if item.sha256 in seen:
        item.gate_status, item.gate_message = DUPLICATE, _SAME_UPLOAD
        return
    seen.add(item.sha256)
    if item.gate_status != UNREADABLE and item.original_name.lower().endswith(".pdf"):
        gate, text = check_pdf_text(data, container.container_no)
        item.gate_status, item.gate_message = gate["status"], gate["message"]
        _route(db, item, gate, text, container, user)
    dup = duplicate_reason(db, item.target_container_id, data, uploads)
    if dup is not None:
        item.gate_status, item.gate_message = DUPLICATE, dup


def _route(db: Session, item: IntakeItem, gate: dict, text: str, container: Container,
           user: User) -> None:
    """Decyzja 13: numer NASZEGO innego kontenera (ta sama spółka, w zakresie) = rozdziel, nie
    konflikt; zbiorczy B/L z naszym numerem zostaje tu. Decyzja 14: bez numeru — PO / faktura."""
    found = gate["found"]
    own = (container.container_no or "").upper()
    if gate["status"] == OK:
        others = [no for no in found if no != own]
        if others:   # zbiorczy B/L: przy „Potwierdź” plik będzie wspólny z tymi kontenerami
            item.gate_message = f"Dotyczy też: {', '.join(others)}"
            item.found_containers = _resolve(db, others, user)
    elif gate["status"] == UNCERTAIN:
        hit = _match_refs(db, text, container.company_id, user)
        if hit is not None:
            item.target_container_id, item.gate_message = hit
    elif gate["status"] == CONFLICT:
        ours = _company_containers(db, found, container.company_id, user)
        if not ours:   # obca spółka / poza zakresem — konflikt jak dotąd („Przenieś do …”)
            item.found_containers = _resolve(db, found, user)
            return
        no, item.target_container_id = next(iter(ours.items()))
        others = [n for n in found if n != no]
        item.gate_status = OK
        item.found_containers = _resolve(db, others, user)
        item.gate_message = f"Rozdzielone: dokument dotyczy {no}" + (
            f". Dotyczy też: {', '.join(others)}" if others else "")


def _company_containers(db: Session, numbers: list[str], company_id: int, user: User) -> dict[str, int]:
    """Numer → id kontenera tej samej spółki w zakresie użytkownika, w kolejności z dokumentu."""
    rows = db.execute(scope_containers(
        select(Container.container_no, Container.id).where(
            Container.container_no.in_(numbers), Container.company_id == company_id)
        .order_by(Container.id), user)).all()
    ids = dict(rows)   # ten sam numer zrealizowany i ponowny przyjazd — wygrywa nowszy rekord
    return {no: ids[no] for no in numbers if no in ids}


def _match_refs(db: Session, text: str, company_id: int | None, user: User) -> tuple[int, str] | None:
    """Decyzja 14: zamówienie (EKKO albo pole numerów zamówień kontenera), potem numer faktury
    z istniejących paczek → (id, komunikat), gdy trafia DOKŁADNIE jeden widoczny kontener spółki
    (company_id None = poczta bez kontekstu: dowolna spółka w zakresie użytkownika)."""
    numbers = order_numbers(text)
    if numbers:
        rows = db.execute(select(SapOrder.container_id, SapOrder.order_number).where(
            SapOrder.order_number.in_(numbers), SapOrder.container_id.is_not(None))).all()
        hits: dict[int, str] = {cid: no for cid, no in rows if cid is not None}
        candidates = select(Container).where(*_company(company_id),
                                             or_(*(Container.order_numbers.contains(n) for n in numbers)))
        for c in db.scalars(scope_containers(candidates, user)):
            token = next((n for n in numbers if n in container_order_numbers(c)), None)
            if token is not None:   # contains() to tylko wstępny filtr — pełny token z helpera
                hits.setdefault(c.id, token)
        hit = _only_visible(db, hits, company_id, user)
        if hit is not None:
            return hit[0], f"Dopasowano po PO {hit[1]}"
    invoice_no = extract_invoice_number(text)
    if invoice_no:
        ids = db.scalars(select(InvoiceBatch.container_id).join(InvoiceJob, InvoiceJob.batch_id == InvoiceBatch.id)
                         .where(InvoiceJob.invoice_number == invoice_no).distinct())
        hit = _only_visible(db, dict.fromkeys(ids, invoice_no), company_id, user)
        if hit is not None:
            return hit[0], f"Dopasowano po fakturze {invoice_no}"
    return None


def _company(company_id: int | None) -> list:
    return [] if company_id is None else [Container.company_id == company_id]


def _only_visible(db: Session, hits: dict[int, str], company_id: int | None,
                  user: User) -> tuple[int, str] | None:
    if not hits:
        return None
    ids = db.scalars(scope_containers(select(Container.id).where(
        Container.id.in_(hits), *_company(company_id)), user)).all()
    return (ids[0], hits[ids[0]]) if len(ids) == 1 else None


def _resolve(db: Session, numbers: list[str], user: User) -> list[dict]:
    """Numery z dokumentu → id kontenerów w zakresie użytkownika (pod „Przenieś do X”)."""
    rows = db.execute(scope_containers(
        select(Container.id, Container.container_no).where(Container.container_no.in_(numbers)), user)).all()
    # ponytail: ten sam numer w dwóch spółkach — wygrywa ostatni wiersz; wybór spółki w UI później
    ids = {no: cid for cid, no in rows}
    return [{"container_no": no, "container_id": ids.get(no)} for no in numbers]


def skip_reason(item: IntakeItem) -> str | None:
    if item.decision == "rejected":
        return "odrzucony"
    if item.gate_status in (DUPLICATE, UNREADABLE):
        return item.gate_message or item.gate_status
    if item.gate_status == CONFLICT:
        allowed = {f.get("container_id") for f in item.found_containers or []} - {None}
        if item.target_container_id not in allowed:   # kontekst nigdy nie jest wśród znalezionych
            return "dotyczy innego kontenera — wybierz „Przenieś do …”"
    return None


def confirm(db: Session, batch: IntakeBatch, user: User) -> dict:
    """„Potwierdź”: zaakceptowane części → kontenery docelowe. Faktury najpierw (_ingest sam
    commituje), potem załączniki + status paczki w jednym commicie; pliki poczekalni znikają
    po sukcesie. Ponowne „Potwierdź” po awarii nie dubluje — bramka dubli wyłapie zapisane."""
    _check_pending(batch)
    # decyzja 12: niepotwierdzone czekają — nierozstrzygnięty konflikt / nieczytelny PDF nie może
    # zniknąć przy „Potwierdź”; użytkownik odrzuca albo przenosi część świadomie
    unresolved = [i.original_name for i in batch.items if i.decision != "rejected"
                  and i.gate_status in ("conflict", "unreadable") and skip_reason(i)]
    if unresolved:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Rozstrzygnij części: " + ", ".join(unresolved)
                            + " — przenieś do właściwego kontenera albo odrzuć.")
    homeless = [i.original_name for i in batch.items if i.target_container_id is None and not skip_reason(i)]
    if batch.container_id is None and homeless:   # poczta bez dopasowania (decyzja 27)
        raise HTTPException(status.HTTP_409_CONFLICT, "Wskaż kontener dla: " + ", ".join(homeless)
                            + " — albo odrzuć te części.")
    uploads = uploads_dir()
    skipped: list[str] = []
    groups: dict[int, list[IntakeItem]] = {}
    for item in batch.items:
        reason = skip_reason(item)
        if reason:
            skipped.append(f"{item.original_name} ({reason})")
        else:
            # bez celu tylko poczta bez dopasowania — odrzucona wyżej (homeless) → 0 nie występuje
            groups.setdefault(item.target_container_id or batch.container_id or 0, []).append(item)
    plan = []
    for cid, items in groups.items():
        container = get_container_checked(db, cid, user)
        invoices: list[tuple[IntakeItem, bytes]] = []
        others: list[tuple[IntakeItem, bytes]] = []
        seen = set()
        for item in items:
            data = (uploads / item.stored_name).read_bytes()
            dup = _SAME_UPLOAD if item.sha256 in seen else duplicate_reason(db, cid, data, uploads)
            seen.add(item.sha256)
            if dup is not None:
                skipped.append(f"{item.original_name} ({dup})")
                continue
            to_invoice = item.doc_type in INVOICE_TYPES and user.role in _INVOICE_ROLES
            (invoices if to_invoice else others).append((item, data))
        plan.append((container, invoices, others))
    summary: dict = {}
    for container, invoices, _ in plan:
        if invoices:
            # ponytail: część trafia do paczki jako osobny plik i splitter klasyfikuje ją
            # ponownie — ręczna zmiana CI↔PL w poczekalni nie wymusza typu dokumentu w paczce
            saved = [(i.original_name, _stored(container.id, i.original_name), d) for i, d in invoices]
            _ingest(db, container, _resolve_supplier(db, container, None), saved, uploads, user)
    written: list[pathlib.Path] = []
    try:
        for container, invoices, others in plan:
            added = _attach(db, container, others, user, written)
            for (item, _), att in zip(others, added, strict=True):
                _share(db, item, att, container, user)
            for item, _ in invoices + others:
                item.decision = "accepted"
            summary[container.container_no] = {"invoices": len(invoices), "attachments": len(others)}
        batch.status = "confirmed"
        db.commit()
    except IntegrityError as exc:   # uq_attachments_container_sha: równoległe wgranie tego samego
        _undo(db, written)
        raise HTTPException(status.HTTP_409_CONFLICT, "Któryś plik właśnie trafił do kontenera — "
                                                      "potwierdź ponownie.") from exc
    except BaseException:
        _undo(db, written)
        raise
    _remove_files(batch, uploads)
    return {"containers": summary, "skipped": skipped}


def _attach(db: Session, container: Container, pairs: list[tuple[IntakeItem, bytes]], user: User,
            written: list[pathlib.Path]) -> list[Attachment]:
    """Załączniki z typem + efekty jak zwykły upload (forwarding_files.upload_attachment):
    BRAK→ZALACZONE, automat SAD-PZ/PW, audyt, JEDNO zbiorcze powiadomienie (decyzja 10)."""
    if not pairs:
        return []
    types = _document_types(db)
    added = []
    for item, data in pairs:
        stored = f"{container.id}_{secrets.token_hex(8)}_{item.original_name}"
        path = uploads_dir() / stored
        path.write_bytes(data)   # przed commitem; błąd commitu sprząta (confirm → _undo)
        written.append(path)
        att = Attachment(container_id=container.id, filename=item.original_name, stored_name=stored,
                         content_type=mimetypes.guess_type(item.original_name)[0] or "",
                         size=len(data), sha256=item.sha256, uploaded_by_id=user.id,
                         document_type=types.get(item.doc_type))
        db.add(att)
        added.append(att)
    typed = [a.document_type for a in added if a.document_type is not None]
    if typed and container.document_status == DocumentStatus.BRAK:
        record_changes(db, container, {"document_status": DocumentStatus.ZALACZONE},
                       user, note="pierwszy otypowany dokument")
    if user.role in CUSTOMS_EDITORS:
        for document_type in typed:
            target = sad_customs_target(container, document_type)
            if target is not None:
                code = (document_type.tile_code or "").replace("_", "-")
                record_changes(db, container, {"customs_status": target}, user,
                               note=f"automatycznie z wgranego {code}")
                sync_status_from_customs(db, container, user)
    names = ", ".join(a.filename for a in added)
    audit.record(db, entity_type="containers", entity_id=container.id, field="attachment_upload",
                 old_value=None, new_value=f"poczekalnia ({len(added)} plików)", user=user,
                 note=names[:500])
    notify(db, [u for u in container_watchers(db, container) if any(forwarder_may_see(a, u) for a in added)],
           kind="file", title=f"Nowe pliki przy {container.container_no} ({len(added)})",
           container_id=container.id, exclude_user_id=user.id)
    return added


def _share(db: Session, item: IntakeItem, att: Attachment, container: Container, user: User) -> None:
    """Decyzja 24: „Dotyczy też: …” → plik wspólny z innymi kontenerami tej samej spółki w zakresie
    wgrywającego; kontener, który już ma ten plik, pomijamy (bramka dubli)."""
    ids = {f.get("container_id") for f in item.found_containers or []} - {None, container.id}
    targets = db.scalars(scope_containers(select(Container).where(
        Container.id.in_(ids), Container.company_id == container.company_id), user)).all() if ids else []
    for target in targets:
        if not db.scalar(select(Attachment.id).where(in_container(target.id),
                                                     Attachment.sha256 == att.sha256).limit(1)):
            add_link(db, att, target, user)


def _document_types(db: Session) -> dict[str, DocumentType]:
    """Kod poczekalni → aktywny typ słownika: kafelki po tile_code, CMR i MAIL po nazwie (bez kafelka)."""
    active = list(db.scalars(select(DocumentType).where(DocumentType.is_active.is_(True))))
    types = {t.tile_code: t for t in active if t.tile_code}
    cmr = next((t for t in active if "CMR" in t.name.upper()), None)
    if cmr is not None:
        types["CMR"] = cmr
    mail = next((t for t in active if t.name.strip().lower() == "korespondencja"), None)
    if mail is not None:   # bez seeda — brak typu = załącznik bez typu
        types["MAIL"] = mail
    return types


def discard(db: Session, batch: IntakeBatch, user: User) -> None:
    _check_pending(batch)
    batch.status = "discarded"
    if batch.container_id is not None:   # poczta bez dopasowania nie ma karty do historii
        audit.record(db, entity_type="containers", entity_id=batch.container_id, field="intake_discard",
                     old_value=None, new_value=f"{len(batch.items)} części", user=user)
    db.commit()
    _remove_files(batch, uploads_dir())


def _check_pending(batch: IntakeBatch) -> None:
    if batch.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "To wgranie jest już zamknięte.")


def _undo(db: Session, written: list[pathlib.Path]) -> None:
    db.rollback()
    for path in written:
        path.unlink(missing_ok=True)


def _remove_files(batch: IntakeBatch, uploads: pathlib.Path) -> None:
    for item in batch.items:
        (uploads / item.stored_name).unlink(missing_ok=True)
