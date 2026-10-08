"""Kontrole dokumentu (etap 3 profilu dostawcy): jednostki podstawowa/uzupełniająca, cena
za jednostkę podstawową, waga netto z PL, suma pozycji ↔ faktura, CI ↔ PL, CI ↔ SAP.
Dane syntetyczne: puste PDF (pypdf) + tekst/tabele podstawione przez szwy splittera."""
import io
import itertools
from decimal import Decimal

from pypdf import PdfWriter
from sqlalchemy import select

from app.config import settings
from app.invoices import checks, extractor, splitter
from app.models import (
    Company,
    Material,
    OrderItem,
    SapOrder,
    Supplier,
    SupplierDocProfile,
    UomConversion,
)

CI = "COMMERCIAL INVOICE Invoice No.: T-1"
PL = "PACKING LIST No. & date of invoice T-1"
CI_TABLE = [["Item No.", "Description", "Qty", "Unit", "Amount"],
            ["A1", "Gloves", "155", "CTN", "1,550.00"],
            ["B2", "Unknown", "5", "", "10.00"],
            ["TOTAL", "", "", "", "1,560.00"]]
PL_TABLE = [["Item No.", "Qty", "N.W. (kg)"],
            ["A1", "153", "310"]]


_PDF_SEQ = itertools.count()


def _pdf(pages: int) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    # unikalna treść: blokada dubla paczki (audyt #2) porównuje pliki — testy wgrywające
    # „ten sam” zestaw kilka razy symulują różne dokumenty
    writer.add_metadata({"/Title": f"test-{next(_PDF_SEQ)}"})
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _setup(db, monkeypatch, tmp_path, tol_qty=0.0):
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))
    monkeypatch.setattr(splitter, "page_texts", lambda p: [CI, PL])
    monkeypatch.setattr(extractor, "read_pages", lambda p: [(PL, [PL_TABLE])]
                        if "_packing_list" in p else [(CI, [CI_TABLE])])
    company = db.scalars(select(Company)).first()
    sup = Supplier(name="Acme", client_company_id=company.id)
    sup.doc_profile = SupplierDocProfile(status="active", tol_amount_pct=0.5, tol_qty_pct=tol_qty)
    db.add_all([sup, UomConversion(ref_norm="A1", unit_from="CTN", unit_to="PCS", factor=100),
                Material(ref_code="A1", ref_norm="A1", base_uom="SZT", name_pl="Rękawice",
                         tariff_cn="40151900", suppl_unit="pary", suppl_factor=0.5)])
    db.commit()
    return company, sup


def _upload_and_check(client, headers, db, company, sup) -> dict:
    cid = client.post("/api/containers", headers=headers, json={
        "container_no": "MSDU0806613", "company_id": company.id, "supplier_id": sup.id}).json()["id"]
    db.add_all([SapOrder(company_id=company.id, order_number="4500000001", container_id=cid),
                OrderItem(company_id=company.id, order_number="4500000001", position="10",
                          material="A1", quantity="15500", unit="SZT")])
    db.commit()
    batch = client.post(f"/api/containers/{cid}/invoice-batches", headers=headers,
                        files=[("pdf", ("cipl.pdf", io.BytesIO(_pdf(2)), "application/pdf"))]).json()
    invoice = next(j for j in batch["jobs"] if j["doc_kind"] == "invoice")
    resp = client.get(f"/api/invoice-jobs/{invoice['id']}/checks", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_checks_units_weights_and_tolerances(client, admin_headers, db_session,
                                             monkeypatch, tmp_path):
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    out = _upload_and_check(client, admin_headers, db_session, company, sup)
    assert out["profile"] == {"supplier": "Acme", "status": "active"}
    assert out["amount"] == {"value": "1560", "reference": "1560", "diff_pct": 0.0, "ok": True}
    a1 = next(r for r in out["refs"] if r["ref"] == "A1")
    # 155 kart. × 100 = 15 500 szt.; pary = 0,5 × szt.; cena = 1550 / 15500
    assert (a1["qty_base"], a1["qty_suppl"], a1["suppl_unit"], a1["price_base"]) == \
        ("15500", "7750", "pary", "0.1")
    assert a1["weight_net"] == "310" and a1["missing"] == []
    assert a1["ci_order"]["ok"] is True
    # CI 155 vs PL 153 (+1,31%) przy tolerancji 0% → rozbieżność
    assert a1["ci_pl"] == {"value": "155", "reference": "153", "diff_pct": 1.31, "ok": False}
    assert out["ok"] is False
    b2 = next(r for r in out["refs"] if r["ref"] == "B2")
    assert not b2["matched"] and {"cn", "name_pl", "weight"} <= set(b2["missing"])
    assert b2["ci_pl"] is None and b2["ci_order"] is None


def test_checks_pass_within_qty_tolerance(client, admin_headers, db_session,
                                          monkeypatch, tmp_path):
    company, sup = _setup(db_session, monkeypatch, tmp_path, tol_qty=2.0)
    out = _upload_and_check(client, admin_headers, db_session, company, sup)
    assert out["ok"] is True and out["tol_qty_pct"] == 2.0


def test_within_boundaries():
    assert checks.within(Decimal("100.5"), Decimal("100"), 0.5)        # na granicy
    assert not checks.within(Decimal("100.51"), Decimal("100"), 0.5)   # poza
    assert checks.within(Decimal("99.9"), Decimal("100"), 0.5)         # w granicy
    assert checks.within(Decimal("0"), Decimal("0"), 0)
    assert not checks.within(Decimal("1"), Decimal("0"), 50)


def test_order_from_invoice_header_suggested_then_linked_and_checks_supplier(
        client, admin_headers, db_session, monkeypatch, tmp_path):
    """FICTIVA (2026-09-29): „Order no. : 4700600638” w nagłówku faktury → zamówienie EKKO
    bez kontenera NIE jest przypinane samo (2026-10-01: zła faktura psuła dane zamówień),
    tylko podpowiadane; przypina je dopiero człowiek. Kontrola porównuje ilości z EKPO
    i dostawcę zamówienia (LIFNR) z dostawcą faktury (kod SAP z LFA1) także przed przypięciem."""
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    ci_text = CI + "\nOrder no. : 4700600638"
    monkeypatch.setattr(splitter, "page_texts", lambda p: [ci_text, PL])
    monkeypatch.setattr(extractor, "read_pages", lambda p: [(PL, [PL_TABLE])]
                        if "_packing_list" in p else [(ci_text, [CI_TABLE])])
    sup.sap_code = "10004408"
    other = Supplier(name="Inny", sap_code="10009999", client_company_id=company.id)
    db_session.add_all([other,
                        SapOrder(company_id=company.id, order_number="4700600638",
                                 supplier_sap="10004408"),
                        OrderItem(company_id=company.id, order_number="4700600638", position="10",
                                  material="A1", quantity="15500", unit="SZT")])
    db_session.commit()
    cid = client.post("/api/containers", headers=admin_headers, json={
        "container_no": "MSDU0806613", "company_id": company.id, "supplier_id": sup.id}).json()["id"]
    batch = client.post(f"/api/containers/{cid}/invoice-batches", headers=admin_headers,
                        files=[("pdf", ("cipl.pdf", io.BytesIO(_pdf(2)), "application/pdf"))]).json()
    job = next(j for j in batch["jobs"] if j["doc_kind"] == "invoice")
    db_session.expire_all()
    order = db_session.scalar(select(SapOrder).where(SapOrder.order_number == "4700600638"))
    assert order.container_id is None                                   # nic samo się nie przypina
    url = f"/api/invoice-jobs/{job['id']}"
    assert client.get(f"{url}/conformity", headers=admin_headers).json()["to_link"] == ["4700600638"]
    out = client.get(f"{url}/checks", headers=admin_headers).json()
    assert next(r for r in out["refs"] if r["ref"] == "A1")["ci_order"]["ok"] is True
    assert client.post(f"{url}/link-orders", headers=admin_headers).json() == ["4700600638"]
    db_session.expire_all()
    assert order.container_id == cid                                    # przypięte przez człowieka
    assert client.get(f"{url}/conformity", headers=admin_headers).json()["to_link"] == []
    out = client.get(f"/api/invoice-jobs/{job['id']}/checks", headers=admin_headers).json()
    a1 = next(r for r in out["refs"] if r["ref"] == "A1")
    assert a1["ci_order"]["ok"] is True                                 # 155 kart. = 15 500 szt.
    assert out["supplier"]["ok"] is True and out["supplier"]["orders"] == ["4700600638"]
    assert out["supplier"]["order_suppliers"] == [{"sap_code": "10004408", "name": "Acme"}]

    order.supplier_sap = "10009999"                                    # zamówienie innego dostawcy
    db_session.commit()
    out = client.get(f"/api/invoice-jobs/{job['id']}/checks", headers=admin_headers).json()
    assert out["supplier"]["ok"] is False and out["ok"] is False
    assert out["supplier"]["order_suppliers"][0]["name"] == "Inny"


def test_order_numbers_regex():
    from app.invoices.orders_link import order_numbers
    assert order_numbers("Order no. : 4700600638 / 4500621905, 44000000001 4700600638") == \
        ["4700600638", "4500621905"]


def test_order_by_invoice_number_in_ekko_supplier_order(
        client, admin_headers, db_session, monkeypatch, tmp_path):
    """2026-09-29: EKKO „Zamówienie dostawcy” = numer faktury FICTIVA (260101E0001) —
    zamówienie znalezione (podpowiedź do przypięcia), choć faktura nie podaje „Order no.”."""
    company, sup = _setup(db_session, monkeypatch, tmp_path)   # CI: „Invoice No.: T-1”, bez numeru PO
    db_session.add_all([SapOrder(company_id=company.id, order_number="4700600638",
                                 supplier_order_no="T-1-X"),        # inny numer — nie ten
                        SapOrder(company_id=company.id, order_number="4700600639",
                                 supplier_order_no="T-1"),
                        OrderItem(company_id=company.id, order_number="4700600639", position="10",
                                  material="A1", quantity="15500", unit="SZT")])
    db_session.commit()
    cid = client.post("/api/containers", headers=admin_headers, json={
        "container_no": "MSDU0806613", "company_id": company.id, "supplier_id": sup.id}).json()["id"]
    batch = client.post(f"/api/containers/{cid}/invoice-batches", headers=admin_headers,
                        files=[("pdf", ("cipl.pdf", io.BytesIO(_pdf(2)), "application/pdf"))]).json()
    job = next(j for j in batch["jobs"] if j["doc_kind"] == "invoice")
    db_session.expire_all()
    linked = {o.order_number: o.container_id for o in db_session.scalars(select(SapOrder))}
    assert linked == {"4700600638": None, "4700600639": None}
    assert client.get(f"/api/invoice-jobs/{job['id']}/conformity",
                      headers=admin_headers).json()["to_link"] == ["4700600639"]
    out = client.get(f"/api/invoice-jobs/{job['id']}/checks", headers=admin_headers).json()
    assert next(r for r in out["refs"] if r["ref"] == "A1")["ci_order"]["ok"] is True
