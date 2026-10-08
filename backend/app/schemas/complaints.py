"""Reklamacje, checklista kontroli przyjęcia i ustawienia powiązane z przypomnieniami."""
import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ..models import ComplaintKind, ComplaintStatus
from .base import ORMModel, _validate_email

# --- reklamacje / zgłoszenia problemów ---

class ProblemTypeOut(ORMModel):
    id: int
    name: str
    sort_order: int
    is_active: bool


class ProblemTypeIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    sort_order: int = 100
    is_active: bool = True


class ComplaintPhotoOut(ORMModel):
    id: int
    filename: str
    content_type: str
    size: int
    caption: str
    created_at: datetime.datetime


class ComplaintCreate(BaseModel):
    container_id: int
    kind: ComplaintKind = ComplaintKind.PROBLEM   # nieprawidłowa wartość → 422, nie 500
    description: str = ""
    driver_note: str = ""
    problem_type_ids: list[int] = []
    report_to_warehouse: bool = True      # zgłoś od razu do magazyniera


COMPLAINT_RECIPIENTS = ("PRZEWOZNIK", "UBEZPIECZYCIEL", "DOSTAWCA")


class ComplaintUpdate(BaseModel):
    description: str | None = None
    driver_note: str | None = None
    problem_type_ids: list[int] | None = None
    # W11 #69/#71: typ adresata ("" = wyczyść) + koszty reklamacji
    recipient_type: Literal["", "PRZEWOZNIK", "UBEZPIECZYCIEL", "DOSTAWCA"] | None = None
    claim_amount: float | None = Field(default=None, ge=0)
    recovered_amount: float | None = Field(default=None, ge=0)
    claim_currency: str | None = Field(default=None, min_length=3, max_length=3)


class ComplaintSendIn(BaseModel):
    target_email: str = Field(min_length=3, max_length=200)
    target_label: str = ""                # np. "spedycja SPEDALFA" / "ubezpieczyciel"
    message: str = ""

    _check_email = field_validator("target_email")(_validate_email)


class ComplaintStatusIn(BaseModel):
    status: ComplaintStatus               # nieprawidłowa wartość → 422 (walidacja Pydantic)
    note: str = ""


class ComplaintOut(ORMModel):
    id: int
    number: str
    kind: str
    status: str
    container_id: int
    container_no: str | None = None
    company_id: int
    description: str
    driver_note: str
    created_by_login: str | None = None
    created_at: datetime.datetime
    reported_at: datetime.datetime | None
    sent_at: datetime.datetime | None
    sent_target: str
    response_at: datetime.datetime | None
    closed_at: datetime.datetime | None
    age_days: int = 0
    problems: list[str] = []
    photo_count: int = 0
    # W11: adresat + zegar przedawnienia + koszty + flaga auto-szkicu
    recipient_type: str = ""
    deadline_at: datetime.date | None = None
    deadline_days_left: int | None = None
    claim_amount: float | None = None
    recovered_amount: float | None = None
    claim_currency: str = "PLN"
    auto_draft: bool = False


class ComplaintDetailOut(ComplaintOut):
    photos: list[ComplaintPhotoOut] = []


class ComplaintStatsRow(BaseModel):
    name: str
    containers: int
    with_complaint: int
    pct: float


class ComplaintCostRow(BaseModel):
    currency: str
    claim: float
    recovered: float
    recovery_pct: float


class ComplaintStatsOut(BaseModel):
    months: int
    suppliers: list[ComplaintStatsRow]
    carriers: list[ComplaintStatsRow]
    costs: list[ComplaintCostRow]


# --- checklista kontroli przyjęcia (W11 #72) ---

class ChecklistPointOut(ORMModel):
    id: int
    name: str
    sort_order: int
    is_active: bool


class ChecklistPointIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    sort_order: int = 100
    is_active: bool = True


class ChecklistItemIn(BaseModel):
    point_id: int
    result: Literal["OK", "NOK", "UWAGA"]
    note: str = ""


class ChecklistPutIn(BaseModel):
    items: list[ChecklistItemIn]


class ChecklistResultOut(BaseModel):
    point_id: int
    name: str
    result: str | None = None            # None = jeszcze nie oceniono
    note: str = ""
    checked_by_login: str | None = None
    checked_at: datetime.datetime | None = None


class SettingsOut(BaseModel):
    reminder_days: str = "15,30"          # progi dni do przypomnienia (po przecinku)
    insurer_email: str = ""
    complaint_prefix: str = "REK"
    docs_reminder_days: str = "7"         # przypomnienie o brakach dokumentów N dni przed ETA
    forecast_alert_days: str = "7"        # alert prognozy przekroczenia limitu magazynu (dni w przód)
    warehouse_eta_buffer_days: str = "3"  # ETA magazynu = ETA portu + tyle dni (odprawa+transport)


class SettingsIn(SettingsOut):
    pass
