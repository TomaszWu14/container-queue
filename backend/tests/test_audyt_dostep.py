"""Audyt dostępu (2026-09-23): role i zakres na fakturach transportowych, zamówieniach
zakupowych, statystykach/archiwum/wyszukiwarce dokumentów oraz walidacja parametrów."""
from app.database import SessionLocal
from app.models import Company, Container, FreightInvoice, Role, User, Warehouse
from app.security import hash_password
from tests.conftest import login, pdf_bytes


def _setup_warehouse_user():
    """Spółka z magazynami W1/W2, kontenerami w obu, fakturą transportową i kontem
    magazynowym przypisanym do W1. Zwraca (company_code, id kontenera W2, id faktury)."""
    with SessionLocal() as db:
        co = Company(name="Audyt Co", code="AUDC"); db.add(co); db.flush()
        w1 = Warehouse(name="W1", company_id=co.id)
        w2 = Warehouse(name="W2", company_id=co.id)
        db.add_all([w1, w2]); db.flush()
        c1 = Container(container_no="AUDU0000001", company_id=co.id, warehouse_id=w1.id)
        c2 = Container(container_no="AUDU0000002", company_id=co.id, warehouse_id=w2.id)
        inv = FreightInvoice(company_id=co.id, bl_number="BL-AUD", stored_name="x.pdf",
                             filename="x.pdf")
        db.add_all([c1, c2, inv])
        db.add(User(login="aud-wh1", hashed_password=hash_password("pass12345"),
                    role=Role.warehouse, company_id=co.id, warehouse_id=w1.id))
        db.commit()
        return co.code, c2.id, inv.id


def test_warehouse_forbidden_on_freight_invoices(client, admin_headers):
    _, _, inv_id = _setup_warehouse_user()
    hdr = login(client, "aud-wh1", "pass12345")
    assert client.get("/api/freight-invoices", headers=hdr).status_code == 403
    assert client.get(f"/api/freight-invoices/{inv_id}/download",
                      headers=hdr).status_code == 403
    # admin nadal widzi
    assert any(i["id"] == inv_id for i in
               client.get("/api/freight-invoices", headers=admin_headers).json())


def test_warehouse_forbidden_on_purchase_orders(client, admin_headers):
    code, _, _ = _setup_warehouse_user()
    hdr = login(client, "aud-wh1", "pass12345")
    assert client.get("/api/purchase-orders", headers=hdr).status_code == 403
    assert client.get(f"/api/purchase-orders?company_code={code}",
                      headers=hdr).status_code == 403


def test_fk_filter_non_ascii_digit_is_ignored(client, admin_headers):
    # "²" (U+00B2) przechodzi str.isdigit(), ale int() rzuca → wcześniej 500
    assert client.get("/api/containers?supplier_id=%C2%B2",
                      headers=admin_headers).status_code == 200


def test_negative_or_huge_limits_rejected(client, admin_headers):
    for url in ("/api/containers?limit=-1", "/api/containers?limit=0",
                "/api/material-units?limit=-1", "/api/material-units?limit=100000",
                "/api/notifications?limit=-1", "/api/admin/auth-log?limit=-1",
                "/api/audit/suppliers?limit=-1"):
        assert client.get(url, headers=admin_headers).status_code == 422, url


def test_zip_arcname_has_no_path_components(client):
    import io
    import secrets
    import types
    import zipfile
    from app.routers.documents import _zip_attachments
    from app.routers.forwarding import uploads_dir
    stored = [f"zipslip_{secrets.token_hex(4)}_{i}" for i in range(3)]
    for s in stored:
        (uploads_dir() / s).write_bytes(b"x")
    try:
        atts = [types.SimpleNamespace(id=i, stored_name=s, filename=f)
                for i, (s, f) in enumerate(zip(stored, ("../../evil.txt", "..\\..\\win.txt", "/")))]
        names = zipfile.ZipFile(io.BytesIO(_zip_attachments(atts))).namelist()
        assert names == ["evil.txt", "win.txt", "plik"]
    finally:
        for s in stored:
            (uploads_dir() / s).unlink(missing_ok=True)


def test_long_upload_filename_is_truncated(client, admin_headers):
    with SessionLocal() as db:
        co = Company(name="Long Co", code="LONC"); db.add(co); db.flush()
        cont = Container(container_no="LONU0000001", company_id=co.id)
        db.add(cont); db.commit(); cid = cont.id
    name = "a" * 300 + ".pdf"
    r = client.post(f"/api/containers/{cid}/attachments", headers=admin_headers,
                    files={"file": (name, pdf_bytes(name), "application/pdf")})
    assert r.status_code == 201, r.text
    assert len(r.json()["filename"]) <= 255 and r.json()["filename"].endswith(".pdf")


def test_safe_filename_unit():
    from app.routers.forwarding import safe_filename
    assert safe_filename("..\\..\\x.pdf") == "x.pdf"
    assert safe_filename(None, "foto") == "foto"
    long = safe_filename("b" * 400 + ".jpeg")
    assert len(long) <= 128 and long.endswith(".jpeg")


def test_commit_with_file_cleans_up_on_failed_commit(tmp_path):
    import pytest
    from app.routers.forwarding import commit_with_file

    class _Boom:
        def commit(self):
            raise RuntimeError("db down")
    path = tmp_path / "f.bin"
    with pytest.raises(RuntimeError):
        commit_with_file(_Boom(), path, b"x")
    assert not path.exists()


def test_public_pages_are_rate_limited(client, monkeypatch):
    from app.routers import portal
    from app.security import api_limiter
    api_limiter._hits.clear()
    monkeypatch.setattr(portal, "_PUBLIC_LIMIT_PER_MINUTE", 2)
    try:
        codes = [client.get("/api/public/branding").status_code for _ in range(3)]
        assert codes == [200, 200, 429]
    finally:
        api_limiter._hits.clear()


def _setup_logistics_w1():
    """Logistyk ograniczony do W1; kontenery z notify_date w W1 i W2; załącznik tylko
    w kontenerze W2. Zwraca company_code."""
    import datetime
    from app.models import Attachment
    with SessionLocal() as db:
        co = Company(name="Log Co", code="LOGC"); db.add(co); db.flush()
        w1 = Warehouse(name="W1", company_id=co.id)
        w2 = Warehouse(name="W2", company_id=co.id)
        db.add_all([w1, w2]); db.flush()
        d = datetime.date(2026, 9, 1)
        c1 = Container(container_no="LOGU0000001", company_id=co.id, warehouse_id=w1.id,
                       notify_date=d)
        c2 = Container(container_no="LOGU0000002", company_id=co.id, warehouse_id=w2.id,
                       notify_date=d)
        db.add_all([c1, c2]); db.flush()
        db.add(Attachment(container_id=c2.id, filename="w2.pdf", stored_name="log-w2.pdf"))
        db.add(User(login="log-w1", hashed_password=hash_password("pass12345"),
                    role=Role.logistics, company_id=co.id, allowed_warehouse_ids=[w1.id]))
        db.commit()
        return co.code


def test_monthly_stats_respects_logistics_warehouse_scope(client, admin_headers):
    _setup_logistics_w1()
    hdr = login(client, "log-w1", "pass12345")
    rows = client.get("/api/stats/monthly", headers=hdr).json()
    assert sum(r["count"] for r in rows) == 1


def test_monthly_zip_respects_logistics_warehouse_scope(client, admin_headers):
    code = _setup_logistics_w1()
    hdr = login(client, "log-w1", "pass12345")
    r = client.get(f"/api/archive/attachments-zip?company_code={code}&month=2026-09",
                   headers=hdr)
    assert r.status_code == 404   # jedyny dokument jest w magazynie spoza zakresu


def test_documents_search_freight_section_scoped(client, admin_headers):
    from app.models import Forwarder
    _setup_warehouse_user()
    with SessionLocal() as db:
        fw = Forwarder(name="Aud Fwd"); db.add(fw); db.flush()
        db.add(User(login="aud-fwd", hashed_password=hash_password("pass12345"),
                    role=Role.forwarder, company_id=None, forwarder_id=fw.id))
        db.commit()
    for name in ("aud-wh1", "aud-fwd"):
        r = client.get("/api/documents/search?q=BL-AUD", headers=login(client, name, "pass12345"))
        assert r.status_code == 200, (name, r.text)
        assert not any(x["source"] == "freight" for x in r.json()), name
    r = client.get("/api/documents/search?q=BL-AUD", headers=admin_headers)
    assert any(x["source"] == "freight" for x in r.json())


def test_logistics_warehouse_scope_applies_to_access_by_id(client, admin_headers):
    """Zakres magazynów logistyka obowiązuje też przy dostępie po id (nie tylko listy)."""
    from sqlalchemy import select
    from app.models import Attachment
    _setup_logistics_w1()
    with SessionLocal() as db:
        c1 = db.scalar(select(Container).where(Container.container_no == "LOGU0000001"))
        c2 = db.scalar(select(Container).where(Container.container_no == "LOGU0000002"))
        att = db.scalar(select(Attachment).where(Attachment.container_id == c2.id))
        ids = (c1.id, c2.id, att.id)
    hdr = login(client, "log-w1", "pass12345")
    assert client.get(f"/api/containers/{ids[0]}", headers=hdr).status_code == 200
    assert client.get(f"/api/containers/{ids[1]}", headers=hdr).status_code == 404
    assert client.get(f"/api/attachments/{ids[2]}/download", headers=hdr).status_code == 404
