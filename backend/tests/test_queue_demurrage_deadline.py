"""Lista kolejki zwraca termin demurrage (ETA + dni wolne; brak ETA = brak terminu)."""
import datetime

from tests.test_api import VALID_NO, _company_id


def test_list_returns_demurrage_deadline(client, admin_headers):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    eta = datetime.date(2030, 1, 10)
    with_eta = client.post("/api/containers", headers=admin_headers, json={
        "container_no": VALID_NO, "company_id": borealis, "eta": eta.isoformat(),
        "demurrage_free_days": 7, "status": "W_TRANSPORCIE"}).json()
    no_eta = client.post("/api/containers", headers=admin_headers, json={
        "container_no": "CSQU3054383", "company_id": borealis}).json()
    rows = {c["id"]: c for c in client.get("/api/containers", headers=admin_headers).json()}
    assert rows[with_eta["id"]]["demurrage_deadline"] == "2030-01-17"
    assert rows[no_eta["id"]]["demurrage_deadline"] is None
