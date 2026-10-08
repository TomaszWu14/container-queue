"""Moduł agencji celnej: rejestr, zlecanie odprawy, wyznaczanie agenta, statusy, separacja."""
import datetime

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Container, CustomsAgency, Notification, User, pl_midnight_utc, today_pl, utcnow
from app.notifications import check_customs_alerts
from app.routers.imports import _match_customs_agency
from tests.conftest import login, pdf_bytes

VALID_NO = "MSDU0806613"
SECOND_NO = "CSQU3054383"


def _agency(client, headers, name):
    resp = client.post("/api/customs-agencies", headers=headers, json={"name": name})
    if resp.status_code == 201:
        return resp.json()
    return next(a for a in client.get("/api/customs-agencies", headers=headers).json()
                if a["name"] == name)


def _setup(client, admin_headers):
    companies = client.get("/api/companies", headers=admin_headers).json()
    borealis = next(c["id"] for c in companies if c["code"] == "BOREALIS")
    cobalt = next(c["id"] for c in companies if c["code"] == "COBALT")
    ag_a = _agency(client, admin_headers, "TEST-CELNA-A")
    ag_b = _agency(client, admin_headers, "TEST-CELNA-B")

    client.post("/api/users", headers=admin_headers, json={
        "login": "log.tim", "password": "haslo123", "role": "logistics",
        "company_id": borealis})
    client.post("/api/users", headers=admin_headers, json={
        "login": "celna.a", "password": "haslo123", "role": "customs",
        "customs_agency_id": ag_a["id"]})
    client.post("/api/users", headers=admin_headers, json={
        "login": "celna.b", "password": "haslo123", "role": "customs",
        "customs_agency_id": ag_b["id"]})

    container = client.post("/api/containers", headers=admin_headers, json={
        "container_no": VALID_NO, "company_id": borealis}).json()
    other = client.post("/api/containers", headers=admin_headers, json={
        "container_no": SECOND_NO, "company_id": cobalt}).json()
    return {"borealis": borealis, "ag_a": ag_a, "ag_b": ag_b,
            "container": container, "other": other}


def test_customs_role_requires_agency(client, admin_headers):
    resp = client.post("/api/users", headers=admin_headers, json={
        "login": "celna.orphan", "password": "haslo123", "role": "customs"})
    assert resp.status_code == 422


def test_full_customs_flow_and_separation(client, admin_headers):
    ctx = _setup(client, admin_headers)
    logistics = login(client, "log.tim", "haslo123")
    agency_a = login(client, "celna.a", "haslo123")
    agency_b = login(client, "celna.b", "haslo123")
    cid = ctx["container"]["id"]

    # 1. logistyka zleca odprawę agencji A
    assigned = client.post(f"/api/customs/containers/{cid}/assign", headers=logistics,
                           json={"customs_agency_id": ctx["ag_a"]["id"],
                                 "customs_note": "pilne"})
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["customs_agency_id"] == ctx["ag_a"]["id"]
    assert assigned.json()["customs_status"] == "ZLECONA"

    # dane handlowe / PII kierowcy są ukryte przed agencją (partner zewnętrzny)
    client.patch(f"/api/containers/{cid}", headers=admin_headers,
                 json={"notes": "TAJNE HANDLOWE", "driver_id_no": "ABC123"})

    # 2. agencja A widzi kontener na swojej tablicy, agencja B — nie
    board_a = client.get("/api/customs/board", headers=agency_a).json()
    assert cid in [c["id"] for c in board_a]
    row = next(c for c in board_a if c["id"] == cid)
    assert row["notes"] == "" and row["driver_id_no"] == ""
    assert row["company_name"] is not None  # dane potrzebne do odprawy zostają
    board_b = client.get("/api/customs/board", headers=agency_b).json()
    assert cid not in [c["id"] for c in board_b]

    # agencja B nie ma dostępu do kontenera ani do akcji na nim
    assert client.get(f"/api/containers/{cid}", headers=agency_b).status_code == 404
    assert client.post(f"/api/customs/containers/{cid}/agent", headers=agency_b,
                       json={"customs_agent_name": "Haker"}).status_code == 404

    # 3. agencja A wyznacza agenta
    agent = client.post(f"/api/customs/containers/{cid}/agent", headers=agency_a,
                        json={"customs_agent_name": "Jan Kowalski",
                              "customs_agent_phone": "600100200"})
    assert agent.status_code == 200, agent.text
    assert agent.json()["customs_agent_name"] == "Jan Kowalski"

    # 4. agencja A aktualizuje status odprawy
    done = client.post(f"/api/customs/containers/{cid}/status", headers=agency_a,
                       json={"customs_status": "ODPRAWIONY", "customs_note": "gotowe"})
    assert done.status_code == 200, done.text
    assert done.json()["customs_status"] == "ODPRAWIONY"

    # 5. agencja nie edytuje statusu głównego ani danych kontenera
    assert client.post(f"/api/containers/{cid}/status", headers=agency_a,
                       json={"status": "W_PORCIE"}).status_code == 403
    assert client.patch(f"/api/containers/{cid}", headers=agency_a,
                        json={"notes": "x"}).status_code == 403

    # 6. logistyka zmienia agencję na B — agent zostaje wyczyszczony, A traci dostęp
    reassigned = client.post(f"/api/customs/containers/{cid}/assign", headers=logistics,
                             json={"customs_agency_id": ctx["ag_b"]["id"]})
    assert reassigned.status_code == 200, reassigned.text
    assert reassigned.json()["customs_agency_id"] == ctx["ag_b"]["id"]
    assert reassigned.json()["customs_agent_name"] == ""
    assert client.get(f"/api/containers/{cid}", headers=agency_a).status_code == 404
    assert cid in [c["id"] for c in client.get("/api/customs/board", headers=agency_b).json()]


def test_customs_delay_alert_fires_once(client, admin_headers):
    """Odprawa ZLECONA dłużej niż próg → jeden alert 'customs-delay' na kontener/dzień."""
    ctx = _setup(client, admin_headers)
    logistics = login(client, "log.tim", "haslo123")
    cid = ctx["container"]["id"]
    client.post(f"/api/customs/containers/{cid}/assign", headers=logistics,
                json={"customs_agency_id": ctx["ag_a"]["id"]})

    # cofnij datę zlecenia o 5 dni, by przekroczyć domyślny próg (3 dni)
    with SessionLocal() as db:
        container = db.get(Container, cid)
        container.customs_assigned_at = utcnow() - datetime.timedelta(days=5)
        db.commit()

    assert check_customs_alerts(db=SessionLocal()) >= 1
    # drugi przebieg tego samego dnia nie dubluje alertu
    assert check_customs_alerts(db=SessionLocal()) == 0
    with SessionLocal() as db:
        alerts = db.scalars(select(Notification).where(
            Notification.kind == "customs-delay",
            Notification.container_id == cid)).all()
        assert len(alerts) >= 1


def test_customs_cannot_read_commercial_endpoints(client, admin_headers):
    """Agencja (partner zewnętrzny) nie może pobrać danych handlowych ani przez API,
    ani przez historię audytu — mimo dostępu do kontenera."""
    ctx = _setup(client, admin_headers)
    logistics = login(client, "log.tim", "haslo123")
    agency_a = login(client, "celna.a", "haslo123")
    cid = ctx["container"]["id"]
    client.post(f"/api/customs/containers/{cid}/assign", headers=logistics,
                json={"customs_agency_id": ctx["ag_a"]["id"]})
    # zmiany pól handlowych/PII w audycie
    client.patch(f"/api/containers/{cid}", headers=admin_headers,
                 json={"notes": "TAJNE", "driver_id_no": "XZY999", "purchase_note": "cena"})

    # pozycje zamówień i linki SENT — 403 (nie tylko ukryte w UI)
    assert client.get(f"/api/containers/{cid}/items", headers=agency_a).status_code == 403
    assert client.get(f"/api/containers/{cid}/sent-links", headers=agency_a).status_code == 403

    # historia audytu nie ujawnia zamaskowanych pól, ale pokazuje pola odprawy
    history = client.get(f"/api/containers/{cid}/history", headers=agency_a)
    assert history.status_code == 200
    fields = {e["field"] for e in history.json()}
    assert "notes" not in fields and "driver_id_no" not in fields and "purchase_note" not in fields
    # dla porównania: admin widzi te zmiany w historii
    admin_fields = {e["field"] for e in
                    client.get(f"/api/containers/{cid}/history", headers=admin_headers).json()}
    assert "notes" in admin_fields


def test_import_matches_agency_by_name(client, admin_headers):
    """Import dopasowuje nazwę agencji do rejestru (bez wielkości liter), pomija nieaktywne."""
    with SessionLocal() as db:
        db.add(CustomsAgency(name="AC Delta", is_active=True))
        db.add(CustomsAgency(name="AC Stara", is_active=False))
        db.commit()

        assert _match_customs_agency(db, "ac delta") is not None
        assert _match_customs_agency(db, "AC DELTA").name == "AC Delta"
        assert _match_customs_agency(db, "AC Stara") is None      # nieaktywna
        assert _match_customs_agency(db, "Nieznana") is None      # brak w rejestrze
        assert _match_customs_agency(db, "") is None


def test_case_status_dictionary_flow(client, admin_headers):
    """Słownik statusów sprawy (admin) + ustawienie statusu przez agencję + powiadomienie."""
    ctx = _setup(client, admin_headers)
    logistics = login(client, "log.tim", "haslo123")
    agency_a = login(client, "celna.a", "haslo123")
    cid = ctx["container"]["id"]

    # tylko admin definiuje słownik
    assert client.post("/api/customs/case-statuses", headers=logistics,
                       json={"name": "Zgłoszone"}).status_code == 403
    created = client.post("/api/customs/case-statuses", headers=admin_headers,
                          json={"name": "Zgłoszone", "sort_order": 10})
    assert created.status_code == 201, created.text
    sid = created.json()["id"]
    # duplikat nazwy → 409
    assert client.post("/api/customs/case-statuses", headers=admin_headers,
                       json={"name": "Zgłoszone"}).status_code == 409

    # bez przypisanej agencji nie ma sprawy
    assert client.post(f"/api/customs/containers/{cid}/case-status", headers=agency_a,
                       json={"customs_case_status_id": sid}).status_code == 404
    client.post(f"/api/customs/containers/{cid}/assign", headers=logistics,
                json={"customs_agency_id": ctx["ag_a"]["id"]})

    # agencja ustawia status ze słownika — widoczny w odpowiedzi po nazwie
    set_resp = client.post(f"/api/customs/containers/{cid}/case-status", headers=agency_a,
                           json={"customs_case_status_id": sid, "customs_note": "w toku"})
    assert set_resp.status_code == 200, set_resp.text
    assert set_resp.json()["customs_case_status_name"] == "Zgłoszone"

    # dezaktywowany status nie jest już do wyboru
    client.patch(f"/api/customs/case-statuses/{sid}", headers=admin_headers,
                 json={"name": "Zgłoszone", "sort_order": 10, "is_active": False})
    assert client.post(f"/api/customs/containers/{cid}/case-status", headers=agency_a,
                       json={"customs_case_status_id": sid}).status_code == 404

    # nasi (logistyka) dostali powiadomienie o zmianie statusu sprawy
    with SessionLocal() as db:
        titles = [n.title for n in db.scalars(select(Notification).where(
            Notification.container_id == cid, Notification.kind == "customs")).all()]
        assert any("Sprawa celna" in t for t in titles)


def test_send_docs_to_agency(client, admin_headers):
    """Wysyłka dokumentów: wymaga agencji i załączników; WYSLANE + powiadomienie agencji."""
    ctx = _setup(client, admin_headers)
    logistics = login(client, "log.tim", "haslo123")
    agency_a = login(client, "celna.a", "haslo123")
    cid = ctx["container"]["id"]
    client.post(f"/api/customs/containers/{cid}/assign", headers=logistics,
                json={"customs_agency_id": ctx["ag_a"]["id"]})

    # agencja nie wysyła sama do siebie; bez załączników → 409
    assert client.post(f"/api/customs/containers/{cid}/send-docs",
                       headers=agency_a).status_code == 403
    assert client.post(f"/api/customs/containers/{cid}/send-docs",
                       headers=logistics).status_code == 409

    upload = client.post(f"/api/containers/{cid}/attachments", headers=logistics,
                         files={"file": ("faktura.pdf", pdf_bytes("faktura.pdf"), "application/pdf")})
    assert upload.status_code in (200, 201), upload.text

    sent = client.post(f"/api/customs/containers/{cid}/send-docs", headers=logistics)
    assert sent.status_code == 200, sent.text
    assert sent.json()["document_status"] == "WYSLANE"

    with SessionLocal() as db:
        titles = [n.title for n in db.scalars(select(Notification).where(
            Notification.container_id == cid, Notification.kind == "customs")).all()]
        assert any("Dokumenty do odprawy" in t for t in titles)

    # agencja pobierze pliki przy kontenerze (dostęp przez scope)
    files = client.get(f"/api/containers/{cid}/attachments", headers=agency_a)
    assert files.status_code == 200
    assert [f["filename"] for f in files.json()] == ["faktura.pdf"]


def _upload(client, headers, cid, name="plik.pdf", type_id=None):
    data = {"document_type_id": str(type_id)} if type_id else {}
    return client.post(f"/api/containers/{cid}/attachments", headers=headers,
                       files={"file": (name, pdf_bytes(name), "application/pdf")}, data=data)


def test_document_checklist_flow(client, admin_headers):
    """Checklista typów: braki, otypowany plik zamyka brak, auto BRAK→ZALACZONE,
    wysyłka blokowana 409 bez force, force wysyła + audyt braków."""
    ctx = _setup(client, admin_headers)
    logistics = login(client, "log.tim", "haslo123")
    cid = ctx["container"]["id"]

    # słownik: tylko admin; wymagane typy
    assert client.post("/api/customs/document-types", headers=logistics,
                       json={"name": "Faktura"}).status_code == 403
    fak = client.post("/api/customs/document-types", headers=admin_headers,
                      json={"name": "Faktura", "is_required": True}).json()
    client.post("/api/customs/document-types", headers=admin_headers,
                json={"name": "Packing list", "is_required": True})
    client.post("/api/customs/document-types", headers=admin_headers,
                json={"name": "Inne", "is_required": False})

    # poza obiegiem celnym checklista nie liczy braków (board bez kontenera)
    client.post(f"/api/customs/containers/{cid}/assign", headers=logistics,
                json={"customs_agency_id": ctx["ag_a"]["id"]})
    board = client.get("/api/customs/board", headers=logistics).json()
    row = next(c for c in board if c["id"] == cid)
    assert row["missing_documents"] == ["Faktura", "Packing list"]

    # nieotypowany plik nie zamyka braków ani nie zmienia obiegu dokumentów
    assert _upload(client, logistics, cid, "luz.pdf").status_code == 201
    row = next(c for c in client.get("/api/customs/board", headers=logistics).json()
               if c["id"] == cid)
    assert row["missing_documents"] == ["Faktura", "Packing list"]
    assert row["document_status"] == "BRAK"

    # wysyłka z brakami → 409 z listą; force=True przechodzi, audyt z brakami
    resp = client.post(f"/api/customs/containers/{cid}/send-docs", headers=logistics,
                       json={})
    assert resp.status_code == 409 and "Faktura" in resp.json()["detail"]
    sent = client.post(f"/api/customs/containers/{cid}/send-docs", headers=logistics,
                       json={"force": True})
    assert sent.status_code == 200, sent.text
    assert sent.json()["document_status"] == "WYSLANE"
    history = client.get(f"/api/containers/{cid}/history", headers=admin_headers).json()
    assert any("MIMO braków" in (e.get("note") or "") for e in history)

    # otypowany plik zamyka brak (drugi kontener, świeży obieg)
    cid2 = ctx["other"]["id"]
    client.post(f"/api/customs/containers/{cid2}/assign", headers=admin_headers,
                json={"customs_agency_id": ctx["ag_a"]["id"]})
    assert _upload(client, admin_headers, cid2, "f.pdf", fak["id"]).status_code == 201
    row2 = next(c for c in client.get("/api/customs/board", headers=admin_headers).json()
                if c["id"] == cid2)
    assert row2["missing_documents"] == ["Packing list"]
    assert row2["document_status"] == "ZALACZONE"   # auto BRAK→ZALACZONE


def test_container_get_exposes_missing_documents(client, admin_headers):
    """GET /containers/{id} wystawia missing_documents (wspólne źródło z listą celną)
    — zasila wiedzę kontekstową (scope document_type) na karcie kontenera."""
    ctx = _setup(client, admin_headers)
    logistics = login(client, "log.tim", "haslo123")
    cid = ctx["container"]["id"]
    client.post("/api/customs/document-types", headers=admin_headers,
                json={"name": "Faktura", "is_required": True})
    # poza obiegiem celnym: brak listy
    r0 = client.get(f"/api/containers/{cid}", headers=logistics).json()
    assert r0["missing_documents"] == []
    # po przypisaniu agencji (obieg celny) → brakująca Faktura widoczna
    client.post(f"/api/customs/containers/{cid}/assign", headers=logistics,
                json={"customs_agency_id": ctx["ag_a"]["id"]})
    r1 = client.get(f"/api/containers/{cid}", headers=logistics).json()
    assert "Faktura" in r1["missing_documents"]


def test_docs_missing_alert(client, admin_headers):
    """Alert o brakach ≤ N dni przed ETA — raz dziennie, tylko obieg celny."""
    from app.notifications import check_docs_alerts
    ctx = _setup(client, admin_headers)
    logistics = login(client, "log.tim", "haslo123")
    cid = ctx["container"]["id"]
    client.post("/api/customs/document-types", headers=admin_headers,
                json={"name": "Faktura", "is_required": True})
    client.post(f"/api/customs/containers/{cid}/assign", headers=logistics,
                json={"customs_agency_id": ctx["ag_a"]["id"]})
    eta = (today_pl() + datetime.timedelta(days=3)).isoformat()
    client.patch(f"/api/containers/{cid}", headers=admin_headers, json={"eta": eta})

    assert check_docs_alerts(db=SessionLocal()) >= 1
    assert check_docs_alerts(db=SessionLocal()) == 0   # dedup dzienny
    with SessionLocal() as db:
        alerts = db.scalars(select(Notification).where(
            Notification.kind == "docs-missing",
            Notification.container_id == cid)).all()
        assert alerts and "Faktura" in alerts[0].title

    # kontener POZA obiegiem celnym (druga spółka, bez agencji) nie alarmuje
    other = ctx["other"]["id"]
    client.patch(f"/api/containers/{other}", headers=admin_headers, json={"eta": eta})
    with SessionLocal() as db:
        assert not db.scalars(select(Notification).where(
            Notification.kind == "docs-missing",
            Notification.container_id == other)).all()


def test_customs_board_agency_scope_only(client, admin_headers):
    """Agencja widzi wyłącznie kontenery jej zlecone (nie całą spółkę)."""
    ctx = _setup(client, admin_headers)
    logistics = login(client, "log.tim", "haslo123")
    agency_a = login(client, "celna.a", "haslo123")
    cid = ctx["container"]["id"]
    client.post(f"/api/customs/containers/{cid}/assign", headers=logistics,
                json={"customs_agency_id": ctx["ag_a"]["id"]})
    board = client.get("/api/customs/board", headers=agency_a).json()
    assert [c["id"] for c in board] == [cid]


def test_customs_status_rozliczony(client, admin_headers):
    from app.models import Container, Company, CustomsStatus
    from app.database import SessionLocal
    with SessionLocal() as db:
        co = db.query(Company).first()
        c = Container(container_no="RLZU0000001", company_id=co.id,
                      customs_status=CustomsStatus.ODPRAWIONY.value)
        db.add(c); db.commit(); cid = c.id
    r = client.post(f"/api/customs/containers/{cid}/status", headers=admin_headers,
                    json={"customs_status": "ROZLICZONY"})
    assert r.status_code == 200, r.text
    assert r.json()["customs_status"] == "ROZLICZONY"


def test_container_t1_flag(client, admin_headers):
    from app.models import Container, Company
    from app.database import SessionLocal
    with SessionLocal() as db:
        co = db.query(Company).first()
        c = Container(container_no="T1CU0000001", company_id=co.id)
        db.add(c); db.commit(); cid = c.id
    r = client.post(f"/api/customs/containers/{cid}/status", headers=admin_headers,
                    json={"customs_status": "ZLECONA", "customs_t1": True})
    assert r.status_code == 200, r.text
    assert r.json()["customs_t1"] is True


def test_pl_midnight_utc_for_given_day():
    # lato (CEST, UTC+2) i zima (CET, UTC+1): polska północ = 22:00 / 23:00 UTC dnia poprzedniego
    assert pl_midnight_utc(datetime.date(2026, 9, 28)) == datetime.datetime(2026, 9, 27, 22, 0)
    assert pl_midnight_utc(datetime.date(2026, 1, 15)) == datetime.datetime(2026, 1, 14, 23, 0)


def test_customs_alert_dedup_between_pl_and_utc_midnight(client, admin_headers):
    """Alert utworzony „dziś” między 00:00 a 02:00 PL (w UTC to jeszcze wczoraj) musi blokować
    drugi — wcześniej porównanie z północą UTC go nie widziało i alert się dublował."""
    ctx = _setup(client, admin_headers)
    logistics = login(client, "log.tim", "haslo123")
    cid = ctx["container"]["id"]
    client.post(f"/api/customs/containers/{cid}/assign", headers=logistics,
                json={"customs_agency_id": ctx["ag_a"]["id"]})
    day = today_pl()
    with SessionLocal() as db:
        db.get(Container, cid).customs_assigned_at = utcnow() - datetime.timedelta(days=5)
        user_id = db.scalar(select(User.id).where(User.login == "log.tim"))
        db.add(Notification(user_id=user_id, kind="customs-delay", title="x", container_id=cid,
                            created_at=pl_midnight_utc(day) + datetime.timedelta(minutes=30)))
        db.commit()
    assert check_customs_alerts(db=SessionLocal(), today=day) == 0


def test_cleared_customs_status_rules(client, admin_headers):
    """Decyzje 2026-09-28: ODPRAWIONY cofa tylko logistyka/admin i zawsze z notatką; agencja
    prowadzi status do przodu, ale nie cofa odprawionego."""
    ctx = _setup(client, admin_headers)
    logistics = login(client, "log.tim", "haslo123")
    agency = login(client, "celna.a", "haslo123")
    cid = ctx["container"]["id"]
    client.post(f"/api/customs/containers/{cid}/assign", headers=logistics,
                json={"customs_agency_id": ctx["ag_a"]["id"]})
    status_url = f"/api/customs/containers/{cid}/status"
    assert client.post(status_url, headers=agency,
                       json={"customs_status": "ODPRAWIONY"}).status_code == 200
    back = client.post(status_url, headers=agency, json={"customs_status": "REWIZJA",
                                                         "customs_note": "rewizja"})
    assert back.status_code == 403
    no_note = client.patch(f"/api/containers/{cid}", headers=logistics,
                           json={"customs_status": "BRAK"})
    assert no_note.status_code == 422 and "notatki" in no_note.json()["detail"]
    ok = client.patch(f"/api/containers/{cid}", headers=logistics,
                      json={"customs_status": "BRAK", "change_note": "pomyłka przy wpisie"})
    assert ok.status_code == 200 and ok.json()["customs_status"] == "BRAK"


def test_revision_requires_note_and_gets_date(client, admin_headers):
    """Spec §2: REWIZJA „z datą i notatką” — bez notatki 422 (każda ścieżka zapisu), data
    domyślnie dzień wpisu, gdy agencja jej nie poda."""
    ctx = _setup(client, admin_headers)
    logistics = login(client, "log.tim", "haslo123")
    agency = login(client, "celna.a", "haslo123")
    cid = ctx["container"]["id"]
    client.post(f"/api/customs/containers/{cid}/assign", headers=logistics,
                json={"customs_agency_id": ctx["ag_a"]["id"]})
    status_url = f"/api/customs/containers/{cid}/status"
    no_note = client.post(status_url, headers=agency, json={"customs_status": "REWIZJA"})
    assert no_note.status_code == 422 and "notatki" in no_note.json()["detail"]
    assert client.patch(f"/api/containers/{cid}", headers=logistics,
                        json={"customs_status": "REWIZJA"}).status_code == 422
    ok = client.post(status_url, headers=agency,
                     json={"customs_status": "REWIZJA", "customs_note": "kontrola fizyczna"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["customs_status"] == "REWIZJA"
    assert ok.json()["customs_date"] == today_pl().isoformat()
    assert ok.json()["customs_note"] == "kontrola fizyczna"


def test_send_docs_is_honest_about_recipients(client, admin_headers):
    """Audyt 2026-10-06 #10/#18: „Wyślij dokumenty do agencji” to powiadomienie w aplikacji —
    podgląd mówi komu i jakie pliki; agencja bez kont = 409 zamiast fałszywego „wysłano”."""
    ctx = _setup(client, admin_headers)
    logistics = login(client, "log.tim", "haslo123")
    cid = ctx["container"]["id"]
    bez_kont = _agency(client, admin_headers, "TEST-CELNA-BEZ-KONT")
    client.post(f"/api/customs/containers/{cid}/assign", headers=logistics,
                json={"customs_agency_id": bez_kont["id"]})
    assert _upload(client, logistics, cid, "faktura.pdf").status_code == 201

    prev = client.get(f"/api/customs/containers/{cid}/send-docs/preview", headers=logistics).json()
    assert prev["agency"] == "TEST-CELNA-BEZ-KONT" and prev["recipients"] == []
    assert prev["files"] == [{"name": "faktura.pdf", "type": None}]
    sent = client.post(f"/api/customs/containers/{cid}/send-docs", headers=logistics, json={"force": True})
    assert sent.status_code == 409 and "nie ma kont" in sent.json()["detail"]
    assert client.get(f"/api/containers/{cid}", headers=logistics).json()["document_status"] != "WYSLANE"

    client.post(f"/api/customs/containers/{cid}/assign", headers=logistics,
                json={"customs_agency_id": ctx["ag_a"]["id"]})
    prev = client.get(f"/api/customs/containers/{cid}/send-docs/preview", headers=logistics).json()
    assert len(prev["recipients"]) == 1
