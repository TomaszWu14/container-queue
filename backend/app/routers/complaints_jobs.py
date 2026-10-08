"""Reklamacje — pętle tła: auto-szkic z opóźnienia (W11 #67) i przypomnienia
(licznik czasu od wysyłki + termin przedawnienia W11 #69). Wołane z app/jobs.py."""
import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..audit import record
from ..config import settings as app_config
from ..models import Complaint, ComplaintKind, ComplaintStatus, Container, today_pl, utcnow
from ..notifications import company_watchers, notify
from .complaints_common import (
    _LOAD,
    _timeline_lines,
    complaint_deadline,
    get_setting,
    next_complaint_number,
)


# --- auto-szkic reklamacji z opóźnienia (W11 #67) ---

def check_complaint_auto_drafts(db: Session, today: datetime.date | None = None) -> int:
    """Kontener >= COMPLAINT_AUTO_DRAFT_DAYS po ETA bez dostawy → szkic reklamacji.

    Jeden szkic per kontener (dedup po fladze auto_draft, niezależnie od statusu) —
    ponowny przebieg pętli i ręczne zamknięcie szkicu nie tworzą duplikatów.
    """
    today = today or today_pl()
    cutoff = today - datetime.timedelta(days=app_config.complaint_auto_draft_days)
    overdue = db.scalars(select(Container)
                         .options(selectinload(Container.supplier))
                         .where(Container.status.notin_(Container.FINISHED),
                                Container.atd.is_(None),
                                Container.eta.is_not(None),
                                Container.eta <= cutoff)).all()
    if not overdue:
        return 0
    drafted = set(db.scalars(select(Complaint.container_id).where(
        Complaint.auto_draft.is_(True),
        Complaint.container_id.in_([c.id for c in overdue]))))
    prefix = get_setting(db, "complaint_prefix") or "REK"
    created = 0
    for container in overdue:
        if container.id in drafted:
            continue
        days = (today - container.eta).days
        timeline = "\n".join(_timeline_lines(db, container))
        description = (
            f"[AUTO-SZKIC] Kontener {container.container_no} jest {days} dni po ETA "
            f"({container.eta}) bez potwierdzonej dostawy.\n\n"
            f"Oś czasu (materiał dowodowy):\n{timeline or '—'}")
        complaint = Complaint(
            number=next_complaint_number(db, container, prefix),
            kind=ComplaintKind.REKLAMACJA, status=ComplaintStatus.SZKIC,
            container_id=container.id, company_id=container.company_id,
            description=description, auto_draft=True)
        db.add(complaint)
        try:
            db.flush()
        except IntegrityError:   # wyścig numeracji z równoległym workerem — pomiń
            db.rollback()
            continue
        record(db, entity_type="complaints", entity_id=complaint.id, field="status",
               old_value=None, new_value=complaint.status.value, user=None,
               note=f"auto-szkic z opóźnienia ({complaint.number})")
        notify(db, company_watchers(db, container.company_id), kind="complaint_draft",
               title=f"Szkic reklamacji czeka: {container.container_no} "
                     f"({days} dni po ETA)",
               body=f"System utworzył szkic reklamacji {complaint.number} — uzupełnij "
                    f"i wyślij albo zamknij, jeśli bezzasadny.",
               container_id=container.id)
        db.commit()
        created += 1
    return created


# --- przypomnienia (licznik czasu) ---

def check_complaint_reminders(db: Session, now: datetime.datetime | None = None) -> int:
    """Przypomnienie do logistyki, gdy reklamacja wysłana i bez odpowiedzi przez próg dni.

    Progi (np. 15,30) z ustawień; każdy próg strzela raz (zapamiętany w reminders_sent).
    """
    now = now or utcnow()
    if now.tzinfo is not None:  # sent_at zapisywane jako naive UTC — ujednolicamy
        now = now.astimezone(datetime.UTC).replace(tzinfo=None)
    raw = get_setting(db, "reminder_days") or "15,30"
    thresholds = sorted({int(x) for x in raw.replace(" ", "").split(",") if x.isdigit()})
    pending = db.scalars(select(Complaint).options(*_LOAD).where(
        Complaint.status == ComplaintStatus.WYSLANA,
        Complaint.sent_at.is_not(None))).all() if thresholds else []
    sent = 0
    for complaint in pending:
        age = (now - complaint.sent_at).days
        done = {int(x) for x in complaint.reminders_sent.split(",") if x.strip().isdigit()}
        due = [t for t in thresholds if age >= t and t not in done]
        if not due:
            continue
        threshold = max(due)
        container = complaint.container
        title = (f"Reklamacja {complaint.number}: brak odpowiedzi od {threshold} dni "
                 f"({container.container_no if container else ''})")
        body = (f"Wysłano do {complaint.sent_target} {complaint.sent_at.date()}.\n"
                f"Sprawdź status sprawy / czy odpowiedź nie przyszła innym kanałem.")
        recipients = company_watchers(db, complaint.company_id)
        if complaint.created_by:
            recipients.append(complaint.created_by)
        # najpierw utrwalamy próg (idempotencja), potem wysyłamy — restart w połowie
        # pętli nie spowoduje ponownej wysyłki tych samych przypomnień
        complaint.reminders_sent = ",".join(str(t) for t in sorted(done | set(due)))
        db.commit()
        notify(db, recipients, kind="complaint_reminder", title=title, body=body,
               container_id=complaint.container_id)
        db.commit()
        sent += 1

    # W11 #69: alert przed upływem terminu przedawnienia (raz per reklamacja —
    # marker "P" w reminders_sent; parser progów wyżej ignoruje go przez isdigit())
    open_typed = db.scalars(select(Complaint).options(*_LOAD).where(
        Complaint.status != ComplaintStatus.ZAMKNIETA,
        Complaint.recipient_type != "")).all()
    for complaint in open_typed:
        if "P" in complaint.reminders_sent.split(","):
            continue
        deadline = complaint_deadline(complaint)
        if deadline is None:
            continue
        days_left = (deadline - now.date()).days
        if days_left > app_config.complaint_deadline_alert_days:
            continue
        container = complaint.container
        if days_left >= 0:
            title = (f"Reklamacja {complaint.number}: termin przedawnienia za "
                     f"{days_left} dni ({deadline})")
        else:
            title = f"Reklamacja {complaint.number}: termin przedawnienia minął {deadline}!"
        recipients = company_watchers(db, complaint.company_id)
        if complaint.created_by:
            recipients.append(complaint.created_by)
        complaint.reminders_sent = ",".join(
            x for x in (complaint.reminders_sent, "P") if x)
        db.commit()   # najpierw marker (idempotencja), potem wysyłka
        notify(db, recipients, kind="complaint_deadline", title=title,
               body=f"Adresat: {complaint.recipient_type}. Kontener "
                    f"{container.container_no if container else ''}.",
               container_id=complaint.container_id)
        db.commit()
        sent += 1
    return sent
