"""SPA z builda: brakujący chunk /assets/* = 404 (nie index.html 200), cache nagłówki."""
from app.main import spa_response


def _dist(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "assets" / "app-abc123.js").write_text("x", encoding="utf-8")
    (tmp_path / "favicon.ico").write_bytes(b"i")
    return tmp_path


def test_brakujacy_chunk_to_404(tmp_path):
    resp = spa_response(_dist(tmp_path), "assets/Stary-deadbeef.js")
    assert resp.status_code == 404


def test_istniejacy_chunk_cache_na_dlugo(tmp_path):
    resp = spa_response(_dist(tmp_path), "assets/app-abc123.js")
    assert resp.status_code == 200
    assert "immutable" in resp.headers["cache-control"]


def test_trasa_spa_to_index_bez_cache(tmp_path):
    dist = _dist(tmp_path)
    for path in ("kolejka", "", "index.html"):
        resp = spa_response(dist, path)
        assert resp.status_code == 200
        assert str(resp.path).endswith("index.html")
        assert resp.headers["cache-control"] == "no-cache"


def test_zwykly_plik_z_dist(tmp_path):
    resp = spa_response(_dist(tmp_path), "favicon.ico")
    assert str(resp.path).endswith("favicon.ico")


def test_api_404_json(tmp_path):
    assert spa_response(_dist(tmp_path), "api/nie-ma").status_code == 404
