"""Powód obserwacji widoczny: /api/watch/reasons (kolejka) i watched[] statku (mapa) — per user."""
from app.models import Role, TrackedVessel
from tests.conftest import login
from tests.test_vessel_card import _company_id, _mk_container, _scoped_user


def test_watch_reasons_lists_own_non_empty(client):
    headers = login(client)
    acme = _company_id(client, headers)
    a = _mk_container(client, headers, "TGBU6784203", "", acme)
    b = _mk_container(client, headers, "MSDU0806613", "", acme)
    client.post(f"/api/containers/{a['id']}/watch", headers=headers, json={"reason": " Reklamacja "})
    client.post(f"/api/containers/{b['id']}/watch", headers=headers)   # bez powodu
    assert client.get("/api/watch/reasons", headers=headers).json() == [
        {"container_id": a["id"], "reason": "Reklamacja"}]

    # cudza obserwacja nie wycieka
    _scoped_user("log-powod", acme, role=Role.logistics)
    other = login(client, "log-powod", "pass12345")
    assert client.get("/api/watch/reasons", headers=other).json() == []


def test_vessel_lists_my_watched_containers_with_reason(client, db_session):
    headers = login(client)
    acme = _company_id(client, headers)
    a = _mk_container(client, headers, "TGBU6784203", "MV DEMO IRIS", acme)
    _mk_container(client, headers, "MSDU0806613", "MV DEMO IRIS", acme)
    db_session.add(TrackedVessel(name="MV DEMO IRIS", lat=10.0, lon=20.0))
    db_session.commit()
    client.post(f"/api/containers/{a['id']}/watch", headers=headers, json={"reason": "Pilne"})

    v = next(x for x in client.get("/api/tracking/vessels", headers=headers).json()
             if x["name"] == "MV DEMO IRIS")
    assert v["watched"] == [{"id": a["id"], "container_no": "TGBU6784203", "reason": "Pilne"}]

    # inny user widzi statek, ale bez cudzej gwiazdki (obserwacja jest per user)
    _scoped_user("log-statek", acme, role=Role.logistics)
    other = login(client, "log-statek", "pass12345")
    v2 = next(x for x in client.get("/api/tracking/vessels", headers=other).json()
              if x["name"] == "MV DEMO IRIS")
    assert v2["watched"] == []
