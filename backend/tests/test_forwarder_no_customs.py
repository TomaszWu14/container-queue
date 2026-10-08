"""Decyzja 2026-09-28: odprawa to wyłącznie agencja celna — spedytor nie widzi statusu odprawy
ani pośrednio: filtr `customs_status` nie może zawęzić jego listy (wyrocznia wartości),
a pulpit nie liczy mu odpraw w toku."""
from tests.conftest import forwarder, login


def _setup(client, admin_headers):
    fwd = forwarder(client, admin_headers, "BEZODPR")
    company_id = client.get("/api/companies", headers=admin_headers).json()[0]["id"]
    ids = []
    for no, cs in (("TCNU0000011", "ODPRAWIONY"), ("TCNU0000027", "BRAK")):
        r = client.post("/api/containers", headers=admin_headers, json={
            "container_no": no, "company_id": company_id, "forwarder_id": fwd["id"]})
        assert r.status_code in (200, 201), r.text
        ids.append(r.json()["id"])
        assert client.patch(f"/api/containers/{ids[-1]}", headers=admin_headers,
                            json={"customs_status": cs, "customs_note": "test"}).status_code == 200
    assert client.post("/api/users", headers=admin_headers, json={
        "login": "sped.bo", "password": "haslo123", "role": "forwarder",
        "forwarder_id": fwd["id"], "email": "sped.bo@example.com"}).status_code == 201
    return login(client, "sped.bo", "haslo123"), ids


def test_customs_filter_ignored_for_forwarder(client, admin_headers):
    hdr, ids = _setup(client, admin_headers)
    got = {c["id"] for c in client.get("/api/containers?customs_status=ODPRAWIONY", headers=hdr).json()}
    assert got == set(ids)   # filtr nie zdradza, który kontener jest odprawiony


def test_dashboard_hides_customs_count_for_forwarder(client, admin_headers):
    hdr, _ = _setup(client, admin_headers)
    assert client.get("/api/stats/dashboard", headers=hdr).json()["customs_in_progress"] is None
    assert client.get("/api/stats/dashboard", headers=admin_headers).json()["customs_in_progress"] is not None
