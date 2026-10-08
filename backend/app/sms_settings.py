"""Ustawienia SMS do kierowców — edytowalne w panelu admina (decyzja 2026-09-28), w tabeli AppSetting.

Domyślne = dotychczasowe zachowanie: przypomnienie dzień przed dostawą o 15:00 (czas PL), limit
3 SMS spedytora na kontener na dobę.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from .database import get_db
from .deps import AdminOnly as admin_only
from .models import AppSetting, User

DEFAULTS = {"sms_reminder_enabled": "1", "sms_reminder_hour": "15",
            "sms_reminder_days_before": "1", "sms_forwarder_daily_limit": "3"}


class SmsSettings(BaseModel):
    reminder_enabled: bool = True
    reminder_hour: int = Field(default=15, ge=0, le=23)        # godzina wysyłki, czas polski
    reminder_days_before: list[int] = Field(default=[1], min_length=1, max_length=5)
    forwarder_daily_limit: int = Field(default=3, ge=0, le=50)  # 0 = spedytor nie wysyła ręcznie

    @field_validator("reminder_days_before")
    @classmethod
    def _days(cls, v: list[int]) -> list[int]:
        if any(d < 0 or d > 14 for d in v):
            raise ValueError("Dni przed dostawą: od 0 do 14.")
        return sorted(set(v), reverse=True)


def _raw(db: Session, key: str) -> str:
    row = db.get(AppSetting, key)
    return row.value if row else DEFAULTS[key]


def load(db: Session) -> SmsSettings:
    try:
        return SmsSettings(
            reminder_enabled=_raw(db, "sms_reminder_enabled") == "1",
            reminder_hour=int(_raw(db, "sms_reminder_hour")),
            reminder_days_before=[int(x) for x in _raw(db, "sms_reminder_days_before").split(",") if x.strip()],
            forwarder_daily_limit=int(_raw(db, "sms_forwarder_daily_limit")))
    except ValueError:   # uszkodzony wpis w bazie → bezpieczne domyślne, nie 500 w pętli tła
        return SmsSettings()


router = APIRouter(prefix="/api/admin", tags=["administracja"])


@router.get("/sms-settings", response_model=SmsSettings)
def get_sms_settings(db: Session = Depends(get_db), user: User = admin_only):
    return load(db)


@router.put("/sms-settings", response_model=SmsSettings)
def put_sms_settings(body: SmsSettings, db: Session = Depends(get_db), user: User = admin_only):
    from .audit import record
    values = {"sms_reminder_enabled": "1" if body.reminder_enabled else "0",
              "sms_reminder_hour": str(body.reminder_hour),
              "sms_reminder_days_before": ",".join(map(str, body.reminder_days_before)),
              "sms_forwarder_daily_limit": str(body.forwarder_daily_limit)}
    for key, value in values.items():
        row = db.get(AppSetting, key)
        old = row.value if row else DEFAULTS[key]
        if old != value:
            record(db, entity_type="settings", entity_id=0, field=key, old_value=old,
                   new_value=value, user=user, note="ustawienia SMS")
        if row:
            row.value = value
        else:
            db.add(AppSetting(key=key, value=value))
    db.commit()
    return load(db)

