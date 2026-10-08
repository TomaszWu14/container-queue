"""Limit nieudanych logowań (audyt SEC-001): udane logowanie na WŁASNE konto nie może zerować
licznika prób na CUDZE konto z tego samego IP; próbowanie wielu kont z jednego IP też ma limit."""
from app.config import settings
from app.models import Role, User
from app.security import hash_password

# stan limitera jest w bazie (login_failures) — fixture `client` daje czystą bazę na test
BAD = {"username": "admin", "password": "zle-haslo-123"}


def _me(db_session, login="ja.logistyka", password="Moje-haslo-2026"):
    db_session.add(User(login=login, hashed_password=hash_password(password), role=Role.logistics))
    db_session.commit()
    return {"username": login, "password": password}


def _post(client, form):
    return client.post("/api/auth/login", data=form).status_code


def test_own_success_does_not_reset_attempts_on_other_account(client, db_session):
    me = _me(db_session)
    codes = []
    for i in range(20):                      # scenariusz z audytu: 20 prób przeplatanych
        codes.append(_post(client, BAD))
        if i % 3 == 2:
            assert _post(client, me) == 200  # własne konto dalej działa
    assert codes[:settings.login_max_attempts] == [401] * settings.login_max_attempts
    assert codes[settings.login_max_attempts] == 429
    assert codes.count(429) >= 20 - settings.login_max_attempts


def test_many_logins_from_one_ip_hit_ip_cap(client):
    cap = settings.login_max_attempts_per_ip
    codes = [_post(client, {"username": f"nie-ma-{i}", "password": "x" * 12}) for i in range(cap + 3)]
    assert codes[:cap] == [401] * cap and set(codes[cap:]) == {429}


def test_locked_pair_does_not_lock_other_user_on_same_ip(client, db_session):
    me = _me(db_session)
    for _ in range(settings.login_max_attempts):
        _post(client, BAD)
    assert _post(client, BAD) == 429         # admin z tego IP zablokowany
    assert _post(client, me) == 200          # kolega zza tego samego NAT loguje się normalnie
