"""Filtr dostawców jest zawężany do modułu/zakładki (Acme vs pozostałe spółki)."""
from tests.conftest import login


def _company_id(client, headers, code):
    companies = client.get("/api/companies", headers=headers).json()
    return next(c["id"] for c in companies if c["code"] == code)


def test_suppliers_scoped_by_module(client, admin_headers):
    acme = _company_id(client, admin_headers, "ACME")
    borealis = _company_id(client, admin_headers, "BOREALIS")

    acme_sup = client.post("/api/suppliers", headers=admin_headers,
                            json={"name": "Dostawca Acme", "company_id": acme}).json()
    borealis_sup = client.post("/api/suppliers", headers=admin_headers,
                             json={"name": "Dostawca Borealis", "company_id": borealis}).json()

    # pełny słownik (admin) zawiera obu dostawców
    all_ids = {s["id"] for s in client.get("/api/suppliers", headers=admin_headers).json()}
    assert {acme_sup["id"], borealis_sup["id"]} <= all_ids

    # zakładka Acme — tylko dostawcy Acme
    acme_ids = {s["id"] for s in client.get(
        "/api/suppliers?company_code=ACME", headers=admin_headers).json()}
    assert acme_sup["id"] in acme_ids
    assert borealis_sup["id"] not in acme_ids

    # pozostałe spółki — Acme wykluczony
    other_ids = {s["id"] for s in client.get(
        "/api/suppliers?exclude_company_code=ACME", headers=admin_headers).json()}
    assert borealis_sup["id"] in other_ids
    assert acme_sup["id"] not in other_ids


# --- czyszczenie duplikatów z importu: edycja, scalanie, usuwanie, dezaktywacja ---
#
# Import z Excela nawiózł duplikaty (SHANGHAI / Shanghai / shangai), do których podpięte
# są już kontenery. Te testy pilnują, że scalanie faktycznie przepina dane, a nie tylko
# kasuje wpis — i że nie da się przez nie przewiercić separacji spółek.

def _port(client, headers, name):
    """Get-or-create portu — część (Shanghai, Xiamen...) jest zasiana przy starcie."""
    response = client.post("/api/ports", headers=headers, json={"name": name})
    if response.status_code == 201:
        return response.json()
    return next(p for p in client.get("/api/ports?include_inactive=true", headers=headers).json()
                if p["name"] == name)


def _make_user(client, headers, login_name, role, company_id):
    response = client.post("/api/users", headers=headers, json={
        "login": login_name, "password": "haslo123", "role": role,
        "company_id": company_id, "view_all_companies": False, "warehouse_id": None})
    assert response.status_code == 201, response.text
    return response.json()


def test_merge_port_repins_containers_and_orders(client, admin_headers):
    """Scalenie duplikatu portu przepina kontenery I zamówienia, dopiero potem kasuje wpis."""
    borealis = _company_id(client, admin_headers, "BOREALIS")
    dirty = _port(client, admin_headers, "shangai")       # literówka z importu
    clean = _port(client, admin_headers, "Shanghai")

    container = client.post("/api/containers", headers=admin_headers, json={
        "container_no": "MEDU9573834", "company_id": borealis, "port_id": dirty["id"]}).json()
    # zamówienie z portem wyjścia zakłada się przez /zlecenia — OrderIn tego pola nie przyjmuje
    order = client.post("/api/zlecenia", headers=admin_headers, json={
        "number": "PO-1", "company_id": borealis, "departure_port_id": dirty["id"],
        "container_count": 1}).json()

    response = client.post(f"/api/ports/{dirty['id']}/merge", headers=admin_headers,
                           json={"target_id": clean["id"]})
    assert response.status_code == 200, response.text
    # 2 kontenery, bo /zlecenia zakłada własny kontener i sam przypina mu port wyjścia
    assert response.json()["repinned"] == {"containers": 2, "orders": 1}

    # dane wskazują na czysty port, duplikat zniknął
    assert client.get(f"/api/containers/{container['id']}",
                      headers=admin_headers).json()["port_id"] == clean["id"]
    assert client.get(f"/api/orders/{order['id']}",
                      headers=admin_headers).json()["departure_port_id"] == clean["id"]
    port_ids = {p["id"] for p in client.get(
        "/api/ports?include_inactive=true", headers=admin_headers).json()}
    assert dirty["id"] not in port_ids
    assert clean["id"] in port_ids


def test_merge_supplier_across_companies_is_blocked(client, admin_headers):
    """Scalanie w poprzek spółek przepięłoby kontenery jednej spółki na słownik drugiej."""
    borealis = _company_id(client, admin_headers, "BOREALIS")
    acme = _company_id(client, admin_headers, "ACME")
    sup_t = client.post("/api/suppliers", headers=admin_headers,
                        json={"name": "Fushide", "company_id": borealis}).json()
    sup_z = client.post("/api/suppliers", headers=admin_headers,
                        json={"name": "Fushide", "company_id": acme}).json()

    response = client.post(f"/api/suppliers/{sup_t['id']}/merge", headers=admin_headers,
                           json={"target_id": sup_z["id"]})
    assert response.status_code == 409, response.text

    # oba wpisy nadal istnieją — nic nie zostało przepięte ani skasowane
    ids = {s["id"] for s in client.get("/api/suppliers?include_inactive=true",
                                       headers=admin_headers).json()}
    assert {sup_t["id"], sup_z["id"]} <= ids


def test_merge_supplier_repins_material_maps_and_drops_colliding(client, admin_headers):
    """Scalanie dostawców przepina mapowania indeksów; kod obecny u celu wygrywa
    (unique company+supplier+code złamałoby się przy ślepym przepięciu)."""
    borealis = _company_id(client, admin_headers, "BOREALIS")
    src = client.post("/api/suppliers", headers=admin_headers,
                      json={"name": "Fushide stary", "company_id": borealis}).json()
    dst = client.post("/api/suppliers", headers=admin_headers,
                      json={"name": "Fushide", "company_id": borealis}).json()
    for supplier_id, code, ref in ((src["id"], "AA-1", "REF-STARY"),
                                   (src["id"], "BB-2", "REF-B"),
                                   (dst["id"], "AA-1", "REF-CEL")):
        assert client.post("/api/supplier-material-maps", headers=admin_headers,
                           json={"company_code": "BOREALIS", "supplier_id": supplier_id,
                                 "supplier_code": code, "ref_code": ref}).status_code == 201

    response = client.post(f"/api/suppliers/{src['id']}/merge", headers=admin_headers,
                           json={"target_id": dst["id"]})
    assert response.status_code == 200, response.text

    maps = client.get(f"/api/supplier-material-maps?supplier_id={dst['id']}",
                      headers=admin_headers).json()
    assert {(m["supplier_code"], m["ref_code"]) for m in maps} == {
        ("AA-1", "REF-CEL"), ("BB-2", "REF-B")}


def test_delete_blocked_when_in_use_allowed_when_free(client, admin_headers):
    """Usuwanie tylko dla nieużywanych wpisów — reszta przez scalanie/dezaktywację."""
    borealis = _company_id(client, admin_headers, "BOREALIS")
    used = _port(client, admin_headers, "NINGBO")
    free = _port(client, admin_headers, "Literówka")
    client.post("/api/containers", headers=admin_headers, json={
        "container_no": "MSBU5870407", "company_id": borealis, "port_id": used["id"]})

    blocked = client.delete(f"/api/ports/{used['id']}", headers=admin_headers)
    assert blocked.status_code == 409
    assert "scal" in blocked.json()["detail"]      # podpowiada właściwe narzędzie

    assert client.delete(f"/api/ports/{free['id']}", headers=admin_headers).status_code == 204


def test_deactivated_port_hidden_from_pickers_but_recoverable(client, admin_headers):
    """Dezaktywacja nie może być kasowaniem na zawsze — admin musi móc cofnąć."""
    port = _port(client, admin_headers, "ZHENJANG")
    client.patch(f"/api/ports/{port['id']}", headers=admin_headers,
                 json={"name": "ZHENJANG", "is_active": False})

    active = {p["id"] for p in client.get("/api/ports", headers=admin_headers).json()}
    assert port["id"] not in active                      # znika z list wyboru

    full = {p["id"] for p in client.get("/api/ports?include_inactive=true",
                                        headers=admin_headers).json()}
    assert port["id"] in full                            # ale admin go widzi

    client.patch(f"/api/ports/{port['id']}", headers=admin_headers,
                 json={"name": "Zhenjiang", "is_active": True})
    revived = {p["name"] for p in client.get("/api/ports", headers=admin_headers).json()}
    assert "Zhenjiang" in revived                        # i może przywrócić + poprawić nazwę


def test_merge_requires_admin(client, admin_headers):
    """Słowniki żyją w panelu administracji — logistyk nie zapisuje w nich nic."""
    borealis = _company_id(client, admin_headers, "BOREALIS")
    _make_user(client, admin_headers, "log.merge", "logistics", borealis)
    log_headers = login(client, "log.merge", "haslo123")

    a = _port(client, admin_headers, "XIAMEN")
    b = _port(client, admin_headers, "Xiamen")

    assert client.post(f"/api/ports/{a['id']}/merge", headers=log_headers,
                       json={"target_id": b["id"]}).status_code == 403
    assert client.delete(f"/api/ports/{a['id']}", headers=log_headers).status_code == 403
    # edycja nazwy też nie — panel słowników widzi tylko admin
    assert client.patch(f"/api/ports/{a['id']}", headers=log_headers,
                        json={"name": "Xiamen Port"}).status_code == 403


def test_merge_map_covers_all_foreign_keys(client):
    """Regression guard: nowa tabela wskazująca na słownik MUSI trafić do mapy scalania.

    Bez tego merge skasowałby wpis, zostawiając osierocone FK wskazujące w pustkę.
    """
    from app.models import Base
    from app.routers.dictionaries import CARRIERS, FORWARDERS, PORTS, SUPPLIERS

    for spec in (PORTS, SUPPLIERS, CARRIERS, FORWARDERS):
        table = spec.model.__tablename__
        # spec.owned = tabele-dzieci kasowane razem z wpisem (cascade), nie odwolania
        in_db = {(t.name, c.name)
                 for t in Base.metadata.sorted_tables if t.name not in spec.owned
                 for c in t.columns
                 for fk in c.foreign_keys if fk.column.table.name == table}
        in_map = {(model.__tablename__, column) for model, column in spec.refs}
        assert in_db == in_map, (
            f"mapa scalania dla '{table}' rozjechała się z modelem: "
            f"brakuje {in_db - in_map}, zbędne {in_map - in_db}")
