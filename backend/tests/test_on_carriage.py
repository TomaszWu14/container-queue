"""Dowóz po odprawie (on_carriage): drogowo / intermodal — edycja, odczyt, historia, walidacja."""


def test_on_carriage_patch_read_history(client, admin_headers):
    companies = client.get("/api/companies", headers=admin_headers).json()
    cobalt = next(c["id"] for c in companies if c["code"] == "COBALT")
    created = client.post("/api/zlecenia", headers=admin_headers, json={
        "number": "ZL-DOWOZ", "company_id": cobalt, "container_count": 1, "main_mode": "SEA"})
    container = created.json()["containers"][0]
    assert container["on_carriage"] is None

    cid = container["id"]
    resp = client.patch(f"/api/containers/{cid}", headers=admin_headers,
                        json={"on_carriage": "intermodal", "change_note": "pociąg z Gdańska"})
    assert resp.status_code == 200
    got = client.get(f"/api/containers/{cid}", headers=admin_headers).json()
    assert (got["transport_type"], got["on_carriage"]) == ("morski", "intermodal")
    history = client.get(f"/api/containers/{cid}/history", headers=admin_headers).json()
    assert any(h["field"] == "on_carriage" for h in history)

    bad = client.patch(f"/api/containers/{cid}", headers=admin_headers, json={"on_carriage": "rower"})
    assert bad.status_code == 422
