"""Audyt 2026-09-23: reset hasła przez admina (PATCH password / reset-invite) musi
unieważnić sesje konta — stary access token i refresh tokeny przestają działać."""
from sqlalchemy import select

from app.database import SessionLocal
from app.models import RefreshToken
from app.routers.avatars import avatars_dir
from tests.conftest import login

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _user_session(client, admin_headers, name):
    r = client.post("/api/users", headers=admin_headers, json={
        "login": name, "email": f"{name}@example.com", "password": "pass12345",
        "role": "logistics", "view_all_companies": True})
    assert r.status_code == 201, r.text
    hdr = login(client, name, "pass12345")
    assert client.get("/api/auth/me", headers=hdr).status_code == 200
    return r.json()["id"], hdr


def _active_refresh_tokens(user_id):
    with SessionLocal() as db:
        return db.scalars(select(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))).all()


def test_admin_password_patch_invalidates_sessions(client, admin_headers):
    uid, hdr = _user_session(client, admin_headers, "przejety1")
    assert _active_refresh_tokens(uid)
    r = client.patch(f"/api/users/{uid}", headers=admin_headers,
                     json={"password": "NoweHaslo123"})
    assert r.status_code == 200, r.text
    assert client.get("/api/auth/me", headers=hdr).status_code == 401
    assert not _active_refresh_tokens(uid)


def test_reset_invite_invalidates_sessions(client, admin_headers):
    uid, hdr = _user_session(client, admin_headers, "przejety2")
    r = client.post(f"/api/users/{uid}/reset-invite", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert client.get("/api/auth/me", headers=hdr).status_code == 401
    assert not _active_refresh_tokens(uid)


def test_delete_user_unlinks_avatar_file(client, admin_headers):
    """M5: usunięcie konta z awatarem sprząta plik, nie tylko wiersz w DB."""
    uid, hdr = _user_session(client, admin_headers, "przejety3")
    client.post("/api/me/avatar", headers=hdr, files={"file": ("a.png", PNG, "image/png")})
    with SessionLocal() as db:
        from app.models import User
        avatar = db.get(User, uid).avatar
    assert avatar
    path = avatars_dir() / avatar
    assert path.is_file()

    r = client.delete(f"/api/users/{uid}", headers=admin_headers)
    assert r.status_code == 204, r.text
    assert not path.exists()
