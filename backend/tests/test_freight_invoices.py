"""Faktury transportowe BL: jedna faktura na zestaw kontenerów (m2m).
Sprawdza tworzenie z wieloma kontenerami, koszt/kontener, izolację spółki, delete."""
import io


def _company_id(client, headers, code):
    return next(c["id"] for c in client.get("/api/companies", headers=headers).json()
               if c["code"] == code)


def _container(client, headers, no, company_id, port_id):
    return client.post("/api/containers", headers=headers, json={
        "container_no": no, "company_id": company_id, "port_id": port_id}).json()


def test_create_freight_invoice_multi_container(client, admin_headers):
    acme_id = _company_id(client, admin_headers, "ACME")
    ports = client.get("/api/ports", headers=admin_headers).json()
    c1 = _container(client, admin_headers, "MEDU1234562", acme_id, ports[0]["id"])
    c2 = _container(client, admin_headers, "CAIU7654324", acme_id, ports[0]["id"])

    resp = client.post("/api/freight-invoices", headers=admin_headers,
                       data={"company_id": acme_id, "container_ids": f"{c1['id']},{c2['id']}",
                             "bl_number": "BL-777", "amount": "1000", "currency": "eur"})
    assert resp.status_code == 201, resp.text
    inv = resp.json()
    assert inv["bl_number"] == "BL-777"
    assert inv["currency"] == "EUR"
    assert {c["id"] for c in inv["containers"]} == {c1["id"], c2["id"]}
    assert inv["amount_per_container"] == 500.0     # 1000 / 2 kontenery
    assert inv["has_file"] is False

    lst = client.get("/api/freight-invoices", headers=admin_headers).json()
    assert any(i["id"] == inv["id"] and len(i["containers"]) == 2 for i in lst)


def test_freight_invoice_with_file_and_delete(client, admin_headers):
    acme_id = _company_id(client, admin_headers, "ACME")
    ports = client.get("/api/ports", headers=admin_headers).json()
    c1 = _container(client, admin_headers, "MEDU1234562", acme_id, ports[0]["id"])

    resp = client.post("/api/freight-invoices", headers=admin_headers,
                       data={"company_id": acme_id, "container_ids": str(c1["id"])},
                       files={"file": ("bl.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")})
    assert resp.status_code == 201, resp.text
    inv = resp.json()
    assert inv["has_file"] is True

    dl = client.get(f"/api/freight-invoices/{inv['id']}/download", headers=admin_headers)
    assert dl.status_code == 200
    assert dl.content == b"%PDF-1.4 test"

    assert client.delete(f"/api/freight-invoices/{inv['id']}", headers=admin_headers).status_code == 204
    assert client.get(f"/api/freight-invoices/{inv['id']}/download",
                      headers=admin_headers).status_code == 404


def test_freight_invoice_rejects_foreign_company_container(client, admin_headers):
    acme_id = _company_id(client, admin_headers, "ACME")
    other_id = next(c["id"] for c in client.get("/api/companies", headers=admin_headers).json()
                    if c["id"] != acme_id)
    ports = client.get("/api/ports", headers=admin_headers).json()
    c_other = _container(client, admin_headers, "MEDU1234562", other_id, ports[0]["id"])

    resp = client.post("/api/freight-invoices", headers=admin_headers,
                       data={"company_id": acme_id, "container_ids": str(c_other["id"])})
    assert resp.status_code == 422
    assert "innej spółki" in resp.json()["detail"]


def test_freight_invoice_requires_container(client, admin_headers):
    acme_id = _company_id(client, admin_headers, "ACME")
    resp = client.post("/api/freight-invoices", headers=admin_headers,
                       data={"company_id": acme_id, "container_ids": ""})
    assert resp.status_code == 422


def test_freight_invoice_non_numeric_container_ids_422(client, admin_headers):
    """Śmieci w CSV id (audyt 2026-09-23) → 422, nie 500 z int()."""
    acme_id = _company_id(client, admin_headers, "ACME")
    for raw in ("12,abc", "12, 15x"):
        resp = client.post("/api/freight-invoices", headers=admin_headers,
                           data={"company_id": acme_id, "container_ids": raw})
        assert resp.status_code == 422, resp.text


def test_freight_invoice_duplicates_and_archive_refused(client, admin_headers, tmp_path, monkeypatch):
    """§4 pkt 31, 38: ten sam numer faktury + BL albo ten sam plik w spółce = 409; .zip = 422."""
    from app.config import settings
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))
    acme_id = _company_id(client, admin_headers, "ACME")
    ports = client.get("/api/ports", headers=admin_headers).json()
    c1 = _container(client, admin_headers, "MEDU1234562", acme_id, ports[0]["id"])

    def post(number, bl, name="fv.pdf", content=b"%PDF-1.4 fracht"):
        return client.post("/api/freight-invoices", headers=admin_headers,
                           data={"company_id": acme_id, "container_ids": str(c1["id"]),
                                 "invoice_number": number, "bl_number": bl},
                           files={"file": (name, io.BytesIO(content), "application/pdf")})

    assert post("FV/1", "BL-1").status_code == 201
    same_number = post("fv/1 ", "bl-1", content=b"%PDF-1.4 inna tresc")
    assert same_number.status_code == 409 and "FV/1" in same_number.json()["detail"]
    same_file = post("FV/2", "BL-2")
    assert same_file.status_code == 409 and "Ten plik już jest" in same_file.json()["detail"]
    assert post("FV/3", "BL-3", name="faktury.zip", content=b"PK\x03\x04").status_code == 422
    assert post("FV/1", "BL-9", content=b"%PDF-1.4 inny BL").status_code == 201   # inny BL — OK
