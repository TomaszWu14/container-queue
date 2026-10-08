"""Spedytor ma ZERO wglądu w odprawę (docs/REGULY-PROCESU.md, decyzja 2026-09-28): status, notatki,
dane agenta i dokumenty celne nie mogą wyciec żadnym bocznym kanałem (digest zmian, odpowiedź
PATCH kierowcy, szczegół zamówienia, kafelki SAD, wyszukiwarka, powiadomienia, braki dokumentów)."""
import pytest
from sqlalchemy import select

from app.models import (AuditLog, Attachment, Company, Container, CustomsAgency, CustomsStatus,
                        DocumentType, Forwarder, InvoiceBatch, Order, Role, SadDraft, User)
from app.security import create_access_token

from .conftest import login
from tests.conftest import pdf_bytes

SECRET = "TAJNEODPRAWA"


@pytest.fixture()
def leak_setup(client, db_session):
    co = db_session.scalars(select(Company)).first()
    fw = Forwarder(name="FW-ODPRAWA")
    ag = CustomsAgency(name=f"AG-{SECRET}")
    db_session.add_all([fw, ag, DocumentType(name=f"{SECRET}-typ", is_required=True)])
    db_session.flush()
    order = Order(number="PO-ODPRAWA-1", company_id=co.id)
    db_session.add(order)
    db_session.flush()
    cont = Container(company_id=co.id, container_no="ODPU1234567", forwarder_id=fw.id,
                     order_id=order.id, customs_agency_id=ag.id,
                     customs_status=CustomsStatus.DRAFT_WYSLANY, customs_note=f"note {SECRET}",
                     customs_agent_name=f"agent {SECRET}", customs_agent_email="a@ag.pl")
    db_session.add(cont)
    db_session.flush()
    sad = Attachment(container_id=cont.id, filename=f"SAD_{SECRET}.pdf", stored_name="sad1.pdf")
    batch = InvoiceBatch(container_id=cont.id)
    db_session.add_all([sad, batch])
    db_session.flush()
    db_session.add(SadDraft(batch_id=batch.id, version=1, attachment_id=sad.id, sha256="x" * 64))
    db_session.add(AuditLog(entity_type="containers", entity_id=cont.id, field="customs_note",
                            old_value="", new_value=f"note {SECRET}", note=""))
    user = User(login="fw-odprawa", hashed_password="x", role=Role.forwarder,
                forwarder_id=fw.id, company_id=co.id)
    db_session.add(user)
    db_session.commit()
    # wgranie SAD przez logistykę → powiadomienie do obserwatorów (w tym spedytora)
    r = client.post(f"/api/containers/{cont.id}/attachments", headers=login(client),
                    files={"file": (f"SAD_PW_{SECRET}.pdf", pdf_bytes("SAD_PW"), "application/pdf")})
    assert r.status_code == 201, r.text
    return {"cid": cont.id, "oid": order.id,
            "hdr": {"Authorization": f"Bearer {create_access_token(user)}"}}


ENDPOINTS = {
    "digest": lambda c, s: c.get("/api/changes/digest", headers=s["hdr"]),
    "driver": lambda c, s: c.patch(f"/api/containers/{s['cid']}/driver", headers=s["hdr"],
                                   json={"driver_name": "Jan"}),
    "order": lambda c, s: c.get(f"/api/orders/{s['oid']}", headers=s["hdr"]),
    "tiles": lambda c, s: c.get(f"/api/containers/{s['cid']}/document-tiles", headers=s["hdr"]),
    "search": lambda c, s: c.get(f"/api/documents/search?q={SECRET}", headers=s["hdr"]),
    "notifications": lambda c, s: c.get("/api/notifications", headers=s["hdr"]),
    "card": lambda c, s: c.get(f"/api/containers/{s['cid']}", headers=s["hdr"]),
}


@pytest.mark.parametrize("name", ENDPOINTS)
def test_forwarder_sees_no_customs_data(client, leak_setup, name):
    r = ENDPOINTS[name](client, leak_setup)
    if name == "order":   # zamówienia to dane wewnętrzne spółki — partner nie ma wglądu wcale
        assert r.status_code in (403, 404), r.text
        return
    assert r.status_code == 200, r.text
    assert SECRET not in r.text, f"{name}: wyciek danych odprawy do spedytora"
    if name == "tiles":   # kafelki SAD puste — stan/„wymagany” zdradzałby status odprawy
        sad = [t for t in r.json()["tiles"] if t["code"].startswith("SAD_")]
        assert all(t["state"] == "none" and not t["required"] for t in sad)
