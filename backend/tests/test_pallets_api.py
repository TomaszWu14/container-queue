import io

import openpyxl
import pytest


@pytest.fixture(autouse=True)
def _mock_powerbi(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "powerbi_provider", "mock")
    monkeypatch.setattr(settings, "powerbi_dlt_locations", "3DLT")
    monkeypatch.setattr(settings, "powerbi_table_stock", "stock")
    monkeypatch.setattr(settings, "powerbi_table_vbba", "vbba")
    monkeypatch.setattr(settings, "powerbi_table_orders", "vbbe")
    monkeypatch.setattr(settings, "powerbi_table_usage", "zuzycie")
    monkeypatch.setattr(settings, "powerbi_cache_ttl_min", 0)   # zawsze świeży fetch


def _add_paz(client, headers, produkt="DEMO-SKU-020", sztuk=100):
    return client.post("/api/paz", headers=headers,
                       json={"produkt": produkt, "sztuk_na_palete": sztuk})


def _company_id(client, headers):
    return client.get("/api/companies", headers=headers).json()[0]["id"]


def test_analysis_returns_signals(client, admin_headers):
    _add_paz(client, admin_headers)
    r = client.get("/api/pallet-calls/analysis?q=DEMO-SKU-020", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    item = next(i for i in body["items"] if i["produkt"] == "DEMO-SKU-020")
    assert item["stan_mag_pal"] == 10 and item["stan_dlt_pal"] == 20
    assert item["sugestia_pal"] == 10
    assert "discrepancies" in body


def test_analysis_missing_paz_filter(client, admin_headers):
    r = client.get("/api/pallet-calls/analysis?missing_paz=true", headers=admin_headers)
    assert all(i["sugestia_pal"] is None for i in r.json()["items"])


def test_create_and_list_call(client, admin_headers):
    payload = {"company_id": _company_id(client, admin_headers),
               "needed_by": "2026-08-20", "notes": "pilne",
               "lines": [{"produkt": "DEMO-SKU-020", "ilosc_pal": 3}]}
    r = client.post("/api/pallet-calls", headers=admin_headers, json=payload)
    assert r.status_code == 201, r.text
    call_id = r.json()["id"]
    assert r.json()["number"].startswith("PC-")
    assert r.json()["status"] == "draft"
    lst = client.get("/api/pallet-calls", headers=admin_headers).json()
    assert any(c["id"] == call_id for c in lst)


def test_send_sets_status(client, admin_headers, monkeypatch):
    from app.config import settings
    from app.routers import pallets
    sent = {}
    monkeypatch.setattr(pallets, "send_html_email",
                        lambda *a, **k: sent.update({"called": True, "kw": k}))
    monkeypatch.setattr(settings, "dlt_email", "dlt@example.com")
    call = client.post("/api/pallet-calls", headers=admin_headers, json={
        "company_id": _company_id(client, admin_headers),
        "lines": [{"produkt": "X", "ilosc_pal": 1}]}).json()
    r = client.post(f"/api/pallet-calls/{call['id']}/send", headers=admin_headers)
    assert r.status_code == 200 and r.json()["status"] == "sent"
    assert sent.get("called") and sent["kw"]["attachments"]


def test_dlt_guard_blocks_over_stock(client, admin_headers):
    _add_paz(client, admin_headers)   # DEMO-SKU-020 stan DLT = 20 pal (2000/100)
    cid = _company_id(client, admin_headers)
    over = {"company_id": cid, "lines": [{"produkt": "DEMO-SKU-020", "ilosc_pal": 25}]}
    r = client.post("/api/pallet-calls", headers=admin_headers, json=over)
    assert r.status_code == 422 and "DLT" in r.text
    over["allow_over_dlt"] = True
    r2 = client.post("/api/pallet-calls", headers=admin_headers, json=over)
    assert r2.status_code == 201


def test_deliver_and_xlsx(client, admin_headers):
    cid = _company_id(client, admin_headers)
    call = client.post("/api/pallet-calls", headers=admin_headers, json={
        "company_id": cid, "allow_over_dlt": True,
        "lines": [{"produkt": "DEMO-SKU-020", "ilosc_pal": 2}]}).json()
    r = client.post(f"/api/pallet-calls/{call['id']}/deliver", headers=admin_headers)
    assert r.status_code == 200 and r.json()["status"] == "delivered"
    x = client.get(f"/api/pallet-calls/{call['id']}/xlsx", headers=admin_headers)
    assert x.status_code == 200
    assert x.headers["content-type"].startswith("application/vnd.openxml")


def test_analysis_refresh_param(client, admin_headers):
    r = client.get("/api/pallet-calls/analysis?refresh=true", headers=admin_headers)
    assert r.status_code == 200


def test_powerbi_status(client, admin_headers):
    r = client.get("/api/pallet-calls/powerbi/status", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "mock" and body["configured"] is True
    assert body["needs_connect"] is False


def test_powerbi_connect_requires_real(client, admin_headers):
    # provider=mock -> connect odrzucony
    r = client.post("/api/pallet-calls/powerbi/connect", headers=admin_headers)
    assert r.status_code == 400


def test_paz_import_xlsx(client, admin_headers):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["produkt", "sztuk_na_palete"])
    ws.append(["ABC-1", 250])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    r = client.post("/api/paz/import", headers=admin_headers,
                    files={"file": ("paz.xlsx", buf,
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 200 and r.json()["imported"] == 1
    rows = client.get("/api/paz", headers=admin_headers).json()
    assert any(p["produkt"] == "ABC-1" and p["sztuk_na_palete"] == 250 for p in rows)
