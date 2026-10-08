"""Awizacja dwuetapowa — tokeny: jednorazowe, per etap, wygasają, unieważnialne, tylko hash w bazie."""
import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app import avizo_workflow as wf
from app.database import SessionLocal
from app.models import AvizoFormToken, AvizoRequest, AvizoStatus, Company, Forwarder, utcnow


def _req(db) -> AvizoRequest:
    req = AvizoRequest(token=wf.hash_token(f"legacy-{utcnow().timestamp()}"),
                       company_id=db.query(Company).first().id,
                       forwarder_id=db.query(Forwarder).first().id,
                       status=AvizoStatus.SENT_STAGE1)
    db.add(req)
    db.flush()
    return req


def _code(fn) -> int:
    with pytest.raises(HTTPException) as exc:
        fn()
    return exc.value.status_code


def test_token_roundtrip_stage_and_single_use(client):
    with SessionLocal() as db:
        req = _req(db)
        raw = wf.issue_token(db, req, 1)
        assert wf.lookup_token(db, raw, 1).request_id == req.id
        # token etapu 1 nie otwiera etapu 2
        assert _code(lambda: wf.lookup_token(db, raw, 2)) == 404
        assert _code(lambda: wf.lookup_token(db, "nie-ma-takiego", 1)) == 404
        tok = wf.lookup_token(db, raw, 1)
        tok.used_at = utcnow()
        db.flush()
        assert _code(lambda: wf.lookup_token(db, raw, 1)) == 409
        assert wf.lookup_token(db, raw, 1, allow_used=True).id == tok.id


def test_claim_token_is_atomic_against_concurrent_submit(client):
    """Wyścig: token wczytany jako nieużyty, ale równoległe żądanie zdążyło go zużyć
    i zatwierdzić — warunkowy UPDATE ... WHERE used_at IS NULL daje 409, nie drugi zapis."""
    with SessionLocal() as db:
        req = _req(db)
        raw = wf.issue_token(db, req, 1)
        db.commit()
    with SessionLocal() as a:
        tok = wf.lookup_token(a, raw, 1)          # w pamięci: used_at = None
        a.commit()                                 # zwolnij transakcję odczytu (SQLite)
        with SessionLocal() as b:                  # „drugie żądanie” wygrywa wyścig
            wf.claim_token(b, wf.lookup_token(b, raw, 1))
            b.commit()
        assert _code(lambda: wf.claim_token(a, tok)) == 409
    with SessionLocal() as c:                      # zwycięzca zużył token raz
        assert _code(lambda: wf.lookup_token(c, raw, 1)) == 409


def test_token_expired_and_revoked_are_gone(client):
    with SessionLocal() as db:
        req = _req(db)
        raw = wf.issue_token(db, req, 1)
        tok = wf.lookup_token(db, raw, 1)
        tok.expires_at = utcnow() - datetime.timedelta(seconds=1)
        db.flush()
        assert _code(lambda: wf.lookup_token(db, raw, 1)) == 410

        raw2 = wf.issue_token(db, req, 1)
        raw3 = wf.issue_token(db, req, 1)   # nowy token unieważnia poprzedni tego etapu
        assert _code(lambda: wf.lookup_token(db, raw2, 1)) == 410
        assert wf.lookup_token(db, raw3, 1)
        assert wf.revoke_tokens(db, req) == 1
        assert _code(lambda: wf.lookup_token(db, raw3, 1)) == 410


def test_token_on_cancelled_request_is_gone(client):
    with SessionLocal() as db:
        req = _req(db)
        raw = wf.issue_token(db, req, 1)
        wf.transition(db, req, AvizoStatus.CANCELLED)
        assert _code(lambda: wf.lookup_token(db, raw, 1)) == 410


def test_expiry_from_settings(client, monkeypatch):
    monkeypatch.setattr(wf.settings, "avizo_stage1_days", 7)
    monkeypatch.setattr(wf.settings, "avizo_stage2_days", 5)
    with SessionLocal() as db:
        req = _req(db)
        t1 = wf.lookup_token(db, wf.issue_token(db, req, 1), 1)
        t2 = wf.lookup_token(db, wf.issue_token(db, req, 2), 2)
        assert (t1.expires_at - utcnow()).days == 6   # 7 dni minus sekundy
        assert (t2.expires_at - utcnow()).days == 4


def test_no_plaintext_token_in_database(client):
    with SessionLocal() as db:
        raws = [wf.issue_token(db, _req(db), 1) for _ in range(3)]
        db.commit()
        dump = " ".join(str(v) for table in ("avizo_form_tokens", "avizo_requests")
                        for row in db.execute(text(f"SELECT * FROM {table}")) for v in row)
    for raw in raws:
        assert raw not in dump
        assert wf.hash_token(raw) in dump


def test_legacy_request_link_is_adopted(client):
    raw = "legacy" * 8
    with SessionLocal() as db:
        req = _req(db)
        req.token = wf.hash_token(raw)
        req.expires_at = utcnow() + datetime.timedelta(days=1)
        db.flush()
        tok = wf.lookup_token(db, raw, 1)
        assert tok.request_id == req.id and tok.stage == 1
        assert db.query(AvizoFormToken).filter_by(request_id=req.id).count() == 1
