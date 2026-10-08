"""Faktury (CIPL) → Excel przez API: upload z cięciem, dopasowanie do master daty,
weryfikacja, zatwierdzanie, Excel w załącznikach, role i izolacja spółek.

PDF-y są prawdziwe (pypdf, puste strony), a tekst stron i tabele podstawiamy przez szwy
`splitter.page_texts` / `extractor.read_pages` — testy nie zależą od układu konkretnej faktury.
"""
import io
import itertools

import pytest
from openpyxl import Workbook, load_workbook
from pypdf import PdfWriter

from app.config import settings
from app.invoices import extractor, splitter
from tests.conftest import login

CI_TEXT = ("COMMERCIAL INVOICE\nInvoice No.: FV/2026/9\nCONTAINER No.:MSDU0806613\n"
           "Terms of Delivery:\nFOB QINGDAO")
PL_TEXT = "PACKING LIST No. & date of invoice FV/2026/9 CTNS"

INVOICE_TABLE = [
    ["No", "Item No.", "Description", "Qty", "Unit", "Unit price", "Amount"],
    ["1", "NL753-S-40", "Catheter", "1,000", "PCS", "0.25", "250.00"],
    ["2", "MSK", "Mask (X vs X1)", "20", "CTN", "10", "200.00"],
    ["3", "NOPE-1", "Unknown", "5", "PCS", "1", "5.00"],
    ["", "TOTAL", "", "1,025", "", "", "455.00"],
]
PL_TABLE = [
    ["Item No.", "Description", "Qty", "N.W. (kg)", "G.W. (kg)", "CTNS"],
    ["NL753-S-40", "Catheter", "1,000", "12.5", "13.2", "3"],
]


_PDF_SEQ = itertools.count()


def _pdf(pages: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    # unikalna treść: blokada dubla paczki (audyt #2) porównuje pliki — testy wgrywające
    # „ten sam” zestaw kilka razy symulują różne dokumenty
    writer.add_metadata({"/Title": f"test-{next(_PDF_SEQ)}"})
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _xlsx(rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


MASTER_ROWS = [
    ["", "", "", "", "", "", "KAR"],
    ["ref_code", "opis_pl", "Kod CN", "SENT", "Podstawowa jednostka miary", "EAN",
     "Ilość podstawowej jednostki miary"],
    ["NL753-S-40", "Cewnik", "9018", "TAK", "SZT", "5907996800810", "240"],
    ["MSK1", "Maska A", "6307", "", "SZT", "", ""],
    ["MSK2", "Maska B", "6307", "", "SZT", "", ""],
]


@pytest.fixture()
def fake_pdf(monkeypatch, tmp_path):
    """Upload: strony [CI, PL] → cięcie na fakturę i packing listę; tabele wg nazwy części."""
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))

    def page_texts(path):
        if "_doc1_invoice" in path:
            return [CI_TEXT]
        if "_doc2_packing_list" in path:
            return [PL_TEXT]
        return [CI_TEXT, PL_TEXT]

    def read_pages(path):
        if "_doc2_packing_list" in path:
            return [(PL_TEXT, [PL_TABLE])]
        return [(CI_TEXT, [INVOICE_TABLE])]

    monkeypatch.setattr(splitter, "page_texts", page_texts)
    monkeypatch.setattr(extractor, "read_pages", read_pages)
    return tmp_path


def _company_id(client, headers, index=0):
    return client.get("/api/companies", headers=headers).json()[index]["id"]


def _container(client, headers, company_id=None, no="MSDU0806613", supplier_id=None):
    body = {"container_no": no, "company_id": company_id or _company_id(client, headers)}
    if supplier_id:
        body["supplier_id"] = supplier_id
    resp = client.post("/api/containers", headers=headers, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _import_master(client, headers, rows=MASTER_ROWS, dry_run=False):
    resp = client.post(f"/api/materials/import?dry_run={str(dry_run).lower()}", headers=headers,
                       files={"file": ("master.xlsx", io.BytesIO(_xlsx(rows)),
                                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _upload(client, headers, cid, pages=2, name="cipl.pdf", data=None):
    return client.post(f"/api/containers/{cid}/invoice-batches", headers=headers,
                       files=[("pdf", (name, io.BytesIO(_pdf(pages)), "application/pdf"))],
                       data=data or {})


def test_master_import_dry_run_then_commit_and_search(client, admin_headers):
    preview = _import_master(client, admin_headers, dry_run=True)
    assert preview == {"dry_run": True, "counts": {"total": 3, "new": 3, "updated": 0, "conversions": 1}}
    assert client.get("/api/materials/count", headers=admin_headers).json() == {"count": 0}
    done = _import_master(client, admin_headers)
    assert done["dry_run"] is False and done["counts"]["new"] == 3
    again = _import_master(client, admin_headers)
    assert again["counts"] == {"total": 3, "new": 0, "updated": 3, "conversions": 1}
    found = client.get("/api/materials?q=nl753s40", headers=admin_headers).json()
    assert [m["ref_code"] for m in found] == ["NL753-S-40"]
    assert found[0]["sent"] is True and found[0]["tariff_cn"] == "9018" and found[0]["ean"] == "5907996800810"


def test_master_import_requires_admin_and_xlsx(client, admin_headers):
    client.post("/api/users", headers=admin_headers, json={
        "login": "log", "password": "haslo123", "role": "logistics",
        "company_id": _company_id(client, admin_headers)})
    log = login(client, "log", "haslo123")
    resp = client.post("/api/materials/import", headers=log,
                       files={"file": ("m.xlsx", io.BytesIO(_xlsx(MASTER_ROWS)), "application/octet-stream")})
    assert resp.status_code == 403
    resp = client.post("/api/materials/import", headers=admin_headers,
                       files={"file": ("m.csv", io.BytesIO(b"a;b"), "text/csv")})
    assert resp.status_code == 422
    resp = client.post("/api/materials/import", headers=admin_headers,
                       files={"file": ("m.xlsx", io.BytesIO(_xlsx([["kolumna", "inna"], ["1", "2"]])),
                                       "application/octet-stream")})
    assert resp.status_code == 422   # brak kolumny REF


def test_upload_splits_extracts_matches_and_weights(client, admin_headers, fake_pdf):
    _import_master(client, admin_headers)
    cid = _container(client, admin_headers)
    resp = _upload(client, admin_headers, cid)
    assert resp.status_code == 201, resp.text
    batch = resp.json()
    assert batch["total"] == 1 and batch["confirmed"] == 0 and batch["ready"] is False
    kinds = [(j["doc_kind"], j["status"]) for j in batch["jobs"]]
    assert kinds == [("invoice", "extracted"), ("packing_list", "packing_list")]
    inv = batch["jobs"][0]
    assert inv["invoice_number"] == "FV/2026/9" and inv["container_no"] == "MSDU0806613"
    assert inv["delivery_terms"] == "FOB QINGDAO" and inv["items_count"] == 3

    detail = client.get(f"/api/invoice-jobs/{inv['id']}", headers=admin_headers).json()
    items = {i["raw_ref"]: i for i in detail["items"]}
    cath = items["NL753-S-40"]
    assert cath["match_status"] == "matched" and cath["name_pl"] == "Cewnik"
    assert cath["tariff_cn"] == "9018" and cath["sent"] is True
    assert cath["weight_net"] == "12.5" and cath["weight_gross"] == "13.2" and cath["weight_source"] == "pl"
    assert cath["cartons"] == "3" and cath["amount"] == "250"
    # MSK → kandydaci MSK1/MSK2: niejednoznaczne; NOPE-1: brak w master
    assert items["MSK"]["match_status"] == "ambiguous" and items["MSK"]["master_ref"] == ""
    assert items["NOPE-1"]["match_status"] == "unmatched" and items["NOPE-1"]["weight_source"] == "brak"
    # pliki części leżą w uploads_dir
    assert (fake_pdf / batch["jobs"][0]["filename"]).exists() is False   # oryginał ma prefiks
    assert any(p.name.endswith("_doc1_invoice.pdf") for p in fake_pdf.iterdir())


def test_review_confirm_export_and_download(client, admin_headers, fake_pdf):
    _import_master(client, admin_headers)
    cid = _container(client, admin_headers)
    batch = _upload(client, admin_headers, cid).json()
    job = batch["jobs"][0]
    items = client.get(f"/api/invoice-jobs/{job['id']}", headers=admin_headers).json()["items"]
    by_ref = {i["raw_ref"]: i for i in items}

    # zatwierdzenie zablokowane przez pozycję niejednoznaczną
    resp = client.put(f"/api/invoice-jobs/{job['id']}/review", headers=admin_headers,
                      json={"items": [], "confirm": True, "conformity_reason": "test: brak danych SAP"})
    assert resp.status_code == 409 and "niejednoznaczne" in resp.json()["detail"]
    # eksport paczki niegotowej → 409
    assert client.post(f"/api/invoice-batches/{batch['id']}/export", headers=admin_headers).status_code == 409

    # operator wskazuje MSK2, poprawia ilość, pomija nieznany REF, zatwierdza
    body = {"items": [
        {"id": by_ref["MSK"]["id"], "master_ref": "MSK2", "qty": "20", "amount": "200",
         "weight_net": "", "weight_gross": ""},
        {"id": by_ref["NOPE-1"]["id"], "master_ref": "", "qty": "5", "amount": "5",
         "weight_net": "", "weight_gross": "", "skipped": True},
        {"id": by_ref["NL753-S-40"]["id"], "master_ref": "NL753-S-40", "qty": "1000", "amount": "250",
         "weight_net": "12.5", "weight_gross": "13.2"},
    ], "confirm": True, "conformity_reason": "test: brak danych SAP"}
    resp = client.put(f"/api/invoice-jobs/{job['id']}/review", headers=admin_headers, json=body)
    assert resp.status_code == 200, resp.text
    detail = resp.json()
    assert detail["status"] == "confirmed" and detail["items_count"] == 2
    msk = next(i for i in detail["items"] if i["raw_ref"] == "MSK")
    assert msk["match_status"] == "matched" and msk["name_pl"] == "Maska B" and msk["master_ref"] == "MSK2"

    listing = client.get(f"/api/containers/{cid}/invoice-batches", headers=admin_headers).json()
    assert listing[0]["confirmed"] == 1 and listing[0]["ready"] is True   # wszystkie zatwierdzone
    assert listing[0]["excel_current"] is False                            # Excel jeszcze nie wygenerowany

    resp = client.post(f"/api/invoice-batches/{batch['id']}/export", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["ready"] is True and out["attachment_id"] and out["attachment_filename"].endswith(".xlsx")

    download = client.get(f"/api/attachments/{out['attachment_id']}/download", headers=admin_headers)
    assert download.status_code == 200
    ws = load_workbook(io.BytesIO(download.content)).active
    rows = list(ws.iter_rows(values_only=True))
    assert list(rows[0]) == ["Nr faktury", "Ilość", "REF", "Nazwa PL", "Waga netto", "Waga brutto",
                             "Przelicznik jednostki", "Kwota", "Kod celny (CN)", "SENT",
                             "Status dopasowania"]
    assert len(rows) == 3   # nagłówek + 2 pozycje (pominięta nie wchodzi)
    cath = rows[1]
    assert cath[0] == "FV/2026/9" and cath[2] == "NL753-S-40" and cath[3] == "Cewnik"
    # liczby jako komórki liczbowe (odbiorca sumuje), kod CN zostaje tekstem (wiodące zera)
    assert cath[1] == 1000 and cath[4] == 12.5 and cath[5] == 13.2 and cath[6] == 1
    assert cath[7] == 250 and cath[8] == "9018"
    assert cath[9] == "TAK" and cath[10] == "matched"
    assert rows[2][2] == "MSK2" and rows[2][9] == "NIE" and rows[2][1] == 20

    # Excel widoczny jako zwykły załącznik kontenera
    att = client.get(f"/api/containers/{cid}/attachments", headers=admin_headers).json()
    assert any(a["id"] == out["attachment_id"] for a in att)

    # poprawka po zatwierdzeniu cofa status i gotowość paczki
    resp = client.put(f"/api/invoice-jobs/{job['id']}/review", headers=admin_headers,
                      json={"items": [], "confirm": False})
    assert resp.json()["status"] == "extracted"
    listing = client.get(f"/api/containers/{cid}/invoice-batches", headers=admin_headers).json()
    assert listing[0]["ready"] is False


def test_uom_factor_from_master_conversions(client, admin_headers, fake_pdf, monkeypatch):
    """Karton → sztuki z przelicznika poziomu KAR w master dacie."""
    _import_master(client, admin_headers)
    table = [["Item No.", "Description", "Qty", "Unit", "Amount"],
             ["NL753-S-40", "Catheter", "4", "CTN", "250.00"]]
    monkeypatch.setattr(extractor, "read_pages", lambda p: [(CI_TEXT, [table])])
    monkeypatch.setattr(splitter, "page_texts", lambda p: [CI_TEXT])
    cid = _container(client, admin_headers)
    batch = _upload(client, admin_headers, cid, pages=1).json()
    item = client.get(f"/api/invoice-jobs/{batch['jobs'][0]['id']}", headers=admin_headers).json()["items"][0]
    assert item["uom_factor"] == "240"


def test_company_override_changes_name_and_cn(client, admin_headers, fake_pdf):
    _import_master(client, admin_headers)
    company = _company_id(client, admin_headers)
    mat = client.get("/api/materials?q=NL753", headers=admin_headers).json()[0]
    resp = client.put(f"/api/materials/{mat['id']}/override", headers=admin_headers,
                      json={"company_id": company, "name_pl": "Cateter (PT)", "tariff_cn": "9999",
                            "sent": False})
    assert resp.status_code == 200 and resp.json()["overrides"][0]["tariff_cn"] == "9999"
    cid = _container(client, admin_headers, company_id=company)
    batch = _upload(client, admin_headers, cid).json()
    items = client.get(f"/api/invoice-jobs/{batch['jobs'][0]['id']}", headers=admin_headers).json()["items"]
    cath = next(i for i in items if i["raw_ref"] == "NL753-S-40")
    assert cath["name_pl"] == "Cateter (PT)" and cath["tariff_cn"] == "9999" and cath["sent"] is False
    # puste nadpisanie = usunięcie
    resp = client.put(f"/api/materials/{mat['id']}/override", headers=admin_headers,
                      json={"company_id": company})
    assert resp.json()["overrides"] == []


def test_supplier_column_map_used_for_extraction(client, admin_headers, fake_pdf, monkeypatch):
    _import_master(client, admin_headers)
    company = _company_id(client, admin_headers)
    sup = client.post("/api/suppliers", headers=admin_headers, json={
        "name": "Shieldco", "company_id": company,
        "column_map": "ref=Kod towaru; qty=Sztuk; net=Wartość"}).json()
    assert sup["column_map"].startswith("ref=")
    table = [["Lp", "Kod towaru", "Nazwa", "Sztuk", "Wartość"],
             ["1", "NL753-S-40", "Cewnik", "10", "2,50"]]
    monkeypatch.setattr(extractor, "read_pages", lambda p: [(CI_TEXT, [table])])
    monkeypatch.setattr(splitter, "page_texts", lambda p: [CI_TEXT])
    cid = _container(client, admin_headers, company_id=company, supplier_id=sup["id"])
    batch = _upload(client, admin_headers, cid, pages=1).json()
    assert batch["supplier_name"] == "Shieldco"
    item = client.get(f"/api/invoice-jobs/{batch['jobs'][0]['id']}", headers=admin_headers).json()["items"][0]
    assert item["raw_ref"] == "NL753-S-40" and item["qty"] == "10" and item["amount"] == "2.5"


def test_scan_without_text_is_document_error_not_500(client, admin_headers, fake_pdf, monkeypatch):
    monkeypatch.setattr(splitter, "page_texts", lambda p: [""])
    monkeypatch.setattr(extractor, "read_pages", lambda p: [("", [])])
    cid = _container(client, admin_headers)
    batch = _upload(client, admin_headers, cid, pages=1).json()
    # pusta strona = „other” → poza pipeline'em faktur; paczka bez faktur nie jest gotowa
    assert batch["jobs"][0]["status"] == "ignored" and batch["total"] == 0
    # faktura bez rozpoznanej tabeli → status error z czytelnym komunikatem, reprocess dostępny
    monkeypatch.setattr(splitter, "page_texts", lambda p: [CI_TEXT])
    batch = _upload(client, admin_headers, cid, pages=1).json()
    job = batch["jobs"][0]
    assert job["status"] == "error" and "skan" in job["error"] and batch["errors"] == 1
    monkeypatch.setattr(extractor, "read_pages", lambda p: [(CI_TEXT, [INVOICE_TABLE])])
    resp = client.post(f"/api/invoice-jobs/{job['id']}/reprocess", headers=admin_headers)
    assert resp.status_code == 200 and resp.json()["status"] == "extracted"


def test_upload_rejects_non_pdf_and_too_many_pages(client, admin_headers, fake_pdf, monkeypatch):
    cid = _container(client, admin_headers)
    resp = client.post(f"/api/containers/{cid}/invoice-batches", headers=admin_headers,
                       files=[("pdf", ("skan.png", io.BytesIO(b"x"), "image/png"))])
    assert resp.status_code == 422
    monkeypatch.setattr(settings, "invoice_pdf_max_pages", 1)
    assert _upload(client, admin_headers, cid, pages=2).status_code == 422
    resp = client.post(f"/api/containers/{cid}/invoice-batches", headers=admin_headers,
                       files=[("pdf", ("zly.pdf", io.BytesIO(b"nie pdf"), "application/pdf"))])
    assert resp.status_code == 422


def test_roles_and_isolation(client, admin_headers, fake_pdf):
    _import_master(client, admin_headers)
    cid = _container(client, admin_headers)
    batch = _upload(client, admin_headers, cid).json()
    company = _company_id(client, admin_headers)
    wh = client.post("/api/warehouses", headers=admin_headers,
                     json={"name": "Radom", "company_id": company}).json()
    agency = client.post("/api/customs-agencies", headers=admin_headers,
                         json={"name": "Agencja A"}).json()
    for login_name, role, extra in (
            ("mag", "warehouse", {"company_id": company, "warehouse_id": wh["id"]}),
            ("agent", "customs", {"customs_agency_id": agency["id"]})):
        resp = client.post("/api/users", headers=admin_headers, json={
            "login": login_name, "password": "haslo123", "role": role, **extra})
        assert resp.status_code == 201, resp.text
        headers = login(client, login_name, "haslo123")
        assert client.get(f"/api/containers/{cid}/invoice-batches", headers=headers).status_code == 403
        assert client.get(f"/api/invoice-jobs/{batch['jobs'][0]['id']}", headers=headers).status_code == 403
    # spedytor bez przypisania — panel niedostępny dla roli
    client.post("/api/forwarders", headers=admin_headers, json={"name": "SPEDALFA"})
    fid = next(f["id"] for f in client.get("/api/forwarders", headers=admin_headers).json()
               if f["name"] == "SPEDALFA")
    client.post("/api/users", headers=admin_headers, json={
        "login": "sped.spedalfa", "password": "haslo123", "role": "forwarder", "forwarder_id": fid})
    assert client.get(f"/api/containers/{cid}/invoice-batches",
                      headers=login(client, "sped.spedalfa", "haslo123")).status_code == 403
    # zakupy innej spółki nie widzą paczki ani dokumentu (404, jak brak)
    other = _company_id(client, admin_headers, index=1)
    client.post("/api/users", headers=admin_headers, json={
        "login": "zak", "password": "haslo123", "role": "purchasing", "company_id": other})
    zak = login(client, "zak", "haslo123")
    assert client.get(f"/api/containers/{cid}/invoice-batches", headers=zak).status_code == 404
    assert client.get(f"/api/invoice-jobs/{batch['jobs'][0]['id']}", headers=zak).status_code == 404
    assert client.post(f"/api/invoice-batches/{batch['id']}/export", headers=zak).status_code == 404
    # zakupy własnej spółki: pełny dostęp do weryfikacji
    own = _container(client, admin_headers, company_id=other, no="CMAU8963315")
    own_batch = _upload(client, zak, own).json()
    assert own_batch["total"] == 1
    # usunięcie paczki kasuje pliki części, zostawia załączniki
    resp = client.delete(f"/api/invoice-batches/{batch['id']}", headers=admin_headers)
    assert resp.status_code == 204
    assert client.get(f"/api/containers/{cid}/invoice-batches", headers=admin_headers).json() == []


def test_delete_container_purges_invoice_batches(client, admin_headers, fake_pdf, db_session):
    """FK bez kaskad (Postgres): kasowanie kontenera musi zabrać pozycje/dokumenty/paczki."""
    from sqlalchemy import select

    from app.models import InvoiceBatch, InvoiceItem, InvoiceJob
    _import_master(client, admin_headers)
    cid = _container(client, admin_headers)
    batch = _upload(client, admin_headers, cid).json()
    resp = client.delete(f"/api/containers/{cid}", headers=admin_headers)
    assert resp.status_code in (200, 204), resp.text
    db_session.expire_all()
    assert db_session.scalar(select(InvoiceBatch).where(InvoiceBatch.id == batch["id"])) is None
    assert db_session.scalars(select(InvoiceJob)).all() == []
    assert db_session.scalars(select(InvoiceItem)).all() == []


def test_manual_ref_change_drops_stale_enrichment(client, admin_headers, fake_pdf):
    _import_master(client, admin_headers)
    cid = _container(client, admin_headers)
    batch = _upload(client, admin_headers, cid).json()
    job = batch["jobs"][0]
    items = client.get(f"/api/invoice-jobs/{job['id']}", headers=admin_headers).json()["items"]
    cath = next(i for i in items if i["raw_ref"] == "NL753-S-40")
    assert cath["name_pl"] == "Cewnik" and cath["sent"] is True
    # operator kasuje REF master → pozycja „brak w master” bez starej nazwy/CN/SENT
    resp = client.put(f"/api/invoice-jobs/{job['id']}/review", headers=admin_headers,
                      json={"items": [{"id": cath["id"], "master_ref": "", "qty": cath["qty"],
                                       "amount": cath["amount"]}]})
    out = next(i for i in resp.json()["items"] if i["id"] == cath["id"])
    assert out["match_status"] == "unmatched" and out["name_pl"] == "" and out["tariff_cn"] == ""
    assert out["sent"] is False and out["match_source"] == ""
    # nieznany REF wpisany ręcznie → niejednoznaczny (blokuje), też bez starego wzbogacenia
    resp = client.put(f"/api/invoice-jobs/{job['id']}/review", headers=admin_headers,
                      json={"items": [{"id": cath["id"], "master_ref": "NIE-MA", "qty": "1", "amount": "1"}]})
    out = next(i for i in resp.json()["items"] if i["id"] == cath["id"])
    assert out["match_status"] == "ambiguous" and out["name_pl"] == "" and out["master_ref"] == "NIE-MA"


def test_partial_master_import_keeps_other_fields(client, admin_headers):
    _import_master(client, admin_headers)
    done = _import_master(client, admin_headers, rows=[["ref_code", "Kod CN"], ["NL753-S-40", "3926"]])
    assert done["counts"]["updated"] == 1
    mat = client.get("/api/materials?q=NL753", headers=admin_headers).json()[0]
    assert mat["tariff_cn"] == "3926" and mat["name_pl"] == "Cewnik" and mat["base_uom"] == "SZT"
    assert mat["ean"] == "5907996800810" and mat["sent"] is True
    # kolumna obecna, komórka pusta = brak danych: nie zeruje istniejącego CN
    _import_master(client, admin_headers, rows=[["ref_code", "Kod CN", "opis_pl"],
                                                ["NL753-S-40", "", "Cewnik v2"], ["NOWY-1", "", ""]])
    mats = {m["ref_code"]: m for m in client.get("/api/materials?q=", headers=admin_headers).json()}
    assert mats["NL753-S-40"]["tariff_cn"] == "3926" and mats["NL753-S-40"]["name_pl"] == "Cewnik v2"
    assert mats["NOWY-1"]["tariff_cn"] == ""


def test_ignore_is_reversible_and_hides_counts(client, admin_headers, fake_pdf):
    _import_master(client, admin_headers)
    cid = _container(client, admin_headers)
    batch = _upload(client, admin_headers, cid).json()
    job, pl = batch["jobs"][0], batch["jobs"][1]
    out = client.post(f"/api/invoice-jobs/{job['id']}/ignore", headers=admin_headers).json()
    assert out["status"] == "ignored" and out["doc_kind"] == "invoice" and out["items_count"] == 0
    listing = client.get(f"/api/containers/{cid}/invoice-batches", headers=admin_headers).json()
    assert listing[0]["total"] == 0
    assert client.post(f"/api/invoice-jobs/{job['id']}/ignore", headers=admin_headers).status_code == 409
    # „Przywróć” = ponowna ekstrakcja: dokument wraca do paczki z pozycjami
    out = client.post(f"/api/invoice-jobs/{job['id']}/reprocess", headers=admin_headers).json()
    assert out["status"] == "extracted" and out["items_count"] == 3
    assert client.get(f"/api/containers/{cid}/invoice-batches", headers=admin_headers).json()[0]["total"] == 1
    # pominięta packing lista przestaje dawać wagi; „Przywróć” oddaje ją paczce (status PL)
    client.post(f"/api/invoice-jobs/{pl['id']}/ignore", headers=admin_headers)
    out = client.post(f"/api/invoice-jobs/{job['id']}/reprocess", headers=admin_headers).json()
    assert all(i["weight_source"] == "brak" for i in out["items"])
    back = client.post(f"/api/invoice-jobs/{pl['id']}/reprocess", headers=admin_headers).json()
    assert back["status"] == "packing_list" and back["doc_kind"] == "packing_list"
    out = client.post(f"/api/invoice-jobs/{job['id']}/reprocess", headers=admin_headers).json()
    assert any(i["weight_source"] == "pl" for i in out["items"])
    # dokument „inne” (B/L) nie jest częścią paczki — pomijanie go nic nie znaczy
    assert client.post(f"/api/invoice-jobs/{pl['id']}/ignore", headers=admin_headers).status_code == 200


def test_resave_without_changes_keeps_excel_ready(client, admin_headers, fake_pdf):
    _import_master(client, admin_headers)
    cid = _container(client, admin_headers)
    batch = _upload(client, admin_headers, cid).json()
    job = batch["jobs"][0]
    items = client.get(f"/api/invoice-jobs/{job['id']}", headers=admin_headers).json()["items"]
    body = {"items": [{"id": i["id"], "skipped": i["match_status"] != "matched"} for i in items],
            "confirm": True, "conformity_reason": "test: brak danych SAP"}
    client.put(f"/api/invoice-jobs/{job['id']}/review", headers=admin_headers, json=body)
    assert client.post(f"/api/invoice-batches/{batch['id']}/export", headers=admin_headers).json()["ready"]
    # ponowne „Zatwierdź” z identycznymi wartościami nie unieważnia Excela
    detail = client.get(f"/api/invoice-jobs/{job['id']}", headers=admin_headers).json()
    same = {"items": [{"id": i["id"], "master_ref": i["master_ref"], "qty": i["qty"], "amount": i["amount"],
                       "weight_net": i["weight_net"], "weight_gross": i["weight_gross"],
                       "skipped": i["skipped"]} for i in detail["items"]],
            "invoice_number": detail["invoice_number"], "confirm": True, "conformity_reason": "test: brak danych SAP"}
    assert client.put(f"/api/invoice-jobs/{job['id']}/review", headers=admin_headers, json=same).status_code == 200
    listing = client.get(f"/api/containers/{cid}/invoice-batches", headers=admin_headers).json()
    assert listing[0]["ready"] is True and listing[0]["excel_current"] is True
    # cofnięcie zatwierdzenia (zapis roboczy) — Excel nieaktualny, paczka niegotowa
    same["confirm"] = False
    client.put(f"/api/invoice-jobs/{job['id']}/review", headers=admin_headers, json=same)
    listing = client.get(f"/api/containers/{cid}/invoice-batches", headers=admin_headers).json()
    assert listing[0]["ready"] is False and listing[0]["excel_current"] is False


def test_delete_container_removes_invoice_files(client, admin_headers, fake_pdf):
    _import_master(client, admin_headers)
    cid = _container(client, admin_headers)
    _upload(client, admin_headers, cid)
    assert list(fake_pdf.glob("inv_*"))   # oryginał + części po cięciu
    assert client.delete(f"/api/containers/{cid}", headers=admin_headers).status_code in (200, 204)
    assert list(fake_pdf.glob("inv_*")) == []


def test_ml_history_ignores_auto_ml_matches(client, admin_headers, fake_pdf, db_session):
    """Auto-dopasowanie ML zatwierdzone „jak leci” nie wraca do historii jako decyzja operatora."""
    from sqlalchemy import select

    from app.invoices import ml
    from app.models import InvoiceItem
    _import_master(client, admin_headers)
    cid = _container(client, admin_headers)
    job = _upload(client, admin_headers, cid).json()["jobs"][0]
    items = client.get(f"/api/invoice-jobs/{job['id']}", headers=admin_headers).json()["items"]
    body = {"items": [{"id": i["id"], "master_ref": "MSK2" if i["raw_ref"] == "MSK" else None,
                       "skipped": i["raw_ref"] == "NOPE-1"} for i in items], "confirm": True, "conformity_reason": "test: brak danych SAP"}
    assert client.put(f"/api/invoice-jobs/{job['id']}/review", headers=admin_headers, json=body).status_code == 200
    db_session.expire_all()
    cath = db_session.scalar(select(InvoiceItem).where(InvoiceItem.raw_ref == "NL753-S-40"))
    cath.match_source = "ml"
    db_session.commit()
    _, examples, _, _ = ml.training_data(db_session)
    assert [(e["raw_ref"], e["master_ref"]) for e in examples] == [("MSK", "MSK2")]
