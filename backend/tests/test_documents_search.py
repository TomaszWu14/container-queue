"""Wyszukiwarka dokumentów (#41): full-text po źródłach + izolacja spółki (bezpieczeństwo)."""
from sqlalchemy import select

from app.models import Attachment, Company, Container, FreightInvoice, Role, User
from app.security import create_access_token

from .conftest import login


def _hdr(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def test_search_finds_across_sources(client, db_session):
    co = db_session.scalars(select(Company)).first()
    cont = Container(company_id=co.id, container_no="HLCU1112223")
    db_session.add(cont)
    db_session.flush()
    db_session.add(Attachment(container_id=cont.id, filename="CMR_umowa_ACME.pdf", stored_name="a1.pdf"))
    db_session.add(FreightInvoice(company_id=co.id, bl_number="BL-ZZZ-9", amount=100))
    db_session.commit()
    hdr = login(client)

    res = client.get("/api/documents/search?q=ACME", headers=hdr).json()
    assert any(r["source"] == "attachment" and "ACME" in r["title"] for r in res)

    res2 = client.get("/api/documents/search?q=BL-ZZZ-9", headers=hdr).json()
    assert any(r["source"] == "freight" for r in res2)


def test_search_respects_company_scope(client, db_session):
    co_a = db_session.scalars(select(Company)).first()
    co_b = Company(name="Inna Sp", code="INNA")
    db_session.add(co_b)
    db_session.flush()
    cont_b = Container(company_id=co_b.id, container_no="OOLU9998887")
    db_session.add(cont_b)
    db_session.flush()
    db_session.add(Attachment(container_id=cont_b.id, filename="TAJNE_spolki_B.pdf", stored_name="b1.pdf"))
    user_a = User(login="log-a", hashed_password="x", role=Role.logistics, company_id=co_a.id)
    db_session.add(user_a)
    db_session.commit()
    # user spółki A nie może znaleźć dokumentu spółki B
    res = client.get("/api/documents/search?q=TAJNE", headers=_hdr(user_a)).json()
    assert res == []


def test_search_hides_cipl_and_supplier_from_external_roles(client, db_session):
    """Audyt 2026-09-23: faktury CIPL (InvoiceJob) i nazwa dostawcy nie wyciekają do
    magazynu/agencji celnej/spedytora przez wyszukiwarkę — jak w routerze invoices i to_out."""
    from app.models import CustomsAgency, Forwarder, InvoiceBatch, InvoiceJob, Supplier, Warehouse
    co = db_session.scalars(select(Company)).first()
    wh = Warehouse(name="WH-CIPL", company_id=co.id)
    ag = CustomsAgency(name="AG-CIPL")
    fw = Forwarder(name="FW-CIPL")
    sup = Supplier(name="Tajny Dostawca", client_company_id=co.id)
    db_session.add_all([wh, ag, fw, sup])
    db_session.flush()
    cont = Container(company_id=co.id, container_no="CIPU1234567", warehouse_id=wh.id,
                     customs_agency_id=ag.id, forwarder_id=fw.id, supplier_id=sup.id)
    db_session.add(cont)
    db_session.flush()
    db_session.add(Attachment(container_id=cont.id, filename="CIPL_zal.pdf", stored_name="c1.pdf"))
    batch = InvoiceBatch(container_id=cont.id)
    db_session.add(batch)
    db_session.flush()
    db_session.add(InvoiceJob(batch_id=batch.id, filename="CIPL_faktura.pdf", stored_name="c2.pdf",
                              text_excerpt="unit price USD 12.50"))
    users = {
        "wh": User(login="cipl-wh", hashed_password="x", role=Role.warehouse,
                   company_id=co.id, warehouse_id=wh.id),
        "cu": User(login="cipl-cu", hashed_password="x", role=Role.customs,
                   customs_agency_id=ag.id),
        "fw": User(login="cipl-fw", hashed_password="x", role=Role.forwarder,
                   forwarder_id=fw.id),
    }
    db_session.add_all(users.values())
    db_session.commit()

    for key, u in users.items():
        res = client.get("/api/documents/search?q=CIPL", headers=_hdr(u)).json()
        assert not any(r["source"] == "invoice" for r in res), key
        # brak wyroczni po treści faktury (text_excerpt)
        assert client.get("/api/documents/search?q=USD", headers=_hdr(u)).json() == [], key
    res = client.get("/api/documents/search?q=CIPL", headers=_hdr(users["cu"])).json()
    assert res and all(r["supplier_name"] is None for r in res)
    # magazyn: cudzy plik bez typu dokumentu ukryty (decyzja 2026-10-05)
    assert client.get("/api/documents/search?q=CIPL", headers=_hdr(users["wh"])).json() == []

    # rola z dostępem do faktur nadal widzi CIPL i dostawcę
    res = client.get("/api/documents/search?q=CIPL", headers=login(client)).json()
    assert any(r["source"] == "invoice" and r["supplier_name"] == "Tajny Dostawca" for r in res)


def _scope_fixture(db_session):
    """Kontener spedytora i magazynu + załączniki różnych typów i autorów."""
    from app.models import DocumentType, Forwarder, Warehouse
    co = db_session.scalars(select(Company)).first()
    fw, wh = Forwarder(name="FW-LIMIT"), Warehouse(name="MAG-LIMIT", company_id=co.id)
    types = [DocumentType(name="CMR"), DocumentType(name="list cmr kopia"), DocumentType(name="Inne"),
             DocumentType(name="Faktura CI", tile_code="CI"), DocumentType(name="Packing", tile_code="PL")]
    db_session.add_all([fw, wh, *types])
    db_session.flush()
    cont = Container(company_id=co.id, container_no="LIMU1234565", forwarder_id=fw.id, warehouse_id=wh.id)
    users = {"fw": User(login="fw-limit", hashed_password="x", role=Role.forwarder, forwarder_id=fw.id),
             "wh": User(login="wh-limit", hashed_password="x", role=Role.warehouse, warehouse_id=wh.id,
                        company_id=co.id),
             "log": User(login="log-limit", hashed_password="x", role=Role.logistics, company_id=co.id)}
    db_session.add_all([cont, *users.values()])
    db_session.flush()
    # najpierw wiersze ukryte dla spedytora/magazynu (autor obcy, CI, bez typu) — test limitu
    for author in (None, users["log"], users["wh"], users["fw"]):
        for dt in (types[3], None, *types[:3], types[4]):
            name = f"LIMIT_{author and author.login}_{dt and dt.name}.pdf"
            db_session.add(Attachment(container_id=cont.id, stored_name=name, filename=name,
                                      uploaded_by_id=author and author.id, document_type_id=dt and dt.id))
    db_session.commit()
    return users


def test_forwarder_may_see_sql_matches_python(client, db_session):
    """Jedno źródło reguły: warunek SQL (wyszukiwarka z limitem) = forwarder_may_see (listy)."""
    from sqlalchemy.orm import selectinload

    from app.deps import forwarder_may_see, forwarder_may_see_sql
    from app.models import DocumentType
    users = _scope_fixture(db_session)
    atts = db_session.scalars(select(Attachment).options(selectinload(Attachment.document_type))).all()
    for key, u in users.items():
        py = {a.id for a in atts if forwarder_may_see(a, u)}
        sql = set(db_session.scalars(select(Attachment.id).outerjoin(
            DocumentType, Attachment.document_type_id == DocumentType.id).where(forwarder_may_see_sql(u))))
        assert py == sql, key
        assert 0 < len(py) <= len(atts), key


def test_search_limit_applies_after_role_filter(client, db_session):
    """Filtr spedytora/magazynu przed limitem: ukryte wiersze nie zjadają miejsca w wynikach."""
    users = _scope_fixture(db_session)
    for key in ("fw", "wh"):
        res = client.get("/api/documents/search?q=LIMIT_&limit=3", headers=_hdr(users[key])).json()
        assert len(res) == 3, key
