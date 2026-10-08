"""#65 Inwentaryzacja HU: rozjazdy HU wg PBI (stan DLT) vs HU wywołane."""
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
    monkeypatch.setattr(settings, "powerbi_cache_ttl_min", 0)


def _company_id(client, headers):
    return client.get("/api/companies", headers=headers).json()[0]["id"]


def test_hu_inventory_marks_called_and_mismatches(client, admin_headers):
    # mock DLT ma HU 10000777 dla DEMO-SKU-020; wywołujemy je + jedno nieistniejące
    call = client.post("/api/pallet-calls", headers=admin_headers, json={
        "company_id": _company_id(client, admin_headers), "allow_over_dlt": True,
        "lines": [
            {"produkt": "DEMO-SKU-020", "ilosc_pal": 1, "hu_numbers": "10000777"},
            {"produkt": "DEMO-SKU-020", "ilosc_pal": 1, "hu_numbers": "99999999"},
        ]}).json()
    # status draft nie liczy się do wywołanych — raport pusty po stronie called
    r0 = client.get("/api/pallet-calls/hu-inventory", headers=admin_headers).json()
    assert r0["available"] is True
    assert all(not row["called"] for row in r0["rows"])

    # po wysłaniu (sent) HU są 'called'; brakujące w DLT = mismatch
    from app.database import SessionLocal
    from app.models import PalletCall, PalletCallStatus
    with SessionLocal() as db:
        row = db.get(PalletCall, call["id"])
        row.status = PalletCallStatus.sent
        db.commit()

    r = client.get("/api/pallet-calls/hu-inventory", headers=admin_headers).json()
    by_hu = {row["hu"]: row for row in r["rows"]}
    assert by_hu["10000777"]["called"] and by_hu["10000777"]["in_dlt"]
    assert by_hu["10000777"]["call_number"] == call["number"]
    ghost = by_hu["99999999"]
    assert ghost["called"] and not ghost["in_dlt"] and ghost["mismatch"]
    assert r["mismatches"] >= 1


def test_hu_inventory_degrades_without_hu_column(client, admin_headers, monkeypatch):
    # PBI bez kolumny HU → available=False (feature-detect)
    from app.routers import pallets as pallets_router
    monkeypatch.setattr(pallets_router, "get_analysis",
                        lambda db, force=False: ([], [], None, {"hu": False}))
    r = client.get("/api/pallet-calls/hu-inventory", headers=admin_headers)
    assert r.status_code == 200 and r.json()["available"] is False
