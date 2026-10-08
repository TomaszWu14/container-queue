"""Okno łaski dla wyścigu rotacji refresh tokenów (dwie karty odświeżają naraz).

Ponowne użycie ZROTOWANEGO tokenu w oknie łaski to nie kradzież — wydajemy sam access
token zamiast unieważniać wszystkie sesje użytkownika ("Sesja wygasła" na prodzie); nowego
refresh tokenu z zużytego nie wydajemy (SEC-010). Okno domyślnie 10 s.
Po oknie łaski zachowanie bez zmian: rodzina odwołana + session_version podbite.
"""
import datetime

from app.database import SessionLocal
from app.models import RefreshToken


def _login(client):
    return client.post("/api/auth/login",
                       data={"username": "admin", "password": "admin123"}).json()


def test_rotation_race_within_grace_keeps_sessions(client):
    tokens = _login(client)
    old_refresh = tokens["refresh_token"]
    # karta A rotuje token
    first = client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
    assert first.status_code == 200
    # karta B używa STAREGO tokenu ułamek sekundy później — okno łaski: nowy access
    second = client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
    assert second.status_code == 200
    # sesje żyją: access karty A dalej działa (session_version nie podbite)
    me = client.get("/api/auth/me",
                    headers={"Authorization": f"Bearer {first.json()['access_token']}"})
    assert me.status_code == 200


def test_reuse_after_grace_still_kills_family(client):
    tokens = _login(client)
    old_refresh = tokens["refresh_token"]
    first = client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
    assert first.status_code == 200
    # zestarz odwołanie poza okno łaski — to już wygląda jak kradzież
    with SessionLocal() as db:
        for row in db.query(RefreshToken).filter(RefreshToken.revoked.is_(True)).all():
            row.revoked_at = (row.revoked_at or datetime.datetime.utcnow()) \
                - datetime.timedelta(seconds=3600)
        db.commit()
    second = client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
    assert second.status_code == 401
    # rodzina odwołana + access unieważniony przez podbicie wersji sesji
    me = client.get("/api/auth/me",
                    headers={"Authorization": f"Bearer {first.json()['access_token']}"})
    assert me.status_code == 401
    retry = client.post("/api/auth/refresh",
                        json={"refresh_token": first.json()["refresh_token"]})
    assert retry.status_code == 401


def _age_rotations(seconds: int) -> None:
    with SessionLocal() as db:
        for row in db.query(RefreshToken).filter(RefreshToken.revoked_at.isnot(None)).all():
            row.revoked_at -= datetime.timedelta(seconds=seconds)
        db.commit()


def test_reuse_after_11_seconds_kills_family(client):
    # audyt SEC-010: okno łaski 60 s dawało złodziejowi minutę na cichą wymianę tokenu
    old_refresh = _login(client)["refresh_token"]
    first = client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
    assert first.status_code == 200
    _age_rotations(11)
    assert client.post("/api/auth/refresh",
                       json={"refresh_token": old_refresh}).status_code == 401
    me = client.get("/api/auth/me",
                    headers={"Authorization": f"Bearer {first.json()['access_token']}"})
    assert me.status_code == 401
    assert client.post("/api/auth/refresh",
                       json={"refresh_token": first.json()["refresh_token"]}).status_code == 401


def test_grace_reuse_issues_access_only_no_new_refresh(client):
    # audyt SEC-010: zużyty token w oknie łaski nie może wydać NOWEGO refresh tokenu
    # (inaczej kradzież przedłuża sesję bez wykrycia); druga karta dostaje sam access
    old_refresh = _login(client)["refresh_token"]
    first = client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
    assert first.status_code == 200
    with SessionLocal() as db:
        issued = db.query(RefreshToken).count()
    second = client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
    assert second.status_code == 200
    assert second.json()["refresh_token"] is None and second.json()["access_token"]
    assert "timporye_refresh" not in second.cookies     # cookie z rotacji karty A zostaje
    assert "timporye_access" in second.cookies
    with SessionLocal() as db:
        assert db.query(RefreshToken).count() == issued
    me = client.get("/api/auth/me",
                    headers={"Authorization": f"Bearer {second.json()['access_token']}"})
    assert me.status_code == 200
    # token z rotacji karty A dalej działa — rodzina nieunieważniona
    assert client.post("/api/auth/refresh",
                       json={"refresh_token": first.json()["refresh_token"]}).status_code == 200
