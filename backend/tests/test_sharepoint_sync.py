"""SharePoint → sync kolejki: Graph zamockowany (httpx), job domyślnie wyłączony."""
import json

import httpx
import pytest

from app import jobs, sharepoint
from app.database import SessionLocal
from app.importers import queue as queue_importer
from tests.conftest import login

CFG = {"sharepoint_tenant_id": "t", "sharepoint_client_id": "c",
       "sharepoint_client_secret": "SEKRET", "sharepoint_site": "acme.sharepoint.com:/sites/T",
       "sharepoint_queue_path": "Shared Documents/Kolejka/kolejka.xlsx",
       "sharepoint_queue_company": "BOREALIS"}


class Resp:
    def __init__(self, status=200, body=None, content=b""):
        self.status_code, self._body, self.content = status, body or {}, content
        self.text = json.dumps(self._body)

    def json(self):
        return self._body


@pytest.fixture(autouse=True)
def _db(client):
    """fixture client stawia bazę testową (schemat + seed)."""


@pytest.fixture
def graph(monkeypatch):
    """Konfiguracja + fałszywy Graph; zwraca (log wywołań, stan pliku)."""
    for k, v in CFG.items():
        monkeypatch.setattr(sharepoint.settings, k, v)
    monkeypatch.setattr(sharepoint.settings, "sharepoint_auto_sync", True)   # automat tylko jawnie (2026-09-28)
    monkeypatch.setattr(sharepoint, "_token", lambda: "AT")
    monkeypatch.setattr(sharepoint, "_site_ids", {})
    calls, file = [], {"etag": "e1", "content": b"XLSX", "error": None}

    def fake_get(url, headers=None, **kw):
        calls.append((url, dict(headers or {})))
        assert headers["Authorization"] == "Bearer AT"
        if file["error"]:
            raise file["error"]
        if url.endswith("/sites/acme.sharepoint.com:/sites/T"):
            return Resp(body={"id": "SITE1"})
        if url.endswith(":/content"):
            return Resp(content=file["content"])
        if headers.get("If-None-Match") == file["etag"]:
            return Resp(status=304)
        return Resp(body={"eTag": file["etag"], "lastModifiedDateTime": "2026-09-20T10:00:00Z"})

    monkeypatch.setattr(sharepoint.httpx, "get", fake_get)
    return calls, file


@pytest.fixture
def fake_import(monkeypatch):
    seen = []

    def fake(db, company, content, actor, **kw):
        seen.append((company.code, content, actor, kw))
        return {"dry_run": False, "containers": 3, "changed": 2, "notified": 1, "skipped_old": 0}

    monkeypatch.setattr(queue_importer, "sync_queue_bytes", fake)
    return seen


def _state():
    with SessionLocal() as db:
        return sharepoint.load_state(db)


def test_disabled_without_config(monkeypatch, fake_import):
    monkeypatch.setattr(sharepoint.settings, "sharepoint_client_secret", "")
    assert not sharepoint.is_configured()
    assert "sharepoint_queue" not in {j.name for j in jobs.build_jobs()}
    with SessionLocal() as db:
        assert sharepoint.sharepoint_queue_sync(db) is None
    assert fake_import == [] and _state() == {}


def test_fetch_file_resolves_site_and_downloads(graph):
    calls, _ = graph
    content, meta = sharepoint.fetch_file("/Shared Documents/Kolejka/kolejka.xlsx")
    assert content == b"XLSX" and meta["eTag"] == "e1"
    urls = [u for u, _ in calls]
    assert urls[1].endswith("/sites/SITE1/drive/root:/Shared%20Documents/Kolejka/kolejka.xlsx")
    assert urls[2].endswith("kolejka.xlsx:/content")


def test_job_imports_then_skips_unchanged_etag(graph, fake_import):
    assert "sharepoint_queue" in {j.name for j in jobs.build_jobs()}
    with SessionLocal() as db:
        assert sharepoint.sharepoint_queue_sync(db) == "ok"
    assert len(fake_import) == 1
    code, content, actor, kw = fake_import[0]
    assert (code, content, actor, kw["dry_run"]) == ("BOREALIS", b"XLSX", None, False)
    assert kw["file_mtime"].isoformat() == "2026-09-20T10:00:00"
    st = _state()
    assert st["etag"] == "e1" and st["result"]["changed"] == 2
    with SessionLocal() as db:                         # ten sam eTag → 304, bez importu
        assert sharepoint.sharepoint_queue_sync(db) == "unchanged"
    assert len(fake_import) == 1
    graph[1]["etag"] = "e2"                             # nowa wersja pliku → import
    with SessionLocal() as db:
        assert sharepoint.sharepoint_queue_sync(db) == "ok"
    assert len(fake_import) == 2 and _state()["etag"] == "e2"


def test_network_error_recorded_not_raised(graph, fake_import, client):
    graph[1]["error"] = httpx.ConnectTimeout("timeout")
    with SessionLocal() as db:
        assert sharepoint.sharepoint_queue_sync(db) == "error"
    st = _state()
    assert "błąd sieci" in st["error"] and "SEKRET" not in json.dumps(st)
    assert fake_import == []
    items = client.get("/api/admin/integrations", headers=login(client)).json()["integrations"]
    sp = next(i for i in items if i["key"] == "sharepoint")
    assert sp["status"] == "on" and "błąd sieci" in sp["detail"]


def test_real_import_through_queue_core(graph):
    """Bez mocka importera: bajty trafiają do sync_queue_bytes (ten sam rdzeń co upload)."""
    from tests.test_queue_sync_date_from import _xlsx
    import datetime
    graph[1]["content"] = _xlsx([["ACME", "MAERSK", datetime.datetime(2026, 9, 1), "kolej",
                                  "MSKU5000009", "", datetime.datetime(2026, 9, 1)]])
    with SessionLocal() as db:
        assert sharepoint.sharepoint_queue_sync(db) == "ok"
    assert _state()["result"]["changed"] == 1
