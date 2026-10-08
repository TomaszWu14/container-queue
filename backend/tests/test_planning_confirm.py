import datetime
"""Wysyłka planu do spedycji i potwierdzanie daty (portal + token)."""
from app.models import AvizoItem, AvizoRequest, Container, PlanningStatus
from app.routers.avizo import _hash_token
from tests.conftest import forwarder, login


# Daty z przykładów przesunięte o pełne tygodnie w przyszłość (≥ 4 tygodnie od dziś), żeby test
# nie przeterminował się — ten sam dzień tygodnia, więc limity dzienne magazynu działają tak samo.
_ANCHOR = datetime.date(2026, 10, 1)
_SHIFT = datetime.timedelta(weeks=max(0, -(-((datetime.date.today() - _ANCHOR).days + 28) // 7)))


def _d(iso: str) -> str:
    return (datetime.date.fromisoformat(iso) + _SHIFT).isoformat()


def _create(client, headers, container_no, **extra):
    companies = client.get("/api/companies", headers=headers).json()
    company_id = next(c["id"] for c in companies if c["code"] == "BOREALIS")
    payload = {"container_no": container_no, "company_id": company_id,
               "status": "ZAPOWIEDZIANY", **extra}
    response = client.post("/api/containers", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _forwarder_id(client, headers):
    forwarders = client.get("/api/forwarders", headers=headers).json()
    assert forwarders, "brak spedytorów w danych testowych"
    return forwarders[0]["id"]


def test_send_freezes_date_and_snapshots_eta(client, db_session):
    headers = login(client)
    created = _create(client, headers, "TIMU5000201", eta=_d("2026-10-01"),
                      forwarder_id=_forwarder_id(client, headers))
    response = client.post("/api/containers/plan/send",
                           json={"container_ids": [created["id"]]}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["sent"] == 1

    container = db_session.get(Container, created["id"])
    assert container.planning_status == PlanningStatus.WYSLANE
    assert container.planning_sent_at is not None
    assert container.planning_eta_at_send == container.eta


def test_send_reports_container_without_forwarder(client):
    headers = login(client)
    created = _create(client, headers, "TIMU5000217", eta=_d("2026-10-01"))
    response = client.post("/api/containers/plan/send",
                           json={"container_ids": [created["id"]]}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["sent"] == 0
    assert response.json()["no_forwarder"] == ["TIMU5000217"]


def test_confirm_sets_status_and_date(client, db_session):
    headers = login(client)
    created = _create(client, headers, "TIMU5000238", eta=_d("2026-10-01"),
                      forwarder_id=_forwarder_id(client, headers))
    client.post("/api/containers/plan/send",
                json={"container_ids": [created["id"]]}, headers=headers)
    response = client.post(f"/api/containers/{created['id']}/plan/confirm",
                           json={"delivery_date": _d("2026-10-07")}, headers=headers)
    assert response.status_code == 200, response.text

    container = db_session.get(Container, created["id"])
    assert container.planning_status == PlanningStatus.POTWIERDZONE
    assert container.notify_date.isoformat() == _d("2026-10-07")
    assert container.planning_confirmed_at is not None
    assert container.planning_confirmed_by_id is not None


def test_changing_date_of_confirmed_container_resets_to_proposal(client, db_session):
    headers = login(client)
    created = _create(client, headers, "TIMU5000243", eta=_d("2026-10-01"),
                      forwarder_id=_forwarder_id(client, headers))
    client.post("/api/containers/plan/send",
                json={"container_ids": [created["id"]]}, headers=headers)
    client.post(f"/api/containers/{created['id']}/plan/confirm",
                json={"delivery_date": _d("2026-10-07")}, headers=headers)

    response = client.patch(f"/api/containers/{created['id']}",
                            json={"notify_date": _d("2026-10-09")}, headers=headers)
    assert response.status_code == 200, response.text
    container = db_session.get(Container, created["id"])
    assert container.planning_status == PlanningStatus.PROPOZYCJA, \
        "data, ktorej spedycja nie widziala, nie moze uchodzic za uzgodniona"
    assert container.planning_confirmed_at is None
    assert container.planning_confirmed_by_id is None
    assert container.planning_sent_at is None, "nowa data wymaga nowej rundy wysylki"


def test_pending_lists_only_sent_containers(client):
    headers = login(client)
    sent = _create(client, headers, "TIMU5000259", eta=_d("2026-10-01"),
                   forwarder_id=_forwarder_id(client, headers))
    proposal = _create(client, headers, "TIMU5000264", eta=_d("2026-10-01"),
                       forwarder_id=_forwarder_id(client, headers))
    client.post("/api/containers/plan/send",
                json={"container_ids": [sent["id"]]}, headers=headers)

    response = client.get("/api/containers/plan/pending", headers=headers)
    assert response.status_code == 200, response.text
    ids = [c["id"] for c in response.json()]
    assert sent["id"] in ids
    assert proposal["id"] not in ids, "propozycja jeszcze nie czeka na spedycje"


def _forwarder_login(client, headers, name, login_name):
    """Konto spedytora przypisane do spedycji `name` (zwraca nagłówki + id spedycji)."""
    forwarder_id = forwarder(client, headers, name)["id"]
    client.post("/api/users", headers=headers, json={
        "login": login_name, "password": "haslo123", "role": "forwarder",
        "forwarder_id": forwarder_id, "email": f"{login_name}@example.com"})
    return login(client, login_name, "haslo123"), forwarder_id


def test_forwarder_cannot_confirm_foreign_container(client):
    """Spedytor przypisany do innej spedycji nie widzi cudzego kontenera."""
    headers = login(client)
    own_headers, spedalfa = _forwarder_login(client, headers, "SPEDALFA", "sped.spedalfa")
    other = forwarder(client, headers, "Speddelta")["id"]
    created = _create(client, headers, "TIMU5000304", eta=_d("2026-10-01"), forwarder_id=other)

    response = client.post(f"/api/containers/{created['id']}/plan/confirm",
                           json={"delivery_date": _d("2026-10-07")}, headers=own_headers)
    assert response.status_code in (403, 404), response.text

    own = _create(client, headers, "TIMU5000325", eta=_d("2026-10-01"), forwarder_id=spedalfa)
    assert client.post(f"/api/containers/{own['id']}/plan/confirm",
                       json={"delivery_date": _d("2026-10-07")},
                       headers=own_headers).status_code == 200


def test_avizo_form_confirms_delivery_date(client, db_session):
    """Termin z formularza tokenowego trafia do planu tą samą funkcją co portal —
    od awizacji dwuetapowej dopiero po zatwierdzeniu przez logistykę."""
    headers = login(client)
    forwarder_id = forwarder(client, headers, "SPEDALFA")["id"]
    created = _create(client, headers, "TIMU5000330", eta=_d("2026-10-01"),
                      forwarder_id=forwarder_id)
    raw_token = "beefcafe" * 6                     # surowy token, jak z linku e-mail
    db_session.add(AvizoRequest(
        token=_hash_token(raw_token), company_id=db_session.get(Container, created["id"]).company_id,
        forwarder_id=forwarder_id,
        items=[AvizoItem(container_id=created["id"])]))
    db_session.commit()
    token = raw_token

    form = client.get(f"/api/avizo/{token}")
    assert form.status_code == 200, form.text
    assert form.json()["items"][0]["planning_status"] == "PROPOZYCJA"

    response = client.post(f"/api/avizo/{token}", json={"items": [{
        "container_id": created["id"], "decision": "date_change",
        "proposed_date": _d("2026-10-09")}]})
    assert response.status_code == 200, response.text
    db_session.expire_all()
    assert db_session.get(Container, created["id"]).planning_status == PlanningStatus.PROPOZYCJA

    request_id = db_session.query(AvizoRequest).one().id
    assert client.post(f"/api/avizo-requests/{request_id}/approve",
                       headers=headers).status_code == 200
    db_session.expire_all()
    container = db_session.get(Container, created["id"])
    assert container.planning_status == PlanningStatus.POTWIERDZONE
    assert container.notify_date.isoformat() == _d("2026-10-09")
    assert container.planning_confirmed_by_id is not None, "zatwierdził zalogowany użytkownik"


def test_confirm_rejects_past_date(client):
    """Link tokenowy nie może przestawić dostawy wstecz."""
    headers = login(client)
    created = _create(client, headers, "TIMU5000346", eta=_d("2026-10-01"),
                      forwarder_id=_forwarder_id(client, headers))
    response = client.post(f"/api/containers/{created['id']}/plan/confirm",
                           json={"delivery_date": _d("2020-01-01")}, headers=headers)
    assert response.status_code == 422, response.text


def test_changing_date_of_sent_container_also_resets(client, db_session):
    """Spedycja ma starą datę w mailu — zmiana u nas unieważnia rundę uzgodnień."""
    headers = login(client)
    created = _create(client, headers, "TIMU5000351", eta=_d("2026-10-01"),
                      forwarder_id=_forwarder_id(client, headers))
    client.post("/api/containers/plan/send",
                json={"container_ids": [created["id"]]}, headers=headers)

    client.patch(f"/api/containers/{created['id']}",
                 json={"notify_date": _d("2026-10-09")}, headers=headers)
    container = db_session.get(Container, created["id"])
    assert container.planning_status == PlanningStatus.PROPOZYCJA
    assert container.planning_sent_at is None
    assert container.planning_eta_at_send is None


def test_reset_keeps_audit_trail_of_who_confirmed(client):
    """Po cofnięciu planu dalej wiadomo, kto uzgodnił poprzednią datę."""
    headers = login(client)
    created = _create(client, headers, "TIMU5000367", eta=_d("2026-10-01"),
                      forwarder_id=_forwarder_id(client, headers))
    client.post("/api/containers/plan/send",
                json={"container_ids": [created["id"]]}, headers=headers)
    client.post(f"/api/containers/{created['id']}/plan/confirm",
                json={"delivery_date": _d("2026-10-07")}, headers=headers)
    client.patch(f"/api/containers/{created['id']}",
                 json={"notify_date": _d("2026-10-09")}, headers=headers)

    history = client.get(f"/api/containers/{created['id']}/history", headers=headers).json()
    fields = [entry["field"] for entry in history]
    assert fields.count("planning_confirmed_by_id") == 2, "potwierdzenie i jego cofnięcie"


def test_confirm_over_daily_limit_passes_but_leaves_audit_trace(client):
    """D10: zapis ponad limit dzienny przechodzi (bez blokady), ale zostaje ślad kto."""
    headers = login(client)
    companies = client.get("/api/companies", headers=headers).json()
    borealis = next(c["id"] for c in companies if c["code"] == "BOREALIS")
    wh = client.post("/api/warehouses", headers=headers, json={
        "name": "Limit D10", "company_id": borealis, "country": "PL"}).json()
    client.put("/api/limits", headers=headers,
               json={"warehouse_id": wh["id"], "day": _d("2026-10-07"), "limit": 1})
    ids = []
    for no in ("TIMU5000407", "TIMU5000412"):
        created = _create(client, headers, no, eta=_d("2026-10-01"), warehouse_id=wh["id"],
                          forwarder_id=_forwarder_id(client, headers))
        response = client.post(f"/api/containers/{created['id']}/plan/confirm",
                               json={"delivery_date": _d("2026-10-07")}, headers=headers)
        assert response.status_code == 200, response.text
        ids.append(created["id"])

    def limit_entries(cid):
        history = client.get(f"/api/containers/{cid}/history", headers=headers).json()
        return [e for e in history if e["field"] == "daily_limit"]

    assert limit_entries(ids[0]) == [], "w limicie — bez wpisu"
    entry, = limit_entries(ids[1])
    assert "przekroczono limit dzienny" in entry["note"]
    assert (entry["old_value"], entry["new_value"]) == ("1", "2")


def test_patch_warehouse_into_full_day_leaves_audit_trace(client):
    """D10 (review): PATCH warehouse_id liczy limit NOWEGO magazynu, nie starego
    (relacja container.warehouse bywa załadowana ze starą wartością)."""
    headers = login(client)
    companies = client.get("/api/companies", headers=headers).json()
    borealis = next(c["id"] for c in companies if c["code"] == "BOREALIS")
    full, other = (client.post("/api/warehouses", headers=headers, json={
        "name": name, "company_id": borealis, "country": "PL"}).json()
        for name in ("Pelny D10", "Inny D10"))
    client.put("/api/limits", headers=headers,
               json={"warehouse_id": full["id"], "day": _d("2026-10-07"), "limit": 1})
    ids = []
    for no, wh in (("TIMU5000433", full), ("TIMU5000449", other)):
        created = _create(client, headers, no, eta=_d("2026-10-01"), warehouse_id=wh["id"],
                          forwarder_id=_forwarder_id(client, headers))
        response = client.post(f"/api/containers/{created['id']}/plan/confirm",
                               json={"delivery_date": _d("2026-10-07")}, headers=headers)
        assert response.status_code == 200, response.text
        ids.append(created["id"])

    def limit_entries():
        history = client.get(f"/api/containers/{ids[1]}/history", headers=headers).json()
        return [e for e in history if e["field"] == "daily_limit"]

    assert limit_entries() == []
    for _ in range(2):   # ponowny zapis tego samego magazynu nie dubluje wpisu
        response = client.patch(f"/api/containers/{ids[1]}", headers=headers,
                                json={"warehouse_id": full["id"]})
        assert response.status_code == 200, response.text
        entry, = limit_entries()
        assert (entry["old_value"], entry["new_value"]) == ("1", "2")
