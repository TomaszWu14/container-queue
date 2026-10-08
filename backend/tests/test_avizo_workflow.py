"""Awizacja dwuetapowa — maszyna stanów: każde dozwolone przejście przechodzi, reszta → 409."""
import pytest
from fastapi import HTTPException

from app import avizo_workflow as wf
from app.database import SessionLocal
from app.models import AuditLog, AvizoRequest, AvizoStatus, Company, Forwarder

S = AvizoStatus
# sorted: TRANSITIONS trzyma zbiory — kolejność zależy od seeda, a workery xdist muszą zebrać
# identyczną listę testów
ALLOWED = sorted((a, b) for a, targets in wf.TRANSITIONS.items() for b in targets)
FORBIDDEN = [(a, b) for a in S for b in S if b not in wf.TRANSITIONS[a]]


def test_table_covers_every_status_and_happy_path():
    assert set(wf.TRANSITIONS) == set(S)
    path = [S.DRAFT, S.SENT_STAGE1, S.CONFIRMED_BY_FORWARDER, S.REJECTED, S.SENT_STAGE1,
            S.CONFIRMED_BY_FORWARDER, S.APPROVED_BY_US, S.SENT_STAGE2,
            S.DRIVERS_SUBMITTED, S.CLOSED]
    for a, b in zip(path, path[1:]):
        assert b in wf.TRANSITIONS[a], (a, b)
    assert wf.TRANSITIONS[S.CLOSED] == wf.TRANSITIONS[S.CANCELLED] == set()


def _check(start, target):
    with SessionLocal() as db:
        req = AvizoRequest(token=f"t-{start.value}-{target.value}",
                           company_id=db.query(Company).first().id,
                           forwarder_id=db.query(Forwarder).first().id, status=start)
        db.add(req)
        db.flush()
        try:
            wf.transition(db, req, target, note="test")
            ok = True
        except HTTPException as exc:
            assert exc.status_code == 409
            ok = False
        db.flush()   # SessionLocal ma autoflush=False
        audit = [(a.old_value, a.new_value) for a in db.query(AuditLog).filter_by(
            entity_type="avizo_requests", entity_id=req.id, field="status")]
        db.rollback()
        return ok, audit


@pytest.mark.parametrize("start,target", ALLOWED)
def test_allowed_transition(client, start, target):
    ok, audit = _check(start, target)
    assert ok
    assert audit == [(start.value, target.value)]


def test_forbidden_transitions(client):
    for start, target in FORBIDDEN:
        ok, audit = _check(start, target)
        assert not ok, (start, target)
        assert audit == []
