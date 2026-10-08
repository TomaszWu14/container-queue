"""Spedytorzy: edycja nazwy, dezaktywacja, usuwanie (guarded) i scalanie duplikatów."""


def _company(client, headers, code="BOREALIS"):
    return next(c["id"] for c in client.get("/api/companies", headers=headers).json()
               if c["code"] == code)


def _fwd(client, headers, name):
    r = client.post("/api/forwarders", headers=headers, json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_edit_name_and_deactivate(client, admin_headers):
    fid = _fwd(client, admin_headers, "ZZTEST-EDIT")
    r = client.patch(f"/api/forwarders/{fid}", headers=admin_headers,
                     json={"name": "ZZTEST-EDIT2", "is_active": False})
    assert r.status_code == 200 and r.json()["name"] == "ZZTEST-EDIT2"
    # domyślna lista pomija nieaktywnych, include_inactive pokazuje
    assert all(f["id"] != fid for f in client.get("/api/forwarders", headers=admin_headers).json())
    assert any(f["id"] == fid for f in
               client.get("/api/forwarders?include_inactive=true", headers=admin_headers).json())


def test_delete_unused_and_guarded(client, admin_headers):
    fid = _fwd(client, admin_headers, "ZZTEST-DEL")
    # nieużywany → usuwa się
    assert client.delete(f"/api/forwarders/{fid}", headers=admin_headers).status_code == 204

    used = _fwd(client, admin_headers, "ZZTEST-USED")
    cid = _company(client, admin_headers)
    c = client.post("/api/containers", headers=admin_headers, json={
        "container_no": "CSQU3054383", "company_id": cid, "forwarder_id": used,
        "status": "W_PORCIE"}).json()["id"]
    # w użyciu → 409
    assert client.delete(f"/api/forwarders/{used}", headers=admin_headers).status_code == 409

    # scalenie przepina kontener na docelowego, kasuje duplikat
    target = _fwd(client, admin_headers, "ZZTEST-TGT")
    m = client.post(f"/api/forwarders/{used}/merge", headers=admin_headers,
                    json={"target_id": target})
    assert m.status_code == 200
    assert client.get(f"/api/containers/{c}", headers=admin_headers).json()["forwarder_id"] == target
