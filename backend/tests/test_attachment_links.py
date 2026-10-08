"""Wspólny plik dla kilku kontenerów (spec 2026-10-06 decyzja 24): plik właściciela widoczny
w powiązanym kontenerze (lista, pobranie, kafelki, bramka dubli); podmiana przepina powiązania,
usunięcie u właściciela zdejmuje plik wszędzie, „Odepnij” tylko powiązanie."""
import io

from sqlalchemy import select

from app.models import AttachmentLink, Company, Container, DocumentType, Role, User
from app.security import hash_password
from tests.conftest import forwarder, login, pdf_bytes
from tests.test_document_gate import OWN, _text_pdf
from tests.test_idor_scoping import _mk
from tests.test_intake import _post, _start
from tests.test_intake_routing import B, BODY, _items
from tests.test_invoice_conformity import _container


def _type(db, name, tile=None) -> int:
    t = db.scalar(select(DocumentType).where(DocumentType.name == name))
    if t is None:
        t = DocumentType(name=name, is_active=True, tile_code=tile)
        db.add(t)
        db.commit()
    return t.id


def _upload(client, headers, cid, data, type_id, name="bl.pdf", replaces=None):
    form = {"document_type_id": str(type_id)} | ({"replaces_id": str(replaces)} if replaces else {})
    return client.post(f"/api/containers/{cid}/attachments", headers=headers, data=form,
                       files={"file": (name, io.BytesIO(data), "application/pdf")})


def _link(client, headers, cid, aid, target):
    return client.post(f"/api/containers/{cid}/attachments/{aid}/link", headers=headers,
                       json={"container_id": target})


def _files(client, headers, cid) -> dict[str, dict]:
    return {a["filename"]: a for a in client.get(f"/api/containers/{cid}/attachments", headers=headers).json()}


def _setup_two(client, headers, db, monkeypatch, tmp_path):
    company, sup, a_id = _start(client, headers, db, monkeypatch, tmp_path)
    return company, sup, a_id, _container(client, headers, company, sup, no=B)


def test_link_lists_tiles_duplicate_replace_delete(client, admin_headers, db_session, monkeypatch, tmp_path):
    company, sup, a_id, b_id = _setup_two(client, admin_headers, db_session, monkeypatch, tmp_path)
    bl = _type(db_session, "Konosament", "BL")
    data = pdf_bytes("zbiorczy")
    aid = _upload(client, admin_headers, a_id, data, bl).json()["id"]
    resp = _link(client, admin_headers, a_id, aid, b_id)
    assert resp.status_code == 201, resp.text
    assert resp.json()["owner_container_no"] == OWN
    assert _link(client, admin_headers, a_id, aid, b_id).status_code == 409        # już jest
    seen = _files(client, admin_headers, b_id)["bl.pdf"]
    assert (seen["owner_container_no"], seen["shared_with"]) == (OWN, [OWN])
    assert (seen["can_unlink"], seen["can_delete"], seen["can_replace"]) == (True, False, False)
    assert _files(client, admin_headers, a_id)["bl.pdf"]["shared_with"] == [B]
    tiles = client.get(f"/api/containers/{b_id}/document-tiles", headers=admin_headers).json()
    assert "bl.pdf" in str(tiles)
    # bramka dubli: plik powiązany z B liczy się jak obecny w B
    dup = _upload(client, admin_headers, b_id, data, bl, name="znowu.pdf")
    assert dup.status_code == 409 and "bl.pdf" in dup.json()["detail"]
    # inna spółka: bez powiązania
    other = Company(name="Obca", code="OBCA")
    db_session.add(other)
    db_session.commit()
    c_id = _mk(db_session, "containers", container_no="CAIU9756747", company_id=other.id).id
    db_session.commit()
    assert _link(client, admin_headers, a_id, aid, c_id).status_code == 422
    # podmiana u właściciela: powiązanie idzie za nowym plikiem
    new = _upload(client, admin_headers, a_id, pdf_bytes("v2"), bl, name="bl_v2.pdf", replaces=aid)
    assert new.status_code == 201, new.text
    assert list(_files(client, admin_headers, b_id)) == ["bl_v2.pdf"]
    # usunięcie u właściciela zdejmuje plik wszędzie
    assert client.delete(f"/api/attachments/{new.json()['id']}", headers=admin_headers).status_code == 204
    assert _files(client, admin_headers, b_id) == {}
    assert db_session.scalar(select(AttachmentLink.id)) is None


def test_unlink_and_access_through_linked_container(client, admin_headers, db_session, monkeypatch, tmp_path):
    company, sup, a_id, b_id = _setup_two(client, admin_headers, db_session, monkeypatch, tmp_path)
    cmr = _type(db_session, "CMR")
    fwd = forwarder(client, admin_headers, "SPEDALFA")
    db_session.get(Container, b_id).forwarder_id = fwd["id"]     # spedytor widzi tylko B
    other = Company(name="Obca", code="OBCA")
    db_session.add_all([other,
                        User(login="spd1", hashed_password=hash_password("pass12345"),
                             role=Role.forwarder, forwarder_id=fwd["id"])])
    db_session.flush()
    db_session.add(User(login="obcy", hashed_password=hash_password("pass12345"),
                        role=Role.logistics, company_id=other.id))
    db_session.commit()
    spd, obcy = login(client, "spd1", "pass12345"), login(client, "obcy", "pass12345")
    aid = _upload(client, admin_headers, a_id, pdf_bytes("cmr"), cmr, name="cmr.pdf").json()["id"]
    url = f"/api/attachments/{aid}/download"
    assert client.get(url, headers=spd).status_code == 404
    assert _link(client, admin_headers, a_id, aid, b_id).status_code == 201
    assert client.get(url, headers=spd).status_code == 200                    # przez powiązany B
    assert "cmr.pdf" in _files(client, spd, b_id)
    assert client.get(url, headers=obcy).status_code == 404                   # obca spółka nie
    assert client.delete(f"/api/attachments/{aid}", headers=spd).status_code == 403   # nie swój plik
    # spedytor nie odepnie powiązania dodanego przez kogoś innego; u właściciela „Odepnij” nie ma
    assert client.delete(f"/api/containers/{b_id}/attachments/{aid}/link", headers=spd).status_code == 403
    assert client.delete(f"/api/containers/{a_id}/attachments/{aid}/link",
                         headers=admin_headers).status_code == 409
    assert client.delete(f"/api/containers/{b_id}/attachments/{aid}/link",
                         headers=admin_headers).status_code == 204
    assert _files(client, admin_headers, b_id) == {}
    assert "cmr.pdf" in _files(client, admin_headers, a_id)
    assert client.get(url, headers=spd).status_code == 404


def test_intake_collective_bl_shared_on_confirm(client, admin_headers, db_session, monkeypatch, tmp_path):
    company, sup, a_id, b_id = _setup_two(client, admin_headers, db_session, monkeypatch, tmp_path)
    body = _post(client, admin_headers, a_id, {
        "zbiorczy.pdf": _text_pdf(tmp_path, f"{BODY} zbiorczy\n{B}\n{OWN}")}).json()
    assert _items(body)["zbiorczy.pdf"]["gate_message"] == f"Dotyczy też: {B}"
    assert client.post(f"/api/intake/{body['id']}/confirm", headers=admin_headers).status_code == 200
    shared = _files(client, admin_headers, b_id)["zbiorczy.pdf"]
    assert shared["owner_container_no"] == OWN
    tiles = client.get(f"/api/containers/{b_id}/document-tiles", headers=admin_headers).json()
    assert "zbiorczy.pdf" in str(tiles)
