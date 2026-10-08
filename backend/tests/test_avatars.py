"""Awatar użytkownika: upload/usuń, walidacja, widoczność wg can_see_watcher."""
from app.database import SessionLocal
from app.models import Role, User
from app.security import hash_password
from tests.conftest import login

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
WEBP = b"RIFF" + b"\x00" * 4 + b"WEBP" + b"\x00" * 32
HEIC = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 32


def _company_id(client, headers, code="ACME"):
    return next(c["id"] for c in client.get("/api/companies", headers=headers).json()
                if c["code"] == code)


def _user(login_name, role, company_id):
    with SessionLocal() as db:
        u = User(login=login_name, hashed_password=hash_password("pass12345"), role=role,
                 company_id=company_id, view_all_companies=False, email="")
        db.add(u)
        db.commit()
        return u.id


def test_upload_get_delete_own_avatar(client):
    h = login(client)
    r = client.post("/api/me/avatar", headers=h, files={"file": ("a.png", PNG, "image/png")})
    assert r.status_code == 201, r.text
    assert r.json() == {"has_avatar": True}
    me = client.get("/api/auth/me", headers=h).json()
    assert me["has_avatar"] is True
    got = client.get(f"/api/users/{me['id']}/avatar", headers=h)
    assert got.status_code == 200 and got.content.startswith(b"\x89PNG")
    # I1: no-cache (nie max-age) — przeglądarka rewaliduje przy każdym GET, ETag daje 304
    assert "no-cache" in got.headers["cache-control"]
    assert got.headers.get("etag")
    assert client.delete("/api/me/avatar", headers=h).json() == {"has_avatar": False}
    assert client.get(f"/api/users/{me['id']}/avatar", headers=h).status_code == 404


def test_rejects_non_image_and_too_big(client):
    h = login(client)
    r = client.post("/api/me/avatar", headers=h, files={"file": ("a.txt", b"hello", "text/plain")})
    assert r.status_code == 422
    big = PNG + b"\x00" * (2 * 1024 * 1024)
    r = client.post("/api/me/avatar", headers=h, files={"file": ("b.png", big, "image/png")})
    assert r.status_code == 413


def test_webp_upload_served_with_correct_content_type(client):
    h = login(client)
    r = client.post("/api/me/avatar", headers=h, files={"file": ("a.webp", WEBP, "image/webp")})
    assert r.status_code == 201, r.text
    me = client.get("/api/auth/me", headers=h).json()
    got = client.get(f"/api/users/{me['id']}/avatar", headers=h)
    assert got.status_code == 200
    assert got.headers["content-type"].startswith("image/webp")


def test_heic_upload_rejected(client):
    h = login(client)
    r = client.post("/api/me/avatar", headers=h, files={"file": ("a.heic", HEIC, "image/heic")})
    assert r.status_code == 422


def test_avatar_visibility_follows_watcher_rule(client):
    admin = login(client)
    acme = _company_id(client, admin)
    borealis = _company_id(client, admin, "BOREALIS")
    _user("logz", Role.logistics, acme)
    _user("logt", Role.logistics, borealis)
    _user("magz", Role.warehouse, acme)
    lz = login(client, "logz", "pass12345")
    lt_id = client.get("/api/auth/me", headers=login(client, "logt", "pass12345")).json()["id"]
    lt = login(client, "logt", "pass12345")
    client.post("/api/me/avatar", headers=lt, files={"file": ("a.png", PNG, "image/png")})

    # ta sama spółka / admin z widokiem wszystkich — widzi; inna spółka — nie
    assert client.get(f"/api/users/{lt_id}/avatar", headers=admin).status_code == 200
    assert client.get(f"/api/users/{lt_id}/avatar", headers=lz).status_code == 404
    # rola zewnętrzna nie widzi cudzych awatarów
    mz = login(client, "magz", "pass12345")
    assert client.get(f"/api/users/{lt_id}/avatar", headers=mz).status_code == 404
