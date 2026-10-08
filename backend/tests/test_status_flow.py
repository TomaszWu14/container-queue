"""D2: maszyna stanów statusu kontenera — w przód dowolnie, wstecz o 1 krok z notatką,
większe cofnięcie tylko admin."""
from .conftest import login
from .test_api import _company_id, _make_user


def test_status_transitions(client, admin_headers):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    _make_user(client, admin_headers, "log.flow", "logistics", borealis)
    log = login(client, "log.flow", "haslo123")
    cid = client.post("/api/containers", headers=log,
                      json={"container_no": "CSQU3054383", "company_id": borealis}).json()["id"]

    def move(headers, st, note=""):
        return client.post(f"/api/containers/{cid}/status", headers=headers,
                           json={"status": st, "note": note}).status_code

    assert move(log, "ODPRAWA") == 200                    # skok w przód — wolno
    assert move(log, "W_PORCIE") == 422                   # 1 krok wstecz bez notatki
    assert move(log, "W_PORCIE", "pomyłka") == 200        # 1 krok wstecz z notatką
    assert move(log, "ZREALIZOWANY") == 200
    assert move(log, "W_DOSTAWIE", "korekta") == 403      # 2 kroki wstecz — tylko admin
    assert move(admin_headers, "W_DOSTAWIE") == 422       # admin też podaje powód
    assert move(admin_headers, "ZAPOWIEDZIANY", "reset") == 200


def test_process_stages_2_3(client, admin_headers):
    """Etapy procesu (2026-09-24): W_PRODUKCJI i TRANSPORT_WSTEPNY leżą między
    ZAPOWIEDZIANY a W_TRANSPORCIE."""
    from app.models import ContainerStatus

    flow = list(ContainerStatus)
    assert flow[:4] == [ContainerStatus.ZAPOWIEDZIANY, ContainerStatus.W_PRODUKCJI,
                        ContainerStatus.TRANSPORT_WSTEPNY, ContainerStatus.W_TRANSPORCIE]
    borealis = _company_id(client, admin_headers, "BOREALIS")
    cid = client.post("/api/containers", headers=admin_headers,
                      json={"container_no": "MSDU0806613", "company_id": borealis}).json()["id"]
    for st in ("W_PRODUKCJI", "TRANSPORT_WSTEPNY"):
        r = client.post(f"/api/containers/{cid}/status", headers=admin_headers, json={"status": st})
        assert r.status_code == 200 and r.json()["status"] == st
