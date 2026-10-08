"""Wymagane dokumenty per dostawca (spec 2026-10-06 decyzja 16) i ostrzeżenie przy zmianie statusu
z brakami (decyzja 9): zestaw dostawcy zmienia `missing` kafelków (pojedynczo i w kolejce),
null = domyślne reguły etapu, ODPRAWIONY/DOSTARCZONY przy brakach = wpis w historii, bez blokady."""
from sqlalchemy import select

from app.models import AuditLog, ContainerStatus, CustomsStatus
from tests.test_document_tiles import _set, _tiles
from tests.test_document_tiles_bulk import _bulk
from tests.test_invoice_conformity import _container
from tests.test_invoices_checks import _setup


def _required(client, headers, sup_id, codes):
    return client.put(f"/api/suppliers/{sup_id}/required-docs", headers=headers, json={"codes": codes})


def _warn_audit(db, cid) -> list[AuditLog]:
    return list(db.scalars(select(AuditLog).where(AuditLog.entity_type == "containers",
                                                  AuditLog.entity_id == cid,
                                                  AuditLog.field == "docs_missing_on_status")))


def test_supplier_set_changes_missing_single_and_bulk(client, admin_headers, db_session, monkeypatch, tmp_path):
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    cid = _container(client, admin_headers, company, sup)
    _set(db_session, cid, status=ContainerStatus.W_TRANSPORCIE)
    assert _tiles(client, admin_headers, cid)["missing"] == ["PI", "CI", "PL", "BL"]   # domyślnie

    resp = _required(client, admin_headers, sup.id, ["BL", "CI"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["required_docs"] == ["CI", "BL"]          # kolejność kafelków
    result = _tiles(client, admin_headers, cid)
    assert result["missing"] == ["CI", "BL"]
    assert not next(t for t in result["tiles"] if t["code"] == "PI")["required"]
    assert _bulk(client, admin_headers, [cid])[str(cid)]["missing"] == ["CI", "BL"]

    assert _required(client, admin_headers, sup.id, None).json()["required_docs"] is None   # „domyślne”
    assert _tiles(client, admin_headers, cid)["missing"] == ["PI", "CI", "PL", "BL"]


def test_unknown_code_rejected(client, admin_headers, db_session, monkeypatch, tmp_path):
    _, sup = _setup(db_session, monkeypatch, tmp_path)
    assert _required(client, admin_headers, sup.id, ["XYZ"]).status_code == 422


def test_customs_odprawiony_with_missing_docs_warns_not_blocks(client, admin_headers, db_session,
                                                             monkeypatch, tmp_path):
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    cid = _container(client, admin_headers, company, sup)
    _required(client, admin_headers, sup.id, ["BL", "SAD_PZ"])
    _set(db_session, cid, status=ContainerStatus.W_PORCIE, customs=CustomsStatus.DRAFT_POTWIERDZONY)

    resp = client.post(f"/api/customs/containers/{cid}/status", headers=admin_headers,
                       json={"customs_status": "ODPRAWIONY"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["customs_status"] == "ODPRAWIONY"          # bez blokady
    assert resp.json()["docs_warning"].endswith("Braki: BL, SAD_PZ")
    [entry] = _warn_audit(db_session, cid)
    assert entry.new_value == "BL, SAD_PZ" and entry.note.startswith("Braki: BL, SAD_PZ")


def test_patch_customs_and_delivered_status_warn(client, admin_headers, db_session, monkeypatch, tmp_path):
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    cid = _container(client, admin_headers, company, sup)
    _required(client, admin_headers, sup.id, ["BL"])
    _set(db_session, cid, status=ContainerStatus.W_PORCIE, customs=CustomsStatus.ODPRAWIONY)

    resp = client.patch(f"/api/containers/{cid}", headers=admin_headers, json={"customs_status": "ZWOLNIONY"})
    assert resp.status_code == 200 and resp.json()["docs_warning"].endswith("Braki: BL")
    resp = client.post(f"/api/containers/{cid}/status", headers=admin_headers, json={"status": "DOSTARCZONY"})
    assert resp.status_code == 200 and resp.json()["status"] == "DOSTARCZONY"
    assert resp.json()["docs_warning"].endswith("Braki: BL")
    assert len(_warn_audit(db_session, cid)) == 2

    # bez braków (zestaw pusty) — ani ostrzeżenia, ani wpisu
    _required(client, admin_headers, sup.id, [])
    _set(db_session, cid, status=ContainerStatus.AWIZOWANY)
    resp = client.post(f"/api/containers/{cid}/status", headers=admin_headers, json={"status": "DOSTARCZONY"})
    assert resp.json()["docs_warning"] is None and len(_warn_audit(db_session, cid)) == 2


def test_bulk_status_records_warning(client, admin_headers, db_session, monkeypatch, tmp_path):
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    cid = _container(client, admin_headers, company, sup)
    _set(db_session, cid, status=ContainerStatus.AWIZOWANY)
    resp = client.post("/api/containers/bulk/status", headers=admin_headers,
                       json={"ids": [cid], "status": "DOSTARCZONY"})
    assert resp.status_code == 200 and resp.json()["ok"] == [cid]
    assert _warn_audit(db_session, cid)[0].new_value == "PI, CI, PL, BL"   # domyślny zestaw
