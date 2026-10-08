"""Awizacja dwuetapowa — pętla utrzymaniowa: EXPIRED, CLOSED, anonimizacja danych kierowców."""
import datetime

from app import avizo_workflow as wf
from app.database import SessionLocal
from app.models import (AuditLog, AvizoFormToken, AvizoItem, AvizoRequest, AvizoStatus, Company,
                        Container, ContainerStatus, Forwarder, utcnow)

S = AvizoStatus


def _req(db, status, *containers, closed_days_ago=None):
    req = AvizoRequest(token=wf.hash_token(f"m-{utcnow().timestamp()}-{status.value}"),
                       company_id=db.query(Company).first().id,
                       forwarder_id=db.query(Forwarder).first().id, status=status)
    if closed_days_ago is not None:
        req.closed_at = utcnow() - datetime.timedelta(days=closed_days_ago)
    db.add(req)
    db.flush()
    for c in containers:
        db.add(AvizoItem(request_id=req.id, container_id=c.id))
    db.flush()
    return req


def _container(db, no, status=ContainerStatus.ZAPOWIEDZIANY, driver=True):
    c = Container(container_no=no, company_id=db.query(Company).first().id, status=status)
    if driver:
        c.driver_name, c.driver_phone, c.truck_no = "Jan", "+48600100200", "WX12345"
    db.add(c)
    db.flush()
    return c


def test_expire_close_and_anonymize(client):
    with SessionLocal() as db:
        # EXPIRED: link etapu 1 po terminie; aktywny link zostaje w SENT_STAGE1
        stale = _req(db, S.SENT_STAGE1, _container(db, "MNTU0000001"))
        wf.issue_token(db, stale, 1)
        db.query(AvizoFormToken).filter_by(request_id=stale.id).update(
            {"expires_at": utcnow() - datetime.timedelta(hours=1)})
        fresh = _req(db, S.SENT_STAGE1, _container(db, "MNTU0000002"))
        wf.issue_token(db, fresh, 1)
        # CLOSED: wszystkie kontenery dostarczone
        done = _req(db, S.DRIVERS_SUBMITTED,
                    _container(db, "MNTU0000003", ContainerStatus.DOSTARCZONY),
                    _container(db, "MNTU0000004", ContainerStatus.ZREALIZOWANY))
        partly = _req(db, S.DRIVERS_SUBMITTED,
                      _container(db, "MNTU0000005", ContainerStatus.DOSTARCZONY),
                      _container(db, "MNTU0000006"))
        # anonimizacja: zamknięte 91 dni temu; kontener współdzielony z aktywną awizacją — zostaje
        old_c, shared_c = _container(db, "MNTU0000007"), _container(db, "MNTU0000008")
        old = _req(db, S.CLOSED, old_c, shared_c, closed_days_ago=91)
        _req(db, S.SENT_STAGE2, shared_c)
        recent_c = _container(db, "MNTU0000009")
        recent = _req(db, S.CLOSED, recent_c, closed_days_ago=10)
        db.commit()
        ids = {k: v.id for k, v in dict(stale=stale, fresh=fresh, done=done, partly=partly,
                                         old=old, recent=recent).items()}
        cids = (old_c.id, shared_c.id, recent_c.id)

    with SessionLocal() as db:
        stats = wf.run_maintenance(db)
    assert stats["expired"] >= 1 and stats["closed"] == 1 and stats["anonymized"] == 1

    with SessionLocal() as db:
        status = {k: db.get(AvizoRequest, v).status for k, v in ids.items()}
        assert status["stale"] == S.EXPIRED and status["fresh"] == S.SENT_STAGE1
        assert status["done"] == S.CLOSED and status["partly"] == S.DRIVERS_SUBMITTED
        assert db.get(AvizoRequest, ids["done"]).closed_at is not None
        old_c, shared_c, recent_c = (db.get(Container, i) for i in cids)
        assert (old_c.driver_name, old_c.driver_phone, old_c.truck_no) == ("", "", "")
        assert shared_c.driver_name == "Jan" and recent_c.driver_name == "Jan"
        assert db.get(AvizoRequest, ids["old"]).driver_data_purged_at is not None
        assert db.get(AvizoRequest, ids["recent"]).driver_data_purged_at is None
        audit = db.query(AuditLog).filter_by(entity_type="containers", entity_id=cids[0],
                                             field="driver_phone").one()
        assert audit.new_value == "" and "RODO" in audit.note

    with SessionLocal() as db:   # idempotencja
        assert wf.run_maintenance(db) == {"expired": 0, "closed": 0, "anonymized": 0}


def test_purge_driver_id_no_after_realization(client):
    """D8: driver_id_no czyszczony 30 dni po ZREALIZOWANY; świeże/niezrealizowane zostają."""
    now = utcnow()
    with SessionLocal() as db:
        cs = [_container(db, no, st) for no, st in (
            ("PRGU0000001", ContainerStatus.ZREALIZOWANY),
            ("PRGU0000002", ContainerStatus.ZREALIZOWANY),
            ("PRGU0000003", ContainerStatus.DOSTARCZONY))]
        for c, days in zip(cs, (31, 10, 60)):
            c.driver_id_no, c.completed_at = "ABC123456", now - datetime.timedelta(days=days)
        db.commit()
        cids = [c.id for c in cs]

    with SessionLocal() as db:
        assert wf.purge_driver_id_no(db) == 1
    with SessionLocal() as db:
        old, fresh, delivered = (db.get(Container, i) for i in cids)
        assert old.driver_id_no == "" and old.driver_name == "Jan"
        assert fresh.driver_id_no == delivered.driver_id_no == "ABC123456"
        audit = db.query(AuditLog).filter_by(entity_type="containers", entity_id=cids[0],
                                             field="driver_id_no").one()
        assert "RODO" in audit.note
        assert wf.purge_driver_id_no(db) == 0   # idempotencja


def test_purge_driver_id_no_in_avizo_job():
    from app import jobs
    job = next(j for j in jobs.build_jobs() if j.name == "avizo_maintenance")
    assert wf.purge_driver_id_no in job.fns


def test_confirmed_by_forwarder_closes_and_gets_anonymized(client):
    """Awizacja w CONFIRMED_BY_FORWARDER (nikt nie zatwierdził) po realizacji kontenerów:
    zamykana jak inne, a po retencji dane kierowców anonimizowane (RODO)."""
    with SessionLocal() as db:
        c = _container(db, "MNTU0000010", ContainerStatus.ZREALIZOWANY)
        req = _req(db, S.CONFIRMED_BY_FORWARDER, c)
        db.commit()
        req_id, cid = req.id, c.id
    with SessionLocal() as db:
        assert wf.run_maintenance(db)["closed"] == 1
    with SessionLocal() as db:
        req = db.get(AvizoRequest, req_id)
        assert req.status == S.CLOSED
        req.closed_at = utcnow() - datetime.timedelta(days=91)
        db.commit()
    with SessionLocal() as db:
        wf.run_maintenance(db)
    with SessionLocal() as db:
        assert db.get(Container, cid).driver_name == ""
