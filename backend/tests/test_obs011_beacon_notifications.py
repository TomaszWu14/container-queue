"""OBS-011: beacon błędów JS nie zapisuje tokenów linków publicznych; retencja
przeczytanych powiadomień (nieprzeczytane i świeże zostają)."""
import datetime

from sqlalchemy import select

from app.models import ClientError, Notification, User, utcnow

TOKEN = "AbCdEfGhIjKlMnOpQrStUv123456"


def test_beacon_masks_public_link_token(client, db_session):
    url = f"https://app.example/dostawa/{TOKEN}?x=1"
    body = {"name": "TypeError", "message": f"fail at {url}", "stack": f"at {url}:1:2",
            "url": url}
    assert client.post("/api/client-error", json=body).status_code == 202
    row = db_session.scalars(select(ClientError)).one()
    for field in (row.url, row.message, row.stack):
        assert TOKEN not in field and "/dostawa/[token]" in field


def test_purge_read_notifications_keeps_unread_and_fresh(client, db_session):
    from app.notifications import purge_read_notifications
    uid = db_session.scalars(select(User.id)).first()
    old = utcnow() - datetime.timedelta(days=181)
    db_session.add_all([
        Notification(user_id=uid, kind="eta", title="old-read", is_read=True, created_at=old),
        Notification(user_id=uid, kind="eta", title="old-unread", is_read=False, created_at=old),
        Notification(user_id=uid, kind="eta", title="fresh-read", is_read=True),
    ])
    db_session.commit()
    assert purge_read_notifications(db_session) == 1
    left = set(db_session.scalars(select(Notification.title)))
    assert "old-read" not in left and {"old-unread", "fresh-read"} <= left
