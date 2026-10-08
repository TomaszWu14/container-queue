import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.database import SessionLocal
from app.deps import check_container_access, scope_containers
from app.models import (
    Company,
    Container,
    CustomsAgency,
    Forwarder,
    Role,
    User,
    Warehouse,
)


def test_forwarder_sees_only_own_containers_within_same_company(client):
    """Spedytor SPEDALFA w spółce TESTCO nie widzi kontenera przypisanego SPEDBETA."""
    with SessionLocal() as db:
        company = Company(name="Test Company", code="TESTCO")
        spedalfa = Forwarder(name="TEST-SPEDALFA")
        kn = Forwarder(name="TEST-KN")
        db.add_all([company, spedalfa, kn])
        db.flush()
        own = Container(container_no="TESTU0000001",
                        company_id=company.id, forwarder_id=spedalfa.id)
        other = Container(container_no="TESTU0000002",
                          company_id=company.id, forwarder_id=kn.id)
        db.add_all([own, other])
        user = User(login="test-sped-spedalfa", hashed_password="x",
                    role=Role.forwarder, forwarder_id=spedalfa.id)
        db.add(user)
        db.commit()

        visible = db.scalars(scope_containers(select(Container), user)).all()

        visible_ids = {c.id for c in visible}
        assert own.id in visible_ids
        assert other.id not in visible_ids


def test_forwarder_without_forwarder_id_is_denied(client):
    """Fail-closed: forwarder z forwarder_id=None dostaje 403, nie widzi wszystkiego."""
    with SessionLocal() as db:
        user = User(login="test-sped-orphan", hashed_password="x",
                    role=Role.forwarder, forwarder_id=None)
        db.add(user)
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            scope_containers(select(Container), user)

        assert exc_info.value.status_code == 403
        assert "Konto bez przypisanego spedytora" in exc_info.value.detail


def test_customs_sees_only_containers_assigned_to_its_agency(client):
    """Agencja celna A nie widzi kontenera, którego odprawę zlecono agencji B."""
    with SessionLocal() as db:
        company = Company(name="Customs Co", code="CUSTCO")
        agency_a = CustomsAgency(name="TEST-AGCJA-A")
        agency_b = CustomsAgency(name="TEST-AGCJA-B")
        db.add_all([company, agency_a, agency_b])
        db.flush()
        own = Container(container_no="CUSTU0000001",
                        company_id=company.id, customs_agency_id=agency_a.id)
        other = Container(container_no="CUSTU0000002",
                          company_id=company.id, customs_agency_id=agency_b.id)
        db.add_all([own, other])
        user = User(login="test-customs-a", hashed_password="x",
                    role=Role.customs, customs_agency_id=agency_a.id)
        db.add(user)
        db.commit()

        visible = db.scalars(scope_containers(select(Container), user)).all()

        visible_ids = {c.id for c in visible}
        assert own.id in visible_ids
        assert other.id not in visible_ids

        # dostęp do pojedynczego kontenera: własny OK, cudzy → 404
        check_container_access(user, own)
        with pytest.raises(HTTPException) as exc_info:
            check_container_access(user, other)
        assert exc_info.value.status_code == 404


def test_customs_without_agency_is_denied(client):
    """Fail-closed: customs z customs_agency_id=None dostaje 403, nie widzi wszystkiego."""
    with SessionLocal() as db:
        user = User(login="test-customs-orphan", hashed_password="x",
                    role=Role.customs, customs_agency_id=None)
        db.add(user)
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            scope_containers(select(Container), user)

        assert exc_info.value.status_code == 403
        assert "Konto bez przypisanej agencji celnej" in exc_info.value.detail


def test_logistics_scoped_sees_only_own_company_containers(client):
    """Logistics (view_all_companies=False) widzi tylko kontenery swojej spółki."""
    with SessionLocal() as db:
        own_co = Company(name="Own Company", code="OWNCO")
        other_co = Company(name="Other Company", code="OTHCO")
        db.add_all([own_co, other_co])
        db.flush()
        own = Container(container_no="OWNU0000001", company_id=own_co.id)
        other = Container(container_no="OTHU0000001", company_id=other_co.id)
        db.add_all([own, other])
        user = User(login="test-log-scoped", hashed_password="x",
                    role=Role.logistics, company_id=own_co.id,
                    view_all_companies=False)
        db.add(user)
        db.commit()

        visible = db.scalars(scope_containers(select(Container), user)).all()

        visible_ids = {c.id for c in visible}
        assert own.id in visible_ids
        assert other.id not in visible_ids


def test_logistics_scoped_without_company_id_is_denied(client):
    """Fail-closed: logistics scoped z company_id=None → 403 zamiast fail-open."""
    with SessionLocal() as db:
        user = User(login="test-log-orphan", hashed_password="x",
                    role=Role.logistics, company_id=None,
                    view_all_companies=False)
        db.add(user)
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            scope_containers(select(Container), user)

        assert exc_info.value.status_code == 403
        assert "Konto bez przypisanej spółki" in exc_info.value.detail


def test_warehouse_sees_only_own_company_and_warehouse(client):
    """Warehouse widzi tylko kontenery swojej spółki AND swojego magazynu.

    NIE widzi ani innego magazynu tej samej spółki, ani cudzej spółki.
    """
    with SessionLocal() as db:
        own_co = Company(name="WH Own Company", code="WHOWN")
        other_co = Company(name="WH Other Company", code="WHOTH")
        db.add_all([own_co, other_co])
        db.flush()
        own_wh = Warehouse(name="Own WH", company_id=own_co.id)
        sibling_wh = Warehouse(name="Sibling WH", company_id=own_co.id)
        db.add_all([own_wh, sibling_wh])
        db.flush()
        own = Container(container_no="WHOU0000001",
                        company_id=own_co.id, warehouse_id=own_wh.id)
        sibling = Container(container_no="WHOU0000002",
                            company_id=own_co.id, warehouse_id=sibling_wh.id)
        foreign = Container(container_no="WHOU0000003",
                            company_id=other_co.id, warehouse_id=None)
        db.add_all([own, sibling, foreign])
        user = User(login="test-wh-scoped", hashed_password="x",
                    role=Role.warehouse, company_id=own_co.id,
                    warehouse_id=own_wh.id)
        db.add(user)
        db.commit()

        visible = db.scalars(scope_containers(select(Container), user)).all()

        visible_ids = {c.id for c in visible}
        assert own.id in visible_ids
        assert sibling.id not in visible_ids   # inny magazyn tej samej spółki
        assert foreign.id not in visible_ids   # inna spółka


def test_warehouse_without_warehouse_id_is_denied(client):
    """Fail-closed: warehouse z warehouse_id=None → 403 (nie widzi całej spółki)."""
    with SessionLocal() as db:
        co = Company(name="WH NoWh Company", code="WHNOW")
        db.add(co)
        db.flush()
        user = User(login="test-wh-orphan", hashed_password="x",
                    role=Role.warehouse, company_id=co.id,
                    warehouse_id=None)
        db.add(user)
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            scope_containers(select(Container), user)

        assert exc_info.value.status_code == 403
        assert "Konto magazynu bez przypisanego magazynu" in exc_info.value.detail


def test_warehouse_without_company_id_hits_company_guard_first(client):
    """Ordering: company_id=None + warehouse_id=None → guard spółki (nie magazynu).

    scope_containers wywołuje company_filter_ids PRZED warehouse-check,
    więc brak spółki daje komunikat spółki — nawet gdy warehouse_id też jest None.
    """
    with SessionLocal() as db:
        user = User(login="test-wh-no-co", hashed_password="x",
                    role=Role.warehouse, company_id=None,
                    warehouse_id=None, view_all_companies=False)
        db.add(user)
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            scope_containers(select(Container), user)

        assert exc_info.value.status_code == 403
        assert "Konto bez przypisanej spółki" in exc_info.value.detail
        assert "magazynu" not in exc_info.value.detail  # NIE warehouse msg


def test_warehouse_with_view_all_stays_scoped_to_own_company(client):
    """warehouse + view_all_companies=True (błąd konfiguracji) NIE otwiera dostępu
    do innych spółek: can_view_all() ignoruje flagę na roli magazynu, więc konto
    widzi tylko kontenery WŁASNEJ spółki i WŁASNEGO magazynu.
    """
    with SessionLocal() as db:
        co_a = Company(name="WH-VA Co A", code="WHVAA")
        co_b = Company(name="WH-VA Co B", code="WHVAB")
        db.add_all([co_a, co_b])
        db.flush()
        wh = Warehouse(name="Cross-company WH", company_id=co_a.id)
        db.add(wh)
        db.flush()
        cont_a = Container(container_no="WHVU0000001",
                           company_id=co_a.id, warehouse_id=wh.id)
        cont_b = Container(container_no="WHVU0000002",
                           company_id=co_b.id, warehouse_id=wh.id)
        db.add_all([cont_a, cont_b])
        user = User(login="test-wh-view-all", hashed_password="x",
                    role=Role.warehouse, company_id=co_a.id,
                    warehouse_id=wh.id, view_all_companies=True)
        db.add(user)
        db.commit()

        visible = db.scalars(scope_containers(select(Container), user)).all()

        visible_ids = {c.id for c in visible}
        # tylko własna spółka (co_a) mimo view_all; co_b odcięte filtrem spółki
        assert cont_a.id in visible_ids
        assert cont_b.id not in visible_ids


# Regression guard: rejestr ról, dla których scope_containers/check_container_access
# mają udokumentowane, przetestowane zachowanie w tests/test_deps*.py. deps.py nie ma explicit
# allowlisty ról — nieznana rola cicho wpada w gałąź "logistics scoped" (patrz
# analiza). Ten rejestr + parametryzowany test poniżej wymuszają, żeby nowa wartość
# w enum Role wymagała jawnej deklaracji semantyki tutaj.
DOCUMENTED_ROLES_SCOPE_BEHAVIOR = {
    Role.forwarder: "filtr Container.forwarder_id; 403 gdy forwarder_id=None",
    Role.warehouse: "filtr company + Container.warehouse_id; 403 gdy warehouse_id=None",
    Role.logistics: "filtr company_id (chyba że view_all); 403 gdy company_id=None",
    Role.admin:     "bez filtrów (can_view_all bypass)",
    Role.customs:   "filtr Container.customs_agency_id; 403 gdy customs_agency_id=None",
    Role.purchasing: "filtr company_id jak logistics (bez gałęzi specjalnej); "
                     "403 gdy company_id=None. Separacja: tests/test_purchasing_role.py",
    Role.sales:     "filtr company_id jak purchasing (bez gałęzi specjalnej); 403 gdy "
                    "company_id=None. Separacja + brak zapisu/kosztów: tests/test_role_sales.py",
}


@pytest.mark.parametrize("role", list(Role))
def test_every_role_has_documented_scope_behavior(role):
    """Dodanie nowej wartości do enum Role bez wpisu tutaj = czerwony test,
    zmuszający autora do zadeklarowania semantyki separacji dla nowej roli
    ORAZ dopisania testów zachowania (scope_containers + check_container_access).
    Sygnał, nie substytut TDD dla nowej roli.
    """
    assert role in DOCUMENTED_ROLES_SCOPE_BEHAVIOR, (
        f"Rola {role.value!r} nie ma udokumentowanego zachowania w scope_containers/"
        f"check_container_access. Dodaj wpis do DOCUMENTED_ROLES_SCOPE_BEHAVIOR "
        f"ORAZ napisz testy separacji dla tej roli — deps.py nie fail-close'uje "
        f"nieznanych ról (patrz analiza)."
    )


def test_list_scope_matches_single_access_per_role(client):
    """Drift-guard: dla każdej roli zbiór kontenerów widocznych na LIŚCIE
    (scope_containers, SQL) musi być identyczny ze zbiorem dostępnych POJEDYNCZO
    (check_container_access, obiekt). Ta sama reguła izolacji jest zakodowana dwa
    razy w deps.py — ten test pilnuje, żeby zmiana jednej ścieżki bez drugiej nie
    rozjechała ich (np. lista pokazuje kontener, w który wejście daje 404, albo
    odwrotnie: lista ukrywa coś, do czego szczegół puszcza).
    """
    with SessionLocal() as db:
        co_a = Company(name="EQ Co A", code="EQCOA")
        co_b = Company(name="EQ Co B", code="EQCOB")
        db.add_all([co_a, co_b])
        db.flush()
        f1, f2 = Forwarder(name="EQ-F1"), Forwarder(name="EQ-F2")
        g1, g2 = CustomsAgency(name="EQ-G1"), CustomsAgency(name="EQ-G2")
        db.add_all([f1, f2, g1, g2])
        db.flush()
        wa1 = Warehouse(name="EQ-WA1", company_id=co_a.id)
        wa2 = Warehouse(name="EQ-WA2", company_id=co_a.id)
        wb1 = Warehouse(name="EQ-WB1", company_id=co_b.id)
        db.add_all([wa1, wa2, wb1])
        db.flush()
        # zróżnicowany wszechświat: różne spółki × spedytorzy × agencje × magazyny
        specs = [
            dict(company_id=co_a.id, forwarder_id=f1.id, warehouse_id=wa1.id),
            dict(company_id=co_a.id, forwarder_id=f2.id, warehouse_id=wa2.id),
            dict(company_id=co_a.id, customs_agency_id=g1.id, warehouse_id=wa1.id),
            dict(company_id=co_a.id, customs_agency_id=g2.id),
            dict(company_id=co_a.id),
            dict(company_id=co_b.id, forwarder_id=f1.id, warehouse_id=wb1.id),
            dict(company_id=co_b.id, customs_agency_id=g1.id),
            dict(company_id=co_b.id),
        ]
        containers = [Container(container_no=f"EQXU{i:07d}", **s)
                      for i, s in enumerate(specs)]
        db.add_all(containers)
        # użytkownicy o POPRAWNYCH przypisaniach (orphany mają własne testy 403 wyżej)
        users = {
            "forwarder F1": User(login="eq-fwd", hashed_password="x",
                                 role=Role.forwarder, forwarder_id=f1.id),
            "customs G1": User(login="eq-cus", hashed_password="x",
                               role=Role.customs, customs_agency_id=g1.id),
            "warehouse A/WA1": User(login="eq-wh", hashed_password="x",
                                    role=Role.warehouse, company_id=co_a.id,
                                    warehouse_id=wa1.id),
            "logistics A scoped": User(login="eq-log", hashed_password="x",
                                       role=Role.logistics, company_id=co_a.id,
                                       view_all_companies=False),
            "logistics view_all": User(login="eq-log-va", hashed_password="x",
                                       role=Role.logistics, company_id=co_a.id,
                                       view_all_companies=True),
            "admin": User(login="eq-adm", hashed_password="x",
                          role=Role.admin, company_id=co_a.id),
            "purchasing A": User(login="eq-pur", hashed_password="x",
                                 role=Role.purchasing, company_id=co_a.id),
        }
        db.add_all(list(users.values()))
        db.commit()

        # ograniczamy do naszego wszechświata — niezależnie od izolacji fixtury `client`
        universe_ids = {c.id for c in containers}
        for label, user in users.items():
            list_ids = {c.id for c in db.scalars(scope_containers(select(Container), user))
                        if c.id in universe_ids}
            access_ids = set()
            for c in containers:
                try:
                    check_container_access(user, c)
                    access_ids.add(c.id)
                except HTTPException:
                    pass
            assert list_ids == access_ids, (
                f"[{label}] lista != szczegół — "
                f"tylko-na-liście={list_ids - access_ids}, "
                f"tylko-w-szczególe={access_ids - list_ids}")
