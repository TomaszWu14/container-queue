"""Noty eskalacyjne per spółka: logistyk spółki A nie widzi not spółki B, a nota do roli
„forwarder” trafia tylko do spedycji obsługujących kontenery tej spółki. NULL = cała grupa."""
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Container, Notification, User
from tests.conftest import forwarder, login
from tests.test_quotes import _company_id

URL = "/api/knowledge/bulletins"


def _user(client, admin_headers, name, **fields):
    r = client.post("/api/users", headers=admin_headers, json={
        "login": name, "password": "haslo123", "email": f"{name}@example.com", **fields})
    assert r.status_code in (200, 201), r.text
    return login(client, name, "haslo123")


def _notified(name):
    with SessionLocal() as db:
        uid = db.scalar(select(User.id).where(User.login == name))
        return [n.title for n in db.scalars(select(Notification).where(
            Notification.user_id == uid, Notification.kind == "bulletin"))]


def test_bulletins_scoped_to_company(client, admin_headers):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    acme = _company_id(client, admin_headers, "ACME")
    f_a, f_b = forwarder(client, admin_headers, "SPED-A")["id"], forwarder(client, admin_headers, "SPED-B")["id"]
    with SessionLocal() as db:   # SPED-A wozi dla BOREALIS, SPED-B tylko dla ACME
        db.add_all([Container(container_no="MSDU0806613", company_id=borealis, forwarder_id=f_a),
                    Container(container_no="CSQU3054383", company_id=acme, forwarder_id=f_b)])
        db.commit()
    log_a = _user(client, admin_headers, "log.a", role="logistics", company_id=borealis,
                  view_all_companies=False)
    log_b = _user(client, admin_headers, "log.b", role="logistics", company_id=acme,
                  view_all_companies=False)
    fw_a = _user(client, admin_headers, "fw.a", role="forwarder", forwarder_id=f_a)
    fw_b = _user(client, admin_headers, "fw.b", role="forwarder", forwarder_id=f_b)

    # logistyk jednej spółki nie wybierze cudzej spółki — nota zawsze jego spółki
    r = client.post(URL, headers=log_a, json={"title": "Brama BOREALIS", "roles": ["logistics", "forwarder"],
                                              "company_id": acme})
    assert r.status_code == 201, r.text
    note = r.json()
    assert note["company_id"] == borealis

    ids = lambda h: [b["id"] for b in client.get(URL, headers=h).json()]   # noqa: E731
    assert note["id"] in ids(log_a) and note["id"] in ids(admin_headers)
    assert note["id"] not in ids(log_b) and note["id"] not in ids(fw_b)
    assert note["id"] in ids(fw_a)
    assert "Nota: Brama BOREALIS" in _notified("fw.a") and _notified("fw.b") == []
    assert _notified("log.b") == []
    assert client.get(f"{URL}/unread", headers=fw_b).json() == []
    assert client.post(f"{URL}/{note['id']}/ack", headers=fw_b).status_code == 404
    assert client.get(f"{URL}/{note['id']}/acks", headers=log_b).status_code == 404

    # admin bez spółki = cała grupa (jak noty sprzed migracji); admin może też wskazać spółkę
    group = client.post(URL, headers=admin_headers, json={"title": "Dla grupy", "roles": ["logistics"]}).json()
    assert group["company_id"] is None and group["id"] in ids(log_b)
    only_b = client.post(URL, headers=admin_headers,
                         json={"title": "Dla ACME", "roles": ["logistics"], "company_id": acme}).json()
    assert only_b["id"] in ids(log_b) and only_b["id"] not in ids(log_a)
