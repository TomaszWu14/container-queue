"""„Dziś" wg kalendarza polskiego: 23:30 UTC w lecie to już następny dzień w Polsce."""
import datetime
from unittest import mock

from app.models import enums


def _frozen(utc):
    class Frozen(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return utc.astimezone(tz) if tz else utc.replace(tzinfo=None)
    return mock.patch.object(enums.datetime, "datetime", Frozen)


def test_today_pl_after_polish_midnight():
    with _frozen(datetime.datetime(2026, 9, 24, 23, 30, tzinfo=datetime.UTC)):
        assert enums.today_pl() == datetime.date(2026, 9, 25)
        assert enums.pl_midnight_utc() == datetime.datetime(2026, 9, 24, 22, 0)
