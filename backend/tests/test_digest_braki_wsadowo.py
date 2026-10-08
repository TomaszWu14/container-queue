"""ARCH-006 (c): poranny digest liczy braki dokumentów wsadowo — liczba zapytań nie rośnie
z liczbą kontenerów (wcześniej 2 zapytania na kontener z ETA ≤ 7 dni)."""
import datetime
from zoneinfo import ZoneInfo

from app import notifications as n
from app.config import settings
from app.models import Notification, today_pl
from tests.test_docs_gaps_batch import _seed
from tests.test_notifications_w4 import _company_id, _mk_user, login
from tests.test_query_bounds import _count_statements


def _digest_statements(db, monkeypatch):
    db.query(Notification).filter(Notification.kind == "daily_digest").delete()
    db.commit()
    now = datetime.datetime.combine(today_pl(), datetime.time(5, 0))
    local = now.replace(tzinfo=datetime.UTC).astimezone(ZoneInfo("Europe/Warsaw"))
    monkeypatch.setattr(settings, "digest_hour", local.hour)
    with _count_statements() as counter:
        assert n.check_daily_digest_alerts(db, now=now) >= 1
    return counter["n"]


def test_digest_query_count_does_not_grow(client, db_session, monkeypatch):
    headers = login(client)
    _mk_user(client, headers, "logdigperf", company_id=_company_id(client, headers))
    _seed(db_session, 5, "D")
    few = _digest_statements(db_session, monkeypatch)
    _seed(db_session, 20, "E")
    many = _digest_statements(db_session, monkeypatch)
    assert many <= few + 2, (few, many)
