"""ARCH-004: OCR/cięcie/ekstrakcja faktur poza wątkiem żądania HTTP.

Upload zapisuje pliki i dokumenty-zaślepki `uploaded` i od razu zwraca 202; pętla tła
(`invoices.ingest.process_pending`, zadanie `invoice_ingest`) robi resztę. Bez pętli tła na
instancji (RUN_BACKGROUND_JOBS=false) — wszystko w żądaniu jak dotąd (201)."""
import pytest

from app import jobs
from app.config import settings
from app.database import SessionLocal
from app.invoices import ingest, pipeline
from tests.test_invoices_api import (  # noqa: F401 — fake_pdf to fixture pytest
    _container,
    _import_master,
    _upload,
    fake_pdf,
)


@pytest.fixture()
def background(monkeypatch):
    monkeypatch.setattr(settings, "run_background_jobs", True)
    monkeypatch.setattr(settings, "invoice_ocr_in_background", True)


def test_upload_returns_202_without_ocr_in_request(client, admin_headers, fake_pdf, background,
                                                   monkeypatch):
    cid = _container(client, admin_headers)

    def no_ocr_in_request(*_args, **_kwargs):
        raise AssertionError("OCR/ekstrakcja w wątku żądania")
    monkeypatch.setattr(pipeline, "process_job", no_ocr_in_request)
    monkeypatch.setattr(ingest, "page_texts", no_ocr_in_request)
    resp = _upload(client, admin_headers, cid)
    assert resp.status_code == 202, resp.text
    batch = resp.json()
    assert [(j["doc_kind"], j["status"]) for j in batch["jobs"]] == [("invoice", "uploaded")]
    assert batch["ready"] is False
    # lista paczek pokazuje zaślepkę — front odpytuje, dopóki coś jest „uploaded”
    listed = client.get(f"/api/containers/{cid}/invoice-batches", headers=admin_headers).json()
    assert listed[0]["jobs"][0]["status"] == "uploaded"


def test_background_run_gives_same_result_as_sync(client, admin_headers, fake_pdf, background):
    _import_master(client, admin_headers)
    cid = _container(client, admin_headers)
    assert _upload(client, admin_headers, cid).status_code == 202
    with SessionLocal() as db:
        assert ingest.process_pending(db) == 1
        assert ingest.process_pending(db) == 0          # nic nie zostaje w kolejce
    batch = client.get(f"/api/containers/{cid}/invoice-batches", headers=admin_headers).json()[0]
    assert [(j["doc_kind"], j["status"]) for j in batch["jobs"]] == [
        ("invoice", "extracted"), ("packing_list", "packing_list")]
    inv = batch["jobs"][0]
    assert inv["invoice_number"] == "FV/2026/9" and inv["items_count"] == 3
    assert any(p.name.endswith("_doc1_invoice.pdf") for p in fake_pdf.iterdir())


def test_failed_background_run_marks_error_once(client, admin_headers, fake_pdf, background,
                                                monkeypatch):
    cid = _container(client, admin_headers)
    assert _upload(client, admin_headers, cid).status_code == 202

    def boom(*_args, **_kwargs):
        raise RuntimeError("tesseract padł")
    monkeypatch.setattr(ingest, "ingest_files", boom)
    with SessionLocal() as db:
        assert ingest.process_pending(db) == 0
        assert ingest.process_pending(db) == 0          # błąd nie wraca do kolejki co przebieg
    job = client.get(f"/api/containers/{cid}/invoice-batches", headers=admin_headers).json()[0]["jobs"][0]
    assert job["status"] == "error" and "w tle" in job["error"]


def test_without_background_loop_upload_stays_synchronous(client, admin_headers, fake_pdf,
                                                         monkeypatch):
    monkeypatch.setattr(settings, "invoice_ocr_in_background", True)
    monkeypatch.setattr(settings, "run_background_jobs", False)   # instancja bez pętli tła
    cid = _container(client, admin_headers)
    resp = _upload(client, admin_headers, cid)
    assert resp.status_code == 201
    assert resp.json()["jobs"][0]["status"] == "extracted"


def test_ingest_job_registered_in_background_loop():
    job = next(j for j in jobs.build_jobs() if j.name == "invoice_ingest")
    assert job.fns == (ingest.process_pending,) and job.interval_s <= 60


# --- 2026-10-06: kolejka widoczna i odporna (zgłoszenie „WGRANE · 0 pozycji” bez końca) -------

def _jobs(client, headers, cid):
    return client.get(f"/api/containers/{cid}/invoice-batches", headers=headers).json()[0]["jobs"]


def test_error_keeps_reason_and_requeue_goes_back_to_background(client, admin_headers, fake_pdf,
                                                                background, monkeypatch):
    cid = _container(client, admin_headers)
    assert _upload(client, admin_headers, cid).status_code == 202

    def boom(*_args, **_kwargs):
        raise RuntimeError("tesseract padł")
    real = ingest.ingest_files
    monkeypatch.setattr(ingest, "ingest_files", boom)
    with SessionLocal() as db:
        ingest.process_pending(db)
    monkeypatch.setattr(ingest, "ingest_files", real)   # tesseract „naprawiony”
    job = _jobs(client, admin_headers, cid)[0]
    assert job["status"] == "error" and "tesseract padł" in job["error"]   # przyczyna, nie ogólnik
    # „Pomiń dokument” nie może wyrzucić niepociętego zestawu; „Ponów” = z powrotem do kolejki
    resp = client.post(f"/api/invoice-jobs/{job['id']}/reprocess", headers=admin_headers)
    assert resp.status_code == 200 and (resp.json()["status"], resp.json()["attempts"]) == ("uploaded", 0)
    ignore = client.post(f"/api/invoice-jobs/{job['id']}/ignore", headers=admin_headers)
    assert ignore.status_code == 409 and "pocięty" in ignore.json()["detail"]
    with SessionLocal() as db:
        assert ingest.process_pending(db) == 1
    assert [j["status"] for j in _jobs(client, admin_headers, cid)] == ["extracted", "packing_list"]


def test_interrupted_processing_retries_once_then_errors(client, admin_headers, fake_pdf, background,
                                                         monkeypatch):
    from app.models import InvoiceJob
    cid = _container(client, admin_headers)
    assert _upload(client, admin_headers, cid).status_code == 202
    monkeypatch.setattr(ingest, "_ingest_queued", lambda *a, **k: None)   # „restart” w trakcie
    with SessionLocal() as db:
        ingest.process_pending(db)
        job = db.query(InvoiceJob).one()
        assert job.attempts == 1 and job.processing_started_at is not None
    assert _jobs(client, admin_headers, cid)[0]["processing_started_at"] is not None
    with SessionLocal() as db:
        ingest.process_pending(db)                   # 2. podejście
        ingest.process_pending(db)                   # 3. = błąd zamiast wiecznej kolejki
    job = _jobs(client, admin_headers, cid)[0]
    assert job["status"] == "error" and "przerwane 2×" in job["error"]


def test_one_batch_per_run_and_busy_batch_not_deletable(client, admin_headers, fake_pdf, background,
                                                        monkeypatch):
    import datetime

    from app.models import InvoiceJob
    cid = _container(client, admin_headers)
    first = _upload(client, admin_headers, cid).json()["id"]
    assert _upload(client, admin_headers, cid).status_code == 202
    seen = []
    monkeypatch.setattr(ingest, "_ingest_queued", lambda db, batch, up: seen.append(batch.id))
    with SessionLocal() as db:
        assert ingest.process_pending(db) == 1
    assert seen == [first]                           # najstarsza, tylko jedna na przebieg
    busy = client.delete(f"/api/invoice-batches/{first}", headers=admin_headers)
    assert busy.status_code == 409 and "przetwarzana" in busy.json()["detail"]
    with SessionLocal() as db:                       # „przetwarza” od godziny = przerwane → wolno usunąć
        for job in db.query(InvoiceJob).filter_by(batch_id=first):
            job.processing_started_at = datetime.datetime.utcnow() - datetime.timedelta(hours=1)
        db.commit()
    assert client.delete(f"/api/invoice-batches/{first}", headers=admin_headers).status_code == 204


def test_health_reports_stale_invoice_queue(client, admin_headers, fake_pdf, background):
    import datetime

    from app.models import InvoiceJob
    from app.routers.health import run_checks
    cid = _container(client, admin_headers)
    assert _upload(client, admin_headers, cid).status_code == 202
    assert run_checks()[1]["invoice_queue"]["ok"] is True
    with SessionLocal() as db:
        for job in db.query(InvoiceJob):
            job.created_at = datetime.datetime.utcnow() - datetime.timedelta(hours=2)
        db.commit()
    queue = run_checks()[1]["invoice_queue"]
    assert queue["ok"] is False and queue["oldest_minutes"] >= 119
