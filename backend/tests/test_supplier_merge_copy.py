"""Scalanie duplikatów dostawców (#20): przepięcie FK, przeniesienie brakujących pól,
rollback przy błędzie w środku transakcji."""
import pytest
from sqlalchemy import select

from app.models import Container, Supplier, User
from app.routers.dictionaries import SUPPLIERS, _merge
from app.schemas import MergeIn


@pytest.fixture()
def pair(client, admin_headers, db_session):
    """Duplikat (z kodem SAP z importu) + cel (bez kodu) + kontener wskazujący duplikat."""
    cid = client.get("/api/companies", headers=admin_headers).json()[0]["id"]
    source = client.post("/api/suppliers", headers=admin_headers,
                         json={"name": "shangai", "company_id": cid}).json()
    target = client.post("/api/suppliers", headers=admin_headers,
                         json={"name": "Shanghai", "company_id": cid}).json()
    row = db_session.get(Supplier, source["id"])
    row.sap_code, row.country = "30001", "CN"
    container = client.post("/api/containers", headers=admin_headers, json={
        "container_no": "MSDU0806613", "company_id": cid,
        "supplier_id": source["id"]}).json()
    db_session.commit()
    return source["id"], target["id"], container["id"]


def test_merge_repins_and_copies_missing_fields(client, admin_headers, db_session, pair):
    source_id, target_id, container_id = pair
    response = client.post(f"/api/suppliers/{source_id}/merge", headers=admin_headers,
                           json={"target_id": target_id})
    assert response.status_code == 200, response.text
    assert response.json()["repinned"].get("containers") == 1
    db_session.expire_all()
    assert db_session.get(Container, container_id).supplier_id == target_id
    assert db_session.get(Supplier, source_id) is None
    target = db_session.get(Supplier, target_id)
    # brakujące pola przeniesione z duplikatu (bez nadpisywania niepustych)
    assert target.sap_code == "30001" and target.country == "CN"
    assert target.name == "Shanghai"


def test_merge_error_rolls_back_everything(db_session, admin_headers, client, pair,
                                           monkeypatch):
    source_id, target_id, container_id = pair
    from app.routers import dictionaries as D

    def boom(*args, **kwargs):
        raise RuntimeError("awaria w środku scalania")

    monkeypatch.setattr(D.audit, "record", boom)
    user = db_session.scalar(select(User))
    with pytest.raises(RuntimeError):
        _merge(db_session, SUPPLIERS, source_id, MergeIn(target_id=target_id), user)
    db_session.rollback()
    # nic nie zostało utrwalone: duplikat żyje, kontener dalej wskazuje duplikat
    assert db_session.get(Supplier, source_id) is not None
    assert db_session.get(Container, container_id).supplier_id == source_id
