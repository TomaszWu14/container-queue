"""TEST-008: ścieżki OCR bez binarki tesseract — granica `pytesseract` podmieniona atrapą.

Test z prawdziwym tesseractem (test_invoices_ocr_ml.py) jest na CI pomijany (brak binarki
na runnerze). Tu ta sama ścieżka — render strony (pypdfium2) → `_words` → wiersze →
klasyfikacja i ekstrakcja faktury — biegnie zawsze; atrapa zwraca to, co tesseract
przeczytałby z obrazu (format `image_to_data(..., output_type=DICT)`)."""
import base64
import io
import re

import pytesseract
import pytest
from PIL import Image

from app import llm
from app.config import settings
from app.invoices import extractor, ocr, splitter
from app.models import InvoiceDocKind

LINES = [
    "COMMERCIAL INVOICE          Invoice No.: FV/77",
    "Item No.        Description          Qty      Amount",
    "NL753-S-40      Catheter             1000     250.00",
    "MSK2            Mask                 20       200.00",
]
CHAR_W, LINE_H = 18, 40
KEYS = ("text", "conf", "block_num", "par_num", "line_num", "left", "top", "width", "height")


def _tesseract_dict(lines: list[str]) -> dict:
    """Wynik image_to_data jak z tesseracta: słowa z pozycjami + wiersze-śmieci (conf -1)."""
    data = {k: [] for k in KEYS}

    def add(text, conf, line, left, top, width, height):
        for k, v in zip(KEYS, (text, conf, 1, 1, line, left, top, width, height), strict=True):
            data[k].append(v)

    add("", "-1", 0, 0, 0, 1400, 700)            # wiersz strony/bloku bez słowa
    for n, line in enumerate(lines, 1):
        for m in re.finditer(r"\S+", line):
            add(m.group(), "96.5", n, 40 + m.start() * CHAR_W, 40 + n * LINE_H,
                len(m.group()) * CHAR_W, 24)
    add("szum", -1, 9, 5, 5, 10, 10)              # conf -1 = nie słowo
    add("plama", "abc", 9, 5, 600, 10, 10)        # nieczytelny conf → 0, słowo zostaje
    return data


@pytest.fixture()
def fake_tesseract(monkeypatch):
    """Tesseract „zainstalowany” (which) i atrapa image_to_data; zwraca listę wywołań."""
    calls = []

    def image_to_data(image, **kwargs):
        assert isinstance(image, Image.Image)
        calls.append({"size": image.size, **kwargs})
        return _tesseract_dict(LINES)

    ocr.clear_cache()
    monkeypatch.setattr(settings, "ocr_enabled", True)
    monkeypatch.setattr(settings, "ollama_url", "")          # bez warstwy vision
    monkeypatch.setattr(ocr.shutil, "which", lambda name: "/usr/bin/tesseract")
    monkeypatch.setattr(pytesseract, "image_to_data", image_to_data)
    yield calls
    ocr.clear_cache()


def _blank_scan(tmp_path) -> str:
    """PDF z samym obrazem (bez warstwy tekstowej) — 1400×700 px przy 150 dpi."""
    buf = io.BytesIO()
    Image.new("RGB", (1400, 700), "white").save(buf, format="PDF", resolution=150)
    path = tmp_path / "skan.pdf"
    path.write_bytes(buf.getvalue())
    return str(path)


def test_words_reads_tesseract_dict(fake_tesseract):
    words = ocr._words(Image.new("RGB", (10, 10)))
    texts = [w["text"] for w in words]
    assert texts[:3] == ["COMMERCIAL", "INVOICE", "Invoice"]
    assert "" not in texts and "szum" not in texts and texts[-1] == "plama"
    assert words[0] == {"block": 1, "par": 1, "line": 1, "left": 40, "top": 80,
                        "width": 10 * CHAR_W, "height": 24, "text": "COMMERCIAL"}
    call = fake_tesseract[0]
    assert call["lang"] == settings.ocr_lang and call["config"] == "--psm 6"
    assert call["timeout"] == ocr.TESSERACT_TIMEOUT_S
    assert call["output_type"] == pytesseract.Output.DICT


def test_render_page_uses_configured_dpi(tmp_path, monkeypatch):
    path = _blank_scan(tmp_path)          # strona 672×336 pt
    assert ocr.render_page(path, 0, dpi=72).size == (672, 336)
    monkeypatch.setattr(settings, "ocr_dpi", 144)
    image = ocr.render_page(path, 0)
    assert image.size == (1344, 672) and image.mode == "RGB"


def test_scanned_invoice_goes_through_ocr_without_binary(tmp_path, fake_tesseract):
    path = _blank_scan(tmp_path)
    texts = splitter.page_texts(path)
    assert "COMMERCIAL INVOICE" in texts[0].upper()
    assert splitter._marker_kind(texts[0]) == InvoiceDocKind.invoice
    doc = extractor.parse_pdf(path)
    assert doc.ocr_used and doc.invoice_number == "FV/77"
    refs = [i["ref"] for i in doc.items]
    assert "NL753-S-40" in refs and "MSK2" in refs
    assert next(i for i in doc.items if i["ref"] == "MSK2")["qty"] == "20"
    # render przy OCR_DPI, a splitter i ekstraktor dzielą cache — jedna strona = jeden OCR
    assert len(fake_tesseract) == 1
    assert fake_tesseract[0]["size"] == ocr.render_page(path, 0).size


def test_tesseract_error_leaves_page_for_manual_review(tmp_path, fake_tesseract, monkeypatch):
    def boom(image, **kwargs):
        raise RuntimeError("Tesseract process timeout")

    monkeypatch.setattr(pytesseract, "image_to_data", boom)
    assert ocr.ocr_page(_blank_scan(tmp_path), 0).text == ""


def test_vision_parses_json_and_shrinks_image(monkeypatch):
    sent = {}

    def chat(model, prompt, **kwargs):
        sent.update(model=model, **kwargs)
        return 'Wynik: {"text": "A\\nB", "rows": [["x", 1], "zly", ["y", null]]} koniec'

    monkeypatch.setattr(settings, "ocr_vision_model", "qwen2.5vl:3b")
    monkeypatch.setattr(llm, "chat", chat)
    text, rows = ocr._vision(Image.new("RGB", (3000, 2000), "white"))
    assert text == "A\nB" and rows == [["x", "1"], ["y", ""]]
    assert sent["model"] == "qwen2.5vl:3b" and sent["json_mode"] is True
    sent_image = Image.open(io.BytesIO(base64.b64decode(sent["images"][0])))
    assert max(sent_image.size) <= 1280
    assert sent["timeout"] == sent["wait"] == settings.ollama_timeout
