"""Skrypt migracji z bazy Compare: SQLite ze schematem Compare → materiały, przeliczniki,
mapy kolumn dostawców w TIMPORYE (podgląd nie zapisuje, --commit zapisuje)."""
import sqlite3
import sys

from sqlalchemy import select

from app.models import Material, Supplier, UomConversion
from scripts import import_compare_db as mig


def _compare_db(path):
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE material_master (id INTEGER PRIMARY KEY, ref_code TEXT, ref_norm TEXT,
            opis_pl TEXT, opis_en TEXT, ean TEXT, rodzina TEXT, base_uom TEXT, producer_code TEXT,
            tariff_cn TEXT, supplier_codes TEXT, txt_short_pl TEXT, customs_code TEXT,
            vat_rate TEXT, sent INTEGER, levels_json TEXT, active INTEGER);
        INSERT INTO material_master VALUES (1, 'NL753-S-40', 'NL753S40', 'Cewnik', 'Catheter',
            '5907996800810', 'Cewniki', 'SZT', 'P9', '9018', '', '', '', '23', 1,
            '{"karton": {"qty_base": "240"}}', 1);
        INSERT INTO material_master VALUES (2, 'OLD', 'OLD', 'Nieaktywny', '', '', '', '', '',
            '', '', '', '', '', 0, '{}', 0);
        CREATE TABLE uom_conversion (id INTEGER PRIMARY KEY, ref_norm TEXT, unit_from TEXT,
            unit_to TEXT, factor REAL);
        INSERT INTO uom_conversion VALUES (1, '*', 'PAL', 'PCS', 1000);
        INSERT INTO uom_conversion VALUES (2, 'NL753S40', 'CTN', 'PCS', 240);
        CREATE TABLE suppliers (id INTEGER PRIMARY KEY, code TEXT, name TEXT,
            pi_column_mapping_json TEXT, column_mapping_json TEXT);
        INSERT INTO suppliers VALUES (1, 'FG', 'Shieldco', '{"S.No": "ref", "Q''ty": "qty", "Amount": "net", "Photo": "skip"}', '{}');
        INSERT INTO suppliers VALUES (2, 'DM', 'Demomed', '{}', '{"PI": {"ref": "Item No.", "qty": "Quantity"}}');
        INSERT INTO suppliers VALUES (3, 'XX', 'Nieznany', '{"ref": "Code"}', '{}');
    """)
    db.commit()
    db.close()


def test_column_map_both_conventions():
    assert mig.column_map_text({"pi_column_mapping_json": '{"S.No": "ref", "Photo": "skip", "Amount": "net"}'}) \
        == "ref=S.No; net=Amount"
    assert mig.column_map_text({"pi_column_mapping_json": "{}",
                                "column_mapping_json": '{"PI": {"ref": "Item No.", "quantity": "Qty"}}'}) \
        == "ref=Item No.; qty=Qty"
    assert mig.column_map_text({}) == ""


def test_preview_then_commit(client, admin_headers, db_session, tmp_path, monkeypatch, capsys):
    path = tmp_path / "doccompare.db"
    _compare_db(path)
    company = client.get("/api/companies", headers=admin_headers).json()[0]["id"]
    client.post("/api/suppliers", headers=admin_headers, json={"name": "SHIELDCO", "company_id": company})

    monkeypatch.setattr(sys, "argv", ["import_compare_db", "--db", f"sqlite:///{path}"])
    assert mig.main() == 0
    out = capsys.readouterr().out
    assert "Materiały: 1 (nowe 1" in out and "nic nie zapisano" in out
    assert "brak dostawcy „Nieznany”" in out
    assert db_session.scalar(select(Material)) is None

    monkeypatch.setattr(sys, "argv", ["import_compare_db", "--db", f"sqlite:///{path}", "--commit"])
    assert mig.main() == 0
    db_session.expire_all()
    material = db_session.scalar(select(Material).where(Material.ref_code == "NL753-S-40"))
    assert material.name_pl == "Cewnik" and material.tariff_cn == "9018" and material.sent is True
    assert material.vat_rate == "23" and material.base_uom == "SZT"
    assert db_session.scalar(select(Material).where(Material.ref_code == "OLD")) is None
    rules = {(r.ref_norm, r.unit_from, r.unit_to): float(r.factor)
             for r in db_session.scalars(select(UomConversion))}
    assert rules[("*", "PAL", "PCS")] == 1000.0 and rules[("NL753S40", "CTN", "PCS")] == 240.0
    supplier = db_session.scalar(select(Supplier).where(Supplier.name == "SHIELDCO"))
    assert supplier.column_map == "ref=S.No; qty=Q'ty; net=Amount"


def test_commit_twice_updates_existing_materials(client, admin_headers, db_session, tmp_path, monkeypatch, capsys):
    """Ponowna migracja po poprawkach w Compare musi nadpisać pola istniejących materiałów."""
    path = tmp_path / "doccompare.db"
    _compare_db(path)
    monkeypatch.setattr(sys, "argv", ["import_compare_db", "--db", f"sqlite:///{path}", "--commit"])
    assert mig.main() == 0
    src = sqlite3.connect(path)
    src.execute("UPDATE material_master SET opis_pl='Cewnik Nelaton', tariff_cn='9018 39' WHERE ref_code='NL753-S-40'")
    src.commit()
    src.close()
    assert mig.main() == 0
    db_session.expire_all()
    material = db_session.scalar(select(Material).where(Material.ref_code == "NL753-S-40"))
    assert material.name_pl == "Cewnik Nelaton" and material.tariff_cn == "9018 39"
