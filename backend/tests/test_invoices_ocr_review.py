"""OCR/ML faktur: regresje z dogłębnego code review (pozycje słów, cache OCR,
historia dostawcy, trening w tle, sprzątanie po splicie, edycja pozycji)."""
import pathlib

import pytest

from app.config import settings
from app.invoices import extractor, ml, ocr, splitter
from app.models import InvoiceDocKind
from tests.test_invoices_api import fake_pdf  # noqa: F401 — fixture pytest
from tests.test_invoices_ocr_ml import _w


# --- poprawki po dogłębnym code review ------------------------------------------------

def test_rows_grouped_by_vertical_position_not_tesseract_line_ids():
    """PSM 6 tnie wiersz tabeli na osobne bloki (opis | liczby) — grupujemy po współrzędnej."""
    words = [dict(_w("NL753", 10, 40, line=1), block=1), dict(_w("Catheter", 78, 41, line=1), block=1),
             dict(_w("1,000", 500, 39, line=1), block=2), dict(_w("250.00", 640, 40, line=1), block=2)]
    _, rows = ocr.words_to_rows(words)
    assert rows == [["NL753 Catheter", "1,000", "250.00"]]


def test_pdf_page_without_table_lines_uses_word_positions(monkeypatch, tmp_path):
    """PDF z warstwą tekstową, ale bez linii tabeli: pozycje słów zamiast extract_tables."""
    class FakePage:
        def extract_text(self):
            return "COMMERCIAL INVOICE Invoice No.: FV/5 Item No. Description Qty Amount NL753-S-40 Catheter 10 25.00"

        def extract_tables(self):
            return []

        def extract_words(self, **kwargs):
            def w(text, x0, top):
                return {"text": text, "x0": x0, "x1": x0 + 7 * len(text), "top": top, "bottom": top + 10}
            return [w("Item", 10, 100), w("No.", 42, 100), w("Description", 150, 100), w("Qty", 400, 100),
                    w("Amount", 500, 100),
                    w("NL753-S-40", 10, 120), w("Catheter", 150, 120), w("10", 400, 120), w("25.00", 500, 120)]

    class FakePdf:
        pages = [FakePage()]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    import pdfplumber
    monkeypatch.setattr(pdfplumber, "open", lambda path: FakePdf())
    doc = extractor.parse_pdf(str(tmp_path / "x.pdf"))
    assert not doc.ocr_used and [i["ref"] for i in doc.items] == ["NL753-S-40"]
    assert doc.items[0]["qty"] == "10" and doc.items[0]["amount"] == "25"


def test_ocr_alias_reuses_source_page_result(monkeypatch, tmp_path):
    ocr.clear_cache()
    monkeypatch.setattr(settings, "ocr_enabled", True)
    monkeypatch.setattr(ocr.shutil, "which", lambda name: "/usr/bin/tesseract")
    calls = []
    monkeypatch.setattr(ocr, "render_page", lambda path, index, dpi=None: calls.append(path) or object())
    monkeypatch.setattr(ocr, "_words", lambda image: [_w("COMMERCIAL", 10, 10), _w("INVOICE", 150, 10)])
    src, part = tmp_path / "src.pdf", tmp_path / "src_doc1_invoice.pdf"
    src.write_bytes(b"%PDF-1.4")
    part.write_bytes(b"%PDF-1.4")
    assert ocr.ocr_page(str(src), 0).text == "COMMERCIAL INVOICE"
    ocr.alias_page(str(src), 0, str(part), 0)
    assert ocr.ocr_page(str(part), 0).text == "COMMERCIAL INVOICE"
    assert calls == [str(src)]        # część nie była renderowana ani czytana ponownie


def test_needs_ocr_counts_words_not_chars():
    assert ocr.needs_ocr("CONFIDENTIAL DRAFT COPY")            # watermark, 3 słowa
    assert not ocr.needs_ocr("a b c d e f g h i")


def test_ambiguous_not_resolved_by_global_history_of_other_supplier(monkeypatch):
    from app.invoices import matching
    from app.models import InvoiceItem, InvoiceMatchStatus
    item = InvoiceItem(raw_ref="MSK", descr="", match_status=InvoiceMatchStatus.ambiguous)
    monkeypatch.setattr(ml, "suggest_ref", lambda *a, **k: [ml.Suggestion("MSK2", 1.0, "history_global")])
    matching.suggest(None, item, None, None, conversions=[])
    assert item.match_status == InvoiceMatchStatus.ambiguous and item.ml_suggestion == "MSK2"


def test_stale_model_label_does_not_crash_split(monkeypatch):
    monkeypatch.setattr(ml, "predict_doc_kind", lambda t: ("delivery_note", 0.99))
    text = "Seller ACME Buyer ACME Item No Qty Amount NL753 100 250.00 lots of text here"
    assert splitter.classify_first_page(text) == InvoiceDocKind.invoice


def test_background_training_coalesces(monkeypatch):
    """N zgłoszeń w trakcie treningu = jeden dodatkowy trening po jego zakończeniu."""
    import threading
    runs = []
    gate = threading.Event()

    def fake_train(db):
        runs.append(1)
        gate.wait(timeout=5)

    monkeypatch.setattr(ml, "train", fake_train)
    monkeypatch.setattr(settings, "ml_train_in_background", True)
    monkeypatch.setattr(settings, "ml_auto_train", True)
    ml.schedule_training()
    for _ in range(5):
        ml.schedule_training()
    gate.set()
    for _ in range(50):
        with ml._train_state_lock:
            if not ml._train_running:
                break
        threading.Event().wait(0.05)
    assert len(runs) == 2


def test_weight_map_ignores_packing_lists_of_other_invoices(monkeypatch, tmp_path):
    from app.invoices import pipeline
    from app.models import InvoiceBatch, InvoiceDocKind, InvoiceJob, InvoiceJobStatus
    docs = {"pl1.pdf": extractor.ParsedDoc(raw_text="PACKING LIST invoice FV/1",
                                           items=[{"ref": "A", "weight_net": "1"}]),
            "pl10.pdf": extractor.ParsedDoc(raw_text="PACKING LIST invoice FV/10",
                                            items=[{"ref": "B", "weight_net": "9"}])}
    calls = []

    def parse_pdf(path, column_map=None):
        calls.append(path)
        return docs[path.replace("\\", "/").rsplit("/", 1)[-1]]
    monkeypatch.setattr(extractor, "parse_pdf", parse_pdf)
    batch = InvoiceBatch(jobs=[InvoiceJob(stored_name=n, filename=n, doc_kind=InvoiceDocKind.packing_list,
                                          status=InvoiceJobStatus.packing_list)
                               for n in ("pl1.pdf", "pl10.pdf")])
    cache: dict = {}
    assert pipeline.weight_map_for(batch, "FV/1", tmp_path, cache) == {"A": {"weight_net": "1"}}   # nie FV/10
    assert pipeline.weight_map_for(batch, "FV/10", tmp_path, cache) == {"B": {"weight_net": "9"}}
    assert pipeline.weight_map_for(batch, "FV/7", tmp_path, cache) == {}   # kilka PL, żadna nie pasuje
    assert len(calls) == 2   # każda PL parsowana RAZ (tekst + tabele z jednego przebiegu)
    # pominięta packing lista nie daje wag (zostaje jedna PL → fallback na nią)
    batch.jobs[1].status = InvoiceJobStatus.ignored
    assert pipeline.weight_map_for(batch, "FV/10", tmp_path, cache) == {"A": {"weight_net": "1"}}


def test_ignore_document_and_partial_item_update(client, admin_headers, fake_pdf):  # noqa: F811
    from tests.test_invoices_api import _container, _import_master, _upload
    _import_master(client, admin_headers)
    cid = _container(client, admin_headers)
    batch = _upload(client, admin_headers, cid).json()
    job = batch["jobs"][0]
    items = client.get(f"/api/invoice-jobs/{job['id']}", headers=admin_headers).json()["items"]
    cath = next(i for i in items if i["raw_ref"] == "NL753-S-40")
    # częściowa aktualizacja: samo „pomiń” nie zeruje ilości/kwoty
    resp = client.put(f"/api/invoice-jobs/{job['id']}/review", headers=admin_headers,
                      json={"items": [{"id": cath["id"], "skipped": True}]})
    out = next(i for i in resp.json()["items"] if i["id"] == cath["id"])
    assert out["skipped"] is True and out["qty"] == cath["qty"] and out["amount"] == cath["amount"]
    # brak numeru faktury blokuje zatwierdzenie
    resp = client.put(f"/api/invoice-jobs/{job['id']}/review", headers=admin_headers,
                      json={"items": [], "invoice_number": "", "confirm": True, "conformity_reason": "test: brak danych SAP"})
    assert resp.status_code == 409 and "numer faktury" in resp.json()["detail"].lower()
    # pominięcie dokumentu: znika z liczników, nie blokuje paczki
    resp = client.post(f"/api/invoice-jobs/{job['id']}/ignore", headers=admin_headers)
    assert resp.status_code == 200 and resp.json()["status"] == "ignored"
    assert resp.json()["doc_kind"] == "invoice"   # typ zostaje — „Przywróć” (reprocess) cofa pomyłkę
    listing = client.get(f"/api/containers/{cid}/invoice-batches", headers=admin_headers).json()
    assert listing[0]["total"] == 0


def test_reedit_after_export_marks_excel_stale(client, admin_headers, fake_pdf):  # noqa: F811
    from tests.test_invoices_api import _container, _import_master, _upload
    _import_master(client, admin_headers)
    cid = _container(client, admin_headers)
    batch = _upload(client, admin_headers, cid).json()
    job = batch["jobs"][0]
    items = client.get(f"/api/invoice-jobs/{job['id']}", headers=admin_headers).json()["items"]
    body = {"items": [{"id": i["id"], "skipped": i["match_status"] != "matched"} for i in items], "confirm": True, "conformity_reason": "test: brak danych SAP"}
    assert client.put(f"/api/invoice-jobs/{job['id']}/review", headers=admin_headers, json=body).status_code == 200
    out = client.post(f"/api/invoice-batches/{batch['id']}/export", headers=admin_headers).json()
    assert out["ready"] is True
    # poprawka ilości po eksporcie (nadal zatwierdzone) → paczka wymaga ponownego Excela
    cath = next(i for i in items if i["match_status"] == "matched")
    client.put(f"/api/invoice-jobs/{job['id']}/review", headers=admin_headers,
               json={"items": [{"id": cath["id"], "qty": "999"}], "confirm": True, "conformity_reason": "test: brak danych SAP"})
    listing = client.get(f"/api/containers/{cid}/invoice-batches", headers=admin_headers).json()
    assert listing[0]["ready"] is True and listing[0]["excel_current"] is False
    assert listing[0]["attachment_id"] == out["attachment_id"]


def test_material_patch_is_partial(client, admin_headers):
    from tests.test_invoices_api import _import_master
    _import_master(client, admin_headers)
    mat = client.get("/api/materials?q=NL753", headers=admin_headers).json()[0]
    resp = client.patch(f"/api/materials/{mat['id']}", headers=admin_headers, json={"is_active": False})
    assert resp.status_code == 200
    out = resp.json()
    assert out["is_active"] is False and out["name_pl"] == "Cewnik" and out["tariff_cn"] == "9018" and out["sent"] is True
    assert client.get("/api/materials/count", headers=admin_headers).json()["count"] == 2   # aktywne
    assert client.patch(f"/api/materials/{mat['id']}", headers=admin_headers, json={}).status_code == 422


def test_ocr_failure_is_cached_until_forgotten(monkeypatch, tmp_path):
    """Timeout tesseracta na stronie nie może być powtarzany przez splitter i ekstraktor
    (2 × 90 s × strony); /reprocess czyści cache (forget) i próbuje naprawdę od nowa."""
    ocr.clear_cache()
    path = tmp_path / "skan.pdf"
    path.write_bytes(b"%PDF-1.4 fake")
    calls = []
    monkeypatch.setattr(ocr, "is_available", lambda: True)
    monkeypatch.setattr(ocr, "render_page", lambda p, i, dpi=None: calls.append(i) or (_ for _ in ()).throw(RuntimeError("tesseract timeout")))
    assert ocr.ocr_page(str(path), 0).text == ""
    assert ocr.ocr_page(str(path), 0).text == ""
    assert calls == [0]
    ocr.forget(str(path))
    ocr.ocr_page(str(path), 0)
    assert calls == [0, 0]


def test_split_pdf_cleans_partial_outputs_on_failure(monkeypatch, tmp_path):
    from tests.test_invoices_api import CI_TEXT, PL_TEXT
    src = tmp_path / "zestaw.pdf"
    src.write_bytes(b"%PDF")
    monkeypatch.setattr(splitter, "page_texts", lambda p: [CI_TEXT, PL_TEXT])
    written = []

    def write_range(path, page_from, page_to, out_path):
        if len(written) == 1:
            raise ValueError("uszkodzona strona")
        pathlib.Path(out_path).write_bytes(b"%PDF part")
        written.append(out_path)
    monkeypatch.setattr(splitter, "write_range", write_range)
    with pytest.raises(ValueError):
        splitter.split_pdf(str(src))
    assert [p.name for p in tmp_path.iterdir()] == ["zestaw.pdf"]
