"""C13 (audyt UI 2026-09-27): magazyn czyta zawartość REF SWOJEGO kontenera — tylko odczyt."""
from app.models import OrderItem
from tests.conftest import login
from tests.test_api import VALID_NO, _company_id, _make_user


def test_warehouse_reads_items_of_own_container_only(client, admin_headers, db_session):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    own = client.post("/api/warehouses", headers=admin_headers, json={
        "name": "DLT", "company_id": borealis, "country": "PL"}).json()
    other = client.post("/api/warehouses", headers=admin_headers, json={
        "name": "Inny", "company_id": borealis, "country": "PL"}).json()
    cid = client.post("/api/containers", headers=admin_headers, json={
        "container_no": VALID_NO, "company_id": borealis, "warehouse_id": own["id"],
        "order_numbers": "4500000001"}).json()["id"]
    db_session.add(OrderItem(company_id=borealis, order_number="4500000001", position="10",
                             material="ABC1", description="Rurka", quantity="5", unit="PCS"))
    db_session.commit()
    _make_user(client, admin_headers, "mag.own", "warehouse", borealis, warehouse_id=own["id"])
    _make_user(client, admin_headers, "mag.other", "warehouse", borealis, warehouse_id=other["id"])

    own_h = login(client, "mag.own", "haslo123")
    r = client.get(f"/api/containers/{cid}/items", headers=own_h)
    assert r.status_code == 200 and [i["material"] for i in r.json()] == ["ABC1"]
    # tylko odczyt: linki SENT (zapis) nadal zabronione
    assert client.post(f"/api/containers/{cid}/sent-links", headers=own_h, json={
        "sent_number": "S1", "order_number": "4500000001"}).status_code == 403
    # kontener cudzego magazynu → 404 (check_container_access), nie wyciek
    other_h = login(client, "mag.other", "haslo123")
    assert client.get(f"/api/containers/{cid}/items", headers=other_h).status_code == 404
