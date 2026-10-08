def _company(client, headers, code="BOREALIS"):
    companies = client.get("/api/companies", headers=headers).json()
    return next(c["id"] for c in companies if c["code"] == code)


def test_order_progress(client, admin_headers):
    borealis = _company(client, admin_headers)
    numbers = ["MSDU0806613", "CSQU3054383", "TGBU6784203"]
    statuses = ["ZREALIZOWANY", "W_PORCIE", "W_TRANSPORCIE"]
    for number, status in zip(numbers, statuses):
        client.post("/api/containers", headers=admin_headers, json={
            "container_no": number, "company_id": borealis,
            "order_number": "2733", "status": status})

    orders = client.get("/api/orders", headers=admin_headers).json()
    assert len(orders) == 1
    order = orders[0]
    assert order["number"] == "2733"
    assert order["container_count"] == 3
    progress = order["progress"]
    assert progress == {"total": 3, "delivered": 1, "at_port_or_customs": 1,
                        "in_transit": 1, "delayed": 0, "percent": 33,
                        "derived_status": "W_TOKU"}

    detail = client.get(f"/api/orders/{order['id']}", headers=admin_headers).json()
    assert [c["container_no"] for c in detail["containers"]] \
        == sorted(numbers, key=lambda n: numbers.index(n))
    assert detail["company_name"] == "Borealis"

    # separacja: inna spółka nie widzi zamówienia
    client.post("/api/users", headers=admin_headers, json={
        "login": "log.cobalt", "password": "haslo123", "role": "logistics",
        "company_id": _company(client, admin_headers, "COBALT")})
    from tests.conftest import login
    cobalt = login(client, "log.cobalt", "haslo123")
    assert client.get("/api/orders", headers=cobalt).json() == []
    assert client.get(f"/api/orders/{order['id']}", headers=cobalt).status_code == 404


def test_order_derived_statuses(client, admin_headers):
    borealis = _company(client, admin_headers)
    # zamówienie bez kontenerów
    empty = client.post("/api/orders", headers=admin_headers,
                        json={"number": "3001", "company_id": borealis}).json()
    assert empty["progress"]["derived_status"] == "PUSTE"

    # wszystkie dostarczone → ZAKONCZONE
    client.post("/api/containers", headers=admin_headers, json={
        "container_no": "MSDU0806613", "company_id": borealis,
        "order_number": "3002", "status": "DOSTARCZONY"})
    orders = {o["number"]: o for o in
              client.get("/api/orders", headers=admin_headers).json()}
    assert orders["3002"]["progress"]["derived_status"] == "ZAKONCZONE"
    assert orders["3002"]["progress"]["percent"] == 100

    # wszystko w transporcie → NOWE
    client.post("/api/containers", headers=admin_headers, json={
        "container_no": "CSQU3054383", "company_id": borealis,
        "order_number": "3003", "status": "W_TRANSPORCIE"})
    orders = {o["number"]: o for o in
              client.get("/api/orders", headers=admin_headers).json()}
    assert orders["3003"]["progress"]["derived_status"] == "NOWE"


def test_order_progress_counts_only_visible_containers(client, admin_headers, db_session):
    """Logistyk z ograniczeniem magazynów widzi w szczegółach tylko swoje kontenery — postęp
    i liczba kontenerów też liczone z widocznych (bez zdradzania stanu cudzych dostaw)."""
    from app.models import Container, ContainerStatus, Order, Warehouse
    from tests.conftest import login
    borealis = _company(client, admin_headers)
    wh_a, wh_b = Warehouse(name="ORD-MAG-A", company_id=borealis), Warehouse(name="ORD-MAG-B", company_id=borealis)
    order = Order(number="4004", company_id=borealis)
    db_session.add_all([wh_a, wh_b, order])
    db_session.flush()
    db_session.add_all([
        Container(container_no="MSDU0806613", company_id=borealis, order_id=order.id,
                  warehouse_id=wh_a.id, status=ContainerStatus.W_TRANSPORCIE),
        Container(container_no="CSQU3054383", company_id=borealis, order_id=order.id,
                  warehouse_id=wh_b.id, status=ContainerStatus.ZREALIZOWANY),
    ])
    db_session.commit()
    uid = client.post("/api/users", headers=admin_headers, json={
        "login": "log.maga", "password": "haslo123", "role": "logistics",
        "company_id": borealis}).json()["id"]
    client.patch(f"/api/users/{uid}", headers=admin_headers, json={"allowed_warehouse_ids": [wh_a.id]})
    h = login(client, "log.maga", "haslo123")

    listed = next(o for o in client.get("/api/orders", headers=h).json() if o["number"] == "4004")
    detail = client.get(f"/api/orders/{order.id}", headers=h).json()
    for out in (listed, detail):
        assert out["container_count"] == 1
        assert out["progress"]["total"] == 1 and out["progress"]["delivered"] == 0
        assert out["progress"]["derived_status"] == "NOWE"
    assert [c["container_no"] for c in detail["containers"]] == ["MSDU0806613"]
