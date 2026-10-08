"""Masowe akcje kolejki: status i magazyn — izolacja per id, walidacja przejść, audyt,
częściowe błędy w `failed` (poprawne zmiany i tak zapisane)."""
from tests.conftest import login
from tests.test_api import VALID_NO, _company_id, _make_user

NO2, NO3 = "CSQU3054383", "TCLU1234568"


def _containers(client, headers, company_id, *nos, **extra):
    return [client.post("/api/containers", headers=headers,
                        json={"container_no": no, "company_id": company_id, **extra}).json()["id"]
            for no in nos]


def _history_fields(client, headers, cid):
    return [h["field"] for h in client.get(f"/api/containers/{cid}/history", headers=headers).json()]


def test_bulk_status_changes_all_and_audits(client, admin_headers):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    ids = _containers(client, admin_headers, borealis, VALID_NO, NO2)
    r = client.post("/api/containers/bulk/status", headers=admin_headers,
                    json={"ids": ids, "status": "W_PORCIE"})
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": ids, "failed": []}
    for cid in ids:
        assert client.get(f"/api/containers/{cid}", headers=admin_headers).json()["status"] == "W_PORCIE"
        assert "status" in _history_fields(client, admin_headers, cid)


def test_bulk_status_partial_failure_keeps_valid_changes(client, admin_headers):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    back_id, fwd_id = _containers(client, admin_headers, borealis, VALID_NO, NO2)
    client.post(f"/api/containers/{back_id}/status", headers=admin_headers,
                json={"status": "AWIZOWANY"})
    # cofnięcie bez notatki → 422 dla tego jednego; drugi przechodzi
    r = client.post("/api/containers/bulk/status", headers=admin_headers,
                    json={"ids": [back_id, fwd_id, 999999], "status": "W_PORCIE"})
    body = r.json()
    assert body["ok"] == [fwd_id]
    assert {f["id"] for f in body["failed"]} == {back_id, 999999}
    assert client.get(f"/api/containers/{fwd_id}", headers=admin_headers).json()["status"] == "W_PORCIE"
    assert client.get(f"/api/containers/{back_id}", headers=admin_headers).json()["status"] == "AWIZOWANY"


def test_bulk_isolation_other_company_ids_fail(client, admin_headers):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    cobalt = _company_id(client, admin_headers, "COBALT")
    (own,) = _containers(client, admin_headers, borealis, VALID_NO)
    (foreign,) = _containers(client, admin_headers, cobalt, NO2)
    _make_user(client, admin_headers, "log.borealis", "logistics", borealis)
    headers = login(client, "log.borealis", "haslo123")
    r = client.post("/api/containers/bulk/warehouse", headers=headers,
                    json={"ids": [own, foreign], "name": "DLT"})
    assert r.json()["ok"] == [own]
    assert [f["id"] for f in r.json()["failed"]] == [foreign]
    assert client.get(f"/api/containers/{foreign}", headers=admin_headers).json()["warehouse_name"] is None


def test_bulk_warehouse_sets_and_audits(client, admin_headers):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    ids = _containers(client, admin_headers, borealis, VALID_NO, NO2, NO3)
    r = client.post("/api/containers/bulk/warehouse", headers=admin_headers,
                    json={"ids": ids, "name": "DLT"})
    assert r.json() == {"ok": ids, "failed": []}
    for cid in ids:
        assert client.get(f"/api/containers/{cid}", headers=admin_headers).json()["warehouse_name"] == "DLT"
        assert "warehouse" in _history_fields(client, admin_headers, cid)


def test_bulk_roles(client, admin_headers):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    wh = client.post("/api/warehouses", headers=admin_headers, json={
        "name": "Borealis", "company_id": borealis, "country": "PL"}).json()
    ids = _containers(client, admin_headers, borealis, VALID_NO, NO2, warehouse_id=wh["id"])
    _make_user(client, admin_headers, "mag.borealis", "warehouse", borealis, warehouse_id=wh["id"])
    headers = login(client, "mag.borealis", "haslo123")
    # magazyn: zmiana magazynu zabroniona, status tylko potwierdzenie rozładunku
    assert client.post("/api/containers/bulk/warehouse", headers=headers,
                       json={"ids": ids, "name": "DLT"}).status_code == 403
    denied = client.post("/api/containers/bulk/status", headers=headers,
                         json={"ids": ids, "status": "W_PORCIE"}).json()
    assert denied["ok"] == [] and len(denied["failed"]) == 2
    ok = client.post("/api/containers/bulk/status", headers=headers,
                     json={"ids": ids, "status": "DOSTARCZONY", "note": "rozładowany"}).json()
    assert ok == {"ok": ids, "failed": []}
