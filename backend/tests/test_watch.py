"""Gwiazdka „moje kontenery": toggle + lista per user."""
from tests.conftest import login


def test_watch_toggle_and_list(client):
    headers = login(client)
    companies = client.get("/api/companies", headers=headers).json()
    company_id = next(c["id"] for c in companies if c["code"] == "ACME")
    c = client.post("/api/containers", headers=headers, json={
        "container_no": "TGBU6784203", "company_id": company_id}).json()

    assert client.get("/api/watch", headers=headers).json() == []
    assert client.post(f"/api/containers/{c['id']}/watch", headers=headers).json() == {"watching": True}
    assert client.get("/api/watch", headers=headers).json() == [c["id"]]
    # toggle w drugą stronę
    assert client.post(f"/api/containers/{c['id']}/watch", headers=headers).json() == {"watching": False}
    assert client.get("/api/watch", headers=headers).json() == []


def test_watch_saves_reason_and_date(client, db_session):
    from sqlalchemy import select
    from app.models import WatchedContainer
    headers = login(client)
    companies = client.get("/api/companies", headers=headers).json()
    company_id = next(c["id"] for c in companies if c["code"] == "ACME")
    c = client.post("/api/containers", headers=headers, json={
        "container_no": "MSDU0806613", "company_id": company_id}).json()

    r = client.post(f"/api/containers/{c['id']}/watch", headers=headers,
                    json={"reason": "  Pilne dla klienta  "})
    assert r.json() == {"watching": True}
    row = db_session.scalar(select(WatchedContainer).where(
        WatchedContainer.container_id == c["id"]))
    assert row.reason == "Pilne dla klienta"
    assert row.created_at is not None


def test_watch_reason_too_long_rejected(client):
    headers = login(client)
    companies = client.get("/api/companies", headers=headers).json()
    company_id = next(c["id"] for c in companies if c["code"] == "ACME")
    c = client.post("/api/containers", headers=headers, json={
        "container_no": "MSDU0806589", "company_id": company_id}).json()
    r = client.post(f"/api/containers/{c['id']}/watch", headers=headers,
                    json={"reason": "x" * 201})
    assert r.status_code == 422
