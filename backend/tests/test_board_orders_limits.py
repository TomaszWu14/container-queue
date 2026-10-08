"""Audyt PERF-003: tablica odpraw domyślnie bez zrealizowanych (archiwum osobno, z limitem),
lista zamówień z limitem — obie mówią X-Total-Count, żeby UI nie gubiło rekordów po cichu."""
from app.models import Company, Container, ContainerStatus, CustomsStatus, Order


def _seed(db_session):
    company = db_session.query(Company).first()
    db_session.add_all([
        Container(container_no="ACTV0000001", company_id=company.id, status=ContainerStatus.W_PORCIE,
                  customs_status=CustomsStatus.ZLECONA),
        Container(container_no="DONE0000001", company_id=company.id, status=ContainerStatus.ZREALIZOWANY,
                  customs_status=CustomsStatus.ROZLICZONY),
    ])
    db_session.add_all([Order(number=f"45000000{i:02d}", company_id=company.id) for i in range(3)])
    db_session.commit()


def test_board_active_by_default_archive_on_demand(client, admin_headers, db_session):
    _seed(db_session)
    active = client.get("/api/customs/board", headers=admin_headers)
    assert [c["container_no"] for c in active.json()] == ["ACTV0000001"]
    assert active.headers["X-Total-Count"] == "1"
    archive = client.get("/api/customs/board?archive=true", headers=admin_headers)
    assert [c["container_no"] for c in archive.json()] == ["DONE0000001"]


def test_orders_limited_with_total(client, admin_headers, db_session):
    _seed(db_session)
    r = client.get("/api/orders?limit=2", headers=admin_headers)
    assert len(r.json()) == 2 and r.headers["X-Total-Count"] == "3"
