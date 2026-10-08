"""Awizacja dwuetapowa — endpointy publiczne: etap 1/2, jednorazowość, limit, JSON/Origin,
nagłówki no-referrer/noindex, maskowanie tokenu w logach i Sentry."""
from app.models import today_pl
import datetime
import logging

import pytest

from app import avizo_workflow as wf
from app import mailer, notifications
from app.database import SessionLocal
from app.main import AvizoTokenLogFilter, _sentry_before_send
from app.models import (AuditLog, AvizoFormToken, AvizoRequest, AvizoStatus, Company, Container,
                        Forwarder, User)

DAY = today_pl() + datetime.timedelta(days=10)


@pytest.fixture()
def outbox(monkeypatch):
    monkeypatch.setattr(notifications, "_submit", lambda fn, *a, **kw: fn(*a, **kw))
    monkeypatch.setattr(mailer.settings, "mail_backend", "console")
    mailer._console.outbox.clear()
    return mailer._console.outbox


def make_request(company_code="BOREALIS", n=2, email="fw@example.com"):
    """Zlecenie wysłane serwisem (jak z kolejki) — zwraca (request_id, surowy token etapu 1, ids).
    Wymaga fixture `outbox` (token czytamy z wysłanego maila, jak spedycja)."""
    with SessionLocal() as db:
        co = db.query(Company).filter_by(code=company_code).one()
        fw = db.query(Forwarder).filter_by(name="SPEDALFA").one()
        fw.email = email
        admin = db.query(User).filter_by(login="admin").one()
        conts = [Container(container_no=f"PUBU{company_code[:2]}{i:05d}", company_id=co.id,
                           notify_date=DAY, vessel="MV DEMO ATLAS") for i in range(n)]
        db.add_all(conts)
        db.flush()
        req = wf.create_and_send(db, company_id=co.id, forwarder=fw, containers=conts,
                                 note="", user=admin, base="http://test")
        raw = mailer._console.outbox[-1].text.split("/avizo/")[1].split()[0]
        return req.id, raw, [c.id for c in conts]


def stage1(ids, **kw):
    return {"items": [{"container_id": i, "decision": "confirmed", **kw} for i in ids]}


def test_stage1_submit_single_use_and_no_driver_fields(client, outbox):
    req_id, raw, ids = make_request()
    assert len(outbox) == 1 and "/avizo/" + raw in outbox[0].html
    form = client.get(f"/api/avizo/{raw}")
    assert form.status_code == 200
    body = form.json()
    assert body["stage"] == 1 and body["status"] == "SENT_STAGE1"
    assert {i["container_id"] for i in body["items"]} == set(ids)
    assert "supplier" not in body["items"][0] and "driver_name" not in body["items"][0]

    # dane kierowcy w etapie 1 są odrzucane (422), niepełna lista kontenerów też
    bad = stage1(ids)
    bad["items"][0]["driver_name"] = "Jan"
    assert client.post(f"/api/avizo/{raw}", json=bad).status_code == 422
    assert client.post(f"/api/avizo/{raw}", json=stage1(ids[:1])).status_code == 422
    problem = {"container_id": ids[1], "decision": "problem", "comment": ""}
    assert client.post(f"/api/avizo/{raw}", json={"items": [
        {"container_id": ids[0], "decision": "confirmed"}, problem]}).status_code == 422

    ok = client.post(f"/api/avizo/{raw}", json=stage1(ids))
    assert ok.status_code == 200, ok.text
    again = client.post(f"/api/avizo/{raw}", json=stage1(ids))
    assert again.status_code == 409 and again.json() == {"detail": {
        "code": "already_submitted", "message": "Formularz już wysłany."}}
    assert client.get(f"/api/avizo/{raw}").status_code == 409
    with SessionLocal() as db:
        req = db.get(AvizoRequest, req_id)
        assert req.status == AvizoStatus.CONFIRMED_BY_FORWARDER
        # termin trafi do planu dopiero po zatwierdzeniu
        assert all(db.get(Container, i).planning_status.value == "PROPOZYCJA" for i in ids)


def test_stage1_token_does_not_open_stage2_and_revoked_is_gone(client, outbox):
    req_id, raw, ids = make_request()
    assert client.get(f"/api/avizo/driver/{raw}").status_code == 404
    with SessionLocal() as db:
        wf.revoke_tokens(db, db.get(AvizoRequest, req_id))
        db.commit()
    assert client.get(f"/api/avizo/{raw}").status_code == 410
    assert client.post(f"/api/avizo/{raw}", json=stage1(ids)).status_code == 410


def test_full_flow_stage2_saves_driver_fields(client, outbox, admin_headers):
    req_id, raw, ids = make_request()
    assert client.post(f"/api/avizo/{raw}", json=stage1(ids)).status_code == 200
    assert client.post(f"/api/avizo-requests/{req_id}/approve",
                       headers=admin_headers).status_code == 200
    assert len(outbox) == 2
    link = outbox[1].text.split("/avizo/driver/")[1].split()[0]
    assert client.get(f"/api/avizo/{link}").status_code == 404   # token etapu 2 ≠ etap 1
    form = client.get(f"/api/avizo/driver/{link}").json()
    assert form["stage"] == 2 and len(form["items"]) == 2

    def drivers(phone="600 100 200", truck="WX 12345"):
        return {"items": [{"container_id": i, "driver_name": "Jan Kowalski", "driver_phone": phone,
                           "truck_no": truck, "trailer_no": "wx-9876a"} for i in ids]}

    assert client.post(f"/api/avizo/driver/{link}", json=drivers(phone="abc")).status_code == 422
    assert client.post(f"/api/avizo/driver/{link}", json=drivers(truck="!")).status_code == 422
    ok = client.post(f"/api/avizo/driver/{link}", json=drivers())
    assert ok.status_code == 200, ok.text
    assert client.post(f"/api/avizo/driver/{link}", json=drivers()).status_code == 409
    with SessionLocal() as db:
        c = db.get(Container, ids[0])
        assert (c.driver_name, c.driver_phone, c.truck_no, c.trailer_no) == (
            "Jan Kowalski", "+48600100200", "WX12345", "WX9876A")
        assert db.get(AvizoRequest, req_id).status == AvizoStatus.DRIVERS_SUBMITTED
        phone_audit = db.query(AuditLog).filter_by(entity_type="containers", entity_id=ids[0],
                                                   field="driver_phone").one()
        assert phone_audit.new_value == "•••"   # RODO: audyt bez wartości


def test_public_rate_limit_429(client, outbox):
    _, raw, _ = make_request()
    codes = [client.get(f"/api/avizo/{raw}").status_code for _ in range(31)]
    assert codes[:30] == [200] * 30 and codes[30] == 429
    last = client.get(f"/api/avizo/{raw}")
    assert last.status_code == 429 and int(last.headers["Retry-After"]) > 0


def test_post_requires_json_and_same_origin(client, outbox):
    _, raw, ids = make_request()
    form = client.post(f"/api/avizo/{raw}", data={"items": "x"})
    assert form.status_code == 415
    foreign = client.post(f"/api/avizo/{raw}", json=stage1(ids),
                          headers={"Origin": "https://evil.example"})
    assert foreign.status_code == 403
    ref = client.post(f"/api/avizo/{raw}", json=stage1(ids),
                      headers={"Referer": "https://evil.example/x"})
    assert ref.status_code == 403
    same = client.post(f"/api/avizo/{raw}", json=stage1(ids),
                       headers={"Origin": "http://testserver"})
    assert same.status_code == 200


def test_privacy_headers(client, outbox):
    _, raw, _ = make_request()
    r = client.get(f"/api/avizo/{raw}")
    assert r.headers["Referrer-Policy"] == "no-referrer"
    assert r.headers["X-Robots-Tag"] == "noindex, nofollow"
    other = client.get("/api/health")
    assert other.headers["Referrer-Policy"] != "no-referrer"


def test_token_scrubbed_from_logs_and_sentry():
    raw = "Zx9_" + "a" * 39
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0,
                               '%s - "%s %s HTTP/%s" %d',
                               ("1.2.3.4", "GET", f"/api/avizo/driver/{raw}", "1.1", 200), None)
    AvizoTokenLogFilter().filter(record)
    assert raw not in record.getMessage() and "/api/avizo/driver/[token]" in record.getMessage()
    app_record = logging.LogRecord("app", logging.WARNING, "", 0, f"bad link /avizo/{raw}", None, None)
    AvizoTokenLogFilter().filter(app_record)
    assert raw not in app_record.getMessage()

    event = {"request": {"url": f"https://app.example/api/avizo/{raw}", "headers": {}},
             "transaction": f"/api/avizo/{raw}/slots",
             "exception": {"values": [{"value": "boom"}]}}
    out = _sentry_before_send(event, None)
    assert raw not in str(out)
    assert out["request"]["url"] == "https://app.example/api/avizo/[token]"


def test_no_plaintext_token_after_send(client, outbox):
    req_id, raw, _ = make_request()
    with SessionLocal() as db:
        assert db.query(AvizoFormToken).filter_by(request_id=req_id).one().token_hash \
            == wf.hash_token(raw)
        assert db.get(AvizoRequest, req_id).token != raw
