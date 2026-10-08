"""Teams (Adaptive Card + wynik wysyłki) i wiersz „Poczta awizacji” w panelu Integracje."""
import httpx
import pytest

from app import mailer, teams
from tests.conftest import login


def _resp(status: int, text: str = "") -> httpx.Response:
    return httpx.Response(status, text=text, request=httpx.Request("POST", "https://x"))


def test_card_is_adaptive_in_message_envelope():
    att = teams.card("Tytuł", "Treść")["attachments"][0]
    assert att["contentType"] == "application/vnd.microsoft.card.adaptive"
    assert [b["text"] for b in att["content"]["body"]] == ["[TIMPORYE] Tytuł", "Treść"]


def test_post_records_ok_and_http_error(monkeypatch):
    url = "https://prod.westeurope.logic.azure.com/workflows/abc"
    monkeypatch.setattr(teams.httpx, "post", lambda *a, **kw: _resp(202))
    teams.post(url, "t", "b")
    assert teams.status_detail(url)[0] == "Workflows webhook · ok"

    monkeypatch.setattr(teams.httpx, "post", lambda *a, **kw: _resp(400, "bad card"))
    with pytest.raises(httpx.HTTPStatusError):
        teams.post(url, "t", "b")
    detail, at = teams.status_detail(url)
    assert "błąd" in detail and "400" in detail and at is not None


def test_legacy_webhook_non_one_body_is_error(monkeypatch):
    url = "https://acme.webhook.office.com/webhookb2/x"
    monkeypatch.setattr(teams.httpx, "post", lambda *a, **kw: _resp(200, "Bad payload"))
    with pytest.raises(RuntimeError):
        teams.post(url, "t", "b")
    assert "przejdź na Workflows" in teams.status_detail(url)[0]


def test_integrations_mail_avizo_graph_row(client, monkeypatch):
    s = mailer.settings
    monkeypatch.setattr(s, "mail_backend", "graph")
    monkeypatch.setattr(s, "ms_tenant_id", "")
    hdr = login(client)
    rows = {i["key"]: i for i in client.get("/api/admin/integrations", headers=hdr)
            .json()["integrations"]}
    assert rows["mail_avizo"]["status"] == "off" and "brak MS_" in rows["mail_avizo"]["detail"]

    for k in ("ms_tenant_id", "ms_client_id", "ms_client_secret"):
        monkeypatch.setattr(s, k, "x")
    monkeypatch.setattr(s, "mail_sender", "awizacje@example.com")
    rows = {i["key"]: i for i in client.get("/api/admin/integrations", headers=hdr)
            .json()["integrations"]}
    assert rows["mail_avizo"]["status"] == "on"
    assert rows["mail_avizo"]["detail"].startswith("graph · awizacje@example.com")
