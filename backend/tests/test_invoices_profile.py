"""Profil dostawcy w ekstrakcji (etap 2): pierwszeństwo aktywnego profilu nad column_map,
fallback, znacznik PL dzieli CI/PL, słowa kluczowe rozpoznają dostawcę, ref_kind=supplier.
Dane syntetyczne: puste PDF (pypdf) + tekst/tabele podstawione przez szwy splittera."""
import io

from pypdf import PdfWriter
from sqlalchemy import select

from app.config import settings
from app.invoices import extractor, matching, profiles, splitter
from app.models import (
    Company,
    InvoiceDocKind,
    InvoiceMatchStatus,
    Material,
    Supplier,
    SupplierDocProfile,
    SupplierMaterialMap,
)

CI = "ACME TRADING CO. COMMERCIAL INVOICE Invoice No.: T-001"
WEIGHTS = "ACME TRADING CO. WEIGHT SPECIFICATION ctns n.w. g.w."
TABLE = [["Old Code", "Our Ref", "Pieces", "Value"],
         ["OLD-1", "NEW-1", "10", "5.00"]]


def _pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _supplier(db, name="Acme", status="active", **profile) -> Supplier:
    company = db.scalars(select(Company)).first()
    sup = Supplier(name=name, client_company_id=company.id, column_map="ref=Old Code; qty=Pieces")
    sup.doc_profile = SupplierDocProfile(status=status, **profile)
    db.add(sup)
    db.commit()
    return sup


def _upload(client, headers, db, sup_id=None) -> dict:
    body = {"container_no": "MSDU0806613", "company_id": db.scalars(select(Company)).first().id}
    if sup_id:
        body["supplier_id"] = sup_id
    cid = client.post("/api/containers", headers=headers, json=body).json()["id"]
    resp = client.post(f"/api/containers/{cid}/invoice-batches", headers=headers,
                       files=[("pdf", ("a.pdf", io.BytesIO(_pdf()), "application/pdf"))])
    assert resp.status_code == 201, resp.text
    return resp.json()


def _fake(monkeypatch, tmp_path, texts):
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))
    monkeypatch.setattr(splitter, "page_texts", lambda p: texts)
    monkeypatch.setattr(extractor, "read_pages", lambda p: [(texts[0], [TABLE])])


def _first_ref(client, headers, batch) -> str:
    job = client.get(f"/api/invoice-jobs/{batch['jobs'][0]['id']}", headers=headers).json()
    return job["items"][0]["raw_ref"]


def test_active_profile_wins_over_column_map(client, admin_headers, db_session,
                                             monkeypatch, tmp_path):
    _fake(monkeypatch, tmp_path, [CI])
    sup = _supplier(db_session, ci_map={"ref": ["Nasz REF", "Our Ref"], "qty": ["Pieces"]})
    batch = _upload(client, admin_headers, db_session, sup.id)
    assert _first_ref(client, admin_headers, batch) == "NEW-1"


def test_draft_profile_falls_back_to_column_map(client, admin_headers, db_session,
                                                monkeypatch, tmp_path):
    _fake(monkeypatch, tmp_path, [CI])
    sup = _supplier(db_session, status="draft", ci_map={"ref": ["Our Ref"], "qty": ["Pieces"]})
    batch = _upload(client, admin_headers, db_session, sup.id)
    assert _first_ref(client, admin_headers, batch) == "OLD-1"


def test_resolve_order():
    sup = Supplier(name="x", column_map="ref=Old Code")
    assert profiles.resolve(None).source == "auto"
    assert profiles.resolve(Supplier(name="y", column_map="")).ci_map == {}
    assert profiles.resolve(sup).ci_map == {"ref": "Old Code"}
    # aktywny profil z pustą mapą CI → stare column_map; nazwy ról compare ujednolicone
    sup.doc_profile = SupplierDocProfile(status="active", ci_map={}, ref_kind="supplier",
                                         pl_map={"net_weight": ["N.W."], "skip": ["Foto"]})
    got = profiles.resolve(sup)
    assert (got.source, got.ci_map, got.ref_kind) == ("column_map", {"ref": "Old Code"}, "supplier")
    assert got.pl_map == {"weight_net": ["N.W."]}


def test_split_marker_divides_ci_and_pl(monkeypatch):
    monkeypatch.setattr(splitter, "write_range", lambda *a: None)
    monkeypatch.setattr(splitter, "page_texts", lambda p: [CI, WEIGHTS])
    # bez znacznika strona wag (bez nagłówka typu) to ciąg dalszy faktury
    assert len(splitter.split_pdf("x/cipl.pdf")) == 1
    parts = splitter.split_pdf("x/cipl.pdf", "Weight  Specification")
    assert [(p["kind"], p["page_from"]) for p in parts] == [
        (InvoiceDocKind.invoice, 1), (InvoiceDocKind.packing_list, 2)]
    # literówka OCR w znaczniku nadal dzieli (tolerancja jak PROFOMA/PORFORMA)
    ocr_texts = [CI, WEIGHTS.replace("WEIGHT", "WE1GHT")]
    assert [p["kind"] for p in splitter.split_pdf("x/c.pdf", "WEIGHT SPECIFICATION", ocr_texts)][1] \
        == InvoiceDocKind.packing_list
    assert not splitter.marker_in("COMMERCIAL INVOICE", "WEIGHT SPECIFICATION")


def test_keywords_detect_supplier(db_session):
    company = db_session.scalars(select(Company)).first().id
    acme = _supplier(db_session, "Acme", keywords=["ACME TRADING CO."])
    _supplier(db_session, "Beta", keywords=["BETA LTD"])
    _supplier(db_session, "Draft", status="draft", keywords=["ACME TRADING CO.", "INVOICE"])
    assert profiles.detect_supplier(db_session, CI, company).id == acme.id
    assert profiles.detect_supplier(db_session, "nic wspólnego", company) is None
    assert profiles.detect_supplier(db_session, "ACME TRADING CO. / BETA LTD", company) is None
    assert profiles.detect_supplier(db_session, "ACMETRADING", company) is None
    assert profiles.detect_supplier(db_session, CI, company + 999) is None


def test_upload_without_container_supplier_uses_keywords(client, admin_headers, db_session,
                                                         monkeypatch, tmp_path):
    _fake(monkeypatch, tmp_path, [CI])
    _supplier(db_session, "Acme", keywords=["ACME TRADING CO."],
              ci_map={"ref": ["Our Ref"], "qty": ["Pieces"]})
    batch = _upload(client, admin_headers, db_session)
    assert batch["supplier_name"] == "Acme"
    assert _first_ref(client, admin_headers, batch) == "NEW-1"


def test_ref_kind_supplier_translates_code(db_session):
    company = db_session.scalars(select(Company)).first()
    sup = _supplier(db_session, ref_kind="supplier")
    db_session.add_all([Material(ref_code="ABC1", ref_norm="ABC1", name_pl="Rurka"),
                        SupplierMaterialMap(company_id=company.id, supplier_id=sup.id,
                                            supplier_code="X-99", ref_code="ABC1")])
    db_session.commit()
    items = matching.build_items(db_session, [{"ref": "X-99"}, {"ref": "ABC1"}], company.id,
                                 supplier_id=sup.id, ref_kind="supplier")
    assert (items[0].match_status, items[0].master_ref) == (InvoiceMatchStatus.matched, "ABC1")
    # kod dostawcy zbieżny z naszym REF, ale bez mapowania = do przypisania, nie „rules”
    assert items[1].match_status == InvoiceMatchStatus.unmatched
    ours = matching.build_items(db_session, [{"ref": "ABC1"}], company.id, supplier_id=sup.id)
    assert ours[0].match_source == "rules"
