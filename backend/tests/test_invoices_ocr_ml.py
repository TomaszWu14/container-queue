"""OCR skanów (Tesseract) i moduł ML (sugestie REF, klasyfikator typu dokumentu)."""
import io
import shutil

import pytest
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select

from app.config import settings
from app.invoices import extractor, ml, ocr, splitter
from app.models import InvoiceDocKind, InvoiceItem
from tests.test_invoices_api import (  # noqa: F401 — fake_pdf to fixture pytest
    CI_TEXT,
    _container,
    _import_master,
    _upload,
    fake_pdf,
)

HAS_TESSERACT = bool(shutil.which("tesseract"))


# --- OCR: słowa → wiersze/komórki (bez binarki) -------------------------------------

def _w(text, left, top, width=None, line=1):
    return {"block": 1, "par": 1, "line": line, "left": left, "top": top,
            "width": width or 12 * len(text), "height": 20, "text": text}


def test_words_to_rows_splits_columns_on_wide_gaps():
    words = [_w("Item", 10, 10), _w("No.", 62, 10), _w("Description", 200, 10), _w("Qty", 500, 10),
             _w("NL753-S-40", 10, 40, line=2), _w("Catheter", 200, 40, line=2),
             _w("Nelaton", 310, 40, line=2), _w("1,000", 500, 40, line=2)]
    text, rows = ocr.words_to_rows(words)
    assert rows == [["Item No.", "Description", "Qty"], ["NL753-S-40", "Catheter Nelaton", "1,000"]]
    assert text.splitlines()[0] == "Item No. Description Qty"
    doc = extractor.parse_pages([extractor.PageData(text=text, tables=[rows], ocr=True)])
    assert doc.items[0]["ref"] == "NL753-S-40" and doc.items[0]["qty"] == "1,000" and doc.ocr_used


def test_needs_ocr_and_unavailable_returns_empty(monkeypatch):
    assert ocr.needs_ocr("") and ocr.needs_ocr("  2  ") and not ocr.needs_ocr(CI_TEXT)
    monkeypatch.setattr(settings, "ocr_enabled", False)
    assert ocr.is_available() is False
    assert ocr.ocr_page("nie-ma.pdf", 0).text == ""


VISION_TEXT = "COMMERCIAL INVOICE Invoice No.: FV/88 Item No. Description Qty Amount"
VISION_ROWS = [["Item No.", "Description", "Qty", "Amount"], ["NL753-S-40", "Catheter", "1000", "250.00"]]


def _vision_setup(monkeypatch, tesseract: bool, tess_words: list):
    ocr.clear_cache()
    monkeypatch.setattr(settings, "ocr_enabled", True)
    monkeypatch.setattr(settings, "ollama_url", "http://ollama:11434")
    monkeypatch.setattr(ocr.shutil, "which", lambda name: "/usr/bin/tesseract" if tesseract else None)
    monkeypatch.setattr(ocr, "render_page", lambda path, index, dpi=None: object())
    monkeypatch.setattr(ocr, "_words", lambda image: tess_words)
    calls = []
    monkeypatch.setattr(ocr, "_vision", lambda image: calls.append(1) or (VISION_TEXT, VISION_ROWS))
    return calls


def test_vision_layer_used_when_tesseract_reads_nothing(monkeypatch):
    calls = _vision_setup(monkeypatch, tesseract=True, tess_words=[_w("2", 10, 10)])
    page = ocr.ocr_page("skan.pdf", 0)
    assert calls == [1] and page.text == VISION_TEXT
    doc = extractor.parse_pages([extractor.PageData(text=page.text, tables=[page.rows], ocr=True)])
    assert doc.items[0]["ref"] == "NL753-S-40" and doc.invoice_number == "FV/88"


def test_vision_layer_without_tesseract_and_skipped_when_tesseract_ok(monkeypatch):
    calls = _vision_setup(monkeypatch, tesseract=False, tess_words=[])
    assert ocr.ocr_page("a.pdf", 0).text == VISION_TEXT and calls == [1]
    good = [_w(w, 10 + i * 150, 10) for i, w in enumerate(VISION_TEXT.split()[:9])]
    calls = _vision_setup(monkeypatch, tesseract=True, tess_words=good)
    assert ocr.ocr_page("b.pdf", 0).text.startswith("COMMERCIAL") and calls == []


def test_vision_failure_keeps_tesseract_result(monkeypatch):
    _vision_setup(monkeypatch, tesseract=True, tess_words=[_w("FV", 10, 10)])
    monkeypatch.setattr(ocr, "_vision", lambda image: (_ for _ in ()).throw(RuntimeError("503")))
    assert ocr.ocr_page("c.pdf", 0).text == "FV"
    monkeypatch.setattr(settings, "ollama_url", "")
    assert ocr.vision_available() is False


def test_llm_chat_sends_local_ollama_request(monkeypatch):
    from app import llm
    sent = {}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": '{"text": "ok"}'}}

    monkeypatch.setattr(settings, "ollama_url", "http://ollama:11434/")
    monkeypatch.setattr(llm.httpx, "post", lambda url, json, timeout: sent.update(url=url, body=json) or _Resp())
    assert llm.chat("qwen2.5vl:3b", "czytaj", images=["b64"], json_mode=True) == '{"text": "ok"}'
    assert sent["url"] == "http://ollama:11434/api/chat" and sent["body"]["format"] == "json"
    assert sent["body"]["messages"][-1]["images"] == ["b64"] and sent["body"]["stream"] is False


def _scan_pdf(lines: list[str]) -> bytes:
    """Obraz z tekstem zapisany jako PDF — strona bez warstwy tekstowej (skan)."""
    img = Image.new("RGB", (1400, 700), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 30)
    for i, line in enumerate(lines):
        draw.text((40, 40 + i * 60), line, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PDF", resolution=150)
    return buf.getvalue()


@pytest.mark.skipif(not HAS_TESSERACT, reason="brak binarki tesseract")
def test_real_scan_is_read_and_classified(tmp_path):
    ocr.clear_cache()
    path = tmp_path / "skan.pdf"
    path.write_bytes(_scan_pdf([
        "COMMERCIAL INVOICE          Invoice No.: FV/77",
        "Item No.        Description          Qty      Amount",
        "NL753-S-40      Catheter             1000     250.00",
        "MSK2            Mask                 20       200.00",
    ]))
    texts = splitter.page_texts(str(path))
    assert "COMMERCIAL INVOICE" in texts[0].upper()
    assert splitter._marker_kind(texts[0]) == InvoiceDocKind.invoice
    doc = extractor.parse_pdf(str(path))
    assert doc.ocr_used and doc.invoice_number == "FV/77"
    refs = [i["ref"] for i in doc.items]
    assert "NL753-S-40" in refs and "MSK2" in refs
    assert next(i for i in doc.items if i["ref"] == "MSK2")["qty"] == "20"


# --- ML: RefModel / DocKindModel na czystych danych ----------------------------------

MATERIALS = [{"ref_code": "NL753-S-40", "name_pl": "Cewnik Nelaton", "name_en": "Nelaton catheter"},
             {"ref_code": "MSK1", "name_pl": "Maska chirurgiczna", "name_en": "Surgical mask"},
             {"ref_code": "GLV-M", "name_pl": "Rękawice nitrylowe M", "name_en": "Nitrile gloves M"}]


def test_ref_model_history_beats_similarity():
    model = ml.RefModel().fit(MATERIALS, [
        {"supplier_id": 5, "raw_ref": "NL-753/S40", "descr": "", "master_ref": "NL753-S-40"},
        {"supplier_id": 5, "raw_ref": "NL-753/S40", "descr": "", "master_ref": "NL753-S-40"},
        {"supplier_id": 9, "raw_ref": "MASKA", "descr": "", "master_ref": "MSK1"}])
    best = model.suggest("NL-753/S40", "", supplier_id=5)[0]
    assert best.master_ref == "NL753-S-40" and best.score == 1.0 and best.source == "history"
    # inny dostawca: decyzje wszystkich dostawców jako historia globalna (słabsze źródło)
    glob = model.suggest("NL-753/S40", "", supplier_id=1)[0]
    assert glob.master_ref == "NL753-S-40" and glob.source == "history_global"
    # REF bez historii (OCR pomylił 0 z O): podobieństwo do master daty
    sim = model.suggest("NL753-S-4O", "", supplier_id=1)[0]
    assert sim.master_ref == "NL753-S-40" and sim.source == "similarity" and sim.score >= ml.SIMILARITY_MIN
    # opis po angielsku dopasowuje po nazwie EN, mimo obcego REF
    glove = model.suggest("X-999", "nitrile gloves size M", supplier_id=1)
    assert glove and glove[0].master_ref == "GLV-M"
    # śmieci = brak sugestii (poniżej progu podobieństwa)
    assert model.suggest("QQQQ", "zzzz", supplier_id=1) == []


def test_ref_model_without_materials_or_history():
    model = ml.RefModel().fit([], [])
    assert model.suggest("NL753", "cokolwiek") == []


def test_dockind_model_trains_only_with_enough_data():
    inv = [f"COMMERCIAL INVOICE No {i} Seller Buyer Item No Qty Unit price Amount Total" for i in range(12)]
    pl = [f"PACKING LIST No {i} Carton Net weight Gross weight CTNS Measurement" for i in range(12)]
    small = ml.DocKindModel().fit(inv[:3] + pl[:3], ["invoice"] * 3 + ["packing_list"] * 3, min_examples=20)
    assert small.pipeline is None and small.predict("x") is None
    model = ml.DocKindModel().fit(inv + pl, ["invoice"] * 12 + ["packing_list"] * 12, min_examples=20)
    label, prob = model.predict("PACK1NG L1ST No 99 Carton Net weight Gross weight CTNS")
    assert label == "packing_list" and prob > 0.6
    assert model.predict("COMMERC1AL 1NVOICE Seller Buyer Qty Unit price Amount")[0] == "invoice"


def test_classify_first_page_uses_ml_when_markers_fail(monkeypatch):
    text = "COMMERC1AL 1NVOICE Seller Buyer Item No Qty Unit price Amount Total 123456"
    assert splitter._marker_kind(text) is None
    monkeypatch.setattr(ml, "predict_doc_kind", lambda t: ("packing_list", 0.95))
    assert splitter.classify_first_page(text) == InvoiceDocKind.packing_list
    monkeypatch.setattr(ml, "predict_doc_kind", lambda t: ("packing_list", 0.4))
    assert splitter.classify_first_page(text) == InvoiceDocKind.invoice   # niepewne → faktura
    assert splitter.classify_first_page("x") == InvoiceDocKind.other
    monkeypatch.setattr(ml, "predict_doc_kind", lambda t: pytest.fail("markery mają pierwszeństwo"))
    assert splitter.classify_first_page(CI_TEXT) == InvoiceDocKind.invoice


def test_split_pdf_first_page_without_marker_becomes_invoice(monkeypatch):
    monkeypatch.setattr(splitter, "page_texts", lambda p: [
        "Seller: ACME Buyer: ACME Item No Qty Amount NL753 100 250.00 lots of text here"])
    monkeypatch.setattr(ml, "predict_doc_kind", lambda t: None)
    parts = splitter.split_pdf("x/bez-naglowka.pdf")
    assert parts[0]["kind"] == InvoiceDocKind.invoice


# --- ML w pipeline (API) --------------------------------------------------------------

@pytest.fixture()
def ml_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ml_model_dir", str(tmp_path / "ml"))
    ml.invalidate()
    yield tmp_path / "ml"
    ml.invalidate()


def test_ml_suggests_and_learns_from_confirmation(client, admin_headers, fake_pdf, ml_dir, db_session):  # noqa: F811
    _import_master(client, admin_headers)   # auto-trening po imporcie: indeks podobieństwa
    stats = client.get("/api/materials/ml/stats", headers=admin_headers).json()
    assert stats["ref_materials"] == 3 and stats["ref_examples"] == 0
    assert (ml_dir / "ref_model.joblib").exists()

    cid = _container(client, admin_headers)
    batch = _upload(client, admin_headers, cid).json()
    job = batch["jobs"][0]
    items = client.get(f"/api/invoice-jobs/{job['id']}", headers=admin_headers).json()["items"]
    by_ref = {i["raw_ref"]: i for i in items}
    assert by_ref["NL753-S-40"]["match_source"] == "rules"
    msk = by_ref["MSK"]
    # niejednoznaczne: podobieństwo podpowiada jednego z kandydatów, ale nie decyduje samo
    assert msk["match_status"] == "ambiguous" and msk["ml_suggestion"] in ("MSK1", "MSK2")
    assert msk["ml_confidence"] is not None and msk["ml_confidence"] < settings.ml_auto_apply_threshold

    # operator wybiera MSK2 i zatwierdza → model dotrenowany (historia dostawcy)
    body = {"items": [{"id": msk["id"], "master_ref": "MSK2", "qty": "20", "amount": "200"},
                      {"id": by_ref["NOPE-1"]["id"], "skipped": True}], "confirm": True, "conformity_reason": "test: brak danych SAP"}
    resp = client.put(f"/api/invoice-jobs/{job['id']}/review", headers=admin_headers, json=body)
    assert resp.status_code == 200, resp.text
    confirmed = {i["raw_ref"]: i for i in resp.json()["items"]}
    assert confirmed["MSK"]["match_source"] == "user"
    stats = client.get("/api/materials/ml/stats", headers=admin_headers).json()
    assert stats["ref_examples"] == 2   # NL753 (reguły) + MSK→MSK2 (operator)

    # kolejna faktura tego samego dostawcy: „MSK” dopasowane automatycznie z historii
    batch2 = _upload(client, admin_headers, cid).json()
    items2 = client.get(f"/api/invoice-jobs/{batch2['jobs'][0]['id']}", headers=admin_headers).json()["items"]
    msk2 = next(i for i in items2 if i["raw_ref"] == "MSK")
    assert msk2["match_status"] == "matched" and msk2["master_ref"] == "MSK2"
    assert msk2["match_source"] == "ml" and msk2["ml_confidence"] == 1.0
    assert msk2["name_pl"] == "Maska B"
    # baza ma zapisany tekst dokumentu (dane treningowe klasyfikatora)
    stored = db_session.scalar(select(InvoiceItem).where(InvoiceItem.id == msk2["id"]))
    assert stored.job.text_excerpt.startswith("COMMERCIAL INVOICE")


def test_ml_train_endpoint_admin_only(client, admin_headers, ml_dir):
    company = client.get("/api/companies", headers=admin_headers).json()[0]["id"]
    client.post("/api/users", headers=admin_headers, json={
        "login": "log", "password": "haslo123", "role": "logistics", "company_id": company})
    from tests.conftest import login
    log = login(client, "log", "haslo123")
    assert client.post("/api/materials/ml/train", headers=log).status_code == 403
    assert client.get("/api/materials/ml/stats", headers=log).status_code == 200
    resp = client.post("/api/materials/ml/train", headers=admin_headers)
    assert resp.status_code == 200 and resp.json()["dockind_trained"] is False


def test_explicit_other_marker_beats_ml(monkeypatch):
    bl = "DEMO MEDICAL BILL OF LADING DMBL4815162 SHANGHAI GDANSK POLAND shipper consignee notify"
    monkeypatch.setattr(ml, "predict_doc_kind", lambda t: ("invoice", 0.99))
    assert splitter.classify_first_page(bl) == InvoiceDocKind.other


def test_split_parts_carry_text_for_training(monkeypatch):
    from tests.test_invoices_api import PL_TEXT
    monkeypatch.setattr(splitter, "page_texts", lambda p: [CI_TEXT, "kontynuacja faktury: pozycje 4-9, razem 123456789 USD", PL_TEXT])
    monkeypatch.setattr(splitter, "write_range", lambda *a: None)
    parts = splitter.split_pdf("x/zestaw.pdf")
    assert parts[0]["text"].startswith("COMMERCIAL INVOICE") and "kontynuacja" in parts[0]["text"]
    assert parts[1]["text"] == PL_TEXT


def test_ambiguous_is_not_auto_resolved_by_similarity(monkeypatch):
    from app.invoices import matching
    from app.models import InvoiceItem, InvoiceMatchStatus
    item = InvoiceItem(raw_ref="MSK", descr="Maska A", match_status=InvoiceMatchStatus.ambiguous)
    monkeypatch.setattr(ml, "suggest_ref", lambda *a, **k: [ml.Suggestion("MSK1", 0.97, "similarity")])
    matching.suggest(None, item, None, None, conversions=[])
    assert item.match_status == InvoiceMatchStatus.ambiguous
    assert item.ml_suggestion == "MSK1" and float(item.ml_confidence) == 0.97


def test_weight_map_cache_parses_each_packing_list_once(monkeypatch, tmp_path):
    from app.invoices import pipeline
    from app.models import InvoiceBatch, InvoiceDocKind, InvoiceJob
    calls = []
    monkeypatch.setattr(extractor, "parse_pdf", lambda p, column_map=None: calls.append(p) or extractor.ParsedDoc(
        raw_text="PACKING LIST invoice FV/1", items=[{"ref": "X", "weight_net": "1"}]))
    batch = InvoiceBatch(jobs=[InvoiceJob(stored_name="pl.pdf", filename="pl.pdf",
                                          doc_kind=InvoiceDocKind.packing_list)])
    cache: dict = {}
    for invoice_no in ("FV/1", "FV/2", "FV/1"):
        assert pipeline.weight_map_for(batch, invoice_no, tmp_path, cache) == {"X": {"weight_net": "1"}}
    assert len(calls) == 1


def test_vision_budget_classification_without_vision_then_once_for_extraction(monkeypatch):
    """Audyt 2026-10-06 #3: klasyfikacja stron zestawu (splitter) bez modelu obrazowego —
    certyfikaty nie kosztują minut na stronę; ekstrakcja tej samej strony dokłada vision
    raz (cache), a nie liczy Tesseracta ponownie."""
    tess_calls = []
    calls = _vision_setup(monkeypatch, tesseract=True, tess_words=[_w("2", 10, 10)])
    monkeypatch.setattr(ocr, "_words", lambda image: tess_calls.append(1) or [_w("2", 10, 10)])
    first = ocr.ocr_page("zestaw.pdf", 6, vision=False)            # splitter
    assert calls == [] and tess_calls == [1] and not first.vision_tried
    assert ocr.ocr_page("zestaw.pdf", 6, vision=False) is first   # cache, bez ponownego OCR
    second = ocr.ocr_page("zestaw.pdf", 6)                         # ekstrakcja faktury
    assert calls == [1] and tess_calls == [1] and second.text == VISION_TEXT
    assert ocr.ocr_page("zestaw.pdf", 6) is not None and calls == [1]   # vision tylko raz


def test_splitter_classifies_scans_without_vision(monkeypatch, tmp_path):
    from app.invoices import splitter
    seen = []
    monkeypatch.setattr(ocr, "needs_ocr", lambda text: True)
    monkeypatch.setattr(ocr, "ocr_page", lambda path, index, vision=True: seen.append(vision) or ocr.OcrPage())
    pdf = tmp_path / "s.pdf"
    from tests.test_invoices_checks import _pdf
    pdf.write_bytes(_pdf(3))
    splitter.page_texts(str(pdf))
    assert seen == [False, False, False]
