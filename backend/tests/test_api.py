import datetime

from app.iso6346 import check_digit, validate
from app.models import today_pl
from tests.conftest import forwarder, login

VALID_NO = "MSDU0806613"  # prawdziwy numer z kolejki Borealis


def test_iso6346_validation():
    ok, _ = validate(VALID_NO)
    assert ok
    ok, message = validate("MSDU0806615")
    assert not ok and "cyfra kontrolna" in message.lower()
    ok, message = validate("ABC123")
    assert not ok and "format" in message.lower()
    assert check_digit("CSQU305438") == 3  # przykład wzorcowy z ISO 6346


def test_login_and_me(client, admin_headers):
    response = client.get("/api/auth/me", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "admin" and body["view_all_companies"]
    assert client.post("/api/auth/login",
                       data={"username": "admin", "password": "zle"}).status_code == 401


def test_refresh_token(client):
    tokens = client.post("/api/auth/login",
                         data={"username": "admin", "password": "admin123"}).json()
    response = client.post("/api/auth/refresh",
                           json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 200
    assert client.post("/api/auth/refresh",
                       json={"refresh_token": tokens["access_token"]}).status_code == 401


def _company_id(client, headers, code):
    companies = client.get("/api/companies", headers=headers).json()
    return next(c["id"] for c in companies if c["code"] == code)


def _make_user(client, headers, login_name, role, company_id, view_all=False,
               warehouse_id=None):
    response = client.post("/api/users", headers=headers, json={
        "login": login_name, "password": "haslo123", "role": role,
        "company_id": company_id, "view_all_companies": view_all,
        "warehouse_id": warehouse_id})
    assert response.status_code == 201, response.text
    return response.json()


def test_container_counts(client, admin_headers):
    """Liczniki per spółka na kartach zakładek — i że /counts nie trafia w /{id}."""
    borealis = _company_id(client, admin_headers, "BOREALIS")
    client.post("/api/containers", headers=admin_headers,
                json={"container_no": VALID_NO, "company_id": borealis})
    counts = client.get("/api/containers/counts", headers=admin_headers).json()
    assert counts["BOREALIS"] >= 1
    assert "ACME" in counts and counts["ACME"] == 0   # zawsze wszystkie spółki


def test_change_warehouse_by_name(client, admin_headers):
    """Menu kontekstowe kolejki: zmiana magazynu rozładunku po nazwie."""
    borealis = _company_id(client, admin_headers, "BOREALIS")
    container = client.post("/api/containers", headers=admin_headers, json={
        "container_no": "TGBU6784203", "company_id": borealis}).json()
    assert container["warehouse_name"] is None

    # nieistniejący magazyn tworzony w locie pod spółką kontenera
    response = client.post(f"/api/containers/{container['id']}/warehouse",
                           headers=admin_headers, json={"name": "ACME"})
    assert response.status_code == 200, response.text
    assert response.json()["warehouse_name"] == "ACME"

    # ponowne przypisanie do innej nazwy (dopasowanie bez względu na wielkość liter)
    again = client.post(f"/api/containers/{container['id']}/warehouse",
                        headers=admin_headers, json={"name": "borealis"})
    assert again.json()["warehouse_name"] == "borealis"

    # audyt odnotował zmianę pola „warehouse"
    history = client.get(f"/api/containers/{container['id']}/history",
                         headers=admin_headers).json()
    assert any(h["field"] == "warehouse" for h in history)


def test_container_crud_status_and_audit(client, admin_headers):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    response = client.post("/api/containers", headers=admin_headers, json={
        "container_no": VALID_NO, "company_id": borealis, "order_number": "2660",
        "eta": "2026-06-16", "notify_date": "2026-06-19", "transport_type": "kola"})
    assert response.status_code == 201, response.text
    container = response.json()
    assert container["order_number"] == "2660"

    # walidacja blokująca
    bad = client.post("/api/containers", headers=admin_headers,
                      json={"container_no": "MSDU0806615", "company_id": borealis})
    assert bad.status_code == 422

    # zmiana statusu z komentarzem + edycja pola z powodem
    cid = container["id"]
    response = client.post(f"/api/containers/{cid}/status", headers=admin_headers,
                           json={"status": "W_PORCIE", "note": "wyładunek DCT"})
    assert response.status_code == 200 and response.json()["status"] == "W_PORCIE"
    response = client.patch(f"/api/containers/{cid}", headers=admin_headers,
                            json={"notify_date": "2026-06-20",
                                  "change_note": "przeniesiony z 19.06"})
    assert response.status_code == 200

    history = client.get(f"/api/containers/{cid}/history", headers=admin_headers).json()
    fields = [h["field"] for h in history]
    assert "status" in fields and "notify_date" in fields
    move = next(h for h in history if h["field"] == "notify_date")
    assert move["old_value"] == "2026-06-19" and move["note"] == "przeniesiony z 19.06"


def test_company_separation(client, admin_headers):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    cobalt = _company_id(client, admin_headers, "COBALT")
    acme = _company_id(client, admin_headers, "ACME")
    _make_user(client, admin_headers, "log.borealis", "logistics", borealis)
    _make_user(client, admin_headers, "log.cobalt", "logistics", cobalt)
    _make_user(client, admin_headers, "log.acme", "logistics", acme, view_all=True)

    borealis_headers = login(client, "log.borealis", "haslo123")
    cobalt_headers = login(client, "log.cobalt", "haslo123")
    acme_headers = login(client, "log.acme", "haslo123")

    created = client.post("/api/containers", headers=borealis_headers,
                          json={"container_no": VALID_NO}).json()

    assert len(client.get("/api/containers", headers=borealis_headers).json()) == 1
    assert client.get("/api/containers", headers=cobalt_headers).json() == []
    assert len(client.get("/api/containers", headers=acme_headers).json()) == 1  # Acme widzi wszystko
    assert client.get(f"/api/containers/{created['id']}",
                      headers=cobalt_headers).status_code == 404
    # logistyka nie podszyje się pod inną spółkę
    assert client.post("/api/containers", headers=cobalt_headers,
                       json={"container_no": "CSQU3054383",
                             "company_id": borealis}).status_code == 403


def test_container_fk_cross_company_rejected(client, admin_headers):
    """Nie można doczepić do kontenera dostawcy/magazynu innej spółki (izolacja)."""
    borealis = _company_id(client, admin_headers, "BOREALIS")
    cobalt = _company_id(client, admin_headers, "COBALT")
    other_wh = client.post("/api/warehouses", headers=admin_headers, json={
        "name": "MagYellow", "company_id": cobalt, "country": "PL"}).json()
    other_sup = client.post("/api/suppliers", headers=admin_headers, json={
        "name": "DostawcaYellow", "company_id": cobalt}).json()
    # kontener Borealis z magazynem/dostawcą Cobalt → 404
    assert client.post("/api/containers", headers=admin_headers, json={
        "container_no": VALID_NO, "company_id": borealis,
        "warehouse_id": other_wh["id"]}).status_code == 404
    assert client.post("/api/containers", headers=admin_headers, json={
        "container_no": VALID_NO, "company_id": borealis,
        "supplier_id": other_sup["id"]}).status_code == 404
    # poprawny kontener Borealis, potem próba PATCH na cudzy magazyn → 404
    c = client.post("/api/containers", headers=admin_headers, json={
        "container_no": VALID_NO, "company_id": borealis}).json()
    assert client.patch(f"/api/containers/{c['id']}", headers=admin_headers,
                        json={"warehouse_id": other_wh["id"]}).status_code == 404


def test_warehouse_role_blocked_from_stats(client, admin_headers):
    """Konto magazynu nie ma dostępu do statystyk/analiz spółki."""
    borealis = _company_id(client, admin_headers, "BOREALIS")
    wh = client.post("/api/warehouses", headers=admin_headers, json={
        "name": "DLT", "company_id": borealis, "country": "PL"}).json()
    _make_user(client, admin_headers, "mag.lit2", "warehouse", borealis, warehouse_id=wh["id"])
    h = login(client, "mag.lit2", "haslo123")
    assert client.get("/api/stats/monthly", headers=h).status_code == 403
    assert client.get("/api/analysis/unloading", headers=h).status_code == 403
    assert client.get("/api/transport-orders", headers=h).json() == []


def test_warehouse_role_limited_to_unload_confirmation(client, admin_headers):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    wh = client.post("/api/warehouses", headers=admin_headers, json={
        "name": "Borealis", "company_id": borealis, "country": "PL"}).json()
    # konto magazynu musi mieć przypisany magazyn (fail-closed) i widzi tylko jego kontenery
    _make_user(client, admin_headers, "mag.borealis", "warehouse", borealis, warehouse_id=wh["id"])
    container = client.post("/api/containers", headers=admin_headers,
                            json={"container_no": VALID_NO, "company_id": borealis,
                                  "warehouse_id": wh["id"]}).json()
    warehouse_headers = login(client, "mag.borealis", "haslo123")
    cid = container["id"]
    assert client.post(f"/api/containers/{cid}/status", headers=warehouse_headers,
                       json={"status": "W_PORCIE"}).status_code == 403
    assert client.patch(f"/api/containers/{cid}", headers=warehouse_headers,
                        json={"notes": "x"}).status_code == 403
    response = client.post(f"/api/containers/{cid}/status", headers=warehouse_headers,
                           json={"status": "DOSTARCZONY", "note": "rozładowany"})
    assert response.status_code == 200 and response.json()["status"] == "DOSTARCZONY"


def test_warehouse_client_view_masks_commercial_fields(client, admin_headers):
    """Konto zewnętrznego magazynu (DLT): widzi dane operacyjne + szczegóły do rozładunku,
    ale NIE dane handlowe (dostawca, spedytor, zamówienia, notatki) ani zamówień."""
    borealis = _company_id(client, admin_headers, "BOREALIS")
    wh = client.post("/api/warehouses", headers=admin_headers, json={
        "name": "DLT", "company_id": borealis, "country": "PL"}).json()
    supplier = client.post("/api/suppliers", headers=admin_headers, json={
        "name": "Dostawca X", "company_id": borealis}).json()
    fwd = forwarder(client, admin_headers, "SPEDALFA")
    _make_user(client, admin_headers, "mag.dlt", "warehouse", borealis, warehouse_id=wh["id"])
    container = client.post("/api/containers", headers=admin_headers, json={
        "container_no": VALID_NO, "company_id": borealis, "warehouse_id": wh["id"],
        "supplier_id": supplier["id"], "forwarder_id": fwd["id"],
        "notes": "notatka wewnętrzna", "purchase_note": "info zakupowe",
        "materials_list": "Palety EUR x10, karton x40", "palletization_note": "Nie piętrować",
        "pallet_count": 12, "driver_id_no": "ABC12345",
        "proposed_delivery_date": "2026-07-20"}).json()
    assert container["supplier_name"] == "Dostawca X"  # admin widzi wszystko

    wh_headers = login(client, "mag.dlt", "haslo123")
    view = client.get(f"/api/containers/{container['id']}", headers=wh_headers).json()
    # operacyjne + szczegóły dla magazynu — widoczne
    assert view["container_no"] == container["container_no"]
    assert view["proposed_delivery_date"] == "2026-07-20"
    assert view["materials_list"].startswith("Palety")
    assert view["palletization_note"] == "Nie piętrować" and view["pallet_count"] == 12
    # handlowe/wewnętrzne + wrażliwe PII — zamaskowane
    assert view["supplier_id"] is None and view["supplier_name"] is None
    assert view["forwarder_id"] is None and view["forwarder_name"] is None
    assert view["notes"] == "" and view["purchase_note"] == "" and view["driver_id_no"] == ""
    # zamówienia, pulpit i linki SENT (dane handlowe) — poza zakresem magazynu;
    # pozycje REF magazyn czyta (C13) — test_ref_items_warehouse.py
    assert client.get("/api/orders", headers=wh_headers).status_code == 403
    assert client.get("/api/stats/dashboard", headers=wh_headers).status_code == 403
    assert client.get(f"/api/containers/{container['id']}/sent-links",
                      headers=wh_headers).status_code == 403
    # magazyn nie uczestniczy w wycenach — nie może pobrać zlecenia po id (wyciek cen/SCFI)
    assert client.get("/api/transport-jobs/1", headers=wh_headers).status_code == 404
    # ale reklamację na swój kontener zgłosić może
    r = client.post("/api/complaints", headers=wh_headers, json={
        "container_id": container["id"], "description": "uszkodzona plomba"})
    assert r.status_code == 201


def test_complaint_by_anyone_with_access(client, admin_headers):
    """Q67: reklamację może zgłosić każdy z dostępem do kontenera (tu: spedytor
    na własnym kontenerze); brak dostępu → 404."""
    borealis = _company_id(client, admin_headers, "BOREALIS")
    spedalfa = forwarder(client, admin_headers, "SPEDALFA")["id"]
    toll = forwarder(client, admin_headers, "Speddelta")["id"]
    client.post("/api/users", headers=admin_headers, json={
        "login": "sped.spedalfa", "password": "haslo123", "role": "forwarder",
        "forwarder_id": spedalfa, "email": "spedalfa@example.com"})
    client.post("/api/users", headers=admin_headers, json={
        "login": "sped.toll", "password": "haslo123", "role": "forwarder",
        "forwarder_id": toll, "email": "toll@example.com"})
    dsv_h = login(client, "sped.spedalfa", "haslo123")
    toll_h = login(client, "sped.toll", "haslo123")
    container = client.post("/api/containers", headers=admin_headers, json={
        "container_no": VALID_NO, "company_id": borealis, "forwarder_id": spedalfa}).json()

    # spedytor przypisany do kontenera może zgłosić reklamację
    r = client.post("/api/complaints", headers=dsv_h, json={
        "container_id": container["id"], "description": "uszkodzenie plomby",
        "report_to_warehouse": False})
    assert r.status_code == 201, r.text
    # spedytor bez dostępu do tego kontenera — nie
    assert client.post("/api/complaints", headers=toll_h, json={
        "container_id": container["id"], "description": "x"}).status_code == 404


def test_queue_limits_and_free_days(client, admin_headers):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    warehouse = client.post("/api/warehouses", headers=admin_headers, json={
        "name": "Borealis", "company_id": borealis, "country": "PL",
        "default_daily_limit": 1}).json()

    # potwierdzać można tylko naprzód, więc data musi być liczona od dziś, nie wpisana
    today = today_pl()
    monday = today + datetime.timedelta(days=(7 - today.weekday()) or 7)
    numbers = ["MSDU0806613", "CSQU3054383"]
    for number in numbers:
        created = client.post("/api/containers", headers=admin_headers, json={
            "container_no": number, "company_id": borealis,
            "warehouse_id": warehouse["id"], "notify_date": monday.isoformat()}).json()
        # limit dzienny liczy tylko daty uzgodnione ze spedycją (app/planning.py)
        client.post(f"/api/containers/{created['id']}/plan/confirm", headers=admin_headers,
                    json={"delivery_date": monday.isoformat()})

    queue = client.get(f"/api/queue?warehouse_id={warehouse['id']}"
                       f"&date_from={monday}&date_to={monday + datetime.timedelta(days=6)}",
                       headers=admin_headers).json()
    by_day = {d["day"]: d for d in queue}
    day = by_day[monday.isoformat()]
    assert day["used"] == 2 and day["limit"] == 1 and day["over_limit"]  # ostrzeżenie, nie blokada
    assert by_day[(monday + datetime.timedelta(days=5)).isoformat()]["is_free_day"]  # sobota

    # nadpisanie limitu na konkretny dzień
    response = client.put("/api/limits", headers=admin_headers, json={
        "warehouse_id": warehouse["id"], "day": monday.isoformat(), "limit": 10})
    assert response.status_code == 200
    queue = client.get(f"/api/queue?warehouse_id={warehouse['id']}"
                       f"&date_from={monday}&date_to={monday}",
                       headers=admin_headers).json()
    assert queue[0]["limit"] == 10 and not queue[0]["over_limit"]

    # pracująca sobota jako wyjątek kalendarza
    saturday = datetime.date(2026, 7, 11)
    client.put("/api/calendar", headers=admin_headers, json={
        "warehouse_id": warehouse["id"], "day": saturday.isoformat(),
        "is_working": True, "note": "sobota za 15.08"})
    queue = client.get(f"/api/queue?warehouse_id={warehouse['id']}"
                       f"&date_from={saturday}&date_to={saturday}",
                       headers=admin_headers).json()
    assert queue and not queue[0]["is_free_day"]


def test_delayed_flag(client, admin_headers):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    yesterday = (today_pl() - datetime.timedelta(days=1)).isoformat()
    tomorrow = (today_pl() + datetime.timedelta(days=1)).isoformat()
    late = client.post("/api/containers", headers=admin_headers, json={
        "container_no": VALID_NO, "company_id": borealis,
        "eta": yesterday, "status": "W_TRANSPORCIE"}).json()
    on_time = client.post("/api/containers", headers=admin_headers, json={
        "container_no": "CSQU3054383", "company_id": borealis,
        "eta": tomorrow, "status": "W_TRANSPORCIE"}).json()
    assert late["is_delayed"] and not on_time["is_delayed"]
    delayed_only = client.get("/api/containers?delayed=true", headers=admin_headers).json()
    assert [c["id"] for c in delayed_only] == [late["id"]]


def test_monthly_stats(client, admin_headers):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    client.post("/api/containers", headers=admin_headers, json={
        "container_no": VALID_NO, "company_id": borealis, "notify_date": "2026-06-19"})
    stats = client.get("/api/stats/monthly", headers=admin_headers).json()
    assert stats == [{"year": 2026, "month": 6, "company_id": borealis,
                      "company_name": "Borealis", "count": 1}]


def test_ui_prefs_roundtrip_and_limit(client, admin_headers):
    """Profil widoku per user: zapis/odczyt JSON i twardy limit rozmiaru."""
    assert client.get("/api/auth/me/prefs", headers=admin_headers).json() == {}
    prefs = {"queueViews": [{"name": "Moje", "search": "?statek=AURORA"}],
             "timporye_row_h": "sm"}
    r = client.put("/api/auth/me/prefs", headers=admin_headers, json=prefs)
    assert r.status_code == 200, r.text
    assert client.get("/api/auth/me/prefs", headers=admin_headers).json() == prefs
    too_big = {"x": "a" * 70_000}
    assert client.put("/api/auth/me/prefs", headers=admin_headers,
                      json=too_big).status_code == 413
