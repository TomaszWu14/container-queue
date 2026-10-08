"""Kolory motywów z Administracji: zapis tylko admin, odczyt każdy zalogowany, walidacja #rrggbb
i nazw tokenów (wartości trafiają do style.setProperty), audyt zmian, uszkodzony wpis = domyślne."""
from sqlalchemy import select

from app.models import AppSetting, AuditLog

URL_ADMIN, URL = "/api/admin/theme-colors", "/api/theme-colors"


def test_defaults_then_save_and_read_back(client, admin_headers, db_session):
    assert client.get(URL, headers=admin_headers).json() == {"light": {}, "dark": {}}
    body = {"light": {"--kq-row-dlt": "#F7D9E3"}, "dark": {"--bg": "#0e1f3f", "--kq-row-dlt": "#4d3a12"}}
    r = client.put(URL_ADMIN, headers=admin_headers, json=body)
    assert r.status_code == 200, r.text
    assert r.json()["light"] == {"--kq-row-dlt": "#f7d9e3"}                 # hex małymi literami
    assert client.get(URL, headers=admin_headers).json()["dark"] == {"--bg": "#0e1f3f", "--kq-row-dlt": "#4d3a12"}
    logs = db_session.scalars(select(AuditLog).where(AuditLog.field.like("theme_colors_%"))).all()
    assert {log.field for log in logs} == {"theme_colors_light", "theme_colors_dark"}
    assert "--bg" in next(log.note for log in logs if log.field == "theme_colors_dark")
    # ponowny zapis bez zmian nie zaśmieca historii
    client.put(URL_ADMIN, headers=admin_headers, json=body)
    assert len(db_session.scalars(select(AuditLog).where(AuditLog.field.like("theme_colors_%"))).all()) == 2


def test_rejects_css_injection_and_bad_values(client, admin_headers):
    for bad in ({"light": {"--bg": "red"}}, {"light": {"--bg": "#fff"}},
                {"light": {"--bg": "#000000; background:url(x)"}}, {"light": {"color": "#000000"}},
                {"dark": {"--bg;x": "#000000"}}, {"dark": {f"--t{i}": "#000000" for i in range(61)}}):
        assert client.put(URL_ADMIN, headers=admin_headers, json=bad).status_code == 422, bad


def test_corrupted_setting_falls_back_to_defaults(client, admin_headers, db_session):
    db_session.add(AppSetting(key="theme_colors", value="{nie json"))
    db_session.commit()
    assert client.get(URL, headers=admin_headers).json() == {"light": {}, "dark": {}}
