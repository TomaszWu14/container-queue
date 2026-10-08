import datetime

from app.analytics.ingest import parse_issues

CSV = b"data;produkt;ilosc;magazyn\n2026-01-02;A;10;MAG1\n2026-01-03;A;5;MAG1\n"

def test_parse_ok():
    rep = parse_issues(CSV, "f1.csv")
    assert rep.errors == []
    assert len(rep.rows) == 2
    assert rep.rows[0] == {"produkt": "A", "date": datetime.date(2026, 1, 2),
                           "qty": 10.0, "firma": "", "magazyn": "MAG1", "kontrahent": ""}

def test_parse_bad_header():
    rep = parse_issues(b"foo;bar\n1;2\n", "x.csv")
    assert any("brak kolumny" in e.lower() for e in rep.errors)
    assert rep.rows == []

def test_parse_corrupt_xlsx_does_not_raise():
    rep = parse_issues(b"\x00\x01 not a real xlsx", "bad.xlsx")
    assert rep.rows == []
    assert rep.errors
