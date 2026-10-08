"""Import MARM (eksport SAP ACME, 2026-09-29) zakłada materiały do dopasowania faktur:
numer, jm podstawowa (1/1, SZT przed innymi, bez „JU”), EAN i przeliczniki; faktura
„AT-SGSP-XL 1-CN” trafia w materiał „AT-SGSP-XL_1-CN”."""
from sqlalchemy import select

from app.database import SessionLocal
from app.invoices.matching import get_material
from app.models import Material, MaterialUnit, UomConversion
from tests.test_import_autodetect import xlsx

HEADER = ["Materiał", "Alternatywna jednostka miary", "Mianownik", "Licznik", "Wykorz. zdoln. prod.",
          "Szerokość", "Wysokość", "Długość", "Jednostka wymiaru", "Waga brutto", "Jednostka wagi",
          "Objętość", "Jednostka objętości", "Kod EAN/UPC"]
ROWS = [
    ["AT-SGSP-XL_1-CN", "JU", 1, 1, 0, 0, 0, 0, "", 0, "", 0, "", ""],
    ["AT-SGSP-XL_1-CN", "KAR", 1, 25, 0, 40, 23, 60, "CM", 5.1, "KG", 55.2, "CD3", "5907996897124"],
    ["AT-SGSP-XL_1-CN", "SZT", 1, 1, 0, 24.5, 4.5, 33.5, "CM", 0.217, "KG", 2.442, "CD3", "5907996896790"],
    ["BT-PCS6060-CN", "JU", 25, 1, 0, 0, 0, 0, "", 0, "", 0, "", ""],
    ["BT-PCS6060-CN", "KAR", 1, 4, 0, 31.5, 22.5, 39.7, "CM", 6.04, "KG", 28.1, "CD3", "5904109600978"],
    ["BT-PCS6060-CN", "OP", 1, 1, 0, 26, 10.1, 40, "CM", 1.51, "KG", 7.0, "CD3", "5904109600961"],
]


def test_marm_import_creates_materials_ean_and_conversions(client, admin_headers):
    files = {"file": ("EXPORT.xlsx", xlsx(HEADER, ROWS), "application/vnd.ms-excel")}
    dry = client.post("/api/import/material-units", headers=admin_headers, files=files).json()
    assert dry["counts"]["materials_new"] == 2
    with SessionLocal() as db:
        assert db.scalar(select(Material)) is None                       # dry run nic nie zapisuje
    files = {"file": ("EXPORT.xlsx", xlsx(HEADER, ROWS), "application/vnd.ms-excel")}
    r = client.post("/api/import/material-units?dry_run=false", headers=admin_headers, files=files)
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        gown = get_material(db, "AT-SGSP-XL 1-CN")                       # zapis z faktury
        assert gown and gown.ref_code == "AT-SGSP-XL_1-CN"
        assert (gown.base_uom, gown.ean) == ("SZT", "5907996896790")
        pads = db.scalar(select(Material).where(Material.ref_code == "BT-PCS6060-CN"))
        assert pads.base_uom == "OP"                                     # bez SZT → 1/1 inna niż JU
        rules = {(c.ref_norm, c.unit_from, c.unit_to): float(c.factor)
                 for c in db.scalars(select(UomConversion))}
        assert rules == {("ATSGSPXL1CN", "CTN", "PCS"): 25.0, ("BTPCS6060CN", "CTN", "OP"): 4.0}
        kar = db.scalar(select(MaterialUnit).where(MaterialUnit.unit == "KAR",
                                                   MaterialUnit.material_no == "AT-SGSP-XL_1-CN"))
        assert kar.ean == "5907996897124"
    # ponowny import nie dubluje i nie nadpisuje uzupełnionych pól
    files = {"file": ("EXPORT.xlsx", xlsx(HEADER, ROWS), "application/vnd.ms-excel")}
    again = client.post("/api/import/material-units?dry_run=false", headers=admin_headers, files=files)
    assert again.json()["counts"]["materials_new"] == 0
