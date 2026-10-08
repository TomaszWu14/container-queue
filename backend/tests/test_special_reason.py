def _company(client, headers, code="BOREALIS"):
    companies = client.get("/api/companies", headers=headers).json()
    return next(c["id"] for c in companies if c["code"] == code)


def _make(client, headers):
    cid = _company(client, headers)
    r = client.post("/api/containers", headers=headers, json={
        "container_no": "CSQU3054383", "company_id": cid, "status": "W_PORCIE"})
    return r.json()["id"]


def test_special_reason_set_and_cleared(client, admin_headers):
    """Włączenie flagi zapisuje powód+notatkę; wyłączenie je czyści."""
    cid = _make(client, admin_headers)

    on = client.post(f"/api/containers/{cid}/special", headers=admin_headers,
                     json={"is_special": True, "reason": "pilne", "note": "kara umowna"})
    assert on.status_code == 200
    assert on.json() == {"is_special": True, "special_reason": "pilne", "special_note": "kara umowna"}

    got = client.get(f"/api/containers/{cid}", headers=admin_headers).json()
    assert got["is_special"] and got["special_reason"] == "pilne" and got["special_note"] == "kara umowna"

    off = client.post(f"/api/containers/{cid}/special", headers=admin_headers,
                      json={"is_special": False})
    assert off.json() == {"is_special": False, "special_reason": None, "special_note": ""}


def test_special_reason_rejects_unknown(client, admin_headers):
    cid = _make(client, admin_headers)
    bad = client.post(f"/api/containers/{cid}/special", headers=admin_headers,
                      json={"is_special": True, "reason": "cokolwiek"})
    assert bad.status_code == 422


def test_special_toggle_without_body_still_works(client, admin_headers):
    """Wstecznie kompatybilne: brak body = toggle."""
    cid = _make(client, admin_headers)
    assert client.post(f"/api/containers/{cid}/special", headers=admin_headers).json()["is_special"] is True
    assert client.post(f"/api/containers/{cid}/special", headers=admin_headers).json()["is_special"] is False
