import io

from app.invoices.suggestions import CONTAINER_NO_RE
from tests.conftest import forwarder, login, pdf_bytes

VALID_NO = "MSDU0806613"
SECOND_NO = "CSQU3054383"


def _setup(client, admin_headers):
    """Spółka Borealis + spedytor SPEDALFA + kontener przypisany do SPEDALFA + konta."""
    companies = client.get("/api/companies", headers=admin_headers).json()
    borealis = next(c["id"] for c in companies if c["code"] == "BOREALIS")
    cobalt = next(c["id"] for c in companies if c["code"] == "COBALT")
    spedalfa = forwarder(client, admin_headers, "SPEDALFA")
    kn = forwarder(client, admin_headers, "SPEDBETA")

    client.post("/api/users", headers=admin_headers, json={
        "login": "sped.spedalfa", "password": "haslo123", "role": "forwarder",
        "forwarder_id": spedalfa["id"]})
    client.post("/api/users", headers=admin_headers, json={
        "login": "log.borealis", "password": "haslo123", "role": "logistics",
        "company_id": borealis})

    container = client.post("/api/containers", headers=admin_headers, json={
        "container_no": VALID_NO, "company_id": borealis,
        "forwarder_id": spedalfa["id"]}).json()
    other = client.post("/api/containers", headers=admin_headers, json={
        "container_no": SECOND_NO, "company_id": cobalt,
        "forwarder_id": kn["id"]}).json()
    return {"borealis": borealis, "spedalfa": spedalfa, "kn": kn,
            "container": container, "other": other}


def test_forwarder_sees_only_assigned_containers(client, admin_headers):
    ctx = _setup(client, admin_headers)
    headers = login(client, "sped.spedalfa", "haslo123")
    visible = client.get("/api/containers", headers=headers).json()
    assert [c["id"] for c in visible] == [ctx["container"]["id"]]
    assert client.get(f"/api/containers/{ctx['other']['id']}",
                      headers=headers).status_code == 404
    # spedytor nie edytuje danych kontenera ani statusu głównego
    assert client.patch(f"/api/containers/{ctx['container']['id']}",
                        headers=headers, json={"notes": "x"}).status_code == 403
    assert client.post(f"/api/containers/{ctx['container']['id']}/status",
                       headers=headers, json={"status": "W_PORCIE"}).status_code == 403


def test_transport_order_full_flow(client, admin_headers):
    ctx = _setup(client, admin_headers)
    logistics = login(client, "log.borealis", "haslo123")
    forwarder = login(client, "sped.spedalfa", "haslo123")

    order = client.post("/api/transport-orders", headers=logistics, json={
        "container_id": ctx["container"]["id"],
        "pickup_location": "DCT Gdańsk", "delivery_location": "Magazyn Borealis",
        "pickup_date": "2026-07-06", "instructions": "awizacja 08:00"}).json()
    assert order["status"] == "WYSTAWIONE"
    assert order["forwarder_id"] == ctx["spedalfa"]["id"]  # domyślnie z kontenera

    def step(headers, order_id, new_status, reason="", expect=200):
        response = client.post(f"/api/transport-orders/{order_id}/status",
                               headers=headers, json={"status": new_status, "reason": reason})
        assert response.status_code == expect, response.text
        return response.json() if expect == 200 else None

    # logistyka nie może wykonać kroku spedytora i odwrotnie
    step(logistics, order["id"], "ZAAKCEPTOWANE", expect=422)   # za spedytora tylko z notatką (2026-09-28)
    updated = step(forwarder, order["id"], "ZAAKCEPTOWANE")
    assert updated["status"] == "ZAAKCEPTOWANE"
    step(forwarder, order["id"], "POTWIERDZONE", expect=403)
    step(forwarder, order["id"], "W_REALIZACJI")
    step(forwarder, order["id"], "WYKONANE")
    # przeskoczenie obiegu niedozwolone
    step(forwarder, order["id"], "ZAAKCEPTOWANE", expect=409)
    final = step(logistics, order["id"], "POTWIERDZONE")
    assert final["status"] == "POTWIERDZONE"

    # odrzucenie wymaga powodu
    second = client.post("/api/transport-orders", headers=logistics, json={
        "container_id": ctx["container"]["id"]}).json()
    step(forwarder, second["id"], "ODRZUCONE", expect=422)
    rejected = step(forwarder, second["id"], "ODRZUCONE", reason="brak wolnych aut")
    assert rejected["rejection_reason"] == "brak wolnych aut"

    # spedytor widzi tylko swoje zlecenia
    orders = client.get("/api/transport-orders", headers=forwarder).json()
    assert {o["forwarder_id"] for o in orders} == {ctx["spedalfa"]["id"]}


def test_forwarder_has_no_access_to_customs(client, admin_headers):
    # decyzja 2026-09-28: odprawa to wyłącznie agencja celna — spedytor nie zmienia i nie widzi
    ctx = _setup(client, admin_headers)
    cid = ctx["container"]["id"]
    client.patch(f"/api/containers/{cid}/customs", headers=admin_headers,
                 json={"customs_status": "ZLECONA", "customs_note": "tajna notatka celna"})
    forwarder = login(client, "sped.spedalfa", "haslo123")
    assert client.patch(f"/api/containers/{cid}/customs", headers=forwarder,
                        json={"customs_note": "x"}).status_code == 403
    assert client.get("/api/customs/docs-gaps", headers=forwarder).status_code == 403
    seen = client.get(f"/api/containers/{cid}", headers=forwarder).json()
    assert seen["customs_status"] == "BRAK" and seen["customs_note"] == ""


def test_customs_agency_text_field_rejected(client, admin_headers):
    # agencję przypisuje logistyka ze słownika — pole tekstowe odrzucane (422), 2026-09-28
    ctx = _setup(client, admin_headers)
    cid = ctx["container"]["id"]
    before = client.get(f"/api/containers/{cid}", headers=admin_headers).json()["customs_agency"]
    response = client.patch(f"/api/containers/{cid}/customs", headers=admin_headers,
                            json={"customs_agency": "Agencja z palca", "customs_status": "ZLECONA"})
    assert response.status_code == 422, response.text
    after = client.get(f"/api/containers/{cid}", headers=admin_headers).json()
    assert after["customs_agency"] == before and after["customs_status"] != "ZLECONA"


def test_messages_and_attachments(client, admin_headers, tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))

    ctx = _setup(client, admin_headers)
    logistics = login(client, "log.borealis", "haslo123")
    forwarder = login(client, "sped.spedalfa", "haslo123")
    cid = ctx["container"]["id"]

    client.post(f"/api/containers/{cid}/messages", headers=logistics,
                json={"body": "Kiedy odbiór z portu?"})
    client.post(f"/api/containers/{cid}/messages", headers=forwarder,
                json={"body": "Jutro rano, kierowca zamówiony."})
    thread = client.get(f"/api/containers/{cid}/messages", headers=logistics).json()
    assert [m["user_login"] for m in thread] == ["log.borealis", "sped.spedalfa"]

    upload = client.post(
        f"/api/containers/{cid}/attachments", headers=forwarder,
        files={"file": ("cmr_2680.pdf", io.BytesIO(pdf_bytes("cmr_2680.pdf")), "application/pdf")})
    assert upload.status_code == 201, upload.text
    attachments = client.get(f"/api/containers/{cid}/attachments", headers=logistics).json()
    assert attachments[0]["filename"] == "cmr_2680.pdf"
    download = client.get(f"/api/attachments/{attachments[0]['id']}/download",
                          headers=logistics)
    assert download.status_code == 200 and download.content == pdf_bytes("cmr_2680.pdf")

    # spedytor SPEDBETA (inny) nie ma dostępu do wątku ani plików tego kontenera
    client.post("/api/users", headers=admin_headers, json={
        "login": "sped.kn", "password": "haslo123", "role": "forwarder",
        "forwarder_id": ctx["kn"]["id"]})
    other_forwarder = login(client, "sped.kn", "haslo123")
    assert client.get(f"/api/containers/{cid}/messages",
                      headers=other_forwarder).status_code == 404
    assert client.get(f"/api/attachments/{attachments[0]['id']}/download",
                      headers=other_forwarder).status_code == 404


def test_container_no_regex_matches_iso6346():
    assert CONTAINER_NO_RE.search("CMR PRZESYLKI: MSDU0806613 zaladunek") \
        .group(0) == "MSDU0806613"
    assert CONTAINER_NO_RE.search("bez numeru kontenera tutaj") is None


def test_logistics_accepts_order_on_behalf_with_note(client, admin_headers):
    # decyzja 2026-09-28: logistyka może zaakceptować zlecenie za spedytora — tylko z notatką
    ctx = _setup(client, admin_headers)
    order = client.post("/api/transport-orders", headers=admin_headers,
                        json={"container_id": ctx["container"]["id"], "forwarder_id": ctx["spedalfa"]["id"]}).json()
    url = f"/api/transport-orders/{order['id']}/status"
    assert client.post(url, headers=admin_headers, json={"status": "ZAAKCEPTOWANE"}).status_code == 422
    ok = client.post(url, headers=admin_headers,
                     json={"status": "ZAAKCEPTOWANE", "reason": "potwierdził telefonicznie"})
    assert ok.status_code == 200 and ok.json()["status"] == "ZAAKCEPTOWANE"


def test_forwarder_sees_only_cmr_and_own_attachments(client, admin_headers, db_session):
    # decyzja 2026-09-28: spedytor nie widzi dokumentów odprawowych/handlowych — tylko CMR i własne
    from app.models import Attachment, DocumentType, User as U
    ctx = _setup(client, admin_headers)
    cid = ctx["container"]["id"]
    forwarder = login(client, "sped.spedalfa", "haslo123")
    fw_id = db_session.query(U).filter_by(login="sped.spedalfa").one().id
    cmr, sad = DocumentType(name="CMR"), DocumentType(name="SAD (zgłoszenie celne)")
    db_session.add_all([cmr, sad])
    db_session.flush()
    db_session.add_all([
        Attachment(container_id=cid, filename="sad.pdf", stored_name="t-sad", document_type_id=sad.id),
        Attachment(container_id=cid, filename="faktura.pdf", stored_name="t-inv"),
        Attachment(container_id=cid, filename="cmr.pdf", stored_name="t-cmr", document_type_id=cmr.id),
        Attachment(container_id=cid, filename="moje.pdf", stored_name="t-own", uploaded_by_id=fw_id),
    ])
    db_session.commit()
    seen = {a["filename"] for a in client.get(f"/api/containers/{cid}/attachments", headers=forwarder).json()}
    assert seen == {"cmr.pdf", "moje.pdf"}
    all_names = client.get(f"/api/containers/{cid}/attachments", headers=admin_headers).json()
    hidden_id = next(a["id"] for a in all_names if a["filename"] == "sad.pdf")
    assert client.get(f"/api/attachments/{hidden_id}/download", headers=forwarder).status_code == 404
    assert len(all_names) == 4
    # reguła siedzi w deps (get_scoped), nie tylko w endpoincie pobierania
    import pytest
    from fastapi import HTTPException

    from app.deps import get_scoped
    fw_user = db_session.get(U, fw_id)
    with pytest.raises(HTTPException) as err:
        get_scoped(db_session, Attachment, hidden_id, fw_user)
    assert err.value.status_code == 404
    own_id = next(a["id"] for a in all_names if a["filename"] == "moje.pdf")
    assert get_scoped(db_session, Attachment, own_id, fw_user).filename == "moje.pdf"


def test_messages_walled_between_customs_and_forwarder(client, admin_headers):
    """Jeden wątek, ale agencja celna i spedytor nie widzą swoich wiadomości nawzajem (odprawa:
    rewizja, dług celny ≠ sprawa spedytora; spedytor ≠ sprawa agencji) — także w powiadomieniach
    i wzmiankach. Wiadomości personelu wewnętrznego widzą wszyscy z dostępem do kontenera."""
    ctx = _setup(client, admin_headers)
    cid = ctx["container"]["id"]
    agency = client.post("/api/customs-agencies", headers=admin_headers, json={"name": "CELNA-W"}).json()
    assert client.post(f"/api/customs/containers/{cid}/assign", headers=admin_headers,
                       json={"customs_agency_id": agency["id"]}).status_code == 200
    client.post("/api/users", headers=admin_headers, json={
        "login": "celna.w", "password": "haslo123", "role": "customs", "customs_agency_id": agency["id"]})
    hdr = {"log": login(client, "log.borealis", "haslo123"), "sped": login(client, "sped.spedalfa", "haslo123"),
           "celna": login(client, "celna.w", "haslo123")}
    for who, text in (("celna", "Rewizja, dług celny 1200 zł"), ("sped", "Kierowca jutro @celna.w"),
                      ("log", "Info dla wszystkich")):
        assert client.post(f"/api/containers/{cid}/messages", headers=hdr[who],
                           json={"body": text}).status_code == 201

    def thread(who):
        return [m["user_login"] for m in client.get(f"/api/containers/{cid}/messages", headers=hdr[who]).json()]
    assert thread("log") == ["celna.w", "sped.spedalfa", "log.borealis"]
    assert thread("sped") == ["sped.spedalfa", "log.borealis"]
    assert thread("celna") == ["celna.w", "log.borealis"]

    def bodies(who):
        return " ".join(n["body"] or "" for n in client.get("/api/notifications", headers=hdr[who]).json())
    assert "dług celny" not in bodies("sped") and "Info dla wszystkich" in bodies("sped")
    assert "Kierowca" not in bodies("celna") and "Info dla wszystkich" in bodies("celna")
