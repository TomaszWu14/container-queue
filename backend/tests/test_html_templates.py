"""ARCH-008: HTML maili i pism przez jeden mechanizm — Jinja2 z autoescape (app/html_templates.py).

Wcześniej f-stringi z ręcznym esc(): bezpieczeństwo zależało od pamiętania o esc() przy każdej
nowej wartości (np. nazwa magazynu w mailu kolejki dnia szła bez esc)."""
import datetime
import pathlib
from types import SimpleNamespace as N

from tests.test_complaints_w11 import _company_id, _complaint, _container

EVIL = "<img src=x onerror=alert(1)>"
APP = pathlib.Path(__file__).resolve().parents[1] / "app"


def test_queue_day_mail_escapes_warehouse_label():
    from app.routers.forwarding import _queue_email_html
    container = N(id=1, notify_date=datetime.date(2026, 9, 5), eta=None, container_no="A1<b>",
                  supplier=None, vessel=None, transport_type=None, order_numbers="",
                  order=None, warehouse=None, incoming_delivery_no=None, rf_number="")
    html = _queue_email_html(datetime.date(2026, 9, 5), EVIL, [container])
    assert EVIL not in html and "&lt;img src=x onerror=alert(1)&gt;" in html
    assert "A1<b>" not in html and "05.09.2026" in html


def test_warehouse_info_mail_escapes_note_and_operator():
    from app.routers.avizo import _warehouse_email_html
    html = _warehouse_email_html([], N(full_name=EVIL, login="op"), EVIL + "\nlinia 2")
    assert EVIL not in html and "&lt;img" in html and "<br>linia 2" in html


def test_no_fstring_html_documents():
    offenders = [f"{path.relative_to(APP)}:{no}"
                 for path in sorted(APP.rglob("*.py"))
                 for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
                 if "HTMLResponse(f" in line]
    assert not offenders, f"HTML dokumentu przez szablon Jinja2 (html_templates.render): {offenders}"


def test_markup_only_in_html_templates():
    """Bandit B704: Markup() tylko w html_templates.nl2br (stała „<br>”); zaufany HTML żyje
    w szablonach (makra mail/_parts.html), nie w Pythonie."""
    offenders = [f"{path.relative_to(APP)}:{no}"
                 for path in sorted(APP.rglob("*.py")) if path.name != "html_templates.py"
                 for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
                 if "Markup(" in line]
    assert not offenders, offenders


def test_nl2br_escapes_before_breaking_lines():
    from app.html_templates import nl2br, render
    assert str(nl2br("<b>\nx")) == "&lt;b&gt;<br>x" and str(nl2br(None)) == ""
    # *.html w app/templates = autoescape
    html = render("complaints/email.html", number=EVIL, container_no="", problems="",
                  description="", photos=0, message="")
    assert EVIL not in html and "&lt;img" in html


def test_complaint_letter_escapes_user_content(client, admin_headers):
    company = _company_id(client, admin_headers)
    cid = _container(client, admin_headers, "MSDU0806613", company)
    c = _complaint(client, admin_headers, cid, description=EVIL)
    for lang, sign in (("pl", "Z poważaniem,<br>Dział Logistyki"),
                       ("en", "Kind regards,<br>Logistics Department")):
        r = client.get(f"/api/complaints/{c['id']}/letter?lang={lang}", headers=admin_headers)
        assert r.status_code == 200 and "text/html" in r.headers["content-type"]
        assert EVIL not in r.text and "&lt;img src=x" in r.text
        assert sign in r.text and c["number"] in r.text and "MSDU0806613" in r.text
        assert "window.print()" in r.text
