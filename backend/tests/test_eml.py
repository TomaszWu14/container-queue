"""build_eml: szkic .eml dla Outlooka — nagłówki, X-Unsent, części, polskie znaki."""
import email
from email.policy import default

from app.eml import build_eml

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_build_eml_parses_as_unsent_draft_with_attachments():
    raw = build_eml(["agencja@x.pl"], ["zespol@firma.pl", "b@firma.pl"],
                    "Faktury — MSDU0806613 — Spółka Łódź",
                    "<p>Zażółć <b>gęślą</b></p>", "Zażółć gęślą",
                    [("faktury_ąę.xlsx", b"XLSX", XLSX),
                     ("faktura śćź 1.pdf", b"%PDF-1", "application/pdf")])
    assert b"From:" not in raw
    raw.decode("ascii")   # całość 7-bit: nagłówki zakodowane (RFC 2047/2231), treści w base64/QP
    msg = email.message_from_bytes(raw, policy=default)
    assert msg["To"] == "agencja@x.pl" and msg["Cc"] == "zespol@firma.pl, b@firma.pl"
    assert msg["X-Unsent"] == "1"
    assert msg["Subject"] == "Faktury — MSDU0806613 — Spółka Łódź"
    assert msg.get_content_type() == "multipart/mixed"
    assert "<b>gęślą</b>" in msg.get_body(preferencelist=("html",)).get_content()
    assert msg.get_body(preferencelist=("plain",)).get_content().strip() == "Zażółć gęślą"
    atts = list(msg.iter_attachments())
    assert [a.get_filename() for a in atts] == ["faktury_ąę.xlsx", "faktura śćź 1.pdf"]
    assert atts[0].get_content_type() == XLSX
    assert atts[1].get_content_type() == "application/pdf" and atts[1].get_content() == b"%PDF-1"


def test_build_eml_without_cc_has_no_cc_header():
    msg = email.message_from_bytes(build_eml(["a@x.pl"], [], "T", "<p>x</p>", "x", []), policy=default)
    assert msg["Cc"] is None and msg["X-Unsent"] == "1"
