"""Zawężone bramki odczytu (2026-10-05): magazyn nie widzi dokumentów handlowych/odprawowych
(faktury, B/L, SAD) — lista, pobranie, wyszukiwarka; CMR dla magazynu bez dostawcy i uwag
zakupowych; agencja celna bez pozycji PO i bez kolejki bramy (dane kierowcy)."""
import io

from app.models import DocumentType

from .conftest import login
from .test_api import VALID_NO, _company_id, _make_user
from tests.conftest import pdf_bytes

SUPPLIER = "Tajny Dostawca SA"
NOTE = "cena 12 USD/szt"


def _setup(client, admin_headers, db_session):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    wh = client.post("/api/warehouses", headers=admin_headers, json={
        "name": "DLT", "company_id": borealis, "country": "PL"}).json()
    supplier = client.post("/api/suppliers", headers=admin_headers, json={
        "name": SUPPLIER, "company_id": borealis}).json()
    r = client.post("/api/containers", headers=admin_headers, json={
        "container_no": VALID_NO, "company_id": borealis, "warehouse_id": wh["id"],
        "supplier_id": supplier["id"], "purchase_note": NOTE})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    db_session.add_all([DocumentType(name="Faktura handlowa", tile_code="CI", is_active=True),
                        DocumentType(name="Packing lista", tile_code="PL", is_active=True)])
    db_session.commit()
    types = {t.tile_code: t.id for t in db_session.query(DocumentType).filter(
        DocumentType.tile_code.in_(("CI", "PL")))}
    ids = {}
    for code, name in (("CI", "faktura.pdf"), ("PL", "packing.pdf")):
        up = client.post(f"/api/containers/{cid}/attachments", headers=admin_headers,
                         data={"document_type_id": str(types[code])},
                         files={"file": (name, io.BytesIO(pdf_bytes(name)), "application/pdf")})
        assert up.status_code == 201, up.text
        ids[code] = up.json()["id"]
    _make_user(client, admin_headers, "mag.b", "warehouse", borealis, warehouse_id=wh["id"])
    return cid, ids


def test_warehouse_sees_packing_list_not_invoice(client, admin_headers, db_session):
    cid, ids = _setup(client, admin_headers, db_session)
    h = login(client, "mag.b", "haslo123")
    names = {a["filename"] for a in
             client.get(f"/api/containers/{cid}/attachments", headers=h).json()}
    assert names == {"packing.pdf"}
    assert client.get(f"/api/attachments/{ids['CI']}/download", headers=h).status_code == 404
    assert client.get(f"/api/attachments/{ids['PL']}/download", headers=h).status_code == 200
    found = client.get("/api/documents/search", params={"q": "pdf"}, headers=h)
    assert found.status_code == 200
    assert {d["title"] for d in found.json()} == {"packing.pdf"}


def test_warehouse_cmr_without_supplier_and_purchase_note(client, admin_headers, db_session):
    cid, _ = _setup(client, admin_headers, db_session)
    admin_cmr = client.get(f"/api/containers/{cid}/cmr", headers=admin_headers).text
    assert SUPPLIER in admin_cmr and NOTE in admin_cmr
    r = client.get(f"/api/containers/{cid}/cmr", headers=login(client, "mag.b", "haslo123"))
    assert r.status_code == 200
    assert SUPPLIER not in r.text and NOTE not in r.text


def test_customs_no_order_lines_nor_gate(client, admin_headers, db_session):
    cid, _ = _setup(client, admin_headers, db_session)
    agency = client.post("/api/customs-agencies", headers=admin_headers,
                         json={"name": "CELNA-B"}).json()
    assert client.post(f"/api/customs/containers/{cid}/assign", headers=admin_headers,
                       json={"customs_agency_id": agency["id"]}).status_code == 200
    assert client.post("/api/users", headers=admin_headers, json={
        "login": "celna.b", "password": "haslo123", "role": "customs",
        "customs_agency_id": agency["id"]}).status_code == 201
    h = login(client, "celna.b", "haslo123")
    assert client.get(f"/api/containers/{cid}/order-lines", headers=h).status_code == 403
    assert client.get("/api/gate", headers=h).status_code == 403


def test_warehouse_untyped_file_only_own(client, admin_headers, db_session):
    """Plik bez typu dokumentu (nieopisany — może być fakturą) magazyn widzi tylko własny."""
    cid, _ = _setup(client, admin_headers, db_session)
    up = client.post(f"/api/containers/{cid}/attachments", headers=admin_headers,
                     files={"file": ("bez-typu.pdf", io.BytesIO(pdf_bytes("bez-typu.pdf")), "application/pdf")})
    assert up.status_code == 201, up.text
    h = login(client, "mag.b", "haslo123")
    names = {a["filename"] for a in
             client.get(f"/api/containers/{cid}/attachments", headers=h).json()}
    assert names == {"packing.pdf"}
    assert client.get(f"/api/attachments/{up.json()['id']}/download", headers=h).status_code == 404
    own = client.post(f"/api/containers/{cid}/attachments", headers=h,
                      files={"file": ("moje.jpg", io.BytesIO(b"\xff\xd8\xff x"), "image/jpeg")})
    if own.status_code == 201:  # magazyn może wgrywać (np. zdjęcia rozładunku) — własny widzi
        names = {a["filename"] for a in
                 client.get(f"/api/containers/{cid}/attachments", headers=h).json()}
        assert names == {"packing.pdf", "moje.jpg"}
