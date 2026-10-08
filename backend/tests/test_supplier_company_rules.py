"""Kartoteka globalna (PR1): którego dostawcy wolno użyć w rekordach której spółki —
kontenery, zlecenia, import kolejki, aliasy, rozpoznanie dostawcy faktury."""
from sqlalchemy import select

from app.database import SessionLocal
from app.importers.queue import resolve_supplier_id
from app.invoices import profiles
from app.models import Company, Container, Supplier, SupplierDocProfile

NOS = ["MSKU5000009", "MSKU5000014", "MSDU0806613", "CSQU3054383", "MEDU9573834"]


def _co(db, code):
    return db.scalar(select(Company).where(Company.code == code))


def _seed():
    with SessionLocal() as db:
        cat = Supplier(name="Kartoteka Co", sap_code="500100")
        tim = Supplier(name="Nadawca Borealis", client_company_id=_co(db, "BOREALIS").id)
        db.add_all([cat, tim])
        db.commit()
        return cat.id, tim.id


def _ids(*codes):
    with SessionLocal() as db:
        return [_co(db, c).id for c in codes]


def test_container_accepts_catalog_only_in_material_company(client, admin_headers):
    cat, tim = _seed()
    acme, pt, borealis = _ids("ACME", "PT", "BOREALIS")

    def post(no, company, supplier):
        return client.post("/api/containers", headers=admin_headers, json={
            "container_no": no, "company_id": company, "supplier_id": supplier}).status_code

    assert post(NOS[0], acme, cat) == 201
    assert post(NOS[1], pt, cat) == 201
    assert post(NOS[2], borealis, cat) == 404
    assert post(NOS[3], borealis, tim) == 201
    assert post(NOS[4], acme, tim) == 404


def test_queue_import_resolves_catalog_name_only_for_material_company(client):
    cat, tim = _seed()
    with SessionLocal() as db:
        acme, borealis = _co(db, "ACME").id, _co(db, "BOREALIS").id
        assert resolve_supplier_id(db, acme, "KARTOTEKA CO") == cat
        assert resolve_supplier_id(db, borealis, "Kartoteka Co") is None
        assert resolve_supplier_id(db, borealis, "nadawca borealis") == tim


def test_found_order_by_name_creates_catalog_or_client_sender(client, admin_headers):
    for code, number in (("ACME", "ZL-K1"), ("BOREALIS", "ZL-K2")):
        r = client.post("/api/zlecenia", headers=admin_headers, json={
            "number": number, "company_code": code, "supplier_name": "Nowy Nadawca",
            "container_count": 1})
        assert r.status_code == 201, r.text
    with SessionLocal() as db:
        owners = sorted(str(s.client_company_id) for s in db.scalars(
            select(Supplier).where(Supplier.name == "Nowy Nadawca")))
        assert owners == sorted(["None", str(_co(db, "BOREALIS").id)])


def test_detect_supplier_sees_catalog_only_for_material_company(client):
    cat, _ = _seed()
    with SessionLocal() as db:
        db.add(SupplierDocProfile(supplier_id=cat, status="active",
                                  keywords=["KARTOTEKA CO LTD"], ci_map={}, pl_map={}))
        db.commit()
        text = "COMMERCIAL INVOICE — KARTOTEKA CO LTD"
        assert profiles.detect_supplier(db, text, _co(db, "ACME").id).id == cat
        assert profiles.detect_supplier(db, text, _co(db, "BOREALIS").id) is None


def test_alias_for_catalog_supplier_needs_file_company(client, admin_headers):
    cat, _ = _seed()
    acme, borealis = _ids("ACME", "BOREALIS")
    url = f"/api/suppliers/{cat}/aliases"
    assert client.post(url, headers=admin_headers, json={"alias": "KART CO"}).status_code == 422
    assert client.post(url, headers=admin_headers,
                       json={"alias": "KART CO", "company_id": borealis}).status_code == 404
    r = client.post(url, headers=admin_headers, json={"alias": "KART CO", "company_id": acme})
    assert r.status_code == 201, r.text
    with SessionLocal() as db:
        assert resolve_supplier_id(db, acme, "Kart Co.") == cat


def test_unmapped_rows_flag_catalog_companies(client, admin_headers):
    with SessionLocal() as db:
        db.add_all([Container(container_no=NOS[0], company_id=_co(db, "ACME").id,
                              supplier_raw="Plik Z"),
                    Container(container_no=NOS[1], company_id=_co(db, "BOREALIS").id,
                              supplier_raw="Plik T")])
        db.commit()
    rows = {r["name"]: r["catalog"]
            for r in client.get("/api/suppliers/unmapped", headers=admin_headers).json()}
    assert rows == {"Plik Z": True, "Plik T": False}


def test_purge_endpoint_is_gone(client, admin_headers):
    r = client.post("/api/suppliers/purge?company_code=BOREALIS", headers=admin_headers,
                    json={"confirm": "BOREALIS"})
    assert r.status_code in (404, 405)
