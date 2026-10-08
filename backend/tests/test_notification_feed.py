"""Aktualności na Pulpicie (spec 2026-10-01-aktualnosci-pulpit): feed z kategorią, ważnością,
wątkiem i kontenerami z treści; filtry, „załaduj starsze”, przypięte pilne, wątek statku,
oznacz jako nieprzeczytaną."""
from sqlalchemy import select

from app import notification_feed as feed
from app.models import Company, Container, Notification, User


def _me(db):
    return db.scalars(select(User).where(User.login == "admin")).one()


def _seed(db):
    me = _me(db)
    co = db.scalars(select(Company)).first()
    c = Container(company_id=co.id, container_no="MSDU0806613")
    db.add(c)
    db.flush()
    rows = [
        Notification(user_id=me.id, kind="vessel_port", title="Statek MV DEMO HELIOS w rejonie portu ROTTERDAM — "
                     "kontenery: MSDU0806613, TGBU8339125. Sprawdź statusy."),
        Notification(user_id=me.id, kind="vessel_port", title="Statek MV DEMO HELIOS w porcie docelowym ROTTERDAM",
                     body="Kontenery na pokładzie: MSDU0806613."),
        Notification(user_id=me.id, kind="customs", title="Odprawa zlecona", container_id=c.id),
        Notification(user_id=me.id, kind="system-error", title="Błąd serwera"),
        Notification(user_id=me.id, kind="weekly_digest", title="Podsumowanie tygodnia", is_read=True),
    ]
    db.add_all(rows)
    db.commit()
    return c, rows


def test_mapping_helpers():
    assert feed.category("vessel_stuck") == "vessels" and feed.category("nowy-rodzaj") == "system"
    assert feed.priority("demurrage") == "urgent" and feed.priority("weekly_digest") == "info"
    assert feed.priority("order") == "normal"
    # rodzaje nadawane poza głównymi modułami też mają kategorię (nie lądują w „system” przez pominięcie)
    assert feed.category("crd_escalation") == "orders" and feed.category("bulletin") == "messages"
    assert feed.category("backup_verify_failed") == "system"
    assert feed.priority("backup_verify_failed") == "urgent"      # admin ma to zobaczyć w przypiętych
    assert feed.vessel_name("Statek MV DEMO DELTA w rejonie portu FELIXSTOWE") == "MV DEMO DELTA"
    assert feed.vessel_name("Statek MV DEMO PALLAS stoi przy GDANSK juz 30 h") == "MV DEMO PALLAS"


def test_feed_enriched_filtered_and_paged(client, admin_headers, db_session):
    c, rows = _seed(db_session)
    out = client.get("/api/notifications/feed", headers=admin_headers).json()
    by_title = {i["title"]: i for i in out["items"]}
    ship = by_title["Statek MV DEMO HELIOS w porcie docelowym ROTTERDAM"]
    assert ship["category"] == "vessels" and ship["thread_key"] == "v:MV DEMO HELIOS"
    assert ship["containers"] == [{"id": c.id, "container_no": "MSDU0806613"}]   # z treści, w zakresie
    first = next(i for i in out["items"] if i["title"].startswith("Statek MV DEMO HELIOS w rejonie"))
    assert [x["container_no"] for x in first["containers"]] == ["MSDU0806613"]   # TGBU… nie istnieje
    assert by_title["Odprawa zlecona"]["thread_key"] == f"c:{c.id}"
    assert [p["title"] for p in out["pinned"]] == ["Błąd serwera"]               # pilne nieprzeczytane
    assert by_title["Podsumowanie tygodnia"]["priority"] == "info"

    customs = client.get("/api/notifications/feed?category=customs", headers=admin_headers).json()
    assert [i["title"] for i in customs["items"]] == ["Odprawa zlecona"]
    system = client.get("/api/notifications/feed?category=system", headers=admin_headers).json()
    assert {i["title"] for i in system["items"]} >= {"Błąd serwera", "Podsumowanie tygodnia"}
    unread = client.get("/api/notifications/feed?unread_only=true", headers=admin_headers).json()
    assert "Podsumowanie tygodnia" not in {i["title"] for i in unread["items"]}
    found = client.get("/api/notifications/feed?q=rotterdam", headers=admin_headers).json()
    assert len(found["items"]) == 2

    page = client.get("/api/notifications/feed?limit=2", headers=admin_headers).json()
    assert page["has_more"] is True and len(page["items"]) == 2
    older = client.get(f"/api/notifications/feed?limit=50&before_id={page['items'][-1]['id']}",
                       headers=admin_headers).json()
    assert older["pinned"] == [] and older["has_more"] is False
    assert not {i["id"] for i in older["items"]} & {i["id"] for i in page["items"]}


def test_thread_and_unread(client, admin_headers, db_session):
    _, rows = _seed(db_session)
    thread = client.get(f"/api/notifications/{rows[1].id}/thread", headers=admin_headers).json()
    assert thread["thread_key"] == "v:MV DEMO HELIOS" and len(thread["items"]) == 2
    assert client.post(f"/api/notifications/read?notification_id={rows[2].id}",
                       headers=admin_headers).status_code == 200
    assert client.post(f"/api/notifications/unread?notification_id={rows[2].id}",
                       headers=admin_headers).status_code == 200
    db_session.expire_all()
    assert db_session.get(Notification, rows[2].id).is_read is False
    assert client.get("/api/notifications/999999/thread", headers=admin_headers).status_code == 404


def test_feed_filters_status_and_priority(client, admin_headers, db_session):
    """Filtry Aktualności (2026-10-06): status przeczytane/nieprzeczytane i ważność."""
    _seed(db_session)

    def titles(**params):
        resp = client.get("/api/notifications/feed", headers=admin_headers, params=params)
        assert resp.status_code == 200, resp.text
        return {n["title"] for n in resp.json()["items"]}

    assert titles(status="read") == {"Podsumowanie tygodnia"}
    assert "Podsumowanie tygodnia" not in titles(status="unread")
    assert titles(priority="urgent") == {"Błąd serwera"}
    assert titles(priority="info") == {"Podsumowanie tygodnia"}
    assert titles(priority="normal") == {"Odprawa zlecona"} | {t for t in titles() if t.startswith("Statek")}
    assert titles(status="read", priority="urgent") == set()
    assert client.get("/api/notifications/feed", headers=admin_headers,
                      params={"status": "zle"}).status_code == 422
