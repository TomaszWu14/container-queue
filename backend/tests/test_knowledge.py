"""Moduł Wiedza (W16): CRUD pinezek, głosowanie 1/user, ack raz, notify per rola."""
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Notification, Role, User
from app.security import hash_password

from .conftest import login


def make_user(client, login_name, role: Role) -> None:
    with SessionLocal() as db:
        db.add(User(login=login_name, hashed_password=hash_password("haslo1234"),
                    role=role, email=""))
        db.commit()


def test_notes_crud_and_permissions(client, admin_headers):
    # admin tworzy pinezkę
    r = client.post("/api/knowledge/notes", headers=admin_headers, json={
        "scope_type": "screen", "scope_key": "kolejka",
        "title": "Jak czytać band pilności", "body": "Opis...",
        "url": "https://youtube.com/watch?v=abc"})
    assert r.status_code == 201, r.text
    note = r.json()
    assert note["created_by_name"]

    # zły scope_type → 422
    r = client.post("/api/knowledge/notes", headers=admin_headers, json={
        "scope_type": "planeta", "scope_key": "x", "title": "t"})
    assert r.status_code == 422

    # magazyn widzi, ale nie edytuje
    make_user(client, "wh-user", Role.warehouse)
    wh = login(client, "wh-user", "haslo1234")
    r = client.get("/api/knowledge/notes?scope_type=screen&scope_key=kolejka", headers=wh)
    assert r.status_code == 200
    assert len(r.json()) == 1
    r = client.post("/api/knowledge/notes", headers=wh, json={
        "scope_type": "screen", "scope_key": "kolejka", "title": "nie"})
    assert r.status_code == 403

    # edycja + soft delete
    r = client.patch(f"/api/knowledge/notes/{note['id']}", headers=admin_headers, json={
        "scope_type": "screen", "scope_key": "kolejka",
        "title": "Nowy tytuł", "body": "", "url": ""})
    assert r.status_code == 200 and r.json()["title"] == "Nowy tytuł"
    assert client.delete(f"/api/knowledge/notes/{note['id']}",
                         headers=admin_headers).status_code == 204
    assert client.get("/api/knowledge/notes?scope_type=screen&scope_key=kolejka",
                      headers=wh).json() == []


def test_topic_vote_once_per_user(client, admin_headers):
    r = client.post("/api/knowledge/topics", headers=admin_headers, json={
        "scope_type": "screen", "scope_key": "odprawa", "title": "Omówić SAD"})
    assert r.status_code == 201
    topic = r.json()
    assert topic["votes"] == 1 and topic["my_vote"] is True  # autor głosuje z automatu

    # drugi głos tego samego usera nie dubluje
    r = client.post(f"/api/knowledge/topics/{topic['id']}/vote", headers=admin_headers)
    assert r.status_code == 200 and r.json()["votes"] == 1

    # inny user dokłada głos
    make_user(client, "log-user", Role.logistics)
    lg = login(client, "log-user", "haslo1234")
    r = client.post(f"/api/knowledge/topics/{topic['id']}/vote", headers=lg)
    assert r.json()["votes"] == 2

    # ranking wg głosów
    client.post("/api/knowledge/topics", headers=lg, json={"title": "Mniej ważny"})
    ranking = client.get("/api/knowledge/topics", headers=lg).json()
    assert ranking[0]["id"] == topic["id"] and ranking[0]["votes"] == 2

    # status zmienia tylko admin/logistics; zły status → 422
    make_user(client, "wh-user2", Role.warehouse)
    wh = login(client, "wh-user2", "haslo1234")
    assert client.patch(f"/api/knowledge/topics/{topic['id']}/status?new_status=zaplanowany",
                        headers=wh).status_code == 403
    assert client.patch(f"/api/knowledge/topics/{topic['id']}/status?new_status=zly",
                        headers=admin_headers).status_code == 422
    r = client.patch(f"/api/knowledge/topics/{topic['id']}/status?new_status=zaplanowany",
                     headers=admin_headers)
    assert r.json()["status"] == "zaplanowany"


def test_bulletin_notify_roles_and_ack_once(client, admin_headers):
    make_user(client, "wh-b", Role.warehouse)
    make_user(client, "fw-b", Role.forwarder)

    r = client.post("/api/knowledge/bulletins", headers=admin_headers, json={
        "title": "Nowa procedura bramy", "body": "Od jutra...",
        "roles": ["warehouse"]})
    assert r.status_code == 201, r.text
    bid = r.json()["id"]

    # notify trafiło do magazynu, nie do spedytora
    with SessionLocal() as db:
        wh_id = db.scalar(select(User.id).where(User.login == "wh-b"))
        fw_id = db.scalar(select(User.id).where(User.login == "fw-b"))
        kinds = {n.user_id for n in db.scalars(
            select(Notification).where(Notification.kind == "bulletin"))}
    assert wh_id in kinds and fw_id not in kinds

    # unread: magazyn widzi, spedytor nie
    wh = login(client, "wh-b", "haslo1234")
    fw = login(client, "fw-b", "haslo1234")
    assert [b["id"] for b in client.get("/api/knowledge/bulletins/unread",
                                        headers=wh).json()] == [bid]
    assert client.get("/api/knowledge/bulletins/unread", headers=fw).json() == []

    # ack idempotentny — read_at z pierwszego potwierdzenia zostaje
    assert client.post(f"/api/knowledge/bulletins/{bid}/ack", headers=wh).status_code == 200
    acks1 = client.get(f"/api/knowledge/bulletins/{bid}/acks", headers=admin_headers).json()
    first = next(a for a in acks1 if a["login"] == "wh-b")["read_at"]
    assert first is not None
    client.post(f"/api/knowledge/bulletins/{bid}/ack", headers=wh)
    acks2 = client.get(f"/api/knowledge/bulletins/{bid}/acks", headers=admin_headers).json()
    assert next(a for a in acks2 if a["login"] == "wh-b")["read_at"] == first
    assert client.get("/api/knowledge/bulletins/unread", headers=wh).json() == []

    # widok kto-przeczytał tylko dla edytorów; zła rola przy tworzeniu → 422
    assert client.get(f"/api/knowledge/bulletins/{bid}/acks", headers=wh).status_code == 403
    assert client.post("/api/knowledge/bulletins", headers=admin_headers, json={
        "title": "x", "roles": ["kosmita"]}).status_code == 422


def test_acl001_partners_without_knowledge_base_and_edit_only_author(client, admin_headers):
    """ACL-001 (decyzja 2026-09-28, wariant a): baza wiedzy wspólna dla grupy, bez partnerów
    zewnętrznych (spedytor, agencja celna); pinezkę edytuje/usuwa autor albo admin.
    Komunikaty (bulletins) adresowane do roli zostają dostępne."""
    note = client.post("/api/knowledge/notes", headers=admin_headers, json={
        "scope_type": "screen", "scope_key": "kolejka", "title": "Adminowa", "body": "x"}).json()
    for name, role in (("acl-fwd", Role.forwarder), ("acl-cus", Role.customs)):
        make_user(client, name, role)
        h = login(client, name, "haslo1234")
        assert client.get("/api/knowledge/notes", headers=h).status_code == 403
        assert client.get("/api/knowledge/topics", headers=h).status_code == 403
        assert client.get("/api/knowledge/bulletins/unread", headers=h).status_code == 200
    make_user(client, "acl-log", Role.logistics)
    log = login(client, "acl-log", "haslo1234")
    assert client.get("/api/knowledge/notes", headers=log).status_code == 200
    body = {"scope_type": "screen", "scope_key": "kolejka", "title": "Zmiana", "body": "y"}
    assert client.patch(f"/api/knowledge/notes/{note['id']}", headers=log, json=body).status_code == 403
    assert client.delete(f"/api/knowledge/notes/{note['id']}", headers=log).status_code == 403
    own = client.post("/api/knowledge/notes", headers=log, json=body).json()
    assert client.patch(f"/api/knowledge/notes/{own['id']}", headers=log, json=body).status_code == 200
    assert client.delete(f"/api/knowledge/notes/{own['id']}", headers=admin_headers).status_code == 204
