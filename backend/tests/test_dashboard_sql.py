"""PERF-003 / ARCH-006(a): pulpit liczy kafelki w SQL i nie hydratuje „cichych” kontenerów.

(1) poprawność — odpowiedź na zasianym zbiorze ma wartości policzone ręcznie z reguł;
(2) wydajność — liczba zapytań i załadowanych obiektów Container nie rośnie z 10 do 50
    kontenerów, które nie trafiają ani na listy, ani do sygnałów."""
import contextlib
import datetime

from sqlalchemy import event, select

from app.models import (
    Company,
    Container,
    ContainerStatus,
    CustomsStatus,
    DocumentStatus,
    SapOrder,
    TrackingEvent,
    today_pl,
)
from tests.test_query_bounds import _count_statements, _numbers


@contextlib.contextmanager
def _count_loaded_containers():
    counter = {"n": 0}

    def _inc(*_args, **_kw):
        counter["n"] += 1

    event.listen(Container, "load", _inc)
    try:
        yield counter
    finally:
        event.remove(Container, "load", _inc)


def _company_id(db, code="BOREALIS"):
    return db.scalar(select(Company.id).where(Company.code == code))


def _add(db, no, company_id, **kw):
    c = Container(container_no=no, company_id=company_id, **kw)
    db.add(c)
    db.flush()
    return c


def test_dashboard_values_on_seeded_dataset(client, admin_headers, db_session):
    db = db_session
    cid = _company_id(db)
    t = today_pl()
    d = datetime.timedelta
    ok = DocumentStatus.ZALACZONE
    n = iter(_numbers(12, prefix="TGHU"))
    today_c = _add(db, next(n), cid, status=ContainerStatus.AWIZOWANY, notify_date=t,
                   document_status=ok)
    delayed_c = _add(db, next(n), cid, status=ContainerStatus.W_TRANSPORCIE, eta=t - d(1))
    port_c = _add(db, next(n), cid, status=ContainerStatus.W_PORCIE, notify_date=t + d(1),
                  customs_status=CustomsStatus.ZLECONA, document_status=DocumentStatus.WYSLANE)
    dem_c = _add(db, next(n), cid, status=ContainerStatus.W_PORCIE, eta=t - d(10),
                 demurrage_free_days=7, document_status=ok)
    shift_c = _add(db, next(n), cid, status=ContainerStatus.W_TRANSPORCIE, eta=t + d(20),
                   notify_date=t + d(25), planning_eta_at_send=t + d(15), document_status=ok)
    _add(db, next(n), cid, status=ContainerStatus.DOSTARCZONY, eta=t - d(5))
    _add(db, next(n), cid, status=ContainerStatus.ZREALIZOWANY, notify_date=t)
    _add(db, next(n), cid, status=ContainerStatus.W_TRANSPORCIE, eta=t + d(30),
         notify_date=t + d(32), document_status=ok)                               # cichy
    po_c = _add(db, next(n), cid, status=ContainerStatus.W_PRODUKCJI, document_status=ok)
    docs_c = _add(db, next(n), cid, status=ContainerStatus.ZAPOWIEDZIANY, eta=t + d(2))
    arr_c = _add(db, next(n), cid, status=ContainerStatus.W_PORCIE, document_status=ok)
    db.add(SapOrder(company_id=cid, order_number="4500000001", container_id=po_c.id,
                    supplier_confirmed=False, doc_date=t - d(10)))
    db.add(TrackingEvent(container_id=arr_c.id, event_code="DISCHARGE",
                         occurred_at=datetime.datetime.combine(t - d(8), datetime.time(12))))
    db.commit()

    data = client.get("/api/stats/dashboard", headers=admin_headers).json()
    assert (data["today"], data["tomorrow"], data["in_transit"], data["at_port"],
            data["customs_in_progress"], data["delayed"]) == (1, 1, 3, 3, 1, 1)
    assert [r["container_no"] for r in data["today_list"]] == [today_c.container_no]
    assert [(r["container_no"], r["delay_days"]) for r in data["delayed_list"]] == \
        [(delayed_c.container_no, 1)]
    # termin: dem_c = ETA-10 + 7 = -3; arr_c = wyładunek -8 + 5 domyślnych = -3 (kolejność id)
    assert [(r["container_no"], r["deadline"]) for r in data["demurrage_list"]] == \
        [(dem_c.container_no, (t - d(3)).isoformat()),
         (arr_c.container_no, (t - d(3)).isoformat())]
    got = {(s["container_no"], s["type"]) for s in data["action_feed"]}
    assert got == {
        (delayed_c.container_no, "delayed"), (delayed_c.container_no, "missing_avizo"),
        (delayed_c.container_no, "missing_docs"),
        (port_c.container_no, "missing_eta"),
        (dem_c.container_no, "demurrage"), (dem_c.container_no, "stuck"),
        (dem_c.container_no, "missing_avizo"),
        (shift_c.container_no, "eta_shift"),
        (po_c.container_no, "po_unconfirmed"),
        (docs_c.container_no, "missing_docs"),
        (arr_c.container_no, "demurrage"), (arr_c.container_no, "missing_eta"),
    }
    scores = [s["score"] for s in data["action_feed"]]
    assert scores == sorted(scores, reverse=True)


def _seed_quiet(db, count, prefix):
    cid = _company_id(db)
    t = today_pl()
    for no in _numbers(count, prefix=prefix):
        db.add(Container(container_no=no, company_id=cid, status=ContainerStatus.W_TRANSPORCIE,
                         eta=t + datetime.timedelta(days=30),
                         notify_date=t + datetime.timedelta(days=32),
                         document_status=DocumentStatus.ZALACZONE))
    db.commit()


def _measure(client, headers):
    with _count_statements() as stmts, _count_loaded_containers() as loaded:
        assert client.get("/api/stats/dashboard", headers=headers).status_code == 200
    return stmts["n"], loaded["n"]


def test_dashboard_cost_does_not_grow_with_quiet_containers(client, admin_headers, db_session):
    _seed_quiet(db_session, 10, "MSKU")
    _measure(client, admin_headers)   # rozgrzewka: pierwsze żądanie ładuje cache (+1 zapytanie)
    small = _measure(client, admin_headers)
    _seed_quiet(db_session, 40, "TCLU")
    big = _measure(client, admin_headers)
    print(f"dashboard 10 vs 50 kontenerów: zapytania {small[0]}→{big[0]}, "
          f"załadowane Container {small[1]}→{big[1]}")
    assert big[0] == small[0], f"zapytania: {small[0]} → {big[0]}"
    assert big[1] == small[1], f"załadowane kontenery: {small[1]} → {big[1]}"
