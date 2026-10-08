"""Awizacja dwuetapowa — panel: izolacja spółek, zatwierdź (1 mail etapu 2), odrzuć
(1 mail etapu 1 z nowym tokenem), unieważnij / wyślij ponownie / anuluj."""
from app.database import SessionLocal
from app.models import AvizoRequest, AvizoStatus, Company
from tests.test_avizo_public import make_request, outbox, stage1  # noqa: F401 — fixture
from tests.test_isolation import _make_scoped_user


def _company(code):
    with SessionLocal() as db:
        return db.query(Company).filter_by(code=code).one().id


def test_scoping_other_company_cannot_list_or_act(client, admin_headers, outbox):
    req_a, raw_a, ids_a = make_request("BOREALIS")
    req_b, _, _ = make_request("COBALT")
    headers_a = _make_scoped_user(client, admin_headers, "log.a", _company("BOREALIS"))
    listed = {r["id"] for r in client.get("/api/avizo-requests", headers=headers_a).json()}
    assert req_a in listed and req_b not in listed
    assert client.get(f"/api/avizo-requests/{req_b}", headers=headers_a).status_code in (403, 404)
    for action in ("approve", "revoke", "cancel", "resend?stage=1"):
        r = client.post(f"/api/avizo-requests/{req_b}/{action}", headers=headers_a)
        assert r.status_code in (403, 404), (action, r.status_code)
    r = client.post(f"/api/avizo-requests/{req_b}/reject", headers=headers_a,
                    json={"comment": "nie moje"})
    assert r.status_code in (403, 404)
    # własna spółka — działa; filtr statusu
    assert client.get(f"/api/avizo-requests/{req_a}", headers=headers_a).status_code == 200
    only = client.get("/api/avizo-requests?status=CONFIRMED_BY_FORWARDER",
                      headers=headers_a).json()
    assert only == []


def test_approve_sends_exactly_one_stage2_mail(client, admin_headers, outbox):
    req_id, raw, ids = make_request()
    # przed odpowiedzią spedycji zatwierdzić się nie da
    assert client.post(f"/api/avizo-requests/{req_id}/approve",
                       headers=admin_headers).status_code == 409
    assert client.post(f"/api/avizo/{raw}", json=stage1(ids)).status_code == 200
    outbox.clear()
    r = client.post(f"/api/avizo-requests/{req_id}/approve", headers=admin_headers)
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["status"] == "SENT_STAGE2"
    assert len(outbox) == 1 and "/avizo/driver/" in outbox[0].text
    assert [(m["kind"], m["status"]) for m in detail["mails"]] == [("stage1", "sent"),
                                                                   ("stage2", "sent")]
    assert all("token_hash" not in t for t in detail["tokens"])
    assert {t["stage"] for t in detail["tokens"]} == {1, 2}
    # drugie zatwierdzenie → 409, bez kolejnego maila
    assert client.post(f"/api/avizo-requests/{req_id}/approve",
                       headers=admin_headers).status_code == 409
    assert len(outbox) == 1


def test_reject_sends_one_stage1_mail_with_new_token(client, admin_headers, outbox):
    req_id, raw, ids = make_request()
    assert client.post(f"/api/avizo/{raw}", json=stage1(ids)).status_code == 200
    outbox.clear()
    r = client.post(f"/api/avizo-requests/{req_id}/reject", headers=admin_headers,
                    json={"comment": "Termin za wcześnie, prosimy o piątek"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "SENT_STAGE1"
    assert len(outbox) == 1
    mail = outbox[0]
    assert "Termin za wcześnie" in mail.html
    new_raw = mail.text.split("/avizo/")[1].split()[0]
    assert new_raw != raw
    assert client.get(f"/api/avizo/{raw}").status_code == 409        # stary: zużyty
    fresh = client.get(f"/api/avizo/{new_raw}")
    assert fresh.status_code == 200 and fresh.json()["reject_comment"].startswith("Termin")
    assert client.post(f"/api/avizo/{new_raw}", json=stage1(ids)).status_code == 200


def test_revoke_resend_cancel(client, admin_headers, outbox):
    req_id, raw, ids = make_request()
    assert client.post(f"/api/avizo-requests/{req_id}/revoke",
                       headers=admin_headers).status_code == 200
    assert client.get(f"/api/avizo/{raw}").status_code == 410
    # etap 2 nie może zostać wysłany przed zatwierdzeniem
    assert client.post(f"/api/avizo-requests/{req_id}/resend?stage=2",
                       headers=admin_headers).status_code == 409
    outbox.clear()
    assert client.post(f"/api/avizo-requests/{req_id}/resend?stage=1",
                       headers=admin_headers).status_code == 200
    new_raw = outbox[0].text.split("/avizo/")[1].split()[0]
    assert client.get(f"/api/avizo/{new_raw}").status_code == 200
    r = client.post(f"/api/avizo-requests/{req_id}/cancel", headers=admin_headers)
    assert r.status_code == 200 and r.json()["status"] == "CANCELLED"
    assert client.get(f"/api/avizo/{new_raw}").status_code == 410
    with SessionLocal() as db:
        assert db.get(AvizoRequest, req_id).status == AvizoStatus.CANCELLED


def test_missing_forwarder_email_logged_as_failed(client, admin_headers, outbox):
    req_id, _, _ = make_request()
    with SessionLocal() as db:
        db.get(AvizoRequest, req_id).forwarder.email = ""
        db.commit()
    client.post(f"/api/avizo-requests/{req_id}/resend?stage=1", headers=admin_headers)
    mails = client.get(f"/api/avizo-requests/{req_id}", headers=admin_headers).json()["mails"]
    assert mails[-1]["status"] == "failed" and "adresu" in mails[-1]["error"]


def test_approve_refused_when_every_container_is_a_problem(client, admin_headers, outbox):
    req_id, raw, ids = make_request()
    body = {"items": [{"container_id": i, "decision": "problem", "comment": "brak kierowcy"}
                      for i in ids]}
    assert client.post(f"/api/avizo/{raw}", json=body).status_code == 200
    outbox.clear()
    assert client.post(f"/api/avizo-requests/{req_id}/approve",
                       headers=admin_headers).status_code == 409
    assert outbox == []
    detail = client.get(f"/api/avizo-requests/{req_id}", headers=admin_headers).json()
    assert detail["status"] == "CONFIRMED_BY_FORWARDER"
    assert detail["items"][0]["answer"]["decision"] == "problem"


def test_concurrent_approve_second_gets_409_one_token_one_mail(client, admin_headers, outbox):
    """Wyścig: drugie żądanie przeczytało CONFIRMED_BY_FORWARDER, zanim pierwsze zatwierdziło —
    bez warunkowego UPDATE wydawało drugi token etapu 2 i drugi mail (pierwszy link 410)."""
    import pytest
    from fastapi import HTTPException

    from app import avizo_workflow as wf
    from app.models import AvizoFormToken, User
    req_id, raw, ids = make_request()
    assert client.post(f"/api/avizo/{raw}", json=stage1(ids)).status_code == 200
    outbox.clear()
    with SessionLocal() as stale:
        req = stale.get(AvizoRequest, req_id)
        assert req.status == AvizoStatus.CONFIRMED_BY_FORWARDER   # odczyt przed wyścigiem
        admin = stale.query(User).filter_by(login="admin").one()
        # w międzyczasie pierwsze żądanie zatwierdza (sesja `stale` trzyma stary status)
        assert client.post(f"/api/avizo-requests/{req_id}/approve",
                           headers=admin_headers).status_code == 200
        with pytest.raises(HTTPException) as exc:
            wf.approve(stale, req, admin, "http://test")
        assert exc.value.status_code == 409
        stale.rollback()
    with SessionLocal() as db:
        assert db.query(AvizoFormToken).filter_by(request_id=req_id, stage=2).count() == 1
    assert len(outbox) == 1
