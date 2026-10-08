"""Wspólny moduł importów tabelarycznych (app/tabular.py) + ścieżki, które na niego przepięto."""
import datetime
import io

import openpyxl
import pytest
from fastapi import HTTPException

from app.tabular import normalize_header, read_rows, text_rows, to_float


@pytest.mark.parametrize("raw, expected", [
    (None, None), ("", None), ("abc", None), (datetime.datetime(2026, 1, 2), None),
    (5, 5.0), (1.5, 1.5), ("12", 12.0), ("1,5", 1.5), ("1,500", 1.5),
    ("1 234,5", 1234.5), ("1 234,5", 1234.5), ("1.234,5", 1234.5), ("1,234.5", 1234.5),
])
def test_to_float(raw, expected):
    assert to_float(raw) == expected


def test_normalize_header():
    assert normalize_header("  Ilość \n palet ") == "ilość palet"
    assert normalize_header("Ilość", accents=False) == "ilosc"
    assert normalize_header(None) == ""


def test_text_rows_detects_delimiter_and_skips_blank_lines():
    assert text_rows(b"a;b\n\n1;2,5\n") == [["a", "b"], ["1", "2,5"]]
    assert text_rows(b"a\tb;c\n1\t2\n") == [["a", "b;c"], ["1", "2"]]
    assert text_rows(b"a,b\n1,2\n") == [["a", "b"], ["1", "2"]]
    assert text_rows("a;b\nż;1\n".encode("cp1250"))[1][0] == "ż"


def test_read_rows_xlsx_and_broken_file():
    wb = openpyxl.Workbook()
    wb.active.append(["produkt", 3])
    buf = io.BytesIO()
    wb.save(buf)
    assert read_rows(buf.getvalue(), "X.XLSX") == [["produkt", 3]]
    with pytest.raises(HTTPException) as exc:
        read_rows(b"\x00 not xlsx", "bad.xlsx")
    assert exc.value.status_code == 422


def test_paz_import_broken_xlsx_is_422_not_500(client, admin_headers):
    r = client.post("/api/paz/import", headers=admin_headers,
                    files={"file": ("paz.xlsx", b"\x00 not xlsx", "application/octet-stream")})
    assert r.status_code == 422


def test_paz_import_csv_semicolon_and_polish_number(client, admin_headers):
    csv_bytes = b"produkt;sztuk_na_palete\nABC-2;1 250,5\n"
    r = client.post("/api/paz/import", headers=admin_headers,
                    files={"file": ("paz.csv", csv_bytes, "text/csv")})
    assert r.status_code == 200 and r.json()["imported"] == 1, r.text
    rows = client.get("/api/paz", headers=admin_headers).json()
    assert any(p["produkt"] == "ABC-2" and p["sztuk_na_palete"] == 1250.5 for p in rows)
