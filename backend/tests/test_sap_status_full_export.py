"""DATA-003 (wariant a): rekord EKKO/MARM nieobecny w PEŁNYM eksporcie SAP → „brak_w_sap”
(bez kasowania); częściowy plik → bez zmian; rekord ponownie w pliku → „aktywny”."""
from sqlalchemy import select

from app.models import MaterialUnit, SapOrder
from tests.test_import_marm import _xlsx as marm_xlsx
from tests.test_import_sap_orders import _row, _xlsx as ekko_xlsx


def _post(client, headers, url, content, full):
    r = client.post(f"{url}&dry_run=false&full_export={str(full).lower()}", headers=headers,
                    files={"file": ("f.xlsx", content, "application/vnd.ms-excel")})
    assert r.status_code == 200, r.text
    return r.json()["counts"]


def _check(client, headers, db, url, both, one, model, key):
    def status():
        db.expire_all()
        return {key(r): r.sap_status for r in db.scalars(select(model))}

    _post(client, headers, url, both, False)
    first, second = sorted(status())
    assert status() == {first: "aktywny", second: "aktywny"}
    assert _post(client, headers, url, one, False)["deactivated"] == 0   # częściowy
    assert status()[second] == "aktywny"
    assert _post(client, headers, url, one, True)["deactivated"] == 1    # pełny eksport
    assert status() == {first: "aktywny", second: "brak_w_sap"}          # nie skasowany
    _post(client, headers, url, both, True)                               # powrót
    assert status() == {first: "aktywny", second: "aktywny"}


def test_ekko_full_export_marks_missing(client, admin_headers, db_session):
    _check(client, admin_headers, db_session, "/api/import/sap-orders?company_code=ACME",
           ekko_xlsx([_row("4500000001"), _row("4500000002")]),
           ekko_xlsx([_row("4500000001")]), SapOrder, lambda o: o.order_number)


def test_marm_full_export_marks_missing(client, admin_headers, db_session):
    kar, pal = ["100200", "KAR", 10, 1, 120, "CDM", 5, "KG"], ["100200", "PAL", 400, 1, 1, "M3", 300, "KG"]
    _check(client, admin_headers, db_session, "/api/import/material-units?",
           marm_xlsx([kar, pal]), marm_xlsx([kar]), MaterialUnit, lambda u: u.unit)


def test_sapstat001_upgrade_downgrade(tmp_path, monkeypatch):
    from sqlalchemy import inspect

    from tests.test_kartoteka_migration import _apply, _engine, _load
    mig = _load("sapstat001_sap_status_ekko_marm.py")
    assert mig.down_revision == "dropcnt001"
    eng = _engine(tmp_path, ["CREATE TABLE sap_orders (id INTEGER PRIMARY KEY)",
                             "CREATE TABLE material_units (id INTEGER PRIMARY KEY)",
                             "INSERT INTO sap_orders VALUES (1)"])
    _apply(eng, mig, mig.upgrade, monkeypatch)
    with eng.connect() as conn:
        assert conn.exec_driver_sql("SELECT sap_status FROM sap_orders").scalar() == "aktywny"
    _apply(eng, mig, mig.downgrade, monkeypatch)
    assert "sap_status" not in {c["name"] for c in inspect(eng).get_columns("material_units")}
