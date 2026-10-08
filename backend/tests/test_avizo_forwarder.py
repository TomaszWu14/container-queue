"""Awizacja w aplikacji (decyzja 2026-10-07: nic bez logowania, przewoźnik = rola forwarder):
spedytor z kontem widzi tylko swoje awizacje, potwierdza etap 1 i podaje kierowców w etapie 2;
odpowiedź w aplikacji unieważnia link z maila; audyt z kontem użytkownika."""
from app.database import SessionLocal
from app.models import AuditLog, Container, Forwarder, Role, User
from app.security import hash_password
from tests.conftest import login
from tests.test_avizo_public import make_request, outbox, stage1  # noqa: F401 — fixture


def _forwarder_user(login_name: str, forwarder_name: str) -> None:
    with SessionLocal() as db:
        fw = db.query(Forwarder).filter_by(name=forwarder_name).one_or_none()
        if fw is None:
            fw = Forwarder(name=forwarder_name)
            db.add(fw)
            db.flush()
        db.add(User(login=login_name, hashed_password=hash_password("pass12345"),
                    role=Role.forwarder, forwarder_id=fw.id))
        db.commit()


def test_forwarder_answers_avizo_in_app(client, outbox, admin_headers):  # noqa: F811
    req_id, raw, ids = make_request()
    _forwarder_user("fw-spedalfa", "SPEDALFA")
    _forwarder_user("fw-inny", "Inny Spedytor")
    other = login(client, "fw-inny", "pass12345")
    assert client.get("/api/avizo-forwarder", headers=other).json() == []
    assert client.post(f"/api/avizo-forwarder/{req_id}/confirm", headers=other,
                       json=stage1(ids)).status_code == 404               # cudza awizacja

    spedalfa = login(client, "fw-spedalfa", "pass12345")
    mine = client.get("/api/avizo-forwarder", headers=spedalfa).json()
    assert [(r["id"], r["stage"]) for r in mine] == [(req_id, 1)]
    assert client.get(f"/api/avizo-forwarder/{req_id}", headers=spedalfa).json()["stage"] == 1
    assert {i["container_id"] for i in mine[0]["items"]} == set(ids)
    assert client.post(f"/api/avizo-forwarder/{req_id}/drivers", headers=spedalfa, json={"items": [
        {"container_id": ids[0], "driver_name": "Jan", "driver_phone": "600100200",
         "truck_no": "WGM1234A"}]}).status_code == 409                   # najpierw etap 1

    ok = client.post(f"/api/avizo-forwarder/{req_id}/confirm", headers=spedalfa, json=stage1(ids))
    assert ok.status_code == 200, ok.text
    assert client.get(f"/api/avizo/{raw}").status_code == 410            # link z maila nieważny
    assert client.post(f"/api/avizo-forwarder/{req_id}/confirm", headers=spedalfa,
                       json=stage1(ids)).status_code == 409               # raz
    assert client.get(f"/api/avizo-forwarder/{req_id}", headers=spedalfa).status_code == 409

    assert client.post(f"/api/avizo-requests/{req_id}/approve", headers=admin_headers,
                       json={}).status_code == 200
    spedalfa = login(client, "fw-spedalfa", "pass12345")
    assert client.get("/api/avizo-forwarder", headers=spedalfa).json()[0]["stage"] == 2
    drivers = client.post(f"/api/avizo-forwarder/{req_id}/drivers", headers=spedalfa, json={"items": [
        {"container_id": i, "driver_name": "Jan Kowalski", "driver_phone": "600100200",
         "truck_no": "WGM1234A"} for i in ids]})
    assert drivers.status_code == 200, drivers.text
    with SessionLocal() as db:
        assert db.get(Container, ids[0]).driver_name == "Jan Kowalski"
        fw_user = db.query(User).filter_by(login="fw-spedalfa").one()
        assert db.query(AuditLog).filter_by(entity_type="avizo_requests", entity_id=req_id,
                                            user_id=fw_user.id).count() >= 2
