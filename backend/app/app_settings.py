"""Ustawienia aplikacji edytowalne w panelu admina (tabela AppSetting: klucz → tekst).

ARCH-001: moduły domenowe (alerty, digest, SharePoint) i kilka routerów czytały te
ustawienia z routers/complaints_common — domena zależała od warstwy HTTP i przez importy
w funkcjach dokładała się do cyklu routerów. Tu jest jedno źródło; routers/complaints*
tylko je re-eksportują (dotychczasowe ścieżki importu działają).
"""
from sqlalchemy.orm import Session

from .models import AppSetting

SETTINGS_DEFAULTS = {"reminder_days": "15,30", "insurer_email": "", "complaint_prefix": "REK",
                     "docs_reminder_days": "7", "forecast_alert_days": "7",
                     "warehouse_eta_buffer_days": "3"}


def get_setting(db: Session, key: str) -> str:
    row = db.get(AppSetting, key)
    return row.value if row else SETTINGS_DEFAULTS.get(key, "")


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.get(AppSetting, key)
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))
