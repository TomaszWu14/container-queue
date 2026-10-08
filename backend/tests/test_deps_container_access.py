"""check_container_access: dostęp do pojedynczego kontenera per rola (para do
scope_containers w tests/test_deps.py)."""
import pytest
from fastapi import HTTPException

from app.database import SessionLocal
from app.deps import check_container_access
from app.models import (
    Company,
    Container,
    Forwarder,
    Role,
    User,
    Warehouse,
)


def test_check_container_access_forwarder(client):
    """Forwarder: OK dla własnego kontenera (nawet w innej spółce);
    404 dla innego spedytora, dla kontenera bez spedytora oraz gdy user.forwarder_id=None.
    Rzucamy 404 (nie 403), by nie zdradzać istnienia cudzych kontenerów.
    """
    with SessionLocal() as db:
        co_a = Company(name="FA Co A", code="FACOA")
        co_b = Company(name="FA Co B", code="FACOB")
        db.add_all([co_a, co_b])
        db.flush()
        spedalfa = Forwarder(name="FA-SPEDALFA")
        kn = Forwarder(name="FA-KN")
        db.add_all([spedalfa, kn])
        db.flush()
        own = Container(container_no="FAOU0000001",
                        company_id=co_b.id, forwarder_id=spedalfa.id)   # cross-company
        other_sped = Container(container_no="FAOU0000002",
                               company_id=co_a.id, forwarder_id=kn.id)
        unassigned = Container(container_no="FAOU0000003",
                               company_id=co_a.id, forwarder_id=None)
        db.add_all([own, other_sped, unassigned])
        user = User(login="test-fa-spedalfa", hashed_password="x",
                    role=Role.forwarder, forwarder_id=spedalfa.id)
        orphan = User(login="test-fa-orphan", hashed_password="x",
                      role=Role.forwarder, forwarder_id=None)
        db.add_all([user, orphan])
        db.commit()

        # OK: kontener przypisany do SPEDALFA — nawet gdy jest w spółce B, a user bez company_id
        assert check_container_access(user, own) is None

        # 404: kontener przypisany innemu spedytorowi
        with pytest.raises(HTTPException) as exc:
            check_container_access(user, other_sped)
        assert exc.value.status_code == 404
        # 404: kontener bez przypisanego spedytora
        with pytest.raises(HTTPException) as exc:
            check_container_access(user, unassigned)
        assert exc.value.status_code == 404
        # 404: user bez forwarder_id, kontener też bez — musi być odmowa (nie fail-open na None==None)
        with pytest.raises(HTTPException) as exc:
            check_container_access(orphan, unassigned)
        assert exc.value.status_code == 404


def test_check_container_access_logistics_scoped(client):
    """Logistics (view_all=False): OK dla własnej spółki; 404 dla innej; 404 gdy company_id=None."""
    with SessionLocal() as db:
        own_co = Company(name="LA Own", code="LAOWN")
        other_co = Company(name="LA Other", code="LAOTH")
        db.add_all([own_co, other_co])
        db.flush()
        own = Container(container_no="LAOU0000001", company_id=own_co.id)
        foreign = Container(container_no="LAOU0000002", company_id=other_co.id)
        db.add_all([own, foreign])
        user = User(login="test-la-scoped", hashed_password="x",
                    role=Role.logistics, company_id=own_co.id,
                    view_all_companies=False)
        orphan = User(login="test-la-orphan", hashed_password="x",
                      role=Role.logistics, company_id=None,
                      view_all_companies=False)
        db.add_all([user, orphan])
        db.commit()

        # OK: kontener własnej spółki
        assert check_container_access(user, own) is None
        # 404: kontener cudzej spółki
        with pytest.raises(HTTPException) as exc:
            check_container_access(user, foreign)
        assert exc.value.status_code == 404
        # 404: user bez company_id (nawet dla „własnego" kontenera — None != <int>)
        with pytest.raises(HTTPException) as exc:
            check_container_access(orphan, own)
        assert exc.value.status_code == 404


def test_check_container_access_warehouse(client):
    """Warehouse: OK dla własnej spółki+magazynu; 404 dla innego magazynu tej samej spółki,
    dla innej spółki oraz gdy user.warehouse_id=None (fail-closed).
    """
    with SessionLocal() as db:
        own_co = Company(name="WA Own", code="WAOWN")
        other_co = Company(name="WA Other", code="WAOTH")
        db.add_all([own_co, other_co])
        db.flush()
        own_wh = Warehouse(name="WA Own WH", company_id=own_co.id)
        sibling_wh = Warehouse(name="WA Sibling WH", company_id=own_co.id)
        db.add_all([own_wh, sibling_wh])
        db.flush()
        own = Container(container_no="WAOU0000001",
                        company_id=own_co.id, warehouse_id=own_wh.id)
        sibling = Container(container_no="WAOU0000002",
                            company_id=own_co.id, warehouse_id=sibling_wh.id)
        foreign_co = Container(container_no="WAOU0000003",
                               company_id=other_co.id, warehouse_id=None)
        # kontener bez magazynu we WŁASNEJ spółce — ważne dla wykrycia mutacji orphan-guard
        unassigned_wh = Container(container_no="WAOU0000004",
                                  company_id=own_co.id, warehouse_id=None)
        db.add_all([own, sibling, foreign_co, unassigned_wh])
        user = User(login="test-wa-scoped", hashed_password="x",
                    role=Role.warehouse, company_id=own_co.id,
                    warehouse_id=own_wh.id)
        orphan = User(login="test-wa-orphan", hashed_password="x",
                      role=Role.warehouse, company_id=own_co.id,
                      warehouse_id=None)
        db.add_all([user, orphan])
        db.commit()

        # OK: kontener własnej spółki + własnego magazynu
        assert check_container_access(user, own) is None
        # 404: inny magazyn tej samej spółki (przechodzi check_company_access, wpada na warehouse)
        with pytest.raises(HTTPException) as exc:
            check_container_access(user, sibling)
        assert exc.value.status_code == 404
        # 404: cudza spółka (odcina check_company_access, jeszcze przed warehouse)
        with pytest.raises(HTTPException) as exc:
            check_container_access(user, foreign_co)
        assert exc.value.status_code == 404
        # 404: user bez warehouse_id — nawet dla własnej spółki
        with pytest.raises(HTTPException) as exc:
            check_container_access(orphan, own)
        assert exc.value.status_code == 404
        # 404: orphan warehouse user + kontener bez magazynu w tej samej spółce
        # (bez orphan-guardu None != None = False = fail-open, guard blokuje)
        with pytest.raises(HTTPException) as exc:
            check_container_access(orphan, unassigned_wh)
        assert exc.value.status_code == 404


def test_check_container_access_admin_or_view_all_sees_any(client):
    """Admin i logistics z view_all_companies=True widzą dowolny kontener,
    niezależnie od tego, do której spółki należy (can_view_all bypass).
    """
    with SessionLocal() as db:
        co_a = Company(name="AA Co A", code="AACOA")
        co_b = Company(name="AA Co B", code="AACOB")
        db.add_all([co_a, co_b])
        db.flush()
        cont_a = Container(container_no="AAOU0000001", company_id=co_a.id)
        cont_b = Container(container_no="AAOU0000002", company_id=co_b.id)
        db.add_all([cont_a, cont_b])
        admin = User(login="test-aa-admin", hashed_password="x",
                     role=Role.admin, company_id=co_a.id)
        viewer = User(login="test-aa-viewer", hashed_password="x",
                      role=Role.logistics, company_id=co_a.id,
                      view_all_companies=True)
        db.add_all([admin, viewer])
        db.commit()

        # admin: widzi obie spółki
        assert check_container_access(admin, cont_a) is None
        assert check_container_access(admin, cont_b) is None
        # logistics z flagą view_all: to samo
        assert check_container_access(viewer, cont_a) is None
        assert check_container_access(viewer, cont_b) is None
