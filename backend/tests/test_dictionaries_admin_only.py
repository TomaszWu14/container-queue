"""Zapis słowników jest zarezerwowany dla admina — także wtedy, gdy ktoś ominie UI.

Panel administracji front pokazuje wyłącznie adminowi (routing.tsx, canAccess), ale endpointy
stały pod Editors (admin + logistyka). Logistyk bez żadnego ekranu mógł samym API przemianować
albo dezaktywować port czy dostawcę. Ten test pilnuje, żeby reguła serwerowa nie rozjechała się
z tym, co obiecuje interfejs.
"""
import pytest

from tests.conftest import login


@pytest.fixture()
def logistics_headers(client, admin_headers):
    response = client.post("/api/users", headers=admin_headers, json={
        "login": "log.slowniki", "password": "haslo123", "role": "logistics",
        "company_id": None, "view_all_companies": True, "warehouse_id": None})
    assert response.status_code == 201, response.text
    return login(client, "log.slowniki", "haslo123")


# (ścieżka, body) — po jednym zapisie na każdy słownik pod panelem admina
DICT_WRITES = [
    ("/api/suppliers", {"name": "Dostawca z API"}),
    ("/api/forwarders", {"name": "Spedytor z API"}),
    ("/api/ports", {"name": "Port z API"}),
    ("/api/carriers", {"name": "Armator z API"}),
    ("/api/container-types", {"name": "40HQ-API"}),
]


@pytest.mark.parametrize("path,body", DICT_WRITES)
def test_logistics_cannot_write_dictionaries(client, logistics_headers, path, body):
    assert client.post(path, headers=logistics_headers, json=body).status_code == 403


def test_logistics_still_reads_dictionaries(client, logistics_headers):
    """Odczyt zostaje — słowniki zasilają listy wyboru w całej aplikacji."""
    for path, _ in DICT_WRITES:
        assert client.get(path, headers=logistics_headers).status_code == 200


def test_logistics_cannot_patch_existing_port(client, admin_headers, logistics_headers):
    port = client.post("/api/ports", headers=admin_headers, json={"name": "Port Testowy"})
    assert port.status_code == 201, port.text
    port_id = port.json()["id"]

    blocked = client.patch(f"/api/ports/{port_id}", headers=logistics_headers,
                           json={"name": "Przejęty", "is_active": False})
    assert blocked.status_code == 403

    after = client.get("/api/ports?include_inactive=true", headers=admin_headers).json()
    entry = next(p for p in after if p["id"] == port_id)
    assert entry["name"] == "Port Testowy" and entry["is_active"] is True


def test_logistics_can_still_add_supplier_contact(client, admin_headers, logistics_headers):
    """Wyjątek od reguły: kontakt u dostawcy dodaje się z ekranu zamówień, nie z panelu."""
    companies = client.get("/api/companies", headers=admin_headers).json()
    supplier = client.post("/api/suppliers", headers=admin_headers, json={
        "name": "Dostawca Kontaktowy", "company_id": companies[0]["id"]})
    assert supplier.status_code == 201, supplier.text

    created = client.post("/api/supplier-contacts", headers=logistics_headers, json={
        "supplier_id": supplier.json()["id"], "full_name": "Li Wei", "email": "li@example.com"})
    assert created.status_code == 201, created.text


# --- ślad w audycie dla słowników, które dotąd zapisywały się po cichu ------------
#
# record_changes wołały tylko dostawca, port, armator, spółka i agencja celna. Spedytor,
# magazyn, typy problemów, typy dokumentów i statusy spraw robiły setattr w pętli, więc
# dezaktywacja typu dokumentu czy zmiana limitu magazynu znikały bez historii.

def _audit_entries(db_session, entity_type: str, entity_id: int, field: str):
    from sqlalchemy import select

    from app.models import AuditLog
    return db_session.scalars(select(AuditLog).where(
        AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id,
        AuditLog.field == field)).all()


def test_document_type_deactivation_is_audited(client, admin_headers, db_session):
    created = client.post("/api/customs/document-types", headers=admin_headers,
                          json={"name": "Świadectwo audytowe"})
    assert created.status_code == 201, created.text
    type_id = created.json()["id"]

    patched = client.patch(f"/api/customs/document-types/{type_id}", headers=admin_headers,
                           json={"name": "Świadectwo audytowe", "is_active": False})
    assert patched.status_code == 200, patched.text
    assert patched.json()["is_active"] is False   # zapis nadal działa, nie tylko się loguje

    entries = _audit_entries(db_session, "document_types", type_id, "is_active")
    assert len(entries) == 1
    assert entries[0].old_value == "True" and entries[0].new_value == "False"


def test_warehouse_limit_change_is_audited(client, admin_headers, db_session):
    companies = client.get("/api/companies", headers=admin_headers).json()
    created = client.post("/api/warehouses", headers=admin_headers, json={
        "name": "Magazyn Audytowy", "country": "PL", "default_daily_limit": 5,
        "company_id": companies[0]["id"]})
    assert created.status_code == 201, created.text
    warehouse_id = created.json()["id"]

    patched = client.patch(f"/api/warehouses/{warehouse_id}", headers=admin_headers, json={
        "name": "Magazyn Audytowy", "country": "PL", "default_daily_limit": 9,
        "company_id": companies[0]["id"]})
    assert patched.status_code == 200, patched.text
    assert patched.json()["default_daily_limit"] == 9

    entries = _audit_entries(db_session, "warehouses", warehouse_id, "default_daily_limit")
    assert len(entries) == 1
    assert entries[0].old_value == "5" and entries[0].new_value == "9"


def test_warehouse_patch_cannot_move_between_companies(client, admin_headers, db_session):
    """company_id celowo poza zasięgiem PATCH-a — inaczej magazyn przeszedłby do innej spółki."""
    companies = client.get("/api/companies", headers=admin_headers).json()
    assert len(companies) >= 2, "test wymaga dwóch spółek z bootstrapu"
    home, other = companies[0]["id"], companies[1]["id"]

    created = client.post("/api/warehouses", headers=admin_headers, json={
        "name": "Magazyn Nieprzenośny", "country": "PL",
        "default_daily_limit": 5, "company_id": home})
    assert created.status_code == 201, created.text
    warehouse_id = created.json()["id"]

    client.patch(f"/api/warehouses/{warehouse_id}", headers=admin_headers, json={
        "name": "Magazyn Nieprzenośny", "country": "PL",
        "default_daily_limit": 5, "company_id": other})

    after = client.get("/api/warehouses", headers=admin_headers).json()
    entry = next(w for w in after if w["id"] == warehouse_id)
    assert entry["company_id"] == home
