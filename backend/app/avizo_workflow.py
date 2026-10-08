"""Awizacja dwuetapowa — JEDYNE miejsce przejść stanów i wydawania tokenów.

Etap 1: spedycja potwierdza dostawy (termin/slot/uwagi) → my zatwierdzamy lub odrzucamy.
Etap 2: po zatwierdzeniu automatycznie drugi link — dane kierowców per kontener.
Tokeny są jednorazowe, per etap; w bazie wyłącznie hash SHA-256.
"""
import datetime
import hashlib
import hmac
import re
import secrets
from typing import cast

from fastapi import HTTPException, status
from sqlalchemy import or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from . import mailer
from .audit import record, record_changes
from .config import settings
from .database import SessionLocal
from .date_pl import date_pl
from .html_templates import env as _env
from .models import (
    AvizoFormToken,
    AvizoItem,
    AvizoMailLog,
    AvizoRequest,
    Container,
    ContainerStatus,
    DeliveryConfirmation,
    Forwarder,
    Notification,
    SmsMessage,
    User,
    utcnow,
)
from .models import AvizoStatus as S

TRANSITIONS: dict[S, set[S]] = {
    S.DRAFT: {S.SENT_STAGE1, S.CANCELLED},
    S.SENT_STAGE1: {S.CONFIRMED_BY_FORWARDER, S.EXPIRED, S.CANCELLED},
    # CLOSED: kontenery dostarczone bez naszego zatwierdzenia — inaczej zlecenie wisi
    # wiecznie i blokuje anonimizację danych kierowców (RODO, run_maintenance)
    S.CONFIRMED_BY_FORWARDER: {S.APPROVED_BY_US, S.REJECTED, S.CLOSED, S.CANCELLED},
    S.REJECTED: {S.SENT_STAGE1, S.CANCELLED},
    S.APPROVED_BY_US: {S.SENT_STAGE2, S.CLOSED, S.CANCELLED},
    S.SENT_STAGE2: {S.DRIVERS_SUBMITTED, S.EXPIRED, S.CLOSED, S.CANCELLED},
    S.DRIVERS_SUBMITTED: {S.CLOSED},
    # po wygaśnięciu: ponowna wysyłka tego samego etapu (resend pilnuje, którego)
    S.EXPIRED: {S.SENT_STAGE1, S.SENT_STAGE2, S.CLOSED, S.CANCELLED},
    S.CLOSED: set(),
    S.CANCELLED: set(),
}


def transition(db: Session, req: AvizoRequest, new: S, user: User | None = None,
               note: str = "") -> None:
    old = req.status or S.DRAFT
    if new not in TRANSITIONS[old]:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Niedozwolona zmiana statusu awizacji: {old.value} → {new.value}.")
    # warunkowy UPDATE … WHERE status=:old — dwa równoległe żądania (podwójny klik, dwóch
    # użytkowników) czytały ten sam stary status; wygrywa pierwsze, drugie dostaje 409
    # zamiast drugiego tokenu i drugiego maila (SQLite i Postgres)
    db.flush()
    current = (AvizoRequest.status.is_(None) if req.status is None
               else AvizoRequest.status == req.status)
    won = cast(CursorResult, db.execute(
        update(AvizoRequest).where(AvizoRequest.id == req.id, current)
        .values(status=new).execution_options(synchronize_session=False))).rowcount
    if not won:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Awizacja została właśnie zmieniona przez kogoś innego — "
                            "odśwież widok.")
    req.status = new
    if new in (S.CLOSED, S.CANCELLED):
        req.closed_at = utcnow()
    record(db, entity_type="avizo_requests", entity_id=req.id, field="status",
           old_value=old.value, new_value=new.value, user=user, note=note)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def revoke_tokens(db: Session, req: AvizoRequest, stage: int | None = None) -> int:
    """Unieważnia aktywne (nieużyte, nieunieważnione) tokeny zlecenia [danego etapu]."""
    query = (update(AvizoFormToken)
             .where(AvizoFormToken.request_id == req.id, AvizoFormToken.used_at.is_(None),
                    AvizoFormToken.revoked_at.is_(None))
             .values(revoked_at=utcnow()))
    if stage is not None:
        query = query.where(AvizoFormToken.stage == stage)
    return db.execute(query).rowcount


def issue_token(db: Session, req: AvizoRequest, stage: int) -> str:
    """Nowy token etapu (poprzednie tego etapu unieważnione). Zwraca SUROWY token —
    trafia tylko do linku e-mail, w bazie zostaje hash."""
    revoke_tokens(db, req, stage)
    raw = secrets.token_urlsafe(32)
    days = settings.avizo_stage1_days if stage == 1 else settings.avizo_stage2_days
    expires = utcnow() + datetime.timedelta(days=days)
    db.add(AvizoFormToken(request_id=req.id, stage=stage, token_hash=hash_token(raw),
                          expires_at=expires))
    if stage == 1:
        req.expires_at = expires
    db.flush()
    return raw


def _adopt_legacy(db: Session, token_hash: str) -> AvizoFormToken | None:
    """Link sprzed tokenów per etap (hash w AvizoRequest.token, bez AvizoFormToken)."""
    req = db.scalar(select(AvizoRequest).where(AvizoRequest.token == token_hash))
    if req is None or db.scalar(select(AvizoFormToken.id)
                                .where(AvizoFormToken.request_id == req.id)):
        return None
    tok = AvizoFormToken(request_id=req.id, stage=1, token_hash=token_hash,
                         expires_at=req.expires_at or req.created_at
                         + datetime.timedelta(days=14),
                         used_at=req.confirmed_at)
    db.add(tok)
    db.flush()
    return tok


GONE_STATUSES = (S.EXPIRED, S.CANCELLED, S.CLOSED)


def lookup_token(db: Session, raw: str, stage: int, allow_used: bool = False) -> AvizoFormToken:
    """404 nieznany / innego etapu, 410 wygasły/unieważniony, 409 już użyty (bez danych)."""
    token_hash = hash_token(raw)
    tok = (db.scalar(select(AvizoFormToken).where(AvizoFormToken.token_hash == token_hash))
           or _adopt_legacy(db, token_hash))
    if tok is None or not hmac.compare_digest(tok.token_hash, token_hash) or tok.stage != stage:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Formularz nie istnieje.")
    if tok.revoked_at or tok.expires_at < utcnow() or tok.request.status in GONE_STATUSES:
        raise HTTPException(status.HTTP_410_GONE, "Link do formularza wygasł lub został unieważniony.")
    if tok.used_at and not allow_used:
        # kod maszynowy: front odróżnia „już wysłany” (koniec) od „slot zajęty” (do poprawy)
        raise HTTPException(status.HTTP_409_CONFLICT, {"code": "already_submitted",
                                                      "message": "Formularz już wysłany."})
    return tok


def claim_token(db: Session, tok: AvizoFormToken) -> datetime.datetime:
    """Atomowe zużycie tokenu: warunkowy UPDATE ... WHERE used_at IS NULL. Dwa równoległe
    wysłania formularza — tylko jedno zmienia wiersz, drugie dostaje 409 (sam odczyt
    used_at w lookup_token tego nie gwarantuje)."""
    db.flush()
    now = utcnow()
    res = db.execute(update(AvizoFormToken)
                     .where(AvizoFormToken.id == tok.id, AvizoFormToken.used_at.is_(None))
                     .values(used_at=now)
                     .execution_options(synchronize_session=False))
    if res.rowcount != 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "Formularz już wysłany.")
    tok.used_at = now
    return now


# --- maile (Jinja2, PL/EN wg Forwarder.language) ---

# wspólne środowisko html_templates (autoescape dla *.html, filtr date_pl) — ARCH-008
SUBJECTS = {
    ("stage1", "pl"): "Prośba o potwierdzenie dostaw — {company} ({n} kont.) [#{id}]",
    ("stage1", "en"): "Delivery confirmation request — {company} ({n} containers) [#{id}]",
    ("rejected", "pl"): "Awizacja odrzucona — prosimy o ponowne potwierdzenie — {company} [#{id}]",
    ("rejected", "en"): "Booking not approved — please confirm again — {company} [#{id}]",
    ("stage2", "pl"): "Prośba o dane kierowców — {company} ({n} kont.) [#{id}]",
    ("stage2", "en"): "Driver details request — {company} ({n} containers) [#{id}]",
}


def split_addresses(value: str) -> list[str]:
    return [a.strip() for a in re.split(r"[,;\s]+", value or "") if a.strip()]


def latest_confirmations(db: Session, req: AvizoRequest) -> list[DeliveryConfirmation]:
    """Odpowiedzi z ostatniego wysłania formularza etapu 1 (po odrzuceniu bywa kilka)."""
    rows = db.scalars(
        select(DeliveryConfirmation).where(DeliveryConfirmation.request_id == req.id)
        .order_by(DeliveryConfirmation.submitted_at.desc(), DeliveryConfirmation.id.desc())).all()
    latest: dict[int, DeliveryConfirmation] = {}
    for row in rows:
        latest.setdefault(row.container_id, row)
    return list(latest.values())


def stage2_items(db: Session, req: AvizoRequest) -> list[AvizoItem]:
    """Kontenery etapu 2: bez tych, dla których spedycja zgłosiła problem."""
    problems = {c.container_id for c in latest_confirmations(db, req) if c.decision == "problem"}
    return [i for i in req.items if i.container_id not in problems]


def build_mail(db: Session, req: AvizoRequest, kind: str, raw: str, base: str,
               user: User | None) -> mailer.Mail:
    lang = req.language if req.language in ("pl", "en") else "pl"
    stage = 2 if kind == "stage2" else 1
    items = stage2_items(db, req) if stage == 2 else req.items
    tok_days = settings.avizo_stage2_days if stage == 2 else settings.avizo_stage1_days
    operator = user or req.created_by
    company = req.company.name if req.company else ""
    ctx = {
        "kind": kind, "request_id": req.id, "company": company,
        "comment": req.reject_comment, "note": req.note,
        "link": f"{base.rstrip('/')}/avizo/{'driver/' if stage == 2 else ''}{raw}",
        "expires": date_pl(utcnow() + datetime.timedelta(days=tok_days)),
        "operator": (operator.full_name or operator.login) if operator else company,
        "operator_email": operator.email if operator else "",
        "containers": [{
            "no": i.container.container_no, "vessel": i.container.vessel or "",
            "date": date_pl(i.container.notify_date),
            "slot": i.container.slot_time or "",
            "warehouse": i.container.warehouse.name if i.container.warehouse else "",
        } for i in items],
    }
    return mailer.Mail(
        to=split_addresses(req.forwarder.email),
        cc=split_addresses(req.company.avizo_cc if req.company else ""),
        subject=SUBJECTS[(kind, lang)].format(company=company, n=len(items), id=req.id),
        html=_env.get_template(f"avizo/{lang}.html").render(ctx),
        text=_env.get_template(f"avizo/{lang}.txt").render(ctx),
        reply_to=(operator.email if operator and operator.email else settings.mail_sender))


def _log_mail(request_id: int, kind: str, *, recipients: str = "", cc: str = "",
              backend: str, attempts: int, error: str) -> None:
    result = "failed" if error else "sent"
    with SessionLocal() as db:
        db.add(AvizoMailLog(request_id=request_id, stage=2 if kind == "stage2" else 1, kind=kind,
                            recipients=recipients, cc=cc, backend=backend, status=result,
                            attempts=attempts, error=error))
        record(db, entity_type="avizo_requests", entity_id=request_id, field="mail_" + kind,
               old_value=None, new_value=result, user=None,
               note=f"{backend}, prób: {attempts}" + (f" — {error[:200]}" if error else ""))
        db.commit()


def deliver(request_id: int, kind: str, mail: mailer.Mail) -> None:
    """Wysyłka z retry + wpis w AvizoMailLog i audycie. Wołane w tle (notifications._submit)."""
    sender = mailer.get_sender()
    attempts, error = mailer.send_with_retry(sender, mail)
    _log_mail(request_id, kind, recipients=", ".join(mail.to), cc=", ".join(mail.cc),
              backend=sender.name, attempts=attempts, error=error)


def _commit_and_send(db: Session, req: AvizoRequest, kind: str, raw: str, base: str,
                     user: User | None) -> None:
    """Commit PRZED wysyłką (token musi istnieć, gdy link dotrze), mail w tle."""
    from .notifications import _submit
    mail = build_mail(db, req, kind, raw, base, user)
    db.commit()
    if not mail.to:
        _log_mail(req.id, kind, backend=mailer.backend_name(), attempts=0,
                  error="Spedytor nie ma adresu e-mail.")
        return
    _submit(deliver, req.id, kind, mail)


# --- operacje (wołane z routerów; każda kończy się commitem) ---

def create_and_send(db: Session, *, company_id: int, forwarder: Forwarder,
                    containers: list[Container], note: str, user: User,
                    base: str) -> AvizoRequest:
    req = AvizoRequest(token=hash_token(secrets.token_urlsafe(32)), company_id=company_id,
                       forwarder_id=forwarder.id, created_by_id=user.id, note=note,
                       status=S.DRAFT, language=forwarder.language or "pl")
    db.add(req)
    db.flush()
    for c in containers:
        db.add(AvizoItem(request_id=req.id, container_id=c.id))
    record(db, entity_type="avizo_requests", entity_id=req.id, field="sent", old_value=None,
           new_value=f"{forwarder.name} <{forwarder.email}>", user=user,
           note=f"{len(containers)} kont.")
    transition(db, req, S.SENT_STAGE1, user)
    raw = issue_token(db, req, 1)
    req.token = hash_token(raw)
    db.flush()
    db.refresh(req)   # items/company/forwarder do szablonu
    _commit_and_send(db, req, "stage1", raw, base, user)
    return req


def book_date_slot(db: Session, c: Container, day: datetime.date | None, slot: str,
                   user: User, note: str) -> None:
    """Termin + slot kontenera — wspólne dla zatwierdzenia etapu 1 i akceptacji propozycji
    zmiany. Slot zapisujemy PO dacie (listener czyści slot_time przy zmianie dnia).
    Magazyn bez okien slotów (albo kontener bez magazynu) → godzina bez rezerwacji."""
    from .planning import confirm_plan
    from .slots import is_free, lock_warehouse, windows
    wins = windows(c.warehouse) if slot else []
    if wins and slot not in wins:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Godzina {slot} dla {c.container_no} jest poza oknami slotów "
                            f"magazynu ({', '.join(wins)}).")
    if wins:
        lock_warehouse(db, c.warehouse_id)   # decyzja 5: bez wyścigu sprawdź→zapisz
    if wins and (slot != c.slot_time or day != c.notify_date) \
            and not is_free(db, c.warehouse, day, slot, c.id):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Slot {slot} dnia {day} dla {c.container_no} jest już zajęty.")
    if day:
        confirm_plan(db, c, day, confirmed_by=user, note=note)
    if slot:
        record_changes(db, c, {"slot_time": slot}, user=user, note=note)
        db.flush()   # autoflush=False — kolejny kontener musi widzieć zajęty slot


def approve(db: Session, req: AvizoRequest, user: User, base: str) -> None:
    """Stosuje odpowiedzi etapu 1 (termin/slot) i wysyła DOKŁADNIE jeden mail etapu 2."""
    transition(db, req, S.APPROVED_BY_US, user)
    if not stage2_items(db, req):
        raise HTTPException(status.HTTP_409_CONFLICT, "Wszystkie kontenery zgłoszone jako "
                            "problem — odrzuć z komentarzem zamiast zatwierdzać.")
    items = {i.container_id: i for i in req.items}
    note = f"awizacja #{req.id} zatwierdzona ({req.forwarder.name})"
    for conf in latest_confirmations(db, req):
        if conf.decision == "problem" or conf.container_id not in items:
            continue
        c = conf.container
        book_date_slot(db, c, conf.proposed_date or c.notify_date, conf.proposed_time,
                       user, note)
        items[conf.container_id].confirmed = True
    req.approved_by_id = user.id
    req.approved_at = utcnow()
    transition(db, req, S.SENT_STAGE2, user)
    raw = issue_token(db, req, 2)
    _commit_and_send(db, req, "stage2", raw, base, user)


def reject(db: Session, req: AvizoRequest, user: User, comment: str, base: str) -> None:
    """Odrzucenie z komentarzem → nowy token etapu 1 i jeden mail z prośbą o poprawę."""
    transition(db, req, S.REJECTED, user, note=comment)
    req.reject_comment = comment
    transition(db, req, S.SENT_STAGE1, user)
    raw = issue_token(db, req, 1)
    _commit_and_send(db, req, "rejected", raw, base, user)


def resend(db: Session, req: AvizoRequest, stage: int, user: User, base: str) -> None:
    target = S.SENT_STAGE1 if stage == 1 else S.SENT_STAGE2
    if req.status == S.EXPIRED:
        last = db.scalar(select(AvizoFormToken).where(AvizoFormToken.request_id == req.id)
                         .order_by(AvizoFormToken.id.desc()))
        if last and last.stage != stage:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"Wygasł link etapu {last.stage}, nie {stage}.")
    if req.status != target:
        transition(db, req, target, user, note="ponowna wysyłka")
    raw = issue_token(db, req, stage)
    _commit_and_send(db, req, "stage2" if stage == 2 else "stage1", raw, base, user)


def revoke(db: Session, req: AvizoRequest, user: User) -> int:
    count = revoke_tokens(db, req)
    record(db, entity_type="avizo_requests", entity_id=req.id, field="tokens_revoked",
           old_value=None, new_value=str(count), user=user)
    db.commit()
    return count


def cancel(db: Session, req: AvizoRequest, user: User) -> None:
    revoke_tokens(db, req)
    transition(db, req, S.CANCELLED, user)
    db.commit()


# --- utrzymanie (pętla dzienna w main.py) ---

DRIVER_FIELDS = ("driver_name", "driver_id_no", "truck_no", "trailer_no", "driver_phone")


def run_maintenance(db: Session) -> dict:
    """EXPIRED (brak aktywnego linku bieżącego etapu), CLOSED (wszystkie kontenery
    dostarczone/zrealizowane), anonimizacja Container.driver_* po DRIVER_DATA_RETENTION_DAYS
    od zamknięcia awizacji albo od realizacji kontenera bez awizacji (RODO).
    Idempotentne; commit na końcu."""
    now = utcnow()
    stats = {"expired": 0, "closed": 0, "anonymized": 0}
    for req in db.scalars(select(AvizoRequest).where(
            AvizoRequest.status.in_((S.SENT_STAGE1, S.SENT_STAGE2)))):
        stage = 1 if req.status == S.SENT_STAGE1 else 2
        active = db.scalar(select(AvizoFormToken.id).where(
            AvizoFormToken.request_id == req.id, AvizoFormToken.stage == stage,
            AvizoFormToken.used_at.is_(None), AvizoFormToken.revoked_at.is_(None),
            AvizoFormToken.expires_at >= now))
        if active is None:
            transition(db, req, S.EXPIRED, None, note=f"link etapu {stage} wygasł")
            stats["expired"] += 1

    for req in db.scalars(select(AvizoRequest).where(
            AvizoRequest.status.not_in((S.CLOSED, S.CANCELLED)))):
        if S.CLOSED in TRANSITIONS[req.status] and req.items \
                and all(i.container.status in Container.FINISHED for i in req.items):
            transition(db, req, S.CLOSED, None, note="wszystkie kontenery dostarczone")
            stats["closed"] += 1
    db.flush()

    cutoff = now - datetime.timedelta(days=settings.driver_data_retention_days)
    for req in db.scalars(select(AvizoRequest).where(
            AvizoRequest.status.in_((S.CLOSED, S.CANCELLED)), AvizoRequest.closed_at < cutoff,
            AvizoRequest.driver_data_purged_at.is_(None))):
        for item in req.items:
            # kontener w nowszej/aktywnej awizacji — jego dane kierowcy są wciąż potrzebne
            newer = db.scalar(select(AvizoItem.id).join(AvizoRequest).where(
                AvizoItem.container_id == item.container_id, AvizoRequest.id != req.id,
                AvizoRequest.status.not_in((S.CLOSED, S.CANCELLED))
                | (AvizoRequest.closed_at >= cutoff)))
            if newer is None:
                stats["anonymized"] += _purge_driver_data(
                    db, item.container, f"retencja RODO — awizacja #{req.id}")
        req.driver_data_purged_at = now

    # GDPR-002: dane wpisane bez awizacji (karta kontenera, import) — ta sama retencja
    # liczona od realizacji; pomija kontenery w aktywnej/świeżo zamkniętej awizacji
    in_avizo = select(AvizoItem.container_id).join(AvizoRequest).where(
        AvizoRequest.status.not_in((S.CLOSED, S.CANCELLED)) | (AvizoRequest.closed_at >= cutoff))
    for c in db.scalars(select(Container).where(
            Container.status == ContainerStatus.ZREALIZOWANY, Container.completed_at < cutoff,
            Container.id.not_in(in_avizo),
            or_(*(getattr(Container, f) != "" for f in DRIVER_FIELDS)))).all():
        stats["anonymized"] += _purge_driver_data(db, c, "retencja RODO — po realizacji")
    db.commit()
    return stats


def _purge_driver_data(db: Session, c: Container, note: str, user: User | None = None) -> int:
    """Czyści Container.driver_* i ich kopie; zwraca 1, jeśli kontener miał dane.
    `user` = autor wpisu w audycie (żądanie RODO przez admina); retencja = system (None)."""
    had = any(getattr(c, f) for f in DRIVER_FIELDS)
    if had:
        record_changes(db, c, {f: "" for f in DRIVER_FIELDS}, user=user, note=note)
    # kopie danych kierowcy poza kontenerem (GDPR-001): powiadomienia i historia SMS
    db.execute(update(Notification).where(Notification.container_id == c.id,
                                          Notification.kind == "driver").values(body=""))
    db.execute(update(SmsMessage).where(SmsMessage.container_id == c.id)
               .values(phone="", body=""))
    return int(had)


DRIVER_ID_RETENTION_DAYS = 30   # decyzja D8: nr dokumentu kierowcy 30 dni po ZREALIZOWANY


def purge_driver_id_no(db: Session) -> int:
    """RODO: czyści Container.driver_id_no 30 dni po ZREALIZOWANY (completed_at) —
    niezależnie od awizacji (dane wpisane ręcznie też). Idempotentne."""
    cutoff = utcnow() - datetime.timedelta(days=DRIVER_ID_RETENTION_DAYS)
    rows = db.scalars(select(Container).where(
        Container.status == ContainerStatus.ZREALIZOWANY,  # dosłownie: retencja po realizacji
        Container.completed_at < cutoff,
        Container.driver_id_no != "")).all()
    for c in rows:
        record_changes(db, c, {"driver_id_no": ""}, user=None,
                       note=f"retencja RODO — {DRIVER_ID_RETENTION_DAYS} dni po realizacji")
    db.commit()
    return len(rows)
