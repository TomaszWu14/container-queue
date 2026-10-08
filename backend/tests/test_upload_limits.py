"""SEC-009: każdy upload ma limit rozmiaru, a xlsx-zip-bomba jest odrzucana przed openpyxl."""
import io
import pathlib
import re
import zipfile

import pytest

from app.config import settings

ROUTERS = pathlib.Path(__file__).resolve().parents[1] / "app" / "routers"


@pytest.mark.parametrize("url, name", [
    ("/api/analytics/upload", "h.csv"),
    ("/api/paz/import", "p.csv"),
    ("/api/containers/import-po", "po.xlsx"),
])
def test_oversize_upload_413(client, admin_headers, monkeypatch, url, name):
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    big = b"a;b\n" * (300 * 1024)   # ~1.2 MB > 1 MB
    r = client.post(url, headers=admin_headers, files={"file": (name, io.BytesIO(big))})
    assert r.status_code == 413, r.text


def test_no_uncapped_reads_in_routers():
    offenders = [p.name for p in ROUTERS.glob("*.py")
                 if re.search(r"\.file\.read\(\)", p.read_text(encoding="utf-8"))]
    assert offenders == []


def _zip_bomb() -> bytes:
    """Mały plik (~200 KB) rozpakowujący się do ~200 MB — szybko budowany strumieniowo."""
    buf = io.BytesIO()
    chunk = b"\0" * (1024 * 1024)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        with z.open("xl/worksheets/sheet1.xml", "w", force_zip64=True) as f:
            for _ in range(200):
                f.write(chunk)
    return buf.getvalue()


@pytest.mark.parametrize("url", [
    "/api/paz/import",
    "/api/import/sp-materials?dry_run=true",   # dawniej własny openpyxl.load_workbook bez limitu
])
def test_xlsx_zip_bomb_rejected(client, admin_headers, monkeypatch, url):
    import openpyxl
    called = []
    monkeypatch.setattr(openpyxl, "load_workbook", lambda *a, **k: called.append(1))
    bomb = _zip_bomb()
    assert len(bomb) < 2 * 1024 * 1024
    r = client.post(url, headers=admin_headers, files={"file": ("p.xlsx", io.BytesIO(bomb))})
    assert r.status_code in (413, 422), r.text
    assert called == []
