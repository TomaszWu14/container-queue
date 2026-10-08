"""B1 — dashboard/demurrage bez N+1.

Potwierdza korektność zbiorczego liczenia terminów demurrage (identyczne wyniki
jak logika per-kontener, z przypadkami brzegowymi) oraz że całość idzie JEDNYM
zapytaniem o tracking_events zamiast N+1.
"""
import datetime

from sqlalchemy import event, select

from app import notifications as N
from app.database import SessionLocal, engine
from app.models import Company, Container, TrackingEvent


def _seed(db):
    cid = db.scalar(select(Company.id))
    # c1: przybycie z trackingu (DISCHARGE nie-estymowane); estymowany ARRIVE ma być pominięty
    c1 = Container(container_no="AAAA1111111", company_id=cid, demurrage_free_days=5)
    # c2: brak trackingu → fallback do ETA
    c2 = Container(container_no="BBBB2222222", company_id=cid, demurrage_free_days=3,
                   eta=datetime.date(2026, 7, 10))
    # c3: brak dni wolnych → liczone wg wartości domyślnej (ETA + settings)
    c3 = Container(container_no="CCCC3333333", company_id=cid,
                   eta=datetime.date(2026, 7, 10))
    # c4: dni wolne, ale brak przybycia i brak ETA → None
    c4 = Container(container_no="DDDD4444444", company_id=cid, demurrage_free_days=7)
    db.add_all([c1, c2, c3, c4])
    db.flush()
    db.add_all([
        TrackingEvent(container_id=c1.id, event_code="DISCHARGE",
                      occurred_at=datetime.datetime(2026, 6, 20, 8, 0), is_estimated=False),
        TrackingEvent(container_id=c1.id, event_code="ARRIVE",  # estymowane — ignorowane
                      occurred_at=datetime.datetime(2026, 6, 10, 8, 0), is_estimated=True),
    ])
    db.commit()
    return [c1, c2, c3, c4]


def test_demurrage_deadlines_values(client):
    with SessionLocal() as db:
        c1, c2, c3, c4 = _seed(db)
        got = N.demurrage_deadlines(db, [c1, c2, c3, c4])
        assert got[c1.id] == datetime.date(2026, 6, 25)   # 06-20 (DISCHARGE) + 5
        assert got[c2.id] == datetime.date(2026, 7, 13)   # ETA 07-10 + 3
        # puste pole → domyślne dni wolne z konfiguracji (nie cisza)
        from app.config import settings
        assert got[c3.id] == datetime.date(2026, 7, 10) + datetime.timedelta(
            days=settings.demurrage_default_free_days)
        assert got[c4.id] is None                          # brak przybycia i ETA
        # wrapper pojedynczy zgodny z wersją zbiorczą
        assert N.demurrage_deadline(db, c1) == datetime.date(2026, 6, 25)


def test_demurrage_batch_is_single_query(client):
    with SessionLocal() as db:
        containers = _seed(db)
        counter = {"tracking_events": 0}

        def _count(conn, cursor, statement, params, context, executemany):
            if "tracking_events" in statement.lower():
                counter["tracking_events"] += 1

        event.listen(engine, "before_cursor_execute", _count)
        try:
            N.demurrage_deadlines(db, containers)
        finally:
            event.remove(engine, "before_cursor_execute", _count)
        # jedno zapytanie GROUP BY na cały zestaw — nie N (po jednym na kontener)
        assert counter["tracking_events"] == 1


def test_demurrage_empty_input_no_query(client):
    with SessionLocal() as db:
        cid = db.scalar(select(Company.id))
        c = Container(container_no="EEEE5555555", company_id=cid)  # bez dni i bez ETA
        db.add(c)
        db.commit()
        counter = {"n": 0}

        def _count(conn, cursor, statement, params, context, executemany):
            if "tracking_events" in statement.lower():
                counter["n"] += 1

        event.listen(engine, "before_cursor_execute", _count)
        try:
            assert N.demurrage_deadlines(db, [c]) == {c.id: None}   # brak przybycia i ETA
            assert N.demurrage_deadlines(db, []) == {}
        finally:
            event.remove(engine, "before_cursor_execute", _count)
        # pusta lista kontenerów → zero zapytań (jedno przypada na wywołanie z danymi)
        assert counter["n"] == 1


def test_demurrage_deadlines_none_for_finished(client):
    """Kontener DOSTARCZONY/ZREALIZOWANY nie ma biegnącego demurrage (dashboard, sygnały)."""
    from app.models import ContainerStatus
    with SessionLocal() as db:
        cid = db.scalar(select(Company.id))
        c = Container(container_no="FFFF6666666", company_id=cid, demurrage_free_days=3,
                      eta=datetime.date(2026, 7, 10), status=ContainerStatus.DOSTARCZONY)
        db.add(c)
        db.commit()
        assert N.demurrage_deadlines(db, [c]) == {c.id: None}
