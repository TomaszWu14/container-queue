"""Słownik dostawców prowadzony ręcznie: import kolejki nie tworzy dostawców, nazwa z pliku
zostaje w Container.supplier_raw, mapowanie nazw przez SupplierAlias."""
import datetime
import io

from openpyxl import Workbook
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Company, Container, Role, Supplier, User, normalize_alias
from app.security import hash_password
from tests.conftest import login

NOS = ["MSKU5000009", "MSKU5000014", "MSDU0806613", "CSQU3054383"]


def _xlsx(rows):
    wb = Workbook()
    ws = wb.active
    ws.append(["DOSTAWCA", "STATEK", "ETA", "KOLEJ/KOŁA", "NR KONTENERA",
               "STATUS ODPRAWY", "DATA ROZŁADUNKU"])
    for supplier, no in rows:
        ws.append([supplier, "MAERSK", datetime.datetime(2026, 9, 1), "kolej", no, "",
                   datetime.datetime(2026, 9, 5)])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _sync(client, hdr, rows):
    r = client.post("/api/import/queue-sync?company_code=BOREALIS&dry_run=false",
                    headers=hdr, files={"file": ("q.xlsx", _xlsx(rows))})
    assert r.status_code == 200, r.text


def _borealis(db):
    return db.scalar(select(Company).where(Company.code == "BOREALIS"))


def _cont(db, no):
    return db.scalar(select(Container).where(Container.container_no == no))


def _supplier(client, hdr, name):
    with SessionLocal() as db:
        cid = _borealis(db).id
    r = client.post("/api/suppliers", headers=hdr, json={"name": name, "company_id": cid})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_normalize_alias():
    assert normalize_alias('  ACME  Co.,  "Ltd";  ') == "acme co ltd"


def test_import_does_not_create_suppliers_and_keeps_raw_name(client, admin_headers):
    _sync(client, admin_headers, [("Nieznany Dostawca Sp. z o.o.", NOS[0])])
    with SessionLocal() as db:
        c = _cont(db, NOS[0])
        assert c.supplier_id is None and c.supplier_raw == "Nieznany Dostawca Sp. z o.o."
        assert db.scalar(select(Supplier).where(
            Supplier.name == "Nieznany Dostawca Sp. z o.o.")) is None
        cid = c.id
    out = client.get(f"/api/containers/{cid}", headers=admin_headers).json()
    assert out["supplier_name"] == "Nieznany Dostawca Sp. z o.o."   # fallback na nazwę z pliku
    assert out["supplier_id"] is None


def test_import_resolves_exact_name_case_insensitive(client, admin_headers):
    sid = _supplier(client, admin_headers, "Acme Ltd")
    _sync(client, admin_headers, [("ACME LTD", NOS[0])])
    with SessionLocal() as db:
        assert _cont(db, NOS[0]).supplier_id == sid


def test_alias_maps_containers_and_future_imports(client, admin_headers):
    _sync(client, admin_headers, [("ACME Co., Ltd.", NOS[0]), ("ACME Co., Ltd.", NOS[1]),
                                  ("Other", NOS[2])])
    rows = client.get("/api/suppliers/unmapped", headers=admin_headers).json()
    assert [(r["name"], r["containers"]) for r in rows] == [("ACME Co., Ltd.", 2), ("Other", 1)]

    sid = _supplier(client, admin_headers, "Acme")
    r = client.post(f"/api/suppliers/{sid}/aliases", headers=admin_headers,
                    json={"alias": "acme co ltd"})
    assert r.status_code == 201, r.text
    assert r.json()["assigned"] == 2
    assert [x["name"] for x in client.get("/api/suppliers/unmapped",
                                          headers=admin_headers).json()] == ["Other"]
    # nowy kontener z tą nazwą w pliku trafia od razu do dostawcy przez alias
    _sync(client, admin_headers, [("ACME Co., Ltd.", NOS[0]), ("ACME Co., Ltd.", NOS[1]),
                                  ("Other", NOS[2]), ("ACME CO LTD", NOS[3])])
    with SessionLocal() as db:
        assert {_cont(db, n).supplier_id for n in NOS[:2] + NOS[3:]} == {sid}
    aliases = client.get(f"/api/suppliers/{sid}/aliases", headers=admin_headers).json()
    assert [a["alias"] for a in aliases] == ["acme co ltd"]

    other = _supplier(client, admin_headers, "Inny")
    clash = client.post(f"/api/suppliers/{other}/aliases", headers=admin_headers,
                        json={"alias": "ACME CO. LTD"})
    assert clash.status_code == 409
    assert client.delete(f"/api/suppliers/aliases/{aliases[0]['id']}",
                         headers=admin_headers).status_code == 204


def test_resync_keeps_manual_supplier_when_name_unmapped(client, admin_headers):
    _sync(client, admin_headers, [("Bez mapy", NOS[0])])
    sid = _supplier(client, admin_headers, "Ręczny")
    with SessionLocal() as db:
        cid = _cont(db, NOS[0]).id
    r = client.patch(f"/api/containers/{cid}", headers=admin_headers, json={"supplier_id": sid})
    assert r.status_code == 200, r.text
    _sync(client, admin_headers, [("Bez mapy", NOS[0])])
    _sync(client, admin_headers, [("Bez mapy", NOS[0])])
    with SessionLocal() as db:
        assert _cont(db, NOS[0]).supplier_id == sid
    # zmiana nazwy w pliku = nowa informacja → Excel wygrywa (niezmapowana → brak dostawcy)
    _sync(client, admin_headers, [("Całkiem inny", NOS[0])])
    with SessionLocal() as db:
        c = _cont(db, NOS[0])
        assert (c.supplier_id, c.supplier_raw) == (None, "Całkiem inny")


def test_merge_moves_aliases_and_adds_source_name(client, admin_headers):
    target = _supplier(client, admin_headers, "Cel")
    dup = _supplier(client, admin_headers, "DUPLIKAT S.A.")
    client.post(f"/api/suppliers/{dup}/aliases", headers=admin_headers, json={"alias": "Dup alias"})
    r = client.post(f"/api/suppliers/{dup}/merge", headers=admin_headers,
                    json={"target_id": target})
    assert r.status_code == 200, r.text
    aliases = client.get(f"/api/suppliers/{target}/aliases", headers=admin_headers).json()
    assert sorted(a["alias"] for a in aliases) == ["DUPLIKAT S.A.", "Dup alias"]


def test_other_company_logistics_cannot_map(client, admin_headers):
    sid = _supplier(client, admin_headers, "Borealis only")
    _sync(client, admin_headers, [("Tajny", NOS[0])])
    with SessionLocal() as db:
        other = Company(name="Obca", code="OBCA")
        db.add(other); db.flush()
        db.add(User(login="obca-log", hashed_password=hash_password("pass12345"),
                    role=Role.logistics, company_id=other.id))
        db.commit()
    hdr = login(client, "obca-log", "pass12345")
    assert client.post(f"/api/suppliers/{sid}/aliases", headers=hdr,
                       json={"alias": "Tajny"}).status_code == 404
    assert client.get("/api/suppliers/unmapped", headers=hdr).json() == []


def test_delete_alias_of_other_company_is_404(client, admin_headers):
    """DELETE aliasu spoza spółki użytkownika: get_scoped -> _enforce_scope -> 404
    (bez enumeracji istnienia cudzego zasobu)."""
    sid = _supplier(client, admin_headers, "Do aliasu")
    alias = client.post(f"/api/suppliers/{sid}/aliases", headers=admin_headers,
                        json={"alias": "alias-borealis"}).json()["alias"]
    with SessionLocal() as db:
        other = Company(name="Obca2", code="OBCA2")
        db.add(other); db.flush()
        db.add(User(login="obca-log2", hashed_password=hash_password("pass12345"),
                    role=Role.logistics, company_id=other.id))
        db.commit()
    hdr = login(client, "obca-log2", "pass12345")
    assert client.delete(f"/api/suppliers/aliases/{alias['id']}",
                         headers=hdr).status_code == 404


