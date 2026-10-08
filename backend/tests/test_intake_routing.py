"""Poczekalnia — rozdział po treści (spec 2026-10-06-dokumenty-dostaw, decyzje 13 i 14): numer
innego NASZEGO kontenera = cel tej części (nie konflikt); bez numeru — dopasowanie po PO / numerze
faktury, inaczej bieżący kontener z plakietką „niepewny”."""
from sqlalchemy import select

from app.models import Attachment, Container
from tests.test_document_gate import OWN, _text_pdf
from tests.test_idor_scoping import _mk
from tests.test_intake import _post, _start
from tests.test_invoice_conformity import _container

B = "CSQU3054383"
BODY = "BILL OF LADING SHIPPED ON BOARD 40HQ said to contain"


def _items(body) -> dict[str, dict]:
    return {i["original_name"]: i for i in body["items"]}


def test_split_between_two_containers(client, admin_headers, db_session, monkeypatch, tmp_path):
    company, sup, cid = _start(client, admin_headers, db_session, monkeypatch, tmp_path)
    b_id = _container(client, admin_headers, company, sup, no=B)
    body = _post(client, admin_headers, cid, {
        "bl_a.pdf": _text_pdf(tmp_path, f"{BODY}\n{OWN}"),
        "bl_b.pdf": _text_pdf(tmp_path, f"{BODY}\n{B}"),
        "zbiorczy.pdf": _text_pdf(tmp_path, f"{BODY} zbiorczy\n{B}\n{OWN}")}).json()
    items = _items(body)
    assert (items["bl_a.pdf"]["target_container_no"], items["bl_a.pdf"]["gate_status"]) == (OWN, "ok")
    assert (items["bl_b.pdf"]["target_container_no"], items["bl_b.pdf"]["gate_status"]) == (B, "ok")
    assert items["bl_b.pdf"]["gate_message"] == f"Rozdzielone: dokument dotyczy {B}"
    # zbiorczy B/L z naszym numerem zostaje w bieżącym kontenerze, reszta tylko w komunikacie
    assert items["zbiorczy.pdf"]["target_container_no"] == OWN
    assert items["zbiorczy.pdf"]["gate_message"] == f"Dotyczy też: {B}"
    summary = client.post(f"/api/intake/{body['id']}/confirm", headers=admin_headers).json()
    assert summary["containers"] == {OWN: {"invoices": 0, "attachments": 2},
                                     B: {"invoices": 0, "attachments": 1}}
    assert db_session.scalar(select(Attachment.filename).where(Attachment.container_id == b_id)) == "bl_b.pdf"


def test_duplicate_checked_against_routed_target(client, admin_headers, db_session, monkeypatch, tmp_path):
    company, sup, cid = _start(client, admin_headers, db_session, monkeypatch, tmp_path)
    b_id = _container(client, admin_headers, company, sup, no=B)
    bl_b = _text_pdf(tmp_path, f"{BODY}\n{B}")
    first = _post(client, admin_headers, b_id, {"bl_b.pdf": bl_b}).json()
    assert client.post(f"/api/intake/{first['id']}/confirm", headers=admin_headers).status_code == 200
    item = _post(client, admin_headers, cid, {"bl_b.pdf": bl_b}).json()["items"][0]
    assert (item["target_container_no"], item["gate_status"]) == (B, "duplicate")


def test_match_by_po_and_invoice_number(client, admin_headers, db_session, monkeypatch, tmp_path):
    company, sup, cid = _start(client, admin_headers, db_session, monkeypatch, tmp_path)
    b_id = _container(client, admin_headers, company, sup, no=B)
    _mk(db_session, "sap_orders", company_id=company.id, order_number="4700600638", container_id=b_id)
    batch = _mk(db_session, "invoice_batches", container_id=b_id)
    _mk(db_session, "invoice_jobs", batch_id=batch.id, invoice_number="INV-7781")
    db_session.get(Container, b_id).order_numbers = "PO4800000001; 4500"   # pole tekstowe z Excela
    db_session.commit()
    body = _post(client, admin_headers, cid, {
        "po.pdf": _text_pdf(tmp_path, "Delivery note for goods\nOrder no.: 4700600638"),
        "pole.pdf": _text_pdf(tmp_path, "Shipping advice for goods\nPO: 4800000001"),
        "faktura.pdf": _text_pdf(tmp_path, "Debit note for goods\nInvoice No.: INV-7781"),
        "nic.pdf": _text_pdf(tmp_path, "Certificate of origin for goods\nOrder no.: 4799999999")}).json()
    items = _items(body)
    assert all(i["gate_status"] == "uncertain" for i in items.values())
    assert items["po.pdf"]["target_container_no"] == B
    assert items["po.pdf"]["gate_message"] == "Dopasowano po PO 4700600638"
    assert items["pole.pdf"]["target_container_no"] == B
    assert items["pole.pdf"]["gate_message"] == "Dopasowano po PO 4800000001"
    assert items["faktura.pdf"]["target_container_no"] == B
    assert items["faktura.pdf"]["gate_message"] == "Dopasowano po fakturze INV-7781"
    assert items["nic.pdf"]["target_container_no"] == OWN               # brak trafienia = bieżący
    assert "nie ma numeru kontenera" in items["nic.pdf"]["gate_message"]


def test_po_in_two_containers_stays_in_context(client, admin_headers, db_session, monkeypatch, tmp_path):
    company, sup, cid = _start(client, admin_headers, db_session, monkeypatch, tmp_path)
    b_id = _container(client, admin_headers, company, sup, no=B)
    c_id = _container(client, admin_headers, company, sup, no="CAIU9756747")
    _mk(db_session, "sap_orders", company_id=company.id, order_number="4700600638", container_id=b_id)
    _mk(db_session, "sap_orders", company_id=company.id, order_number="4700600639", container_id=c_id)
    db_session.commit()
    item = _post(client, admin_headers, cid, {"po.pdf": _text_pdf(
        tmp_path, "Delivery note for goods\nOrders: 4700600638, 4700600639")}).json()["items"][0]
    assert (item["target_container_no"], item["gate_status"]) == (OWN, "uncertain")
