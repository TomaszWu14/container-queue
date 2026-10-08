"""Import stanów DLT z xlsx + fallback w analityce wywołań (gdy Power BI ich nie podaje)."""
import io

from openpyxl import Workbook

from app.models import ProductPaz
from app.pallets_cache import get_analysis


def xlsx(header, rows=()):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(header)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


DLT = xlsx(["Produkt", "Ilość", "Nr HU", "Lokalizacja"],
           [["100200", 400, "HU001", "DLT-A"],
            ["100200", 200, "HU002", "DLT-A"],
            ["300500", 50, "", "DLT-B"]])


def test_unknown_headers_give_422(client, admin_headers):
    response = client.post("/api/import/dlt-stock", headers=admin_headers,
                           files={"file": ("x.xlsx", xlsx(["A", "B"]), "application/x")})
    assert response.status_code == 422


def test_import_snapshot_replaces_and_counts(client, admin_headers):
    r1 = client.post("/api/import/dlt-stock?dry_run=false", headers=admin_headers,
                     files={"file": ("dlt.xlsx", DLT, "application/vnd.ms-excel")})
    assert r1.status_code == 200
    assert r1.json()["counts"] == {"rows": 3, "with_hu": 2, "produkty": 2}
    # ponowny import = snapshot: zastępuje poprzedni w całości
    small = xlsx(["Produkt", "Stan"], [["999", 5]])
    r2 = client.post("/api/import/dlt-stock?dry_run=false", headers=admin_headers,
                     files={"file": ("lit2.xlsx", small, "application/vnd.ms-excel")})
    assert r2.json()["counts"]["rows"] == 1


def test_import_feeds_analysis_as_dlt(client, admin_headers, db_session):
    db_session.add(ProductPaz(produkt="100200", sztuk_na_palete=100))
    db_session.commit()
    client.post("/api/import/dlt-stock?dry_run=false", headers=admin_headers,
                files={"file": ("dlt.xlsx", DLT, "application/vnd.ms-excel")})
    rows, _, _, features = get_analysis(db_session, force=True)
    by_produkt = {r["produkt"]: r for r in rows}
    assert "100200" in by_produkt
    row = by_produkt["100200"]
    assert row["stan_dlt_szt"] == 600           # 400 + 200 zsumowane
    assert row["stan_dlt_pal"] == 6.0           # 600 / 100 szt/paletę
    assert {h["hu"] for h in row["hu"]} == {"HU001", "HU002"}
    assert features["hu"] is True
