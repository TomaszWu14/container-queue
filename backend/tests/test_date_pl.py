"""date_pl — data dla człowieka w tekstach serwera (maile, eksporty, SMS): dd.mm.rrrr."""
import datetime

from app.date_pl import date_pl
from app.mail_html import container_table


def test_date_pl_formats():
    assert date_pl(datetime.date(2026, 9, 25)) == "25.09.2026"
    assert date_pl(datetime.datetime(2026, 9, 25, 14, 5)) == "25.09.2026"
    assert date_pl(datetime.datetime(2026, 9, 25, 14, 5), time=True) == "25.09.2026 14:05"
    assert date_pl("2026-09-25") == "25.09.2026"
    assert date_pl("2026-09-25", time=True) == "25.09.2026"        # sama data — bez 00:00
    assert date_pl("2026-09-25T14:05:00") == "25.09.2026"
    assert date_pl(None) == "" and date_pl("") == ""
    assert date_pl("brak") == "brak"                                # nierozpoznane bez zmian


def test_mail_table_uses_date_pl():
    class C:
        notify_date = datetime.date(2026, 12, 31)
        eta = None
    html = container_table([C()], ["unload", "eta"])
    assert "31.12.2026" in html and "2026-12-31" not in html
