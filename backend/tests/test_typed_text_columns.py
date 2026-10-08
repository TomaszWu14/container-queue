"""DB-008 — liczby i daty zapisane jako tekst: typowane kopie obok surowego tekstu.

order_items.quantity_num, goods_receipt_lines.qty_received_num (Numeric 14,3) i
purchase_orders.ready_on / oem_sample_on (Date) — wypełniane przy każdym zapisie ORM
(nasłuch „set”) i w migracji typed001 dla istniejących wierszy. Obliczenia (objętość z MARM,
packer, status przyjęć) czytają liczbę, a nie parsują tekst w locie — „1.234,000” sprzed
normalizacji importu nie wypada już po cichu z sum (weryfikacja z audytu).
"""
import datetime
import importlib.util
import pathlib
from decimal import Decimal

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal
from app.models import (
    Company,
    Container,
    GoodsReceiptLine,
    MaterialUnit,
    OrderItem,
    PurchaseOrder,
    parse_quantity,
    parse_text_date,
)

_MIG = (pathlib.Path(__file__).resolve().parents[1] / "migrations" / "versions"
        / "typed001_typowane_ilosci_i_daty.py")


@pytest.mark.parametrize("raw, expected", [
    ("1.234,000", Decimal("1234.000")),     # SAP PL: kropka tysięcy, przecinek dziesiętny
    ("1,234.50", Decimal("1234.500")),      # EN
    ("1 200,5", Decimal("1200.500")),       # spacja tysięcy
    ("12,5", Decimal("12.500")),            # pojedynczy przecinek = dziesiętny (PL)
    ("1200.5", Decimal("1200.500")),        # tekst po normalizacji importu REF
    ("3", Decimal("3.000")),
    ("", None), ("abc", None), (None, None),
])
def test_parse_quantity(raw, expected):
    assert parse_quantity(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("15.10.2026", datetime.date(2026, 10, 15)),
    ("15.10.26", datetime.date(2026, 10, 15)),
    ("2026-10-15", datetime.date(2026, 10, 15)),
    ("2026-10-15 00:00:00", datetime.date(2026, 10, 15)),   # komórka daty z Excela
    ("15/10/2026", datetime.date(2026, 10, 15)),
    ("Confirmed", None), ("", None), ("31.02.2026", None),
])
def test_parse_text_date(raw, expected):
    assert parse_text_date(raw) == expected


def test_orm_writes_fill_typed_columns(client):
    with SessionLocal() as db:
        company = db.scalar(select(Company).where(Company.code == "ACME"))
        item = OrderItem(company_id=company.id, order_number="4500000001", position="10",
                         quantity="1.234,000")
        po = PurchaseOrder(company_id=company.id, order_no="PO-1", ready_date="15.10.2026",
                           oem_sample_date="Confirmed")
        container = Container(company_id=company.id, container_no="MSCU1234565")
        db.add_all([item, po, container])
        db.flush()
        line = GoodsReceiptLine(company_id=company.id, container_id=container.id,
                                order_number="4500000001", position="10", qty_received="1 000")
        db.add(line)
        db.commit()
        assert item.quantity_num == Decimal("1234.000")
        assert (po.ready_on, po.oem_sample_on) == (datetime.date(2026, 10, 15), None)
        assert line.qty_received_num == Decimal("1000.000")
        item.quantity = "7"                       # zmiana tekstu → zmiana liczby
        line.qty_received = ""
        db.commit()
        db.expire_all()
        assert item.quantity_num == Decimal("7.000") and line.qty_received_num is None


def test_marm_volume_reads_typed_quantity(client, admin_headers, db_session):
    """Pozycja sprzed normalizacji importu („1.234,000”): dawniej float(replace) → ValueError
    → objętość None (pozycja po cichu poza sumą), teraz z quantity_num."""
    acme = db_session.scalar(select(Company).where(Company.code == "ACME"))
    container = Container(company_id=acme.id, container_no="MSCU1234565",
                          order_numbers="4500011111")
    db_session.add_all([
        container,
        OrderItem(company_id=acme.id, order_number="4500011111", position="10",
                  material="100200", quantity="1.234,000", unit="KAR"),
        MaterialUnit(material_no="100200", unit="KAR", numerator=1, denominator=1,
                     volume=100, volume_unit="CDM"),
    ])
    db_session.commit()
    items = client.get(f"/api/containers/{container.id}/items", headers=admin_headers)
    assert items.status_code == 200, items.text
    assert round(items.json()[0]["computed_volume_m3"], 3) == 123.4   # 1234 KAR × 0,1 m³


def test_migration_sql_fast_paths_equal_runtime_parser():
    """Szybkie ścieżki SQL migracji (PG) dają to samo co parser aplikacji — emulacja
    regexu i replace() na próbkach; wiersze spoza wzorców liczy parser."""
    import re
    spec = importlib.util.spec_from_file_location("mig_typed001", _MIG)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    samples = ["3", "-3", "12.5", "1.234", "742,000", "12,5", "1.234,000", "1.234.567,5",
               "99999999999.999", "123456789012", "1.234.567.890,1", "1,5,5", " 7 ", "1.2345"]
    matched = 0
    for raw in samples:
        for regex, expr in mig._FAST_PATHS.values():
            if re.search(regex, raw.strip()):
                matched += 1
                sql_value = raw.strip()
                if "replace" in expr:
                    sql_value = sql_value.replace(".", "").replace(",", ".")
                assert Decimal(sql_value).quantize(Decimal("0.001")) == parse_quantity(raw), raw
    assert matched >= 8


def test_migration_backfills_existing_rows(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("mig_typed001", _MIG)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    assert mig.down_revision == "chk001"
    eng = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    Base.metadata.create_all(eng)
    with eng.begin() as conn:   # stan sprzed migracji: bez typowanych kolumn
        for table, col in (("order_items", "quantity_num"), ("purchase_orders", "ready_on"),
                           ("purchase_orders", "oem_sample_on"),
                           ("goods_receipt_lines", "qty_received_num")):
            conn.exec_driver_sql(f"ALTER TABLE {table} DROP COLUMN {col}")
        for i, qty in enumerate(("1.234,000", "12,5", "abc", ""), start=1):
            conn.execute(text(
                "INSERT INTO order_items (id, company_id, order_number, position, material, "
                "description, quantity, unit, net_weight, gross_weight, volume, volume_unit, "
                "created_at) VALUES (:i, 1, '45', :p, '', '', :q, '', '', '', '', '', "
                "'2026-01-01')"), {"i": i, "p": str(i), "q": qty})

    def run(fn):
        with eng.connect() as conn:
            monkeypatch.setattr(mig, "op", Operations(MigrationContext.configure(conn)))
            fn()
            conn.commit()

    run(mig.upgrade)
    with Session(eng) as db:
        got = dict(db.execute(select(OrderItem.id, OrderItem.quantity_num)).all())
    assert got == {1: Decimal("1234.000"), 2: Decimal("12.500"), 3: None, 4: None}
    run(mig.downgrade)
    assert "quantity_num" not in {c["name"] for c in inspect(eng).get_columns("order_items")}
    eng.dispose()
