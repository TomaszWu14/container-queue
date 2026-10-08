"""Filtr czyszczenia kolejki: data dostawy (notify_date) + zachowane statusy + dry_run."""
import datetime

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Company, Container
from tests.conftest import login


def _seed(no, notify_date=None, status=None):
    db = SessionLocal()
    try:
        company = db.scalar(select(Company).where(Company.code == "ACME"))
        c = Container(company_id=company.id, container_no=no,
                      notify_date=notify_date, status=status or "ZAPOWIEDZIANY")
        db.add(c)
        db.commit()
        return c.id
    finally:
        db.close()


def _exists(no):
    db = SessionLocal()
    try:
        return db.scalar(select(Container).where(Container.container_no == no)) is not None
    finally:
        db.close()


def test_before_deletes_only_older_and_keeps_without_date(client):
    hdr = login(client)
    _seed("MSKU1000001", notify_date=datetime.date(2026, 1, 1))
    _seed("MSKU1000002", notify_date=datetime.date(2026, 6, 1))
    _seed("MSKU1000003", notify_date=None)
    resp = client.delete(
        "/api/containers?company_code=ACME&before=2026-03-01&confirm=true", headers=hdr)
    assert resp.status_code == 200 and resp.json()["deleted"] == 1
    assert not _exists("MSKU1000001")
    assert _exists("MSKU1000002")
    assert _exists("MSKU1000003")  # bez daty — zostaje


def test_keep_statuses_preserves_selected(client):
    hdr = login(client)
    _seed("MSKU2000001", notify_date=datetime.date(2026, 1, 1), status="ZAPOWIEDZIANY")
    _seed("MSKU2000002", notify_date=datetime.date(2026, 1, 1), status="W_TRANSPORCIE")
    resp = client.delete(
        "/api/containers?company_code=ACME&keep_statuses=W_TRANSPORCIE&confirm=true",
        headers=hdr)
    assert resp.status_code == 200 and resp.json()["deleted"] == 1
    assert not _exists("MSKU2000001")
    assert _exists("MSKU2000002")


def test_dry_run_counts_without_deleting_and_skips_confirm(client):
    hdr = login(client)
    _seed("MSKU3000001", notify_date=datetime.date(2026, 1, 1))
    resp = client.delete(
        "/api/containers?company_code=ACME&before=2026-03-01&dry_run=true", headers=hdr)
    assert resp.status_code == 200 and resp.json()["deleted"] == 1
    assert _exists("MSKU3000001")  # nic nie skasowane


def test_no_params_behaves_as_before_requires_confirm_deletes_all(client):
    hdr = login(client)
    _seed("MSKU4000001", notify_date=datetime.date(2026, 1, 1))
    _seed("MSKU4000002", notify_date=None)
    assert client.delete("/api/containers?company_code=ACME", headers=hdr).status_code == 400
    resp = client.delete("/api/containers?company_code=ACME&confirm=true", headers=hdr)
    assert resp.status_code == 200 and resp.json()["deleted"] == 2
    assert not _exists("MSKU4000001")
    assert not _exists("MSKU4000002")


def test_clear_queue_still_admin_only(client):
    from app.models import Role, User
    from app.security import hash_password
    _seed("MSKU5000001", notify_date=datetime.date(2026, 1, 1))
    db = SessionLocal()
    try:
        company = db.scalar(select(Company).where(Company.code == "ACME"))
        db.add(User(login="log2", hashed_password=hash_password("pass12345"),
                    role=Role.logistics, company_id=company.id))
        db.commit()
    finally:
        db.close()
    hdr = login(client, "log2", "pass12345")
    resp = client.delete("/api/containers?company_code=ACME&confirm=true", headers=hdr)
    assert resp.status_code == 403
