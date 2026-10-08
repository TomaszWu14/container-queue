"""BIZ-008: korekty obiegu zlecenia transportowego przez logistykę/admina (zawsze z powodem):
ponowne wystawienie po odrzuceniu (ODRZUCONE → WYSTAWIONE) i cofnięcie „wykonane” klikniętego
przez spedytora pomyłkowo (WYKONANE → W_REALIZACJI). Spedytor tych kroków nie wykona."""
from sqlalchemy import select

from app.database import SessionLocal
from app.models import AuditLog
from tests.conftest import login
from tests.test_forwarding import _setup


def _order(client, headers, container_id):
    return client.post("/api/transport-orders", headers=headers,
                       json={"container_id": container_id}).json()


def _step(client, headers, order_id, status, reason=""):
    return client.post(f"/api/transport-orders/{order_id}/status", headers=headers,
                       json={"status": status, "reason": reason})


def test_logistics_reissues_rejected_order_with_reason(client, admin_headers):
    ctx = _setup(client, admin_headers)
    logistics = login(client, "log.borealis", "haslo123")
    forwarder = login(client, "sped.spedalfa", "haslo123")
    order = _order(client, logistics, ctx["container"]["id"])
    assert _step(client, forwarder, order["id"], "ODRZUCONE", "brak aut").status_code == 200

    assert _step(client, forwarder, order["id"], "WYSTAWIONE", "jednak").status_code != 200
    assert _step(client, logistics, order["id"], "WYSTAWIONE").status_code == 422   # bez powodu
    r = _step(client, logistics, order["id"], "WYSTAWIONE", "nowy termin odbioru")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "WYSTAWIONE" and r.json()["rejection_reason"] == ""
    # spedytor znów może przyjąć
    assert _step(client, forwarder, order["id"], "ZAAKCEPTOWANE").status_code == 200
    with SessionLocal() as db:
        notes = [a.note for a in db.scalars(select(AuditLog).where(
            AuditLog.entity_type == "transport_orders", AuditLog.entity_id == order["id"]))]
    assert "nowy termin odbioru" in notes


def test_logistics_reverts_done_by_mistake(client, admin_headers):
    ctx = _setup(client, admin_headers)
    logistics = login(client, "log.borealis", "haslo123")
    forwarder = login(client, "sped.spedalfa", "haslo123")
    order = _order(client, logistics, ctx["container"]["id"])
    for status in ("ZAAKCEPTOWANE", "WYKONANE"):
        assert _step(client, forwarder, order["id"], status).status_code == 200
    # spedytor sam nie cofa (jak dotąd: przejście niedozwolone)
    assert _step(client, forwarder, order["id"], "W_REALIZACJI", "pomyłka").status_code == 409
    assert _step(client, logistics, order["id"], "W_REALIZACJI").status_code == 422
    r = _step(client, logistics, order["id"], "W_REALIZACJI", "kliknięte przez pomyłkę")
    assert r.status_code == 200 and r.json()["status"] == "W_REALIZACJI"
    assert _step(client, forwarder, order["id"], "WYKONANE").status_code == 200


def test_other_backward_moves_still_blocked(client, admin_headers):
    ctx = _setup(client, admin_headers)
    logistics = login(client, "log.borealis", "haslo123")
    order = _order(client, logistics, ctx["container"]["id"])
    # WYSTAWIONE → WYSTAWIONE / W_REALIZACJI bez akceptacji — nie korekta, zwykły obieg
    assert _step(client, logistics, order["id"], "WYSTAWIONE", "x").status_code in (409, 422)
    assert _step(client, logistics, order["id"], "W_REALIZACJI", "x").status_code == 403
