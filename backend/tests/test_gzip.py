"""Audyt PERF-001: duże odpowiedzi JSON idą skompresowane (kolejka ~1 MB bez gzip)."""


def test_large_json_is_gzipped(client, admin_headers):
    r = client.get("/openapi.json", headers={**admin_headers, "Accept-Encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers.get("content-encoding") == "gzip"


def test_small_response_not_compressed(client):
    r = client.get("/api/health", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") is None
