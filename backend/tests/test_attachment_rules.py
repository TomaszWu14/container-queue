"""Usuwanie / podmiana dokumentów (spec 2026-10-06 §4 pkt 1–3, 47): partnerzy tylko własne
pliki; po wysłaniu do agencji tylko „Podmień” z powodem; podmiana atomowa z zachowaniem typu."""
from app.database import SessionLocal
from app.models import AuditLog, Container, DocumentStatus, DocumentType
from tests.conftest import login, pdf_bytes
from tests.test_customs import _setup


def _up(client, headers, cid, name, data=None):
    return client.post(f"/api/containers/{cid}/attachments", headers=headers, data=data or {},
                       files={"file": (name, pdf_bytes(name), "application/pdf")})


def _files(client, headers, cid):
    return {f["filename"]: f for f in client.get(f"/api/containers/{cid}/attachments", headers=headers).json()}


def test_agency_deletes_only_own_files(client, admin_headers):
    ctx = _setup(client, admin_headers)
    logistics, agency = login(client, "log.tim", "haslo123"), login(client, "celna.a", "haslo123")
    cid = ctx["container"]["id"]
    client.post(f"/api/customs/containers/{cid}/assign", headers=logistics,
                json={"customs_agency_id": ctx["ag_a"]["id"]})
    theirs = _up(client, logistics, cid, "CI.pdf").json()
    own = _up(client, agency, cid, "korekta.pdf").json()
    assert _files(client, agency, cid)["CI.pdf"]["can_delete"] is False
    assert client.delete(f"/api/attachments/{theirs['id']}", headers=agency).status_code == 403
    assert client.delete(f"/api/attachments/{own['id']}", headers=agency).status_code == 204


def test_after_sending_only_replace_with_reason(client, admin_headers):
    ctx = _setup(client, admin_headers)
    logistics = login(client, "log.tim", "haslo123")
    cid = ctx["container"]["id"]
    with SessionLocal() as db:
        bl_type = DocumentType(name="Konosament", is_active=True, tile_code="BL")
        db.add(bl_type)
        db.commit()
        type_id = bl_type.id
    old = _up(client, logistics, cid, "BL-stary.pdf", {"document_type_id": str(type_id)}).json()
    with SessionLocal() as db:
        db.get(Container, cid).document_status = DocumentStatus.WYSLANE
        db.commit()
    flags = _files(client, logistics, cid)["BL-stary.pdf"]
    assert (flags["can_delete"], flags["can_replace"], flags["replace_needs_reason"]) == (False, True, True)
    gone = client.delete(f"/api/attachments/{old['id']}", headers=logistics)
    assert gone.status_code == 409 and "Podmień" in gone.json()["detail"]
    no_reason = _up(client, logistics, cid, "BL-nowy.pdf", {"replaces_id": str(old["id"])})
    assert no_reason.status_code == 422 and "powód" in no_reason.json()["detail"]
    ok = _up(client, logistics, cid, "BL-nowy.pdf", {"replaces_id": str(old["id"]),
                                                     "replace_reason": "korekta wagi od armatora"})
    assert ok.status_code == 201, ok.text
    files = _files(client, logistics, cid)
    assert list(files) == ["BL-nowy.pdf"] and files["BL-nowy.pdf"]["document_type_id"] == type_id
    with SessionLocal() as db:
        log = db.query(AuditLog).filter_by(field="attachment_replace").one()
        assert (log.old_value, log.new_value, log.note) == ("BL-stary.pdf", "BL-nowy.pdf", "korekta wagi od armatora")


def test_replace_blocked_for_foreign_file_keeps_both_out(client, admin_headers):
    """Nieudana podmiana (cudzy plik) nie zostawia nowego pliku — jedna transakcja."""
    ctx = _setup(client, admin_headers)
    logistics, agency = login(client, "log.tim", "haslo123"), login(client, "celna.a", "haslo123")
    cid = ctx["container"]["id"]
    client.post(f"/api/customs/containers/{cid}/assign", headers=logistics,
                json={"customs_agency_id": ctx["ag_a"]["id"]})
    theirs = _up(client, logistics, cid, "CI.pdf").json()
    resp = _up(client, agency, cid, "CI-v2.pdf", {"replaces_id": str(theirs["id"])})
    assert resp.status_code == 403
    assert list(_files(client, logistics, cid)) == ["CI.pdf"]


def test_upload_is_audited_and_last_typed_delete_reverts_status(client, admin_headers):
    """§4 pkt 8, 10: wgranie w historii; usunięcie ostatniego otypowanego → obieg ZALACZONE→BRAK."""
    ctx = _setup(client, admin_headers)
    logistics = login(client, "log.tim", "haslo123")
    cid = ctx["container"]["id"]
    with SessionLocal() as db:
        cmr = DocumentType(name="CMR", is_active=True)
        db.add(cmr)
        db.commit()
        type_id = cmr.id
    up = _up(client, logistics, cid, "CMR.pdf", {"document_type_id": str(type_id)}).json()
    with SessionLocal() as db:
        assert db.get(Container, cid).document_status == DocumentStatus.ZALACZONE
        assert db.query(AuditLog).filter_by(field="attachment_upload", new_value="CMR.pdf").count() == 1
    assert client.delete(f"/api/attachments/{up['id']}", headers=logistics).status_code == 204
    with SessionLocal() as db:
        assert db.get(Container, cid).document_status == DocumentStatus.BRAK
