"""XML SADUE z faktur (invoices/sad_export): grupy CN × TARIC × kraj pochodzenia, zgodność z naszym
czytnikiem draftu (sad_xml — ten sam format, który agencja odsyła), blokady, endpoint i mail."""
import datetime

import pytest
from sqlalchemy import select

from app.invoices import sad_export, sad_xml
from app.models import (Company, InvoiceBatch, InvoiceDocKind, InvoiceItem, InvoiceJob, InvoiceJobStatus,
                        Material, Supplier, SupplierDocProfile, SupplierMaterial)
from tests.conftest import login
from tests.test_invoice_agency_mail import _assign_agency, _ready_batch
from tests.test_invoices_api import _container, fake_pdf  # noqa: F401


def _batch(client, headers, db, currency="usd", items=None):
    company = db.scalars(select(Company)).first()
    sup = Supplier(name="Fictiva Ltd", country="cn", street="No 8 Road", city="Ningbo", zip="315000",
                   client_company_id=company.id)
    sup.doc_profile = SupplierDocProfile(status="draft", currency=currency)
    a1 = Material(ref_code="A1", ref_norm="A1", base_uom="SZT", tariff_cn="4015 19 00", name_pl="Rękawice")
    b2 = Material(ref_code="B2", ref_norm="B2", base_uom="SZT", tariff_cn="40151900", name_pl="Rękawice nitrylowe")
    c3 = Material(ref_code="C3", ref_norm="C3", base_uom="SZT", tariff_cn="90183900",
                  customs_code="9018390010", name_pl="Cewnik")
    db.add_all([sup, a1, b2, c3])
    db.flush()
    db.add(SupplierMaterial(supplier_id=sup.id, material_id=b2.id, origin_country="VN"))
    db.commit()
    cid = _container(client, headers, company_id=company.id, supplier_id=sup.id)
    batch = InvoiceBatch(container_id=cid, supplier_id=sup.id)
    db.add(batch)
    db.flush()
    job = InvoiceJob(batch_id=batch.id, filename="ci.pdf", stored_name="ci.pdf", status=InvoiceJobStatus.confirmed,
                     invoice_number="E6720", delivery_terms="FOB Ningbo")
    proforma = InvoiceJob(batch_id=batch.id, filename="pi.pdf", stored_name="pi.pdf", doc_kind=InvoiceDocKind.proforma,
                          status=InvoiceJobStatus.confirmed, invoice_number="PI-9")
    db.add_all([job, proforma])
    db.flush()
    db.add_all(items(job, proforma) if items else [
        InvoiceItem(job_id=job.id, line_no=1, master_ref="A1", amount="1,000.00", weight_net="10",
                    weight_gross="12", cartons="5"),
        InvoiceItem(job_id=job.id, line_no=2, master_ref="A1", amount="500.00", cartons="3"),
        InvoiceItem(job_id=job.id, line_no=3, master_ref="B2", amount="200", weight_net="2", weight_gross="3",
                    cartons="1"),
        InvoiceItem(job_id=proforma.id, line_no=1, master_ref="C3", amount="99.5", weight_net="1",
                    weight_gross="1.5", cartons="2"),
        InvoiceItem(job_id=job.id, line_no=4, raw_ref="X9", amount="999", skipped=True)])
    db.commit()
    return db.get(InvoiceBatch, batch.id)


def test_xml_groups_and_reads_back_with_our_parser(client, admin_headers, db_session):
    batch = _batch(client, admin_headers, db_session)
    content, warnings = sad_export.build(db_session, batch, now=datetime.datetime(2026, 10, 7, 12, 0))
    fields, docs = sad_xml.parse(content)
    assert (fields["currency"], fields["country_dispatch"], fields["container"]) == ("USD", "CN", "MSDU0806613")
    assert fields["total"] == "1799.5"                      # bez pominiętej pozycji
    assert [(i["cn"], i["origin"], i["value"], i["net_mass"]) for i in fields["items"]] == [
        ("40151900", "CN", "1500", "10"), ("40151900", "VN", "200", "2"), ("90183900", "CN", "99.5", "1")]
    assert docs.split("\n") == ["E6720", "PI-9"]
    text = content.decode()
    assert 'KodTaric="10"' in text and 'OpisTowaru="Rękawice"' in text and 'LiczbaOpak="8"' in text
    assert 'RodzajSADu' not in text and '<P20WarDostawy Kod="FOB" Miejsce="NINGBO"' in text
    assert 'KodDokum="N325" NrDokum="PI-9"' in text and 'Nazwa="Fictiva Ltd"' in text
    assert warnings == []


def test_blocks_unmatched_ref_missing_cn_and_currency(client, admin_headers, db_session):
    batch = _batch(client, admin_headers, db_session, items=lambda job, _: [
        InvoiceItem(job_id=job.id, line_no=1, raw_ref="NOPE", amount="1"),
        InvoiceItem(job_id=job.id, line_no=2, master_ref="A1", amount="1")])
    with pytest.raises(sad_export.SadExportError, match="NOPE \\(bez dopasowania REF\\)"):
        sad_export.build(db_session, batch)
    db_session.scalars(select(Material).where(Material.ref_code == "A1")).one().tariff_cn = "4015"
    batch.supplier.doc_profile.currency = ""
    db_session.commit()
    with pytest.raises(sad_export.SadExportError, match="waluty"):
        sad_export.build(db_session, batch)
    batch.supplier.doc_profile.currency = "USD"
    db_session.commit()
    with pytest.raises(sad_export.SadExportError, match="A1 \\(brak 8-cyfrowego CN\\)"):
        sad_export.build(db_session, batch)


def test_warns_about_missing_weights_and_cartons(client, admin_headers, db_session):
    batch = _batch(client, admin_headers, db_session, items=lambda job, _: [
        InvoiceItem(job_id=job.id, line_no=1, master_ref="C3", amount="5", weight_net="1")])
    _, warnings = sad_export.build(db_session, batch)
    assert warnings == ["XML: CN 90183900 (CN) bez masy brutto, liczby kartonów — agencja uzupełni ręcznie."]


def test_endpoint_download_conflict_and_isolation(client, admin_headers, fake_pdf, db_session):  # noqa: F811
    batch = _batch(client, admin_headers, db_session)
    resp = client.get(f"/api/invoice-batches/{batch.id}/sadue.xml", headers=admin_headers)
    assert resp.status_code == 200 and resp.headers["content-disposition"] == 'attachment; filename="SAD_MSDU0806613.xml"'
    assert sad_xml.parse(resp.content) is not None
    other = next(c["id"] for c in client.get("/api/companies", headers=admin_headers).json()
                 if c["id"] != batch.container.company_id)
    client.post("/api/users", headers=admin_headers, json={
        "login": "zak", "password": "haslo123", "role": "purchasing", "company_id": other})
    assert client.get(f"/api/invoice-batches/{batch.id}/sadue.xml",
                      headers=login(client, "zak", "haslo123")).status_code == 404
    _, bid = _ready_batch(client, admin_headers)               # kartoteka testowa: CN „9018” (4 cyfry)
    resp = client.get(f"/api/invoice-batches/{bid}/sadue.xml", headers=admin_headers)
    assert resp.status_code == 409


def test_mail_attaches_xml_or_says_why_not(client, admin_headers, fake_pdf, db_session):  # noqa: F811
    cid, bid = _ready_batch(client, admin_headers)
    _assign_agency(db_session, cid)
    preview = client.get(f"/api/invoice-batches/{bid}/agency-mail/preview", headers=admin_headers).json()
    assert not any(a["kind"] == "sadue" for a in preview["attachments"])
    assert any(w.startswith("Bez XML do WinSAD:") for w in preview["warnings"])

    sup = Supplier(name="Fictiva Ltd", country="CN")
    sup.doc_profile = SupplierDocProfile(status="draft", currency="USD")
    db_session.add(sup)
    for material in db_session.scalars(select(Material)):
        material.tariff_cn = "90183900"
    db_session.flush()
    db_session.get(InvoiceBatch, bid).supplier_id = sup.id
    db_session.commit()
    preview = client.get(f"/api/invoice-batches/{bid}/agency-mail/preview", headers=admin_headers).json()
    assert [a["name"] for a in preview["attachments"]][2] == "SAD_MSDU0806613.xml"
    assert preview["attachments"][2]["kind"] == "sadue"
