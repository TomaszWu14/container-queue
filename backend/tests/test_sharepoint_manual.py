"""Okres dwutorowy Excel ↔ aplikacja (decyzja 2026-09-28): synchronizacja z SharePoint domyślnie
tylko ręczna; automat wyłącznie z SHAREPOINT_AUTO_SYNC=true."""
from app import jobs, sharepoint
from app.config import settings


def test_no_auto_sync_job_by_default(monkeypatch):
    monkeypatch.setattr(sharepoint, "is_configured", lambda: True)
    assert "sharepoint_queue" not in {j.name for j in jobs.build_jobs()}
    monkeypatch.setattr(settings, "sharepoint_auto_sync", True)
    assert "sharepoint_queue" in {j.name for j in jobs.build_jobs()}


def test_manual_sync_endpoint(client, admin_headers, monkeypatch):
    assert client.post("/api/import/sharepoint-sync", headers=admin_headers).status_code == 409
    monkeypatch.setattr(sharepoint, "is_configured", lambda: True)
    monkeypatch.setattr(sharepoint, "sharepoint_queue_sync", lambda db: "ok")
    r = client.post("/api/import/sharepoint-sync", headers=admin_headers)
    assert r.status_code == 200 and r.json()["status"] == "ok"
