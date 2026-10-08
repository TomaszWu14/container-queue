"""Import zamówień zakupowych z arkusza ETD (/api/import/purchase-orders)."""
import datetime
import io

from openpyxl import Workbook
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Company, Container, PurchaseOrder
from tests.conftest import login

# nagłówki 1:1 z realnym arkuszem ETD (angielskie, część wielolinijkowa)
ETD_HEADER = [
    "Order No.", "ETD", "Supplier", "PI No.", "Products", "CBM",
    "STANDARD TT OR LONG TT ", "by sea or by train",
    "STATUS YES/NO - decision of the purchasing department", "Port of departure",
    "Container", "Expected Inland Charge\nMax. Amount/40'HQ", "Amount", "Ready Date",
    "Date of OEM \nSample", "Shipper's Contact", "Consignee", "Port of \nDischarge",
    "Forwarder",
]


def _etd_xlsx(rows):
    wb = Workbook()
    ws = wb.active
    ws.append(ETD_HEADER)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _row(order_no, cbm=55.5, supplier="DEMO MEDICAL"):
    return [order_no, datetime.datetime(2026, 8, 1), supplier, "PI2604080071",
            "Wound Dressing", cbm, "STANDARD TT", "by sea", "YES", "WUHAN", "40'HQ",
            "RMB2800", 22075.8, "2026.7.25", "Confirmed",
            "Kontakt kontakt@dostawca-demo.example", "ACME", "GDANSK", "Delta brokers"]


def test_import_etd_maps_dry_run_then_commits(client):
    hdr = login(client)
    xlsx = _etd_xlsx([_row("4500624622"), _row("4500626710", cbm=66.7)])

    # dry-run: liczy, nic nie zapisuje
    dry = client.post("/api/import/purchase-orders?company_code=ACME&dry_run=true",
                      headers=hdr, files={"file": ("etd.xlsx", xlsx)})
    assert dry.status_code == 200, dry.text
    assert dry.json()["counts"] == {"total": 2, "new": 2, "updated": 0,
                                    "linked": 0, "duplicate": 0}
    db = SessionLocal()
    try:
        assert db.scalar(select(PurchaseOrder)) is None  # dry-run nie zapisał
    finally:
        db.close()

    # commit: zapisuje + poprawnie mapuje pola
    real = client.post("/api/import/purchase-orders?company_code=ACME&dry_run=false",
                       headers=hdr, files={"file": ("etd.xlsx", xlsx)})
    assert real.status_code == 200, real.text
    assert real.json()["counts"]["new"] == 2
    db = SessionLocal()
    try:
        po = db.scalar(select(PurchaseOrder).where(PurchaseOrder.order_no == "4500624622"))
        assert po is not None
        assert po.supplier == "DEMO MEDICAL" and po.container_type == "40'HQ"
        assert po.etd == datetime.date(2026, 8, 1)
        assert float(po.cbm) == 55.5
        assert po.consignee == "ACME" and po.ready_date == "2026.7.25"
        assert po.oem_sample_date == "Confirmed"  # tekst zachowany, nie data
        assert po.container_id is None  # brak kontenera → niepowiązane
    finally:
        db.close()


def test_reimport_is_idempotent_and_updates(client):
    hdr = login(client)
    client.post("/api/import/purchase-orders?company_code=ACME&dry_run=false",
                headers=hdr, files={"file": ("etd.xlsx", _etd_xlsx([_row("4500624622")]))})
    # ponowny import tego samego numeru z inną wartością → update, nie duplikat
    again = client.post("/api/import/purchase-orders?company_code=ACME&dry_run=false",
                        headers=hdr,
                        files={"file": ("etd.xlsx", _etd_xlsx([_row("4500624622", cbm=99.9)]))})
    assert again.json()["counts"] == {"total": 1, "new": 0, "updated": 1,
                                      "linked": 0, "duplicate": 0}
    db = SessionLocal()
    try:
        rows = db.scalars(select(PurchaseOrder).where(
            PurchaseOrder.order_no == "4500624622")).all()
        assert len(rows) == 1 and float(rows[0].cbm) == 99.9
    finally:
        db.close()


def test_no_false_link_on_substring(client):
    """order_no będący fragmentem numeru kontenera NIE może się zlinkować
    (4500024 vs 4500624622) — dopasowanie po całych tokenach, nie substring."""
    hdr = login(client)
    db = SessionLocal()
    try:
        company = db.scalar(select(Company).where(Company.code == "ACME"))
        db.add(Container(company_id=company.id, container_no="MSKU7026499",
                         order_numbers="4500624622"))
        db.commit()
    finally:
        db.close()
    res = client.post("/api/import/purchase-orders?company_code=ACME&dry_run=false",
                      headers=hdr, files={"file": ("etd.xlsx", _etd_xlsx([_row("4500024")]))})
    assert res.json()["counts"]["linked"] == 0
    db = SessionLocal()
    try:
        po = db.scalar(select(PurchaseOrder).where(PurchaseOrder.order_no == "4500024"))
        assert po.container_id is None
    finally:
        db.close()


def test_auto_links_to_container_by_order_no(client):
    hdr = login(client)
    db = SessionLocal()
    try:
        company = db.scalar(select(Company).where(Company.code == "ACME"))
        db.add(Container(company_id=company.id, container_no="MSKU7026499",
                         order_numbers="4500624622 4500099999"))
        db.commit()
    finally:
        db.close()
    # order_no złożony: jeden z tokenów pasuje do order_numbers kontenera
    res = client.post("/api/import/purchase-orders?company_code=ACME&dry_run=false",
                      headers=hdr,
                      files={"file": ("etd.xlsx",
                                      _etd_xlsx([_row("4500624622 & 4500055555")]))})
    assert res.json()["counts"]["linked"] == 1
    db = SessionLocal()
    try:
        po = db.scalar(select(PurchaseOrder).where(PurchaseOrder.order_no == "4500624622 & 4500055555"))
        container = db.scalar(select(Container).where(Container.container_no == "MSKU7026499"))
        assert po.container_id == container.id
    finally:
        db.close()
