"""W11 — moduł reklamacji: auto-szkic z opóźnienia, terminy przedawnienia,
rejestr szkód (statystyki), koszty, pismo (print-view) i checklista przyjęcia."""
import datetime

from sqlalchemy import select

from app.models import Complaint, ComplaintStatus, Notification, to_pl_date, today_pl, utcnow


def _company_id(client, headers, code="BOREALIS"):
    return next(c["id"] for c in client.get("/api/companies", headers=headers).json()
                if c["code"] == code)


def _container(client, headers, no, company_id, **extra):
    resp = client.post("/api/containers", headers=headers,
                       json={"container_no": no, "company_id": company_id, **extra})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


def _scoped_user(client, admin_headers, login_name, company_id):
    r = client.post("/api/users", headers=admin_headers, json={
        "login": login_name, "password": "haslo123", "role": "logistics",
        "company_id": company_id, "view_all_companies": False})
    assert r.status_code == 201, r.text
    resp = client.post("/api/auth/login",
                       data={"username": login_name, "password": "haslo123"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# --- #67: auto-szkic reklamacji z opóźnienia ---

def test_auto_draft_created_once(client, admin_headers, db_session):
    from app.routers.complaints import check_complaint_auto_drafts
    company = _company_id(client, admin_headers)
    late_eta = (today_pl() - datetime.timedelta(days=10)).isoformat()
    cid = _container(client, admin_headers, "MSDU0806613", company, eta=late_eta)

    assert check_complaint_auto_drafts(db_session) == 1
    # drugi przebieg pętli nie tworzy duplikatu
    assert check_complaint_auto_drafts(db_session) == 0
    drafts = db_session.scalars(select(Complaint).where(
        Complaint.container_id == cid, Complaint.auto_draft)).all()
    assert len(drafts) == 1
    draft = drafts[0]
    assert draft.status == ComplaintStatus.SZKIC
    assert "10 dni po ETA" in draft.description
    assert "Oś czasu" in draft.description
    # dzwonek do logistyki
    assert db_session.scalar(select(Notification).where(
        Notification.kind == "complaint_draft",
        Notification.container_id == cid)) is not None
    # zamknięcie szkicu też nie odblokowuje duplikatu
    r = client.post(f"/api/complaints/{draft.id}/status", headers=admin_headers,
                    json={"status": "ZAMKNIETA"})
    assert r.status_code == 200, r.text
    assert check_complaint_auto_drafts(db_session) == 0


def test_auto_draft_skips_fresh_and_delivered(client, admin_headers, db_session):
    from app.routers.complaints import check_complaint_auto_drafts
    company = _company_id(client, admin_headers)
    fresh = (today_pl() - datetime.timedelta(days=2)).isoformat()
    _container(client, admin_headers, "MSKU0000006", company, eta=fresh)
    late = (today_pl() - datetime.timedelta(days=30)).isoformat()
    _container(client, admin_headers, "TRHU1306972", company, eta=late,
               atd=(today_pl() - datetime.timedelta(days=5)).isoformat())
    assert check_complaint_auto_drafts(db_session) == 0


# --- #69: typ adresata + termin przedawnienia ---

def _complaint(client, headers, cid, **extra):
    r = client.post("/api/complaints", headers=headers, json={
        "container_id": cid, "kind": "REKLAMACJA",
        "report_to_warehouse": False, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def test_recipient_type_and_deadline_fields(client, admin_headers):
    company = _company_id(client, admin_headers)
    cid = _container(client, admin_headers, "MSDU0806613", company)
    c = _complaint(client, admin_headers, cid)
    assert c["deadline_at"] is None
    r = client.patch(f"/api/complaints/{c['id']}", headers=admin_headers,
                     json={"recipient_type": "PRZEWOZNIK"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["recipient_type"] == "PRZEWOZNIK"
    # default 14 dni od utworzenia
    # termin liczony od daty utworzenia wg kalendarza PL (created_at jest w UTC)
    created = to_pl_date(datetime.datetime.fromisoformat(body["created_at"]).replace(tzinfo=None))
    assert body["deadline_at"] == (created + datetime.timedelta(days=14)).isoformat()
    assert body["deadline_days_left"] == 14
    # nieznany typ → 422
    r = client.patch(f"/api/complaints/{c['id']}", headers=admin_headers,
                     json={"recipient_type": "SASIAD"})
    assert r.status_code == 422


def test_deadline_alert_fires_once(client, admin_headers, db_session):
    from app.routers.complaints import check_complaint_reminders
    company = _company_id(client, admin_headers)
    cid = _container(client, admin_headers, "MSKU0000006", company)
    c = _complaint(client, admin_headers, cid)
    client.patch(f"/api/complaints/{c['id']}", headers=admin_headers,
                 json={"recipient_type": "PRZEWOZNIK"})
    # przesuwamy utworzenie: 12 dni temu → deadline za 2 dni (alert <= 3 dni)
    row = db_session.get(Complaint, c["id"])
    row.created_at = utcnow() - datetime.timedelta(days=12)
    db_session.commit()
    assert check_complaint_reminders(db_session) == 1
    assert check_complaint_reminders(db_session) == 0   # marker "P" — bez powtórki
    note = db_session.scalar(select(Notification).where(
        Notification.kind == "complaint_deadline"))
    assert note is not None and "przedawnienia" in note.title


def test_deadline_alert_not_early(client, admin_headers, db_session):
    from app.routers.complaints import check_complaint_reminders
    company = _company_id(client, admin_headers)
    cid = _container(client, admin_headers, "TRHU1306972", company)
    c = _complaint(client, admin_headers, cid)
    client.patch(f"/api/complaints/{c['id']}", headers=admin_headers,
                 json={"recipient_type": "UBEZPIECZYCIEL"})   # 60 dni — daleko
    assert check_complaint_reminders(db_session) == 0


# --- #68 + #71: rejestr szkód i koszty ---

def test_stats_per_supplier_and_carrier_with_costs(client, admin_headers):
    company = _company_id(client, admin_headers)
    sup = client.post("/api/suppliers", headers=admin_headers,
                      json={"name": "Chiński Dostawca", "company_id": company}).json()
    car = client.post("/api/carriers", headers=admin_headers,
                      json={"name": "Maersk"}).json()
    c1 = _container(client, admin_headers, "MSDU0806613", company,
                    supplier_id=sup["id"], carrier_id=car["id"])
    _container(client, admin_headers, "MSKU0000006", company,
               supplier_id=sup["id"], carrier_id=car["id"])
    complaint = _complaint(client, admin_headers, c1)
    r = client.patch(f"/api/complaints/{complaint['id']}", headers=admin_headers,
                     json={"claim_amount": 1000, "recovered_amount": 250,
                           "claim_currency": "usd"})
    assert r.status_code == 200
    assert r.json()["claim_currency"] == "USD"

    stats = client.get("/api/complaints/stats", headers=admin_headers).json()
    supplier_row = next(s for s in stats["suppliers"] if s["name"] == "Chiński Dostawca")
    assert supplier_row["containers"] == 2
    assert supplier_row["with_complaint"] == 1
    assert supplier_row["pct"] == 50.0
    carrier_row = next(s for s in stats["carriers"] if s["name"] == "Maersk")
    assert carrier_row["pct"] == 50.0
    cost = next(c for c in stats["costs"] if c["currency"] == "USD")
    assert cost["claim"] == 1000.0 and cost["recovered"] == 250.0
    assert cost["recovery_pct"] == 25.0


def test_stats_isolated_between_companies(client, admin_headers):
    a = _company_id(client, admin_headers, "BOREALIS")
    b = _company_id(client, admin_headers, "COBALT")
    cid = _container(client, admin_headers, "MSDU0806613", a)
    _complaint(client, admin_headers, cid)
    headers_b = _scoped_user(client, admin_headers, "intruz.w11", b)
    stats = client.get("/api/complaints/stats", headers=headers_b).json()
    assert stats["suppliers"] == [] and stats["carriers"] == []
    assert stats["costs"] == []


# --- #70: pismo (print-view zamiast PDF) ---

def test_letter_html_pl_en(client, admin_headers):
    company = _company_id(client, admin_headers)
    cid = _container(client, admin_headers, "MSDU0806613", company)
    c = _complaint(client, admin_headers, cid, description="Uszkodzone kartony")
    r = client.get(f"/api/complaints/{c['id']}/letter?lang=pl", headers=admin_headers)
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert c["number"] in r.text and "Reklamacja" in r.text
    r = client.get(f"/api/complaints/{c['id']}/letter?lang=en", headers=admin_headers)
    assert "Claim" in r.text and "Dear Sirs" in r.text


# --- #72: checklista kontroli przyjęcia ---

def test_checklist_dictionary_and_results(client, admin_headers):
    company = _company_id(client, admin_headers)
    cid = _container(client, admin_headers, "MSDU0806613", company)
    p1 = client.post("/api/checklist-points", headers=admin_headers,
                     json={"name": "Plomba nienaruszona"}).json()
    p2 = client.post("/api/checklist-points", headers=admin_headers,
                     json={"name": "Towar bez uszkodzeń"}).json()
    # duplikat nazwy → 409
    assert client.post("/api/checklist-points", headers=admin_headers,
                       json={"name": "Plomba nienaruszona"}).status_code == 409

    r = client.put(f"/api/containers/{cid}/checklist", headers=admin_headers, json={
        "items": [{"point_id": p1["id"], "result": "OK"},
                  {"point_id": p2["id"], "result": "NOK", "note": "wgniecione kartony"}]})
    assert r.status_code == 200, r.text
    by_point = {row["point_id"]: row for row in r.json()}
    assert by_point[p1["id"]]["result"] == "OK"
    assert by_point[p2["id"]]["result"] == "NOK"
    assert by_point[p2["id"]]["note"] == "wgniecione kartony"
    assert by_point[p2["id"]]["checked_by_login"] == "admin"
    # upsert nadpisuje istniejący wynik
    r = client.put(f"/api/containers/{cid}/checklist", headers=admin_headers, json={
        "items": [{"point_id": p2["id"], "result": "UWAGA", "note": "doszlifowano"}]})
    by_point = {row["point_id"]: row for row in r.json()}
    assert by_point[p2["id"]]["result"] == "UWAGA"
    assert by_point[p1["id"]]["result"] == "OK"   # nietknięty punkt zostaje
    # zły wynik → 422
    assert client.put(f"/api/containers/{cid}/checklist", headers=admin_headers, json={
        "items": [{"point_id": p1["id"], "result": "MOZE"}]}).status_code == 422


def test_checklist_isolated_between_companies(client, admin_headers):
    a = _company_id(client, admin_headers, "BOREALIS")
    b = _company_id(client, admin_headers, "COBALT")
    cid = _container(client, admin_headers, "MSDU0806613", a)
    point = client.post("/api/checklist-points", headers=admin_headers,
                        json={"name": "Plomba"}).json()
    client.put(f"/api/containers/{cid}/checklist", headers=admin_headers,
               json={"items": [{"point_id": point["id"], "result": "OK"}]})
    headers_b = _scoped_user(client, admin_headers, "intruz.czk", b)
    assert client.get(f"/api/containers/{cid}/checklist",
                      headers=headers_b).status_code in (403, 404)
    assert client.put(f"/api/containers/{cid}/checklist", headers=headers_b,
                      json={"items": [{"point_id": point["id"], "result": "NOK"}]}
                      ).status_code in (403, 404)
