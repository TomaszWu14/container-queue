"""Szkic maila jako plik .eml — Outlook otwiera go jako nową, edytowalną wiadomość.

Bez From: Outlook wstawia konto użytkownika, który klika „Wyślij”. `X-Unsent: 1` każe
Outlookowi traktować plik jako szkic (bez tego otwiera go jak odebraną wiadomość)."""
from email.message import EmailMessage
from email.policy import SMTP


def build_eml(to: list[str], cc: list[str], subject: str, html: str, text: str,
              attachments: list[tuple[str, bytes, str]]) -> bytes:
    """`attachments`: (nazwa pliku, treść, content-type). Nazwy/temat z polskimi
    znakami kodowane przez stdlib (RFC 2047 w nagłówkach, RFC 2231 w nazwach plików)."""
    msg = EmailMessage()
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    msg["X-Unsent"] = "1"
    msg.set_content(text, cte="quoted-printable")   # 7-bit plik: bezpieczny dla każdego klienta
    msg.add_alternative(html, subtype="html", cte="quoted-printable")
    for filename, content, content_type in attachments:
        maintype, _, subtype = (content_type or "application/octet-stream").partition("/")
        msg.add_attachment(content, maintype=maintype, subtype=subtype or "octet-stream",
                           filename=filename)
    return msg.as_bytes(policy=SMTP)
