"""Poczta → poczekalnia (spec 2026-10-06-dokumenty-dostaw, decyzje 7, 10, 27; docs/POCZTA-DO-POCZEKALNI.md).

n8n przysyła cały mail (.eml/.msg) albo pojedynczy załącznik — bez kontekstu kontenera. Kontener
czytamy z treści każdej części (numer kontenera → PO → numer faktury; te same reguły co rozdział
w poczekalni, w zakresie konta automatu) i tworzymy JEDNO wgranie na kontener. Części bez
dopasowania → wgranie bez kontenera („poczta bez dopasowania”) dla logistyki spółki. Ten sam mail
(sha256 całego pliku) w ciągu 7 dni = te same wgrania, nic nowego."""
import datetime
import pathlib

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..deps import own_company_id, scope_containers
from ..document_gate import UNCERTAIN, UNREADABLE, check_pdf_text, digest
from ..invoices.suggestions import found_container_numbers
from ..models import Container, IntakeBatch, IntakeItem, User
from ..models.enums import utcnow
from ..notifications import company_watchers, notify
from .forwarding_files import uploads_dir
from .intake_flow import _SAME_UPLOAD, DUPLICATE, _gate, _match_refs, _parts
from .intake_unpack import expand

RESEND_WINDOW = datetime.timedelta(days=7)
UNMATCHED = "Poczta bez dopasowania — wskaż kontener albo odrzuć."

Pairs = list[tuple[IntakeItem, bytes]]


def receive_mail(db: Session, filename: str, data: bytes, subject: str, sender: str,
                 user: User) -> tuple[dict, bool]:
    """→ ({batches: [{batch_id, container_no, items}], skipped}, czy utworzono coś nowego)."""
    sha = digest(data)
    again = db.scalars(select(IntakeBatch).where(
        IntakeBatch.mail_sha256 == sha, IntakeBatch.created_at >= utcnow() - RESEND_WINDOW)
        .order_by(IntakeBatch.id)).all()
    if again:
        return _response(db, list(again), []), False
    entries, skipped = expand([(filename, data)])
    if not entries:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Brak plików do wgrania." + (
            f" Pominięte: {'; '.join(skipped)}" if skipped else ""))
    note = " · ".join(filter(None, (sender, subject))) or None
    uploads = uploads_dir()
    written: list[pathlib.Path] = []
    try:
        groups = _group(db, entries, subject, user, uploads, written)
        batches = [_batch(db, cid, pairs, note, sha, user, uploads) for cid, pairs in groups.items()]
        db.commit()
    except BaseException:
        db.rollback()
        for path in written:
            path.unlink(missing_ok=True)
        raise
    return _response(db, batches, skipped), True


def _group(db: Session, entries: list[tuple[str, bytes]], subject: str, user: User,
           uploads: pathlib.Path, written: list[pathlib.Path]) -> dict[int | None, Pairs]:
    """Części → kontener (None = bez dopasowania). PDF po treści; części bez tekstu (sam mail,
    Excel, uszkodzony PDF) po numerze w temacie, inaczej do pierwszego dopasowanego kontenera."""
    groups: dict[int | None, Pairs] = {}
    loose: Pairs = []
    for name, data in entries:
        # nazwa pliku części z id 0 — wgrań (id) jeszcze nie ma; unikalność daje losowy hex
        for item, part in _parts(0, name, data, uploads, written):
            if item.original_name.lower().endswith(".pdf") and item.gate_status != UNREADABLE:
                # ponytail: tekst PDF czytany drugi raz w _gate — bez OCR, tanie; cache gdy zaboli
                gate, text = check_pdf_text(part, "")
                groups.setdefault(_find(db, gate["found"], text, user), []).append((item, part))
            else:
                loose.append((item, part))
    if loose:
        target = _find(db, found_container_numbers(subject), subject, user) if subject else None
        if target is None:
            target = next((cid for cid in groups if cid is not None), None)
        groups.setdefault(target, []).extend(loose)
    return groups


def _find(db: Session, found: list[str], text: str, user: User) -> int | None:
    """Pierwszy numer kontenera z dokumentu widoczny dla konta (ten sam numer w kilku rekordach —
    najnowszy); bez numeru — PO / numer faktury (jedno trafienie w dowolnej spółce w zakresie)."""
    if found:
        rows = db.execute(scope_containers(select(Container.container_no, Container.id).where(
            Container.container_no.in_(found)).order_by(Container.id), user)).all()
        ids = dict(rows)
        return next((ids[no] for no in found if no in ids), None)
    hit = _match_refs(db, text, None, user)
    return hit[0] if hit else None


def _batch(db: Session, cid: int | None, pairs: Pairs, note: str | None, sha: str, user: User,
           uploads: pathlib.Path) -> IntakeBatch:
    container = db.get(Container, cid) if cid is not None else None
    batch = IntakeBatch(container_id=cid, source="mail", note=note, mail_sha256=sha, created_by_id=user.id,
                        company_id=container.company_id if container else own_company_id(user))
    db.add(batch)
    db.flush()
    seen: set[str] = set()
    for item, part in pairs:
        if container is not None:
            _gate(db, item, part, container, user, seen, uploads)
        elif item.sha256 in seen:
            item.gate_status, item.gate_message = DUPLICATE, _SAME_UPLOAD
        else:
            seen.add(item.sha256)
            if item.gate_status != UNREADABLE:
                item.gate_status, item.gate_message = UNCERTAIN, UNMATCHED
        batch.items.append(item)
    where = container.container_no if container else "— bez dopasowania"
    if container is not None:
        audit.record(db, entity_type="containers", entity_id=container.id, field="intake_upload",
                     old_value=None, new_value=f"poczta: {len(batch.items)} części", user=user,
                     note=(note or "")[:500])
    # decyzje 7 i 10: jedno zbiorcze powiadomienie logistyki spółki na wgranie
    notify(db, company_watchers(db, batch.company_id or 0), kind="file",
           title=f"Poczta: {len(batch.items)} dokumentów do sprawdzenia w poczekalni {where}",
           body=note or "", container_id=cid, exclude_user_id=user.id)
    return batch


def _response(db: Session, batches: list[IntakeBatch], skipped: list[str]) -> dict:
    numbers = dict(db.execute(select(Container.id, Container.container_no).where(
        Container.id.in_({b.container_id for b in batches if b.container_id}))).all())
    return {"batches": [{"batch_id": b.id, "container_no": numbers.get(b.container_id or 0),
                         "items": len(b.items)} for b in batches], "skipped": skipped}
