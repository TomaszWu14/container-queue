"""Audyt ACL-002: słowniki filtrów dziennika zmian (`actors`, `entity_types`) i lista „kto
przeczytał” noty nie mogą ujawniać loginów/nazwisk użytkowników innych spółek."""
from app.models import Role
from tests.test_isolation import _company_id, _container_in, _make_scoped_user


def _user_id(client, admin_headers, login):
    return next(u["id"] for u in client.get("/api/users", headers=admin_headers).json()
                if u["login"] == login)


def test_changes_feed_actors_scoped_to_own_company(client, admin_headers):
    a = _company_id(client, admin_headers, "BOREALIS")
    b = _company_id(client, admin_headers, "COBALT")
    headers_a = _make_scoped_user(client, admin_headers, "logistyk.a", a)
    headers_b = _make_scoped_user(client, admin_headers, "logistyk.b", b)
    cont_a = _container_in(client, admin_headers, a)
    cont_b = _container_in(client, admin_headers, b, no="TCLU5779674")
    # dziś w audycie: zmiana B na kontenerze B i zmiana A na kontenerze A
    assert client.patch(f"/api/containers/{cont_b}", headers=headers_b,
                        json={"notes": "B"}).status_code == 200
    assert client.patch(f"/api/containers/{cont_a}", headers=headers_a,
                        json={"notes": "A"}).status_code == 200
    # wpis spoza kontenerów (konto B zmienia własne ustawienia) — typ encji z cudzego audytu
    client.patch("/api/auth/me/settings", headers=headers_b, json={"watch_only_notifications": True})

    feed = client.get("/api/changes/feed", headers=headers_a).json()
    actor_ids = {actor["id"] for actor in feed["actors"]}
    assert _user_id(client, admin_headers, "logistyk.b") not in actor_ids
    assert _user_id(client, admin_headers, "logistyk.a") in actor_ids
    assert set(feed["entity_types"]) <= {"containers"}
    # konto grupowe (admin) dalej widzi wszystkich
    full = client.get("/api/changes/feed", headers=admin_headers).json()
    assert _user_id(client, admin_headers, "logistyk.b") in {x["id"] for x in full["actors"]}


def test_bulletin_acks_scoped_to_own_company(client, admin_headers):
    a = _company_id(client, admin_headers, "BOREALIS")
    b = _company_id(client, admin_headers, "COBALT")
    headers_a = _make_scoped_user(client, admin_headers, "logistyk.a2", a)
    _make_scoped_user(client, admin_headers, "logistyk.b2", b)
    bid = client.post("/api/knowledge/bulletins", headers=admin_headers, json={
        "title": "Nota", "body": "x", "roles": [Role.logistics.value]}).json()["id"]
    logins = {x["login"] for x in client.get(f"/api/knowledge/bulletins/{bid}/acks",
                                             headers=headers_a).json()}
    assert "logistyk.a2" in logins and "logistyk.b2" not in logins
    everyone = {x["login"] for x in client.get(f"/api/knowledge/bulletins/{bid}/acks",
                                               headers=admin_headers).json()}
    assert {"logistyk.a2", "logistyk.b2"} <= everyone
