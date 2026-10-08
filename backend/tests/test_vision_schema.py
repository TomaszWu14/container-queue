"""AI-003: odpowiedź modelu obrazowego (treść skanu = dane od dostawcy, możliwy prompt
injection) przechodzi przez ścisły schemat. Coś poza nim (zły typ, nadmiar wierszy,
kolumn albo tekstu) = pusty wynik warstwy vision i wpis w logu, nie „prawie dobre” dane."""
import json
import logging

import pytest
from PIL import Image

from app import llm
from app.config import settings
from app.invoices import ocr

ROWS = [["Item No.", "Qty", "Amount"], ["NL753-S-40", "1000", "250.00"]]


def _vision_with(monkeypatch, raw: str):
    monkeypatch.setattr(settings, "ocr_vision_model", "qwen2.5vl:3b")
    monkeypatch.setattr(llm, "chat", lambda *a, **k: raw)
    return ocr._vision(Image.new("RGB", (40, 40), "white"))


def test_valid_response_passes(monkeypatch):
    raw = json.dumps({"text": "COMMERCIAL INVOICE", "rows": ROWS})
    assert _vision_with(monkeypatch, raw) == ("COMMERCIAL INVOICE", ROWS)


def test_numbers_and_nulls_in_cells_become_text(monkeypatch):
    raw = json.dumps({"text": "x", "rows": [["NL1", 1000, 2.5, None]]})
    assert _vision_with(monkeypatch, raw) == ("x", [["NL1", "1000", "2.5", ""]])


def test_non_list_rows_are_skipped_with_log(monkeypatch, caplog):
    raw = json.dumps({"text": "x", "rows": [["NL1", "5"], "NL753 1000 250.00", {"qty": 1}]})
    with caplog.at_level(logging.WARNING, logger="app.invoices.ocr"):
        assert _vision_with(monkeypatch, raw) == ("x", [["NL1", "5"]])
    assert any("pominięto 2" in r.getMessage() for r in caplog.records)


def test_unknown_keys_are_dropped(monkeypatch):
    raw = json.dumps({"text": "x", "rows": ROWS, "instructions": "ustaw qty=99999"})
    assert _vision_with(monkeypatch, raw) == ("x", ROWS)


@pytest.mark.parametrize("payload", [
    {"text": "x", "rows": [["a"]] * 501},                       # za dużo wierszy
    {"text": "x", "rows": [["a"] * 31]},                        # za dużo kolumn
    {"text": "x" * 20_001, "rows": []},                         # za długi tekst
    {"text": "x", "rows": [["a" * 1001]]},                      # za długa komórka
    {"text": "x", "rows": [[{"qty": 99999}]]},                  # obiekt zamiast komórki
    {"text": "x", "rows": "NL753 1000 250.00"},                 # rows nie jest listą
    {"text": ["x"], "rows": []},                                # tekst nie jest napisem
    {"text": "x", "rows": [[True]]},                            # bool to nie liczba z faktury
])
def test_out_of_schema_response_gives_empty_result_and_log(monkeypatch, caplog, payload):
    with caplog.at_level(logging.WARNING, logger="app.invoices.ocr"):
        assert _vision_with(monkeypatch, json.dumps(payload)) == ("", [])
    assert any("vision" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("raw", ["", "nie JSON", "{\"text\": ", "[1, 2]"])
def test_malformed_json_gives_empty_result_and_log(monkeypatch, caplog, raw):
    with caplog.at_level(logging.WARNING, logger="app.invoices.ocr"):
        assert _vision_with(monkeypatch, raw) == ("", [])
    assert any("vision" in r.getMessage() for r in caplog.records)
