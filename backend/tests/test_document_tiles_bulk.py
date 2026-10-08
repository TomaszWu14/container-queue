"""Mini-kafelki kolejki (spec 2026-10-06 decyzja 28): GET /api/document-tiles?ids=… — te same stany
co kafelki pojedynczego kontenera, SAD = najdalszy etap obiegu, zakres i widoczność per rola,
liczba części w poczekalni."""
from app.models import (Company, Container, ContainerStatus, CustomsStatus, IntakeBatch, IntakeItem,
                        Role, User, Warehouse)
from app.security import create_access_token
from tests.test_document_tiles import _set, _tiles
from tests.test_invoice_conformity import CI, OTHER, OWN, _container, _upload
from tests.test_invoices_checks import _setup


def _bulk(client, headers, ids) -> dict:
    resp = client.get(f"/api/document-tiles?ids={','.join(map(str, ids))}", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _expected(single: dict) -> dict:
    state = {t["code"]: t["state"] for t in single["tiles"]}
    sad = next((state[c] for c in ("SAD_PW", "SAD_PZ", "SAD_DRAFT") if state[c] != "none"), "none")
    missing = [c for c in ("PI", "CI", "PL", "BL") if c in single["missing"]]
    missing += ["SAD"] if any(c.startswith("SAD_") for c in single["missing"]) else []
    return {"codes": {**{c: state[c] for c in ("PI", "CI", "PL", "BL")}, "SAD": sad}, "missing": missing}


def _intake(db, cid, items=2, status="pending", by=None):
    batch = IntakeBatch(container_id=cid, status=status, created_by_id=by)
    batch.items = [IntakeItem(stored_name=f"x{i}", original_name=f"x{i}.pdf", sha256="0" * 64)
                   for i in range(items)]
    db.add(batch)
    db.commit()


def test_bulk_matches_single_and_counts_intake(client, admin_headers, db_session, monkeypatch, tmp_path):
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    a = _container(client, admin_headers, company, sup)
    b = _container(client, admin_headers, company, sup, no=OTHER)
    _set(db_session, a, status=ContainerStatus.W_TRANSPORCIE)
    _set(db_session, b, status=ContainerStatus.W_PORCIE, customs=CustomsStatus.ZWOLNIONY)
    _upload(client, admin_headers, monkeypatch, a, f"{CI}\nCONTAINER No.: {OWN}")
    _intake(db_session, a, items=2)
    _intake(db_session, a, items=1)
    _intake(db_session, a, items=5, status="confirmed")   # zamknięte wgranie się nie liczy

    bulk = _bulk(client, admin_headers, [a, b, 999999])
    assert set(bulk) == {str(a), str(b)}
    for cid in (a, b):
        got = dict(bulk[str(cid)])
        assert got.pop("intake_pending") == (3 if cid == a else 0)
        assert got == _expected(_tiles(client, admin_headers, cid))
    assert bulk[str(a)]["codes"]["CI"] == "warn" and "CI" not in bulk[str(a)]["missing"]
    assert bulk[str(b)]["missing"] == ["PI", "CI", "PL", "BL", "SAD"]


def test_bulk_skips_other_company_and_hides_for_warehouse(client, admin_headers, db_session,
                                                          monkeypatch, tmp_path):
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    cid = _container(client, admin_headers, company, sup)
    _set(db_session, cid, status=ContainerStatus.W_PORCIE, customs=CustomsStatus.ZWOLNIONY)
    _upload(client, admin_headers, monkeypatch, cid, f"{CI}\nCONTAINER No.: {OWN}")
    _intake(db_session, cid)
    other = Company(name="Inna spółka", code="INNA")
    db_session.add(other)
    db_session.flush()
    foreign = Container(container_no="TGHU1111111", company_id=other.id)
    wh = Warehouse(name="WH-BULK", company_id=company.id)
    db_session.add_all([foreign, wh])
    db_session.flush()
    db_session.get(Container, cid).warehouse_id = wh.id
    mag = User(login="mag.bulk", hashed_password="x", role=Role.warehouse,
               company_id=company.id, warehouse_id=wh.id)
    db_session.add(mag)
    db_session.commit()

    result = _bulk(client, {"Authorization": f"Bearer {create_access_token(mag)}"}, [cid, foreign.id])
    assert list(result) == [str(cid)]                                     # obcy kontener pominięty
    mini = result[str(cid)]
    assert mini["codes"]["PI"] == mini["codes"]["CI"] == mini["codes"]["SAD"] == "none"
    assert mini["codes"]["PL"] != "none"
    assert mini["missing"] == ["BL"] and mini["intake_pending"] == 0     # magazyn bez poczekalni


def test_bulk_ignores_garbage_ids(client, admin_headers):
    assert _bulk(client, admin_headers, ["abc", ""]) == {}
