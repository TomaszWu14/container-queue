"""Strażnik: mail reklamacji (wysyłany do zewnętrznej firmy) escapuje treść użytkownika."""
from types import SimpleNamespace

from app.mail_html import esc
from app.routers.complaints_letters import _complaint_email_html

EVIL = "<a href='http://zly.example'>kliknij</a>"


def test_esc_empty_placeholder():
    assert esc(None) == "" and esc("", empty="—") == "—"
    assert esc("<b>", empty="—") == "&lt;b&gt;"


def test_complaint_email_escapes_user_content():
    complaint = SimpleNamespace(
        number="R/1<i>", description=EVIL, photos=[],
        container=SimpleNamespace(container_no="MSCU<script>"),
        problems=[SimpleNamespace(problem_type=SimpleNamespace(name="<u>brak</u>"))])
    out = _complaint_email_html(complaint, EVIL + "\nlinia 2")
    for raw in ("<a href", "<script>", "<i>", "<u>"):
        assert raw not in out
    assert "&lt;a href=" in out and "<br>linia 2" in out
