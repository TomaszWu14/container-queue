"""Scalanie dubli dostawców po przejściu na globalną kartotekę (spec 2026-09-25 §3):
propozycja = dry-run, wykonanie = te same scalenia co ręczne „Scal z…"."""
import pytest
from sqlalchemy import select

from app.database import SessionLocal
from app.models import (
    AuditLog,
    Company,
    Container,
    Order,
    Supplier,
    SupplierAlias,
    SupplierDocProfile,
)
from app.routers.dictionaries_merge import SUPPLIERS, merge_into
from app.supplier_consolidation import apply_groups, delete_orphans, orphans_preview, proposal
from tests.conftest import login


def _seed():
    with SessionLocal() as db:
        pt = db.scalar(select(Company).where(Company.code == "PT"))
        rows = {
            "z": Supplier(name="Ningbo Tools", sap_code="200"),     # kopia z importu do Acme
            "p": Supplier(name="Ningbo Tools", sap_code="200"),     # kopia z importu do PT
            "lone": Supplier(name="Solo Ltd", sap_code="300"),
            "nosap": Supplier(name="NINGBO TOOLS", sap_code=""),    # ręczny, bez kodu SAP
            "orphan": Supplier(name="Nikt", sap_code=""),
        }
        db.add_all([*rows.values(), Supplier(name="Stary", sap_code="", is_active=False)])
        db.flush()
        db.add(Container(container_no="MSKU5000009", company_id=pt.id, supplier_id=rows["p"].id))
        db.commit()
        return {k: v.id for k, v in rows.items()}


def test_proposal_groups_same_sap_code_and_lists_unresolved(db_session):
    ids = _seed()
    plan = proposal(db_session)
    assert len(plan["merge_groups"]) == 1
    group = plan["merge_groups"][0]
    assert group["sap_code"] == "200"
    assert group["target"]["id"] == ids["p"]                 # używany (kontener) zostaje
    assert [s["id"] for s in group["sources"]] == [ids["z"]]
    unresolved = {u["id"]: u for u in plan["unresolved"]}
    assert set(unresolved) == {ids["nosap"], ids["orphan"]}  # nieaktywny nie wraca na listę
    assert unresolved[ids["nosap"]]["suggestion"]["id"] == ids["p"]
    assert unresolved[ids["orphan"]]["suggestion"] is None
    assert unresolved[ids["orphan"]]["usage"] == 0


def test_apply_merges_groups_and_is_idempotent(db_session):
    ids = _seed()
    assert apply_groups(db_session, None) == {"groups": 1, "merged": 1}
    db_session.commit()
    assert db_session.get(Supplier, ids["z"]) is None
    assert proposal(db_session)["merge_groups"] == []
    assert apply_groups(db_session, None) == {"groups": 0, "merged": 0}


def test_cli_dry_run_changes_nothing_then_applies(client):
    ids = _seed()
    from scripts.consolidate_suppliers import run
    assert run(apply=False) == {"groups": 1, "merged": 0}
    with SessionLocal() as db:
        assert db.get(Supplier, ids["z"]) is not None
    assert run(apply=True) == {"groups": 1, "merged": 1}


def test_resolve_endpoints_admin_only_and_single_decisions(client, admin_headers):
    ids = _seed()
    client.post("/api/users", headers=admin_headers, json={
        "login": "log.res", "password": "haslo123", "role": "logistics",
        "view_all_companies": True})
    log_h = login(client, "log.res", "haslo123")
    assert client.get("/api/suppliers/resolve", headers=log_h).status_code == 403
    assert client.post("/api/suppliers/resolve/apply", headers=log_h).status_code == 403

    plan = client.get("/api/suppliers/resolve", headers=admin_headers).json()
    assert [g["sap_code"] for g in plan["merge_groups"]] == ["200"]
    applied = client.post("/api/suppliers/resolve/apply", headers=admin_headers)
    assert applied.status_code == 200 and applied.json()["merged"] == 1
    # pojedyncze decyzje — istniejące endpointy: scal z podpowiedzią, usuń bez powiązań
    assert client.post(f"/api/suppliers/{ids['nosap']}/merge", headers=admin_headers,
                       json={"target_id": ids["p"]}).status_code == 200
    assert client.delete(f"/api/suppliers/{ids['orphan']}", headers=admin_headers).status_code == 204
    assert client.get("/api/suppliers/resolve", headers=admin_headers).json() == {
        "merge_groups": [], "unresolved": []}


# --- decyzje usera #2 i #8: kopie nadawców spółek-klientów bez powiązań --------------


def _seed_orphans():
    with SessionLocal() as db:
        pt, tim, yel = (db.scalar(select(Company).where(Company.code == c))
                        for c in ("PT", "BOREALIS", "COBALT"))
        rows = {
            "with_container": Supplier(name="Ma kontener", client_company_id=tim.id),
            "with_order": Supplier(name="Ma zamowienie", client_company_id=tim.id),
            "with_alias": Supplier(name="Ma alias", client_company_id=tim.id),
            "with_profile": Supplier(name="Ma profil", client_company_id=tim.id),
            # kartoteka Acme nigdy masowo (decyzja #8) — z kodem SAP i bez
            "catalog_sap": Supplier(name="Kartoteka z SAP", sap_code="777"),
            "catalog_nosap": Supplier(name="Kartoteka bez SAP", sap_code=""),
            "orphan_tim": Supplier(name="Kopia Borealis", sap_code="901", client_company_id=tim.id),
            "orphan_yel": Supplier(name="Kopia Cobalt", client_company_id=yel.id),
        }
        db.add_all(rows.values())
        db.flush()
        db.add(Container(container_no="MSKU5000010", company_id=pt.id,
                         supplier_id=rows["with_container"].id))
        db.add(Order(company_id=pt.id, supplier_id=rows["with_order"].id, number="PO-ORPH-1"))
        db.add(SupplierAlias(company_id=pt.id, supplier_id=rows["with_alias"].id,
                             alias="Ma alias", alias_norm="MA ALIAS"))
        db.add(SupplierDocProfile(supplier_id=rows["with_profile"].id))
        db.commit()
        return {k: v.id for k, v in rows.items()}


def test_orphans_preview_counts_per_company_without_changing_anything(db_session):
    ids = _seed_orphans()
    preview = orphans_preview(db_session)
    assert {s["id"] for s in preview["sample"]} == {ids["orphan_tim"], ids["orphan_yel"]}
    assert preview["count"] == 2
    assert preview["by_company"] == {"BOREALIS": 1, "COBALT": 1}
    assert db_session.get(Supplier, ids["orphan_tim"]) is not None  # dry-run


def test_delete_orphans_only_client_copies_without_relations(db_session):
    ids = _seed_orphans()
    assert delete_orphans(db_session, None) == 2
    db_session.commit()
    assert db_session.get(Supplier, ids["orphan_tim"]) is None
    assert db_session.get(Supplier, ids["orphan_yel"]) is None
    for keep in ("with_container", "with_order", "with_alias", "with_profile",
                 "catalog_sap", "catalog_nosap"):
        assert db_session.get(Supplier, ids[keep]) is not None, keep
    note = db_session.scalar(select(AuditLog.note).where(
        AuditLog.field == "__orphans_deleted__"))
    assert "Kopia Borealis" in note and "SAP=901" in note and "BOREALIS" in note
    assert "Kopia Cobalt" in note and "COBALT" in note
    assert delete_orphans(db_session, None) == 0


def test_orphans_endpoints_admin_only(client, admin_headers):
    ids = _seed_orphans()
    client.post("/api/users", headers=admin_headers, json={
        "login": "log.orph", "password": "haslo123", "role": "logistics",
        "view_all_companies": True})
    log_h = login(client, "log.orph", "haslo123")
    assert client.get("/api/suppliers/resolve/orphans", headers=log_h).status_code == 403
    assert client.post("/api/suppliers/resolve/orphans/delete", headers=log_h).status_code == 403

    preview = client.get("/api/suppliers/resolve/orphans", headers=admin_headers).json()
    assert preview["count"] == 2
    result = client.post("/api/suppliers/resolve/orphans/delete", headers=admin_headers)
    assert result.status_code == 200 and result.json()["deleted"] == 2
    with SessionLocal() as db:
        assert db.get(Supplier, ids["orphan_tim"]) is None
        assert db.get(Supplier, ids["catalog_nosap"]) is not None


# --- decyzja usera #9: grupa z ≥2 profilami dokumentów tylko ręcznie --------------------


def test_group_with_two_profiles_is_flagged_and_skipped_by_apply(db_session):
    ids = _seed()
    extra = Supplier(name="Ningbo Tools", sap_code="300")  # druga kopia „Solo" pod kodem 300
    db_session.add(extra)
    db_session.flush()
    db_session.add_all([SupplierDocProfile(supplier_id=ids["z"]),
                        SupplierDocProfile(supplier_id=ids["p"])])
    db_session.commit()
    groups = {g["sap_code"]: g for g in proposal(db_session)["merge_groups"]}
    assert groups["200"]["profile_conflict"] is True
    assert groups["300"]["profile_conflict"] is False
    assert apply_groups(db_session, None) == {"groups": 1, "merged": 1}
    db_session.commit()
    assert db_session.get(Supplier, ids["z"]) is not None   # konflikt profili — nietknięte
    assert db_session.get(Supplier, ids["p"]) is not None
    assert db_session.get(SupplierDocProfile, db_session.scalar(select(
        SupplierDocProfile.id).where(SupplierDocProfile.supplier_id == ids["z"]))) is not None


# --- review PR #631: scalanie różnych kodów SAP ---------------------------------------


def test_merge_different_sap_codes_is_refused(client, admin_headers, db_session):
    a, b = Supplier(name="A", sap_code="111"), Supplier(name="B", sap_code="222")
    db_session.add_all([a, b])
    db_session.commit()
    r = client.post(f"/api/suppliers/{a.id}/merge", headers=admin_headers,
                    json={"target_id": b.id})
    assert r.status_code == 409 and "111 ≠ 222" in r.json()["detail"]
    db_session.expire_all()
    assert db_session.get(Supplier, a.id).sap_code == "111"
    with pytest.raises(ValueError):
        merge_into(db_session, SUPPLIERS, a, b, None)
