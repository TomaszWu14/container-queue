"""Status kontenera z odprawy (decyzja 2026-09-28): zlecona → ODPRAWA; odprawiony + awizacja → AWIZOWANY;
tylko do przodu."""
import datetime

from sqlalchemy import select

from app.models import Company, Container, ContainerStatus as S


def _c(db, status, notify=None):
    co = db.scalars(select(Company)).first()
    c = Container(company_id=co.id, container_no="MSKU4444440", status=status, notify_date=notify)
    db.add(c)
    db.commit()
    return c.id


def test_container_status_follows_customs(client, admin_headers, db_session):
    cid = _c(db_session, S.W_PORCIE, notify=datetime.date(2030, 5, 5))
    url = f"/api/containers/{cid}"
    assert client.patch(url, headers=admin_headers, json={"customs_status": "ZLECONA"}).json()["status"] == "ODPRAWA"
    assert client.patch(url, headers=admin_headers, json={"customs_status": "ODPRAWIONY"}).json()["status"] == "AWIZOWANY"


def test_never_moves_back(client, admin_headers, db_session):
    cid = _c(db_session, S.W_DOSTAWIE)
    r = client.patch(f"/api/containers/{cid}", headers=admin_headers, json={"customs_status": "ZLECONA"})
    assert r.json()["status"] == "W_DOSTAWIE"


def test_released_counts_as_cleared(client, admin_headers, db_session):
    """ZWOLNIONY (SAD-PW, 2026-10-01) = odprawa zakończona: kontener z awizacją → AWIZOWANY,
    cofnięcie do odprawy w toku wymaga notatki z powodem (jak z ODPRAWIONY)."""
    cid = _c(db_session, S.W_PORCIE, notify=datetime.date(2030, 5, 5))
    url = f"/api/containers/{cid}"
    r = client.patch(url, headers=admin_headers, json={"customs_status": "ZWOLNIONY"})
    assert r.status_code == 200 and r.json()["status"] == "AWIZOWANY"
    assert client.patch(url, headers=admin_headers, json={"customs_status": "ZLECONA"}).status_code == 422
    assert client.patch(url, headers=admin_headers,
                        json={"customs_status": "ODPRAWIONY"}).status_code == 200   # w obrębie zakończonych
