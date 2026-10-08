"""Kontenery tranzytowe (flaga is_transit).

Strażnik jednej reguły: tranzyt NIE zajmuje slotu w dziennym limicie rozładunków
(nie jedzie do naszego magazynu), a poza tym zachowuje się jak zwykły kontener.
"""
import datetime

from app.models import Container, PlanningStatus, today_pl
from tests.conftest import login

TRANSIT_NO = "MSDU0806613"
NORMAL_NO = "CSNU0110266"


def _create(client, headers, container_no, **extra):
    companies = client.get("/api/companies", headers=headers).json()
    company_id = next(c["id"] for c in companies if c["code"] == "BOREALIS")
    body = {"container_no": container_no, "company_id": company_id,
            "status": "ZAPOWIEDZIANY", **extra}
    response = client.post("/api/containers", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_transit_flag_roundtrip(client):
    headers = login(client)
    created = _create(client, headers, TRANSIT_NO, is_transit=True)
    assert created["is_transit"] is True
    fetched = client.get(f"/api/containers/{created['id']}", headers=headers).json()
    assert fetched["is_transit"] is True


def test_transit_filter(client):
    headers = login(client)
    _create(client, headers, TRANSIT_NO, is_transit=True)
    _create(client, headers, NORMAL_NO)

    def numbers(query):
        rows = client.get(f"/api/containers?{query}", headers=headers).json()
        items = rows["items"] if isinstance(rows, dict) else rows
        return {c["container_no"] for c in items}

    assert TRANSIT_NO in numbers("transit=true")
    assert NORMAL_NO not in numbers("transit=true")
    assert NORMAL_NO in numbers("transit=false")
    assert TRANSIT_NO not in numbers("transit=false")
    # brak parametru = bez filtra (kompatybilność wsteczna)
    both = numbers("")
    assert {TRANSIT_NO, NORMAL_NO} <= both


def test_transit_does_not_count_towards_daily_limit(client, db_session):
    """Dwa kontenery na ten sam dzień, jeden tranzytowy — `used` liczy tylko zwykły."""
    headers = login(client)
    day = (today_pl() + datetime.timedelta(days=5)).isoformat()
    _create(client, headers, TRANSIT_NO, is_transit=True, notify_date=day)
    normal = _create(client, headers, NORMAL_NO, notify_date=day)
    # potwierdzony termin, żeby test sprawdzał wyłącznie wykluczenie tranzytu,
    # niezależnie od reguły "tylko potwierdzone liczą się do limitu" (task 4)
    container = db_session.get(Container, normal["id"])
    container.planning_status = PlanningStatus.POTWIERDZONE
    db_session.commit()

    days = client.get(f"/api/queue?date_from={day}&date_to={day}", headers=headers).json()
    entry = next(d for d in days if d["day"] == day)
    assert len(entry["containers"]) == 2      # oba widoczne w kolejce
    assert entry["used"] == 1                 # ale tranzyt nie zajmuje slotu


def test_transit_customer_fields_roundtrip(client, admin_headers):
    created = _create(client, admin_headers, "MSKU1234565", is_transit=True,
                      customer_name="ACME Sp. z o.o.",
                      customer_address="ul. Prosta 1, Poznań",
                      customer_contact="Jan Nowak, 600100200")
    assert created["customer_name"] == "ACME Sp. z o.o."
    cid = created["id"]
    r = client.patch(f"/api/containers/{cid}", headers=admin_headers,
                     json={"customer_name": "ACME 2"})
    assert r.status_code == 200
    assert r.json()["customer_name"] == "ACME 2"


def test_customer_fields_hidden_from_warehouse_and_customs(client, db_session):
    """Maskowanie na wyjściu (to_out) — wzorzec _WAREHOUSE_HIDDEN/_CUSTOMS_HIDDEN."""
    from app.models import Role, User
    from app.routers.containers import to_out
    headers = login(client)
    created = _create(client, headers, TRANSIT_NO, is_transit=True,
                      customer_name="ACME Sp. z o.o.",
                      customer_address="ul. Prosta 1, Poznań",
                      customer_contact="Jan Nowak, 600100200")
    container = db_session.get(Container, created["id"])
    for role in (Role.warehouse, Role.customs):
        out = to_out(container, User(login=f"mask-{role.value}",
                                     hashed_password="x", role=role))
        assert out.customer_name == ""
        assert out.customer_address == ""
        assert out.customer_contact == ""
