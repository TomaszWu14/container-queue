"""Alert „Palety do pilnego wywołania": powiadomienia muszą przetrwać zamknięcie
sesji joba (zamknięcie sesji bez commita = rollback)."""
from sqlalchemy import select

from app import jobs, pallets_cache, powerbi
from app.database import SessionLocal
from app.models import Company, Notification, Role, User
from app.notifications import check_pallet_urgent_alerts


def test_pallet_urgent_notifications_are_committed(client, db_session, monkeypatch):
    acme = db_session.scalar(select(Company).where(Company.code == "ACME"))
    db_session.add(User(login="acme-log", hashed_password="x", role=Role.logistics,
                        company_id=acme.id))
    db_session.commit()
    monkeypatch.setattr(powerbi, "is_configured", lambda: True)
    monkeypatch.setattr(pallets_cache, "get_analysis",
                        lambda db: ([{"produkt": "DLT-1", "pilne": True}], None, None, None))

    assert jobs._run(check_pallet_urgent_alerts) >= 1   # ścieżka pętli tła

    with SessionLocal() as db:
        assert db.scalars(select(Notification).where(
            Notification.kind == "pallet_urgent")).all()
