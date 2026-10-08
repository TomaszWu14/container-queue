import pytest

from app import powerbi


def test_normalize_header():
    assert powerbi.normalize_header("'Stan'[Krótki opis produktu]") == "krotki_opis_produktu"
    assert powerbi.normalize_header("Ilość") == "ilosc"


def test_parse_empty_is_safe():
    assert powerbi.parse_execute_queries({}) == ([], [])
    assert powerbi.parse_execute_queries({"results": [{"tables": []}]}) == ([], [])


def test_parse_rows():
    payload = {"results": [{"tables": [{"rows": [
        {"Stan[Produkt]": "DEMO-SKU-020", "Stan[Ilość]": 112},
    ]}]}]}
    header, rows = powerbi.parse_execute_queries(payload)
    assert header == ["produkt", "ilosc"]
    assert rows == [{"produkt": "DEMO-SKU-020", "ilosc": 112}]


def test_mock_provider(monkeypatch):
    monkeypatch.setattr(powerbi.settings, "powerbi_provider", "mock")
    header, rows = powerbi.fetch_table("ds", "Stan")
    assert "produkt" in header and len(rows) > 0


def test_off_provider_raises(monkeypatch):
    monkeypatch.setattr(powerbi.settings, "powerbi_provider", "off")
    with pytest.raises(powerbi.PowerBINotConfigured):
        powerbi.fetch_table("ds", "Stan")
