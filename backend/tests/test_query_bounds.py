"""Audyt N+1 / pełne skany: filtr delayed w SQL, cargo statku jednym zapytaniem o pozycje."""
import contextlib
import datetime

from sqlalchemy import event, select

from app.database import engine
from app.iso6346 import check_digit
from app.models import Container, Order, OrderItem, TrackedVessel, today_pl
from tests.conftest import login


def _numbers(count, prefix="MSKU"):
    out, n = [], 100000
    while len(out) < count:
        base = f"{prefix}{n:06d}"
        if check_digit(base) != 10:
            out.append(base + str(check_digit(base)))
        n += 1
    return out


@contextlib.contextmanager
def _count_statements():
    counter = {"n": 0}

    def _inc(*_args, **_kw):
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _inc)
    try:
        yield counter
    finally:
        event.remove(engine, "before_cursor_execute", _inc)


def _company_id(client, headers, code="ACME"):
    return next(c["id"] for c in client.get("/api/companies", headers=headers).json()
                if c["code"] == code)


def _mk(client, headers, no, company_id, **extra):
    resp = client.post("/api/containers", headers=headers,
                       json={"container_no": no, "company_id": company_id, **extra})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_delayed_sql_clause_matches_python_property(client, db_session):
    headers = login(client)
    cid = _company_id(client, headers)
    today = today_pl()
    past, future = (today - datetime.timedelta(days=2)).isoformat(), \
        (today + datetime.timedelta(days=2)).isoformat()
    nos = _numbers(6)
    _mk(client, headers, nos[0], cid, eta=past, status="W_TRANSPORCIE")      # opóźniony
    _mk(client, headers, nos[1], cid, notify_date=past, status="W_PORCIE")   # opóźniony
    _mk(client, headers, nos[2], cid, eta=past, status="DOSTARCZONY")        # zakończony
    _mk(client, headers, nos[3], cid)                                        # brak dat
    _mk(client, headers, nos[4], cid, eta=future, status="W_TRANSPORCIE")
    _mk(client, headers, nos[5], cid, eta=past, status="W_PORCIE")           # ETA, ale w porcie

    rows = db_session.scalars(select(Container)).all()
    expected = {c.id for c in rows if c.is_delayed}
    assert len(expected) == 2
    sql_ids = set(db_session.scalars(
        select(Container.id).where(Container.delayed_clause(today))))
    assert sql_ids == expected
    not_ids = set(db_session.scalars(
        select(Container.id).where(~Container.delayed_clause(today))))
    assert not_ids == {c.id for c in rows} - expected

    api_true = {c["id"] for c in client.get("/api/containers?delayed=true",
                                            headers=headers).json()}
    api_false = {c["id"] for c in client.get("/api/containers?delayed=false",
                                             headers=headers).json()}
    assert api_true == expected and api_false == {c.id for c in rows} - expected
    assert len(client.get("/api/containers?delayed=true&limit=1", headers=headers).json()) == 1


def test_vessel_cargo_items_query_count_is_constant(client, db_session):
    headers = login(client)
    cid = _company_id(client, headers)
    vessel = TrackedVessel(name="MV LICZNIK")
    db_session.add(vessel)
    db_session.commit()

    def add(nos):
        ids = [_mk(client, headers, no, cid, vessel="MV LICZNIK") for no in nos]
        for i, (no, container_id) in enumerate(zip(nos, ids, strict=True)):
            order_no = f"4500{no[4:10]}"
            order = Order(company_id=cid, number=order_no)
            db_session.add(order)
            db_session.flush()
            db_session.get(Container, container_id).order_id = order.id
            db_session.add(OrderItem(company_id=cid, order_number=order_no, position=str(i),
                                     material=f"M{i}", description="x", quantity="1",
                                     unit="SZT"))
        db_session.commit()

    def measure():
        with _count_statements() as counter:
            data = client.get(f"/api/tracking/vessels/{vessel.id}/cargo",
                              headers=headers).json()
        assert all(len(c["items"]) == 1 for c in data["containers"])
        return counter["n"], len(data["containers"])

    nos = _numbers(6, "TGBU")
    add(nos[:2])
    small, n_small = measure()
    add(nos[2:])
    big, n_big = measure()
    assert (n_small, n_big) == (2, 6)
    assert big == small
