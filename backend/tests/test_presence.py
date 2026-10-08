"""Pasek obecności: tylko online (ruch ≤ 5 min), bez czasu bezczynności; widzą i są widoczni
tylko wewnętrzni."""
from types import SimpleNamespace

import pytest

from app import presence
from app.models import Role


@pytest.fixture(autouse=True)
def _clean():
    presence._seen.clear()
    yield
    presence._seen.clear()


def _user(uid, name, role=Role.logistics, company_id=1, view_all=False):
    return SimpleNamespace(id=uid, full_name=name, login=f"u{uid}", role=role, avatar="",
                           company_id=company_id, view_all_companies=view_all)


def test_only_online_and_no_idle_time():
    t0 = 1_000_000.0
    presence.record(_user(1, "Anna Nowak"), presence.Ping(path="/kolejka?spolka=1"), now=t0)
    rows = presence.record(_user(2, "Jan Kowalski"), presence.Ping(path="/kalendarz"), now=t0)
    assert [r["name"] for r in rows] == ["Anna Nowak", "Jan Kowalski"]
    assert rows[0]["path"] == "/kolejka"                                     # bez ?query
    assert all("idle_s" not in r and "active" not in r for r in rows)       # czas bezczynności nie wychodzi
    # Anna ma tylko otwartą kartę (sygnały bez ruchu): do 5 min widoczna, potem znika z paska
    presence.record(_user(1, "Anna Nowak"), presence.Ping(path="/kolejka", active=False), now=t0 + 300)
    rows = presence.record(_user(2, "Jan Kowalski"), presence.Ping(path="/kalendarz"), now=t0 + 300)
    assert [r["name"] for r in rows] == ["Anna Nowak", "Jan Kowalski"]
    presence.record(_user(1, "Anna Nowak"), presence.Ping(path="/kolejka", active=False), now=t0 + 301)
    rows = presence.record(_user(2, "Jan Kowalski"), presence.Ping(path="/kalendarz"), now=t0 + 301)
    assert [r["name"] for r in rows] == ["Jan Kowalski"]
    # ruch wraca → znów online
    rows = presence.record(_user(1, "Anna Nowak"), presence.Ping(path="/kolejka"), now=t0 + 400)
    assert [r["name"] for r in rows] == ["Anna Nowak", "Jan Kowalski"]


def test_leave_removes_immediately():
    presence.record(_user(1, "Anna"), presence.Ping(), now=10.0)
    presence.forget(1)
    assert presence._snapshot(11.0, _user(9, "Ktoś")) == []


def test_other_company_not_visible():
    """Pasek obecności jak obserwujący (shares_company_scope): logistyk spółki A nie widzi, kto
    z spółki B jest online; konto grupowe (view_all) widzi wszystkich i jest widoczne dla wszystkich."""
    presence.record(_user(1, "Anna A", company_id=1), presence.Ping(), now=10.0)
    presence.record(_user(2, "Bartek B", company_id=2), presence.Ping(), now=10.0)
    group = _user(3, "Grupa", company_id=None, view_all=True)
    assert [r["name"] for r in presence.record(group, presence.Ping(), now=10.0)] ==         ["Anna A", "Bartek B", "Grupa"]
    rows = presence.record(_user(1, "Anna A", company_id=1), presence.Ping(), now=11.0)
    assert [r["name"] for r in rows] == ["Anna A", "Grupa"]


def test_api_internal_only(client, admin_headers):
    r = client.post("/api/presence", headers=admin_headers, json={"path": "/administracja"})
    assert r.status_code == 200
    me = r.json()[0]
    assert me["path"] == "/administracja" and me["role"] == "admin" and "idle_s" not in me
    assert client.post("/api/presence/leave", headers=admin_headers).status_code == 204
    assert Role.forwarder not in presence.PRESENCE_ROLES and Role.customs not in presence.PRESENCE_ROLES
