"""Reklamacje — wspólne helpery: terminy przedawnienia, serializacja, ładowanie z kontrolą
dostępu, numeracja. Używane przez router reklamacji, pisma i pętle tła (re-eksport
w routers/complaints.py). Ustawienia AppSetting: app/app_settings.py (tu re-eksport)."""
import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..app_settings import SETTINGS_DEFAULTS, get_setting, set_setting  # noqa: F401 — re-eksport
from ..config import settings as app_config
from ..date_pl import date_pl
from ..deps import get_scoped
from ..models import (
    Complaint,
    ComplaintProblem,
    ComplaintStatus,
    Container,
    Role,
    User,
    to_pl_date,
    today_pl,
    utcnow,
)
from ..schemas import ComplaintDetailOut, ComplaintOut, ComplaintPhotoOut

def _looks_like_image(head: bytes) -> bool:
    """Rozpoznaje obraz po sygnaturze bajtowej — nie ufamy Content-Type/rozszerzeniu."""
    if head.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF87a", b"GIF89a")):
        return True
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return True
    if head[4:8] == b"ftyp":  # HEIC/HEIF (kontener ISO-BMFF)
        return True
    return False


# --- reklamacje ---

def deadline_days_for(recipient_type: str) -> int | None:
    """Termin przedawnienia (dni od utworzenia) wg typu adresata; env/defaults 14/60/30."""
    return {
        "PRZEWOZNIK": app_config.complaint_deadline_carrier_days,
        "UBEZPIECZYCIEL": app_config.complaint_deadline_insurer_days,
        "DOSTAWCA": app_config.complaint_deadline_supplier_days,
    }.get(recipient_type)


def complaint_deadline(c: Complaint) -> datetime.date | None:
    days = deadline_days_for(c.recipient_type)
    if days is None:
        return None
    return to_pl_date(c.created_at) + datetime.timedelta(days=days)


# kwoty roszczeń/odzysków: role kosztowe; partnerzy zewnętrzni, magazyn i sprzedaż nie (2026-10-05)
COST_ROLES = (Role.admin, Role.logistics, Role.purchasing)


def complaint_to_out(c: Complaint, user: User, detail: bool = False) -> ComplaintOut:
    end = c.closed_at or utcnow()
    costs = user.role in COST_ROLES
    deadline = complaint_deadline(c)
    data = dict(
        recipient_type=c.recipient_type,
        deadline_at=deadline,
        deadline_days_left=((deadline - today_pl()).days
                            if deadline and c.status != ComplaintStatus.ZAMKNIETA else None),
        claim_amount=float(c.claim_amount) if costs and c.claim_amount is not None else None,
        recovered_amount=(float(c.recovered_amount)
                          if costs and c.recovered_amount is not None else None),
        claim_currency=c.claim_currency or "PLN",
        auto_draft=c.auto_draft,
        id=c.id, number=c.number, kind=c.kind.value, status=c.status.value,
        container_id=c.container_id,
        container_no=c.container.container_no if c.container else None,
        company_id=c.company_id, description=c.description, driver_note=c.driver_note,
        created_by_login=c.created_by.login if c.created_by else None,
        created_at=c.created_at, reported_at=c.reported_at, sent_at=c.sent_at,
        sent_target=c.sent_target, response_at=c.response_at, closed_at=c.closed_at,
        age_days=(end - c.created_at).days,
        problems=[p.problem_type.name for p in c.problems if p.problem_type],
        photo_count=len(c.photos))
    if detail:
        return ComplaintDetailOut(
            **data, photos=[ComplaintPhotoOut.model_validate(p) for p in c.photos])
    return ComplaintOut(**data)


_LOAD = (
    selectinload(Complaint.container),
    selectinload(Complaint.created_by),
    selectinload(Complaint.problems).selectinload(ComplaintProblem.problem_type),
    selectinload(Complaint.photos),
)


def get_complaint_checked(db: Session, complaint_id: int, user: User) -> Complaint:
    return get_scoped(db, Complaint, complaint_id, user, options=_LOAD)


def next_complaint_number(db: Session, container: Container, prefix: str) -> str:
    """Unikalny numer, np. REK-MSDU0806613-20260708 (z sufiksem przy kolizji w dniu)."""
    day = today_pl().strftime("%Y%m%d")
    base = f"{prefix}-{container.container_no}-{day}"
    if not db.scalar(select(Complaint).where(Complaint.number == base)):
        return base
    n = 2
    while db.scalar(select(Complaint).where(Complaint.number == f"{base}-{n}")):
        n += 1
    return f"{base}-{n}"


def _problem_lines(complaint: Complaint) -> str:
    names = [p.problem_type.name for p in complaint.problems if p.problem_type]
    return ", ".join(names) if names else "—"


def _timeline_lines(db: Session, container: Container, hide_orders: bool = False) -> list[str]:
    """Oś czasu kontenera jako tekst dowodowy (data — tytuł (miejsce))."""
    from ..tracking.timeline import build_timeline
    lines = []
    for e in build_timeline(db, container, hide_orders=hide_orders):
        when = date_pl(e.at) or "?"
        loc = f" ({e.location})" if e.location else ""
        est = " [szac.]" if e.estimated else ""
        lines.append(f"{when} — {e.title}{loc}{est}")
    return lines
