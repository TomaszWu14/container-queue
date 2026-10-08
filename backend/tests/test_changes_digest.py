"""Dziennik zmian „od wczoraj" — kubełki z audytu w zakresie usera."""
from tests.conftest import login


def test_digest_buckets_created_and_status(client):
    headers = login(client)
    companies = client.get("/api/companies", headers=headers).json()
    company_id = next(c["id"] for c in companies if c["code"] == "ACME")
    created = client.post("/api/containers", headers=headers, json={
        "container_no": "TGBU6784203", "company_id": company_id}).json()
    # zmiana statusu → wpis w audycie
    resp = client.post(f"/api/containers/{created['id']}/status",
                       headers=headers, json={"status": "W_TRANSPORCIE"})
    assert resp.status_code == 200, resp.text

    digest = client.get("/api/changes/digest", headers=headers).json()
    created_nos = [e["container_no"] for e in digest["created"]]
    status_nos = [e["container_no"] for e in digest["status"]]
    assert "TGBU6784203" in created_nos
    assert "TGBU6784203" in status_nos
    assert digest["since_hours"] == 24
