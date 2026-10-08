"""Audyt SEC-014: twardy termin ważności publicznych linków (PUBLIC_LINK_MAX_DAYS).
DLT bez
terminu działały bez końca. Termin liczony od wystawienia — obejmuje też stare linki."""
import datetime

from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models import PalletCallLink
from tests.test_dlt_confirm import _mock_powerbi, _send_call  # noqa: F401 — fixture autouse


def _age(model, days: int) -> None:
    with SessionLocal() as db:
        for row in db.scalars(select(model)):
            row.created_at -= datetime.timedelta(days=days)
        db.commit()


def test_default_max_days():
    from app.config import Settings
    assert Settings.model_fields["public_link_max_days"].default == 90


def test_dlt_link_without_needed_by_capped(client, admin_headers, monkeypatch):
    _, token = _send_call(client, admin_headers, monkeypatch)
    assert client.get(f"/api/dlt/{token}").status_code == 200
    _age(PalletCallLink, settings.public_link_max_days + 1)
    assert client.get(f"/api/dlt/{token}").status_code == 404
