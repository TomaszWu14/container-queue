"""Kolejka 'do zlecenia' + flaga needs_forwarding."""
from app.database import SessionLocal
from app.models import Container

VALID_NO = "MSDU0806613"


def _make_container(client, admin_headers, no=VALID_NO, forwarder_id=None):
    companies = client.get("/api/companies", headers=admin_headers).json()
    borealis = next(c["id"] for c in companies if c["code"] == "BOREALIS")
    body = {"container_no": no, "company_id": borealis}
    if forwarder_id:
        body["forwarder_id"] = forwarder_id
    return client.post("/api/containers", headers=admin_headers, json=body).json()


def _to_forward_nos(client, headers):
    r = client.get("/api/containers/to-forward", headers=headers)
    assert r.status_code == 200, r.text
    return {c["container_no"] for c in r.json()}


def test_needs_forwarding_defaults_false(client, admin_headers):
    c = _make_container(client, admin_headers)
    with SessionLocal() as db:
        row = db.get(Container, c["id"])
        assert row.needs_forwarding is False


def test_needs_forwarding_toggle(client, admin_headers):
    c = _make_container(client, admin_headers)  # VALID_NO — świeża baza per test
    r = client.patch(f"/api/containers/{c['id']}/needs-forwarding",
                     headers=admin_headers, json={"value": True})
    assert r.status_code == 200 and r.json()["needs_forwarding"] is True
    r = client.patch(f"/api/containers/{c['id']}/needs-forwarding",
                     headers=admin_headers, json={"value": False})
    assert r.json()["needs_forwarding"] is False


def test_to_forward_rule(client, admin_headers):
    # bez spedytora → w kolejce
    a = _make_container(client, admin_headers, no="MSDU0806613")
    assert "MSDU0806613" in _to_forward_nos(client, admin_headers)

    # z przypisanym spedytorem → znika (chyba że flaga)
    fwds = client.get("/api/forwarders", headers=admin_headers).json()
    fid = fwds[0]["id"]
    client.patch(f"/api/containers/{a['id']}", headers=admin_headers,
                 json={"forwarder_id": fid})
    assert "MSDU0806613" not in _to_forward_nos(client, admin_headers)

    # flaga needs_forwarding zwraca go mimo spedytora
    client.patch(f"/api/containers/{a['id']}/needs-forwarding", headers=admin_headers,
                 json={"value": True})
    assert "MSDU0806613" in _to_forward_nos(client, admin_headers)

    # w aktywnym TransportJob (SZKIC) → znika
    client.post("/api/transport-jobs", headers=admin_headers,
                json={"container_ids": [a["id"]], "forwarder_ids": [fid]})
    assert "MSDU0806613" not in _to_forward_nos(client, admin_headers)
