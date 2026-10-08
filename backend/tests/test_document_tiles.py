"""Kafelki dokumentów dostawy (spec 2026-10-01-kafelki-dokumentow): PI · CI ⇄ PL · BL ·
SAD-DRAFT → SAD-PZ → SAD-PW z trzech źródeł (paczki faktur, załączniki z kodem kafelka,
drafty SAD), stany i „wymagane” zależnie od etapu."""
import io

from app.config import settings
from app.models import Container, ContainerStatus, CustomsStatus
from app.invoices import extractor, splitter
from tests.test_invoice_conformity import CI, OWN, _confirm, _container, _upload
from tests.test_invoices_checks import _pdf as _pages_pdf
from tests.test_invoices_checks import _setup
from tests.test_sad_drafts import _pdf
from tests.test_sad_drafts import _upload as _upload_draft
from tests.conftest import pdf_bytes


def _tiles(client, headers, cid) -> dict:
    resp = client.get(f"/api/containers/{cid}/document-tiles", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _tile(result, code):
    return next(t for t in result["tiles"] if t["code"] == code)


def _set(db, cid, status=None, customs=None):
    c = db.get(Container, cid)
    if status:
        c.status = status
    if customs:
        c.customs_status = customs
    db.commit()


def _doc_type(client, headers, name, code):
    resp = client.post("/api/customs/document-types", headers=headers,
                       json={"name": name, "tile_code": code})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_invoice_batch_and_typed_attachment(client, admin_headers, db_session, monkeypatch, tmp_path):
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    cid = _container(client, admin_headers, company, sup)
    _set(db_session, cid, status=ContainerStatus.W_TRANSPORCIE)
    assert _tiles(client, admin_headers, cid)["missing"] == ["PI", "CI", "PL", "BL"]

    _, job_id = _upload(client, admin_headers, monkeypatch, cid, f"{CI}\nCONTAINER No.: {OWN}")
    result = _tiles(client, admin_headers, cid)
    assert _tile(result, "CI")["state"] == "warn"                 # niezatwierdzona
    assert _tile(result, "CI")["files"][0]["url"] == f"/api/invoice-jobs/{job_id}/pdf"
    assert _tile(result, "PL")["state"] != "none"
    assert result["missing"] == ["PI", "BL"]
    assert _confirm(client, admin_headers, job_id, reason="test").status_code == 200
    assert _tile(_tiles(client, admin_headers, cid), "CI")["state"] == "ok"   # zatwierdzona + potwierdzona

    bl_type = _doc_type(client, admin_headers, "Konosament", "BL")
    resp = client.post(f"/api/containers/{cid}/attachments", headers=admin_headers,
                       data={"document_type_id": str(bl_type)},
                       files={"file": ("bl.pdf", io.BytesIO(pdf_bytes("bl.pdf")), "application/pdf")})
    assert resp.status_code == 201, resp.text
    result = _tiles(client, admin_headers, cid)
    assert _tile(result, "BL")["state"] == "present" and result["missing"] == ["PI"]
    pdf = client.get(f"/api/invoice-jobs/{job_id}/pdf", headers=admin_headers)
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"


def test_required_follows_stage_and_customs(client, admin_headers, db_session, monkeypatch, tmp_path):
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    cid = _container(client, admin_headers, company, sup)
    _set(db_session, cid, status=ContainerStatus.ZAPOWIEDZIANY)
    assert _tiles(client, admin_headers, cid)["missing"] == []          # za wcześnie na braki
    _set(db_session, cid, status=ContainerStatus.W_PORCIE, customs=CustomsStatus.ZWOLNIONY)
    assert _tiles(client, admin_headers, cid)["missing"] == [
        "PI", "CI", "PL", "BL", "SAD_DRAFT", "SAD_PZ", "SAD_PW"]
    _set(db_session, cid, customs=CustomsStatus.REWIZJA)                # w toku: draft tak, PZ/PW nie
    assert "SAD_DRAFT" in _tiles(client, admin_headers, cid)["missing"]
    assert "SAD_PZ" not in _tiles(client, admin_headers, cid)["missing"]


def test_sad_draft_counted_once(client, admin_headers, db_session, monkeypatch, tmp_path):
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    cid = _container(client, admin_headers, company, sup)
    batch_id, _ = _upload(client, admin_headers, monkeypatch, cid, f"{CI}\nCONTAINER No.: {OWN}")
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))
    assert _upload_draft(client, admin_headers, batch_id, _pdf("v1")).status_code == 201
    draft = _tile(_tiles(client, admin_headers, cid), "SAD_DRAFT")
    assert draft["state"] == "warn" and len(draft["files"]) == 1      # draft do oceny, plik raz


def test_tile_code_unique(client, admin_headers):
    _doc_type(client, admin_headers, "SAD PZ", "SAD_PZ")
    resp = client.post("/api/customs/document-types", headers=admin_headers,
                       json={"name": "Inny SAD", "tile_code": "SAD_PZ"})
    assert resp.status_code == 409 and "SAD_PZ" in resp.json()["detail"]
    assert client.post("/api/customs/document-types", headers=admin_headers,
                       json={"name": "Zły", "tile_code": "XYZ"}).status_code == 422


def _attach(client, headers, cid, type_id, name="sad.pdf"):
    resp = client.post(f"/api/containers/{cid}/attachments", headers=headers,
                       data={"document_type_id": str(type_id)},
                       files={"file": (name, io.BytesIO(pdf_bytes(f"{name}-{type_id}")), "application/pdf")})
    assert resp.status_code == 201, resp.text


def test_sad_pz_and_pw_move_customs_status_forward(client, admin_headers, db_session, monkeypatch, tmp_path):
    """PR 5: wgrany SAD-PZ → ODPRAWIONY, SAD-PW → ZWOLNIONY (kontener z awizacją → AWIZOWANY);
    nigdy do tyłu (ROZLICZONY zostaje); wpis w historii z powodem."""
    import datetime

    from app.models import AuditLog
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    cid = _container(client, admin_headers, company, sup)
    c = db_session.get(Container, cid)
    c.status, c.customs_status, c.notify_date = (ContainerStatus.W_PORCIE, CustomsStatus.ZLECONA,
                                                  datetime.date(2030, 5, 5))
    db_session.commit()
    pz = _doc_type(client, admin_headers, "SAD PZ", "SAD_PZ")
    pw = _doc_type(client, admin_headers, "SAD PW", "SAD_PW")

    _attach(client, admin_headers, cid, pz)
    db_session.expire_all()
    c = db_session.get(Container, cid)
    assert c.customs_status == CustomsStatus.ODPRAWIONY and c.status == ContainerStatus.AWIZOWANY
    assert db_session.query(AuditLog).filter(AuditLog.field == "customs_status",
                                             AuditLog.note.like("%SAD-PZ%")).count() == 1
    _attach(client, admin_headers, cid, pw)
    db_session.expire_all()
    assert db_session.get(Container, cid).customs_status == CustomsStatus.ZWOLNIONY

    _set(db_session, cid, customs=CustomsStatus.ROZLICZONY)
    _attach(client, admin_headers, cid, pz, name="sad2.pdf")          # dalej — bez zmian
    db_session.expire_all()
    assert db_session.get(Container, cid).customs_status == CustomsStatus.ROZLICZONY


def test_sad_upload_by_forwarder_keeps_customs_status(client, admin_headers, db_session,
                                                      monkeypatch, tmp_path):
    """Spedytor nie zmienia statusu odprawy (reguła check_customs_status_change) — wgrany przez
    niego plik typu SAD-PZ zostaje zapisany, ale automat ODPRAWIONY nie rusza."""
    from tests.conftest import forwarder, login
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    cid = _container(client, admin_headers, company, sup)
    spedalfa = forwarder(client, admin_headers, "SPEDALFA")
    client.post("/api/users", headers=admin_headers, json={
        "login": "sped.sad", "password": "haslo123", "role": "forwarder", "forwarder_id": spedalfa["id"]})
    _set(db_session, cid, status=ContainerStatus.W_PORCIE, customs=CustomsStatus.ZLECONA)
    c = db_session.get(Container, cid)
    c.forwarder_id = spedalfa["id"]
    db_session.commit()
    pz = _doc_type(client, admin_headers, "SAD PZ", "SAD_PZ")

    _attach(client, login(client, "sped.sad", "haslo123"), cid, pz)
    db_session.expire_all()
    c = db_session.get(Container, cid)
    assert c.customs_status == CustomsStatus.ZLECONA and c.status == ContainerStatus.W_PORCIE
    assert len(client.get(f"/api/containers/{cid}/attachments", headers=admin_headers).json()) == 1


def test_customs_groups_cover_process():
    """Grupy statusu odprawy (models.enums) — jedno źródło dla pulpitu, automatu statusu
    kontenera i kafelków: REWIZJA liczy się jak odprawa w toku, reszta rozłączna i pełna."""
    from app.models import CUSTOMS_CLEARED, CUSTOMS_IN_PROGRESS, customs_rank
    assert customs_rank(CustomsStatus.REWIZJA) == customs_rank(CustomsStatus.DRAFT_POTWIERDZONY)
    assert customs_rank(CustomsStatus.ODPRAWIONY) > customs_rank(CustomsStatus.REWIZJA)
    assert not set(CUSTOMS_IN_PROGRESS) & set(CUSTOMS_CLEARED)
    assert set(CUSTOMS_IN_PROGRESS) | set(CUSTOMS_CLEARED) == set(CustomsStatus) - {
        CustomsStatus.BRAK, CustomsStatus.DOKUMENTY_KOMPLETNE}


def test_forwarder_sees_no_commercial_tiles(client, admin_headers, db_session, monkeypatch, tmp_path):
    """Spedytor nie ma wglądu w dokumenty handlowe: kafelki PI/CI/PL puste (bez numeru faktury
    i nazwy pliku), nie liczą się do „wgranych” ani braków. Zestaw 7 kafelków zostaje (UI)."""
    from tests.conftest import forwarder, login
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    cid = _container(client, admin_headers, company, sup)
    _set(db_session, cid, status=ContainerStatus.W_TRANSPORCIE)
    _upload(client, admin_headers, monkeypatch, cid, f"{CI}\nCONTAINER No.: {OWN}")
    spedalfa = forwarder(client, admin_headers, "SPEDALFA")
    client.post("/api/users", headers=admin_headers, json={
        "login": "sped.faktury", "password": "haslo123", "role": "forwarder", "forwarder_id": spedalfa["id"]})
    db_session.get(Container, cid).forwarder_id = spedalfa["id"]
    db_session.commit()
    assert _tile(_tiles(client, admin_headers, cid), "CI")["files"]      # admin widzi fakturę

    result = _tiles(client, login(client, "sped.faktury", "haslo123"), cid)
    assert len(result["tiles"]) == 7
    for code in ("PI", "CI", "PL"):
        assert _tile(result, code) == {"code": code, "state": "none", "required": False, "files": []}
    assert result["missing"] == ["BL"] and result["loaded"] == 0


# strona B/L z realnego zestawu (dane zamaskowane): nagłówek „BILL OF LADING” jest grafiką
BL_PAGE = ("SUPPLIER MEDICAL CO.,LTD.\nSTS00000001\nACME INTERNATIONAL SP. Z O.O.\n"
           f"{OWN}/FJ00000000 40HQ 1295CARTONS 9424.750KGS\nFREIGHT COLLECT\nSHIPPED ON BOARD:\n"
           "1X40HQ CY-CY FCL\nSHIPPER'S LOAD,COUNT&SEAL")


def test_is_bill_of_lading():
    assert splitter.is_bill_of_lading(BL_PAGE)
    assert splitter.is_bill_of_lading("OCEAN BILL OF LADING\nB/L NO. X")
    # awizo wysyłki tylko WSPOMINA numer B/L — to nie konosament
    assert not splitter.is_bill_of_lading("SHIPPING ADVICE\nBILL OF LADING NO： STS1")
    assert not splitter.is_bill_of_lading("Bill of lading No. 5")
    assert not splitter.is_bill_of_lading(CI)


def test_bl_without_header_is_cut_out_and_lights_bl_tile(client, admin_headers, db_session,
                                                          monkeypatch, tmp_path):
    assert splitter.classify_first_page(BL_PAGE).value == "other"
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    cid = _container(client, admin_headers, company, sup)
    _set(db_session, cid, status=ContainerStatus.W_TRANSPORCIE)
    ci = f"{CI}\nCONTAINER No.: {OWN}"
    monkeypatch.setattr(splitter, "page_texts", lambda p: [BL_PAGE, ci])
    monkeypatch.setattr(extractor, "read_pages", lambda p: [(ci, [])])
    resp = client.post(f"/api/containers/{cid}/invoice-batches", headers=admin_headers,
                       files=[("pdf", ("bl+ci.pdf", io.BytesIO(_pages_pdf(2)), "application/pdf"))])
    assert resp.status_code == 201, resp.text
    result = _tiles(client, admin_headers, cid)          # cięcie w tle — po nim strona 1 to B/L
    assert _tile(result, "CI")["state"] != "none"
    assert _tile(result, "BL")["state"] == "present" and "BL" not in result["missing"]
    assert _tile(result, "BL")["files"][0]["source"] == "invoice"


def test_split_parts_are_named_by_type_and_pages(client, admin_headers, db_session, monkeypatch, tmp_path):
    """Audyt 2026-10-06 #13: części zestawu mają własne nazwy (agencja nie dostaje kilku
    „DOC….pdf”); B/L rozpoznany po treści dostaje etykietę BL."""
    from app.invoices.ingest import part_name
    from app.models import InvoiceDocKind
    assert part_name("DOC CBN-E20260692.pdf", {"kind": InvoiceDocKind.packing_list, "page_from": 3,
                                                "page_to": 3}) == "DOC CBN-E20260692_PL_s3.pdf"
    assert part_name("x.pdf", {"kind": InvoiceDocKind.other, "page_from": 4, "page_to": 22,
                               "text": "CERTIFICATE OF ORIGIN"}) == "x_inne_s4-22.pdf"
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    cid = _container(client, admin_headers, company, sup)
    ci = f"{CI}\nCONTAINER No.: {OWN}"
    monkeypatch.setattr(splitter, "page_texts", lambda p: [BL_PAGE, ci])
    monkeypatch.setattr(extractor, "read_pages", lambda p: [(ci, [])])
    client.post(f"/api/containers/{cid}/invoice-batches", headers=admin_headers,
                files=[("pdf", ("DOC.pdf", io.BytesIO(_pages_pdf(2)), "application/pdf"))])
    jobs = client.get(f"/api/containers/{cid}/invoice-batches", headers=admin_headers).json()[0]["jobs"]
    assert sorted(j["filename"] for j in jobs) == ["DOC_BL_s1.pdf", "DOC_faktura_s2.pdf"]


def test_warehouse_sees_no_invoices_nor_sad_on_tiles(client, admin_headers, db_session, monkeypatch, tmp_path):
    """Spec 2026-10-06 decyzja 25 / §4 pkt 4: magazyn bez faktur, proform i obiegu SAD na kafelkach
    (wcześniej widział numer faktury CI i stan draftów); PL i BL zostają."""
    from app.models import Role, User
    from app.security import create_access_token
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    cid = _container(client, admin_headers, company, sup)
    _set(db_session, cid, status=ContainerStatus.W_TRANSPORCIE)
    _upload(client, admin_headers, monkeypatch, cid, f"{CI}\nCONTAINER No.: {OWN}")
    from app.models import Warehouse
    wh = Warehouse(name="WH-KAFELKI", company_id=company.id)
    db_session.add(wh)
    db_session.flush()
    container = db_session.get(Container, cid)
    container.warehouse_id = wh.id
    mag = User(login="mag.kafelki", hashed_password="x", role=Role.warehouse,
               company_id=company.id, warehouse_id=wh.id)
    db_session.add(mag)
    db_session.commit()
    resp = client.get(f"/api/containers/{cid}/document-tiles",
                      headers={"Authorization": f"Bearer {create_access_token(mag)}"})
    assert resp.status_code == 200, resp.text
    result = resp.json()
    for code in ("PI", "CI", "SAD_DRAFT", "SAD_PZ", "SAD_PW"):
        assert _tile(result, code) == {"code": code, "state": "none", "required": False, "files": []}
    assert _tile(result, "PL")["state"] != "none" and _tile(result, "PL")["files"] == []   # bez nazwy zestawu
    assert "CI" not in result["missing"]
