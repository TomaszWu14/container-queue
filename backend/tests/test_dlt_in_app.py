"""DLT w aplikacji (decyzja 2026-10-07: nic bez logowania): magazyn DLT z kontem (rola
warehouse) potwierdza „Przygotowane” i „Wysłane” na wywołaniu — ta sama kolejność,
audyt z użytkownikiem i wygaszenie linku z maila po wysyłce."""
from sqlalchemy import select

from app.database import SessionLocal
from app.models import AuditLog, PalletCall, PalletCallLink, Role, User
from app.security import hash_password
from tests.conftest import login
from tests.test_dlt_confirm import _mock_powerbi, _send_call  # noqa: F401 — fixture autouse


def _user(role: Role, login_name: str, company_id: int) -> None:
    with SessionLocal() as db:
        db.add(User(login=login_name, hashed_password=hash_password("pass12345"),
                    role=role, company_id=company_id))
        db.commit()


def test_warehouse_confirms_prepared_then_shipped(client, admin_headers, monkeypatch):
    call_id, _ = _send_call(client, admin_headers, monkeypatch)
    with SessionLocal() as db:
        company_id = db.get(PalletCall, call_id).company_id
    _user(Role.warehouse, "dlt-mag", company_id)
    _user(Role.forwarder, "dlt-sped", company_id)
    dlt = login(client, "dlt-mag", "pass12345")
    url = f"/api/pallet-calls/{call_id}"

    assert client.post(f"{url}/shipped", headers=dlt).status_code == 409      # najpierw przygotowane
    assert client.post(f"{url}/prepared",
                       headers=login(client, "dlt-sped", "pass12345")).status_code == 403
    dlt = login(client, "dlt-mag", "pass12345")
    prepared = client.post(f"{url}/prepared", headers=dlt)
    assert prepared.status_code == 200 and prepared.json()["status"] == "przygotowane"
    shipped = client.post(f"{url}/shipped", headers=dlt)
    assert shipped.status_code == 200 and shipped.json()["status"] == "wyslane_z_dlt"

    with SessionLocal() as db:
        notes = db.scalars(select(AuditLog.note).where(
            AuditLog.entity_type == "pallet_call", AuditLog.entity_id == call_id,
            AuditLog.field == "status", AuditLog.user_id.is_not(None))).all()
        assert notes.count("w aplikacji") == 2
        assert db.scalar(select(PalletCallLink).where(
            PalletCallLink.pallet_call_id == call_id,
            PalletCallLink.deactivated_at.is_(None))) is None   # link z maila wygaszony
