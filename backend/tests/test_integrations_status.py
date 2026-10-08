"""Panel stanu integracji (W12): zbiorczy status integracji zewnętrznych (admin-only)."""
from tests.conftest import login


def test_integrations_status_shape(client):
    hdr = login(client)
    resp = client.get("/api/admin/integrations", headers=hdr)
    assert resp.status_code == 200, resp.text
    items = resp.json()["integrations"]
    keys = {i["key"] for i in items}
    assert {"powerbi", "ais", "sms", "smtp", "teams", "mail_avizo"} <= keys
    assert "tracking" not in keys   # provider trackingu kontenerów usunięty
    for i in items:
        assert i["status"] in ("on", "off")
        assert "label" in i


def test_integrations_status_requires_admin(client):
    assert client.get("/api/admin/integrations").status_code == 401
