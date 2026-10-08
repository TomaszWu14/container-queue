"""Niedopisany rok z pola daty w przeglądarce („2” → 0002) nie może trafić do bazy —
daty operacyjne kontenera przyjmują tylko lata 2000–2099."""


def _container(client, admin_headers):
    company_id = client.get("/api/companies", headers=admin_headers).json()[0]["id"]
    r = client.post("/api/containers", headers=admin_headers,
                    json={"container_no": "TCNU0000011", "company_id": company_id})
    assert r.status_code in (200, 201), r.text
    return r.json()


def test_patch_rejects_year_outside_range(client, admin_headers):
    c = _container(client, admin_headers)
    url = f"/api/containers/{c['id']}"
    for bad in ("0002-11-09", "0026-11-09", "1999-12-31", "2100-01-01"):
        r = client.patch(url, headers=admin_headers, json={"notify_date": bad})
        assert r.status_code == 422, (bad, r.text)
    assert client.patch(url, headers=admin_headers, json={"eta": "0202-01-01"}).status_code == 422
    assert client.get(url, headers=admin_headers).json()["notify_date"] is None


def test_patch_accepts_operational_year_and_null(client, admin_headers):
    c = _container(client, admin_headers)
    url = f"/api/containers/{c['id']}"
    ok = client.patch(url, headers=admin_headers, json={"notify_date": "2026-11-09"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["notify_date"] == "2026-11-09"
    assert client.patch(url, headers=admin_headers, json={"notify_date": None}).status_code == 200


def test_create_rejects_year_outside_range(client, admin_headers):
    company_id = client.get("/api/companies", headers=admin_headers).json()[0]["id"]
    r = client.post("/api/containers", headers=admin_headers,
                    json={"container_no": "TCNU0000011", "company_id": company_id,
                          "eta": "0002-11-09"})
    assert r.status_code == 422, r.text
