"""Bramka zgodności dokumentu z dostawą (spec 2026-10-01-bramka-dokument-dostawa, PR 2a):
treść faktury (nr kontenera, PO, dostawca, materiały) ↔ kontener paczki. Sprzeczna nie da się
zatwierdzić ani wyeksportować; niepewna wymaga powodu; zgodna przechodzi bez pytań."""
import io

from app.invoices import extractor, splitter
from app.models import InvoiceJob, InvoiceJobStatus, OrderItem, SapOrder
from tests.test_invoices_checks import CI, CI_TABLE, PL, PL_TABLE, _pdf, _setup

OWN, OTHER = "MSDU0806613", "CSQU3054383"


def _container(client, headers, company, sup, no=OWN):
    return client.post("/api/containers", headers=headers, json={
        "container_no": no, "company_id": company.id, "supplier_id": sup.id}).json()["id"]


def _upload(client, headers, monkeypatch, cid, ci_text):
    monkeypatch.setattr(splitter, "page_texts", lambda p: [ci_text, PL])
    monkeypatch.setattr(extractor, "read_pages", lambda p: [(PL, [PL_TABLE])]
                        if "_packing_list" in p else [(ci_text, [CI_TABLE])])
    batch = client.post(f"/api/containers/{cid}/invoice-batches", headers=headers,
                        files=[("pdf", ("cipl.pdf", io.BytesIO(_pdf(2)), "application/pdf"))]).json()
    return batch["id"], next(j for j in batch["jobs"] if j["doc_kind"] == "invoice")["id"]


def _confirm(client, headers, job_id, reason=None):
    body = {"items": [], "confirm": True}
    if reason:
        body["conformity_reason"] = reason
    return client.put(f"/api/invoice-jobs/{job_id}/review", headers=headers, json=body)


def _conformity(client, headers, job_id):
    return client.get(f"/api/invoice-jobs/{job_id}/conformity", headers=headers).json()


def _signal(result, key):
    return next(s for s in result["signals"] if s["key"] == key)["ok"]


def _seed_order(db, company, container_id, material="A1"):
    db.add_all([SapOrder(company_id=company.id, order_number="4500000001",
                         container_id=container_id, supplier_sap="10004408"),
                OrderItem(company_id=company.id, order_number="4500000001", position="10",
                          material=material, quantity="15500", unit="SZT")])
    db.commit()


def test_other_container_number_blocks_and_points_target(
        client, admin_headers, db_session, monkeypatch, tmp_path):
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    cid = _container(client, admin_headers, company, sup)
    _container(client, admin_headers, company, sup, OTHER)
    _, job_id = _upload(client, admin_headers, monkeypatch, cid, f"{CI}\nCONTAINER No.: {OTHER}")
    result = _conformity(client, admin_headers, job_id)
    assert result["status"] == "conflict" and _signal(result, "container") is False
    assert [c["container_no"] for c in result["move_to"]] == [OTHER]
    resp = _confirm(client, admin_headers, job_id, reason="na pewno")   # powód nie obchodzi sprzeczności
    assert resp.status_code == 409 and OTHER in resp.json()["detail"]


def test_uncertain_needs_reason_once(client, admin_headers, db_session, monkeypatch, tmp_path):
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    cid = _container(client, admin_headers, company, sup)
    _, job_id = _upload(client, admin_headers, monkeypatch, cid, CI)   # bez nr kontenera i PO
    assert _conformity(client, admin_headers, job_id)["status"] == "uncertain"
    resp = _confirm(client, admin_headers, job_id)
    assert resp.status_code == 409 and "powód" in resp.json()["detail"]
    assert _confirm(client, admin_headers, job_id, reason="faktura bez numerów").status_code == 200
    ack = _conformity(client, admin_headers, job_id)["ack"]
    assert ack["reason"] == "faktura bez numerów" and ack["by"]
    client.put(f"/api/invoice-jobs/{job_id}/review", headers=admin_headers,
               json={"items": [], "confirm": False})                   # cofnięcie zatwierdzenia
    assert _confirm(client, admin_headers, job_id).status_code == 200    # powód już jest


def test_matching_invoice_confirms_without_reason_and_export_rechecks(
        client, admin_headers, db_session, monkeypatch, tmp_path):
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    sup.sap_code = "10004408"
    db_session.commit()
    cid = _container(client, admin_headers, company, sup)
    other = _container(client, admin_headers, company, sup, OTHER)
    _seed_order(db_session, company, cid)
    batch_id, job_id = _upload(client, admin_headers, monkeypatch, cid,
                               f"{CI}\nCONTAINER No.: {OWN}\nOrder no. : 4500000001")
    result = _conformity(client, admin_headers, job_id)
    assert result["status"] == "ok", result
    assert _confirm(client, admin_headers, job_id).status_code == 200
    # zamówienie przepięte w SAP do innego kontenera po zatwierdzeniu → eksport blokuje
    db_session.query(SapOrder).update({"container_id": other})
    db_session.commit()
    resp = client.post(f"/api/invoice-batches/{batch_id}/export", headers=admin_headers)
    assert resp.status_code == 409 and "zamówienie SAP" in resp.json()["detail"]


def test_order_of_other_container_conflicts(client, admin_headers, db_session, monkeypatch, tmp_path):
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    cid = _container(client, admin_headers, company, sup)
    other = _container(client, admin_headers, company, sup, OTHER)
    _seed_order(db_session, company, other)
    _, job_id = _upload(client, admin_headers, monkeypatch, cid, f"{CI}\nOrder no. : 4500000001")
    result = _conformity(client, admin_headers, job_id)
    assert result["status"] == "conflict" and _signal(result, "orders") is False
    assert [c["container_no"] for c in result["move_to"]] == [OTHER]


def test_unlinked_order_is_uncertain_not_conflict(
        client, admin_headers, db_session, monkeypatch, tmp_path):
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    cid = _container(client, admin_headers, company, sup)
    _seed_order(db_session, company, None)
    _, job_id = _upload(client, admin_headers, monkeypatch, cid, f"{CI}\nOrder no. : 4500000001")
    result = _conformity(client, admin_headers, job_id)
    assert _signal(result, "orders") is None and result["to_link"] == ["4500000001"]
    assert result["status"] == "uncertain"


def test_material_outside_container_conflicts(
        client, admin_headers, db_session, monkeypatch, tmp_path):
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    cid = _container(client, admin_headers, company, sup)
    _seed_order(db_session, company, cid, material="Z9")
    _, job_id = _upload(client, admin_headers, monkeypatch, cid, CI)
    result = _conformity(client, admin_headers, job_id)
    assert result["status"] == "conflict" and _signal(result, "materials") is False


def test_move_to_matching_container(client, admin_headers, db_session, monkeypatch, tmp_path):
    """2b „wrzuć do X”: sprzeczny dokument trafia do kontenera z treści i tam jest zgodny
    co do numeru kontenera; zatwierdzenie i powód nie przechodzą."""
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    cid = _container(client, admin_headers, company, sup)
    other = _container(client, admin_headers, company, sup, OTHER)
    batch_id, job_id = _upload(client, admin_headers, monkeypatch, cid, f"{CI}\nCONTAINER No.: {OTHER}")
    resp = client.post(f"/api/invoice-jobs/{job_id}/move", headers=admin_headers,
                       json={"container_id": other})
    assert resp.status_code == 200, resp.text
    assert resp.json()["container_no"] == OTHER
    result = _conformity(client, admin_headers, job_id)
    assert _signal(result, "container") is True and result["status"] == "uncertain"
    moved = client.get(f"/api/containers/{other}/invoice-batches", headers=admin_headers).json()
    assert [j["id"] for b in moved for j in b["jobs"]] == [job_id]
    source = client.get(f"/api/containers/{cid}/invoice-batches", headers=admin_headers).json()
    assert job_id not in [j["id"] for b in source for j in b["jobs"]]
    # PL z paczki źródłowej zostaje; usunięcie paczki źródłowej nie kasuje przeniesionego pliku
    assert client.delete(f"/api/invoice-batches/{batch_id}", headers=admin_headers).status_code == 204
    assert client.get(f"/api/invoice-jobs/{job_id}", headers=admin_headers).status_code == 200


def test_move_refuses_same_or_foreign_company_container(
        client, admin_headers, db_session, monkeypatch, tmp_path):
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    cid = _container(client, admin_headers, company, sup)
    _, job_id = _upload(client, admin_headers, monkeypatch, cid, CI)
    assert client.post(f"/api/invoice-jobs/{job_id}/move", headers=admin_headers,
                       json={"container_id": cid}).status_code == 409
    foreign_company = next(c["id"] for c in client.get("/api/companies", headers=admin_headers).json()
                           if c["id"] != company.id)
    foreign = client.post("/api/containers", headers=admin_headers, json={
        "container_no": OTHER, "company_id": foreign_company}).json()["id"]
    assert client.post(f"/api/invoice-jobs/{job_id}/move", headers=admin_headers,
                       json={"container_id": foreign}).status_code == 409


def test_move_refuses_target_with_same_invoice_and_processing_job(
        client, admin_headers, db_session, monkeypatch, tmp_path):
    """§4 pkt 18: cel ma już tę fakturę → 409 (bez dubla); dokument w trakcie OCR → 409."""
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    cid = _container(client, admin_headers, company, sup)
    other = _container(client, admin_headers, company, sup, OTHER)
    text = f"{CI}\nCONTAINER No.: {OTHER}"
    _, job_id = _upload(client, admin_headers, monkeypatch, cid, text)
    _upload(client, admin_headers, monkeypatch, other, text)          # ta sama faktura już w OTHER
    dup = client.post(f"/api/invoice-jobs/{job_id}/move", headers=admin_headers,
                      json={"container_id": other})
    assert dup.status_code == 409 and "ma już ten dokument" in dup.json()["detail"]

    third = _container(client, admin_headers, company, sup, "CAIU9756747")
    job = db_session.get(InvoiceJob, job_id)
    job.status = InvoiceJobStatus.uploaded
    db_session.commit()
    busy = client.post(f"/api/invoice-jobs/{job_id}/move", headers=admin_headers,
                       json={"container_id": third})
    assert busy.status_code == 409 and "przetwarzany" in busy.json()["detail"]


def test_invoice_for_several_containers(client, admin_headers, db_session, monkeypatch, tmp_path):
    """PR 3 (decyzja 4): faktura wymienia dwa kontenery — w każdym jest zgodna co do numeru,
    PO drugiego kontenera nie jest sprzecznością, materiały liczymy wobec sumy kontenerów;
    „Dodaj też do X” kopiuje dokument z pozycjami (raz)."""
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    cid = _container(client, admin_headers, company, sup)
    other = _container(client, admin_headers, company, sup, OTHER)
    _seed_order(db_session, company, other)                       # A1 tylko w zamówieniu OTHER
    _, job_id = _upload(client, admin_headers, monkeypatch, cid,
                        f"{CI}\nCONTAINER No.: {OWN}, {OTHER}\nOrder no. : 4500000001")
    result = _conformity(client, admin_headers, job_id)
    assert _signal(result, "container") is True
    assert _signal(result, "orders") is True and _signal(result, "materials") is True
    assert result["also_in"] == [{"id": other, "container_no": OTHER, "has_copy": False}]

    resp = client.post(f"/api/invoice-jobs/{job_id}/copy", headers=admin_headers,
                       json={"container_id": other})
    assert resp.status_code == 200, resp.text
    copy_id = resp.json()["job_id"]
    assert _conformity(client, admin_headers, job_id)["also_in"][0]["has_copy"] is True
    assert client.post(f"/api/invoice-jobs/{job_id}/copy", headers=admin_headers,
                       json={"container_id": other}).status_code == 409   # drugi raz nie
    original = client.get(f"/api/invoice-jobs/{job_id}", headers=admin_headers).json()
    copied = client.get(f"/api/invoice-jobs/{copy_id}", headers=admin_headers).json()
    assert len(copied["items"]) == len(original["items"]) > 0
    assert copied["invoice_number"] == original["invoice_number"]
    assert _conformity(client, admin_headers, copy_id)["also_in"][0]["container_no"] == OWN


def test_copy_only_to_container_named_on_invoice(
        client, admin_headers, db_session, monkeypatch, tmp_path):
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    cid = _container(client, admin_headers, company, sup)
    other = _container(client, admin_headers, company, sup, OTHER)
    _, job_id = _upload(client, admin_headers, monkeypatch, cid, f"{CI}\nCONTAINER No.: {OWN}")
    assert client.post(f"/api/invoice-jobs/{job_id}/copy", headers=admin_headers,
                       json={"container_id": other}).status_code == 409


def test_report_lists_suspicious_documents(client, admin_headers, db_session, monkeypatch, tmp_path):
    """PR 4: raport wsteczny — sprzeczne na górze, zgodne pominięte; nic się nie przenosi."""
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    sup.sap_code = "10004408"
    db_session.commit()
    cid = _container(client, admin_headers, company, sup)
    _container(client, admin_headers, company, sup, OTHER)
    _seed_order(db_session, company, cid)
    _, ok_id = _upload(client, admin_headers, monkeypatch, cid,
                       f"{CI}\nCONTAINER No.: {OWN}\nOrder no. : 4500000001")
    _, bad_id = _upload(client, admin_headers, monkeypatch, cid, f"{CI}\nCONTAINER No.: {OTHER}")
    report = client.get("/api/invoice-conformity/report", headers=admin_headers).json()
    assert report["checked"] >= 2
    ids = [r["job_id"] for r in report["rows"]]
    assert ok_id not in ids and ids[0] == bad_id
    first = report["rows"][0]
    assert first["status"] == "conflict" and first["move_to"][0]["container_no"] == OTHER
    assert first["container_no"] == OWN
