"""Profil dokumentów dostawcy (etap 1): model, backfill column_map, API."""
import importlib.util
import pathlib

from app.database import SessionLocal
from app.models import CustomsAgency, Material, Supplier, SupplierDocProfile, SupplierDocSample


def _migration():
    path = pathlib.Path(__file__).parents[1] / "migrations/versions/profil001_profil_dostawcy.py"
    spec = importlib.util.spec_from_file_location("profil001", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_ci_map_from_column_map():
    conv = _migration().ci_map_from_column_map
    assert conv("ref=Item No.; qty=Q'ty; net=Amount") == {
        "ref": ["Item No."], "qty": ["Q'ty"], "net": ["Amount"]}
    assert conv("") == {}
    assert conv("foo=Bar; qty=") == {}          # nieznana rola / pusty alias pomijane


def test_models_roundtrip(client, admin_headers):
    company = client.get("/api/companies", headers=admin_headers).json()[0]["id"]
    sup = client.post("/api/suppliers", headers=admin_headers,
                      json={"name": "Pulp House", "company_id": company}).json()
    with SessionLocal() as db:
        p = SupplierDocProfile(supplier_id=sup["id"], keywords=["PULP HOUSE"],
                               ci_map={"qty": ["Quantity"]}, pl_map={}, ref_kind="ours")
        db.add(p)
        db.flush()
        db.add(SupplierDocSample(profile_id=p.id, filename="a.pdf", stored_path="x/a.pdf"))
        db.add(CustomsAgency(name="Delta Brokers", export_format="symbols",
                             export_params={"IDZestawu": 106}))
        db.add(Material(ref_code="145851", suppl_unit="pary", suppl_factor=0.5))
        db.commit()
        got = db.get(SupplierDocProfile, p.id)
        assert (got.status, got.currency, got.tol_amount_pct, got.tol_qty_pct) == ("draft", "", 0.5, 0.0)
        assert got.ci_map == {"qty": ["Quantity"]} and len(got.samples) == 1
        assert db.query(CustomsAgency).filter_by(name="Delta Brokers").one().export_params == {"IDZestawu": 106}
        assert db.get(Supplier, sup["id"]).doc_profile.id == p.id


def _supplier(client, headers, name, company_id):
    return client.post("/api/suppliers", headers=headers,
                       json={"name": name, "company_id": company_id}).json()


def test_merge_supplier_repoints_duplicates_doc_profile(client, admin_headers):
    """Scalanie: tylko duplikat ma profil -> cel po scaleniu dziedziczy go razem z próbką
    (bez przepięcia profil zginąłby przez cascade na supplier_doc_profiles.supplier_id)."""
    company = client.get("/api/companies", headers=admin_headers).json()[0]["id"]
    target = _supplier(client, admin_headers, "Fushide", company)
    dup = _supplier(client, admin_headers, "Fushide stary", company)

    with SessionLocal() as db:
        p = SupplierDocProfile(supplier_id=dup["id"], ci_map={"ref": ["Item No."]}, pl_map={})
        db.add(p)
        db.flush()
        db.add(SupplierDocSample(profile_id=p.id, filename="a.pdf", stored_path="x/a.pdf"))
        db.commit()

    response = client.post(f"/api/suppliers/{dup['id']}/merge", headers=admin_headers,
                           json={"target_id": target["id"]})
    assert response.status_code == 200, response.text

    with SessionLocal() as db:
        moved = db.query(SupplierDocProfile).filter_by(supplier_id=target["id"]).one()
        assert moved.ci_map == {"ref": ["Item No."]}
        assert len(moved.samples) == 1
        assert db.query(SupplierDocProfile).filter_by(supplier_id=dup["id"]).first() is None


def test_profile_api_upsert_and_validation(client, admin_headers):
    company = client.get("/api/companies", headers=admin_headers).json()[0]["id"]
    sid = client.post("/api/suppliers", headers=admin_headers,
                      json={"name": "Northbridge", "company_id": company}).json()["id"]
    url = f"/api/suppliers/{sid}/doc-profile"
    empty = client.get(url, headers=admin_headers).json()
    assert (empty["status"], empty["ci_map"], empty["samples"]) == ("draft", {}, [])
    body = {"currency": "USD", "doc_language": "en", "keywords": ["NORTHBRIDGE", " Northbridge "],
            "ci_map": {"ref": ["Item No."], "qty": ["Qty", "Quantity"]}, "pl_map": {"weight_net": ["N.W."]},
            "ref_kind": "supplier", "split_marker": "PACKING LIST", "tol_amount_pct": 0.5,
            "tol_qty_pct": 0, "status": "active"}
    r = client.put(url, headers=admin_headers, json=body)
    assert r.status_code == 200, r.text
    got = client.get(url, headers=admin_headers).json()
    assert got["keywords"] == ["NORTHBRIDGE", "Northbridge"]          # trim + bez pustych
    assert got["ref_kind"] == "supplier" and got["pl_map"] == {"weight_net": ["N.W."]}
    bad = client.put(url, headers=admin_headers, json={**body, "ci_map": {"cena": ["Price"]}})
    assert bad.status_code == 422                               # nieznana rola kolumny
    assert client.put(url, headers=admin_headers, json={**body, "tol_qty_pct": -1}).status_code == 422
    assert client.get("/api/suppliers/999999/doc-profile", headers=admin_headers).status_code == 404


def test_merge_supplier_keeps_targets_doc_profile_when_both_have_one(client, admin_headers):
    """Oba mają profil -> cel zachowuje swój (bez nadpisania); duplikatu profil znika."""
    company = client.get("/api/companies", headers=admin_headers).json()[0]["id"]
    target = _supplier(client, admin_headers, "Fushide", company)
    dup = _supplier(client, admin_headers, "Fushide stary", company)

    with SessionLocal() as db:
        db.add(SupplierDocProfile(supplier_id=target["id"], ci_map={"ref": ["CEL"]}, pl_map={}))
        db.add(SupplierDocProfile(supplier_id=dup["id"], ci_map={"ref": ["DUP"]}, pl_map={}))
        db.commit()

    response = client.post(f"/api/suppliers/{dup['id']}/merge", headers=admin_headers,
                           json={"target_id": target["id"]})
    assert response.status_code == 200, response.text

    with SessionLocal() as db:
        remaining = db.query(SupplierDocProfile).filter_by(supplier_id=target["id"]).all()
        assert len(remaining) == 1
        assert remaining[0].ci_map == {"ref": ["CEL"]}
        assert db.query(SupplierDocProfile).filter_by(supplier_id=dup["id"]).first() is None


def test_migration_backfill_inserts_typed_json():
    """profil001.backfill: kolumny keywords/ci_map/pl_map muszą być otypowane jako JSON w
    sa.table(), inaczej bulk_insert wiąże surowy dict/list wprost do sterownika i
    SQLite/psycopg2 wywalają się ("type 'dict' is not supported"). Odtwarza realny schemat
    z upgrade() migracji na izolowanej bazie w pamięci (bez zależności od schematu
    bootstrapu aplikacji) i woła backfill() przez Operations/MigrationContext."""
    import json

    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import create_engine, text as sa_text

    mod = _migration()
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(sa_text("CREATE TABLE suppliers (id INTEGER PRIMARY KEY, column_map TEXT NOT NULL DEFAULT '')"))
        conn.execute(sa_text(
            "CREATE TABLE supplier_doc_profiles ("
            "id INTEGER PRIMARY KEY, supplier_id INTEGER NOT NULL UNIQUE, "
            "status TEXT NOT NULL DEFAULT 'draft', currency TEXT NOT NULL DEFAULT '', "
            "doc_language TEXT NOT NULL DEFAULT '', keywords JSON NOT NULL, "
            "ci_map JSON NOT NULL, pl_map JSON NOT NULL, ref_kind TEXT NOT NULL DEFAULT 'ours', "
            "split_marker TEXT NOT NULL DEFAULT '', tol_amount_pct FLOAT NOT NULL DEFAULT 0.5, "
            "tol_qty_pct FLOAT NOT NULL DEFAULT 0)"))
        conn.execute(sa_text("INSERT INTO suppliers (id, column_map) VALUES (1, \"ref=Item No.; qty=Q'ty\")"))
        conn.commit()

        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.backfill(conn)
        conn.commit()

        row = conn.execute(sa_text(
            "SELECT supplier_id, ci_map, status FROM supplier_doc_profiles")).one()
        assert row.supplier_id == 1
        assert json.loads(row.ci_map) == {"ref": ["Item No."], "qty": ["Q'ty"]}
        assert row.status == "draft"


def test_agency_export_format_and_material_suppl_unit(client, admin_headers):
    r = client.post("/api/customs-agencies", headers=admin_headers,
                    json={"name": "Delta Brokers", "export_format": "symbols", "export_params": {"IDZestawu": 106}})
    assert r.status_code == 201, r.text
    assert (r.json()["export_format"], r.json()["export_params"]) == ("symbols", {"IDZestawu": 106})
    assert client.post("/api/customs-agencies", headers=admin_headers,
                       json={"name": "X", "export_format": "pdf"}).status_code == 422
    with SessionLocal() as db:
        db.add(Material(ref_code="GLOVE-1"))
        db.commit()
        mid = db.query(Material).filter_by(ref_code="GLOVE-1").one().id
    r = client.patch(f"/api/materials/{mid}", headers=admin_headers,
                     json={"suppl_unit": "pary", "suppl_factor": 0.5})
    assert r.status_code == 200, r.text
    assert (r.json()["suppl_unit"], r.json()["suppl_factor"]) == ("pary", 0.5)


def test_patch_agency_omitted_fields_not_reset(client, admin_headers):
    """PATCH z frontendowego formularza edycji (bez export_format/export_params, tak jak
    dzisiejszy UI) nie może wyzerować tych pól do wartości domyślnych."""
    created = client.post("/api/customs-agencies", headers=admin_headers,
                          json={"name": "Delta Brokers", "export_format": "symbols",
                                "export_params": {"IDZestawu": 106}}).json()
    r = client.patch(f"/api/customs-agencies/{created['id']}", headers=admin_headers,
                     json={"name": "Delta Brokers PL", "email": "biuro@delta.pl"})
    assert r.status_code == 200, r.text
    assert (r.json()["export_format"], r.json()["export_params"]) == ("symbols", {"IDZestawu": 106})
    assert r.json()["name"] == "Delta Brokers PL"
