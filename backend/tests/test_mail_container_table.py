"""Wspólna tabela kontenerów w mailach (awizacja do magazynu, kolejka dnia do spedycji)."""
import datetime
from types import SimpleNamespace as N

from app.mail_html import RED, SIGNATURE, container_table
from app.routers.avizo import _warehouse_email_html
from app.routers.forwarding import _queue_email_html


def _c(i, no, wh):
    return N(id=i, notify_date=datetime.date(2026, 9, i), eta=None, container_no=no,
             supplier=N(name="Sup&Co"), vessel=None, transport_type=None,
             order_numbers="A\nB", order=None, warehouse=N(name=wh),
             incoming_delivery_no=None, rf_number="RF")


def test_container_table_escapes_and_styles():
    out = container_table([_c(1, "MSCU<1>", "W")], ["container", ("supplier", RED), "orders", "unload"])
    assert "<td>NR KONTENERA</td><td>DOSTAWCA</td><td>NR ZAMÓWIENIA</td><td>DATA ROZŁADUNKU</td>" in out
    assert f"<td style='{RED}'>MSCU&lt;1&gt;</td><td style='{RED}'>Sup&amp;Co</td>" in out
    assert "<td>A<br>B</td><td>01.09.2026</td>" in out


def test_both_mails_use_shared_table():
    cs = [_c(2, "B2", "Z"), _c(1, "A1", "A")]
    avizo = _warehouse_email_html(cs, N(full_name="Op", login="op"), "")
    queue = _queue_email_html(datetime.date(2026, 9, 5), "W", cs)
    assert avizo.index("A1") < avizo.index("B2")        # sort po dacie rozładunku
    assert "<td>DATA ROZŁADUNKU</td><td>NR KONTENERA</td>" in avizo
    assert "<td>DOSTAWCA</td><td>STATEK</td><td>ETA</td>" in queue and SIGNATURE in queue
