"""W4 powiadomienia: matryca reguł, digest dzienny, @wzmianki, Teams, dziennik zmian."""
import datetime

from tests.conftest import login

from app.models import Notification, NotificationRule, User, today_pl


def _company_id(client, headers, code="ACME"):
    return next(c["id"] for c in client.get("/api/companies", headers=headers).json()
                if c["code"] == code)


def _mk_user(client, headers, login_name, role="logistics", company_id=None, **extra):
    body = {"login": login_name, "password": "haslo1234", "role": role,
            "company_id": company_id, **extra}
    resp = client.post("/api/users", headers=headers, json=body)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


def _mk_container(client, headers, no, company_id, **extra):
    resp = client.post("/api/containers", headers=headers,
                       json={"container_no": no, "company_id": company_id, **extra})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


# --- matryca reguł ---

def test_rules_api_admin_only(client):
    headers = login(client)
    cid = _company_id(client, headers)
    _mk_user(client, headers, "logi1", company_id=cid)
    log_headers = login(client, "logi1", "haslo1234")
    assert client.get("/api/notifications/rules", headers=log_headers).status_code == 403
    resp = client.get("/api/notifications/rules", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "message" in data["kinds"] and "daily_digest" in data["kinds"]
    assert data["channels"] == ["bell", "email", "teams"]


def test_rules_put_rejects_unknown(client):
    headers = login(client)
    resp = client.put("/api/notifications/rules", headers=headers, json=[
        {"kind": "nope", "role": "admin", "channel": "bell", "enabled": False}])
    assert resp.status_code == 422


def test_notify_respects_bell_rule(client, db_session, monkeypatch):
    """Dzwonek wyłączony dla roli logistics → rekord powstaje jako przeczytany
    (dedup zachowany, bez badge'a); e-mail nadal zbierany."""
    from app import notifications as n
    sent_emails = []
    monkeypatch.setattr(n, "_send_email", lambda emails, t, b: sent_emails.extend(emails))
    headers = login(client)
    cid = _company_id(client, headers)
    _mk_user(client, headers, "logi2", company_id=cid, email="logi2@example.com")
    db_session.add(NotificationRule(kind="testkind", role="logistics",
                                    channel="bell", enabled=False))
    db_session.commit()
    user = db_session.query(User).filter_by(login="logi2").one()
    count = n.notify(db_session, [user], kind="testkind", title="T")
    db_session.commit()
    assert count == 1
    notif = db_session.query(Notification).filter_by(user_id=user.id).one()
    assert notif.is_read is True
    assert sent_emails == ["logi2@example.com"]


def test_notify_respects_email_rule_and_both_off(client, db_session, monkeypatch):
    from app import notifications as n
    sent_emails = []
    monkeypatch.setattr(n, "_send_email", lambda emails, t, b: sent_emails.extend(emails))
    headers = login(client)
    cid = _company_id(client, headers)
    _mk_user(client, headers, "logi3", company_id=cid, email="logi3@example.com")
    user = db_session.query(User).filter_by(login="logi3").one()
    db_session.add(NotificationRule(kind="k1", role="logistics",
                                    channel="email", enabled=False))
    db_session.commit()
    assert n.notify(db_session, [user], kind="k1", title="T") == 1
    db_session.commit()
    assert sent_emails == []
    notif = db_session.query(Notification).filter_by(user_id=user.id).one()
    assert notif.is_read is False
    # oba kanały off → odbiorca pominięty całkowicie
    db_session.add(NotificationRule(kind="k2", role="logistics",
                                    channel="bell", enabled=False))
    db_session.add(NotificationRule(kind="k2", role="logistics",
                                    channel="email", enabled=False))
    db_session.commit()
    assert n.notify(db_session, [user], kind="k2", title="T2") == 0


# --- Teams webhook (mock httpx) ---

def test_teams_card_sent_and_gated(client, db_session, monkeypatch):
    from app import notifications as n
    posts = []
    from app import teams
    ok = type("R", (), {"text": "", "raise_for_status": lambda self: None})()
    monkeypatch.setattr(teams.httpx, "post", lambda url, **kw: posts.append((url, kw)) or ok)
    monkeypatch.setattr(n, "_submit", lambda fn, *a, **kw: fn(*a, **kw))  # sync
    monkeypatch.setattr(n.settings, "teams_webhook_url", "https://teams.example/hook")
    headers = login(client)
    cid = _company_id(client, headers)
    _mk_user(client, headers, "logi4", company_id=cid)
    user = db_session.query(User).filter_by(login="logi4").one()
    n.notify(db_session, [user], kind="k3", title="Tytuł", body="Treść")
    assert posts == []   # kanały zewnętrzne dopiero po commicie
    db_session.commit()
    assert len(posts) == 1
    card = posts[0][1]["json"]
    content = card["attachments"][0]["content"]
    assert content["type"] == "AdaptiveCard" and "Tytuł" in content["body"][0]["text"]
    # kolumna Teams wyłączona dla kindu → brak wysyłki
    db_session.add(NotificationRule(kind="k4", role="*", channel="teams", enabled=False))
    db_session.commit()
    n.notify(db_session, [user], kind="k4", title="X")
    db_session.commit()
    assert len(posts) == 1


# --- poranny digest ---

def test_daily_digest_content_and_dedup(client, db_session, monkeypatch):
    from app import notifications as n
    headers = login(client)
    cid = _company_id(client, headers)
    _mk_user(client, headers, "logdig", company_id=cid, email="d@example.com")
    today = today_pl()
    _mk_container(client, headers, "TGBU6784203", cid)
    container_id = _mk_container(client, headers, "MEDU9573834", cid)["id"]
    # dostawa dziś
    db_session.execute(
        __import__("sqlalchemy").text(
            "UPDATE containers SET notify_date=:d WHERE id=:i"),
        {"d": today.isoformat(), "i": container_id})
    db_session.commit()
    # 05:00 UTC latem = 07:00 w Warszawie
    at7 = datetime.datetime.combine(today, datetime.time(5, 0))
    sent = n.check_daily_digest_alerts(db_session, now=at7)
    assert sent >= 1
    user = db_session.query(User).filter_by(login="logdig").one()
    notif = db_session.query(Notification).filter_by(
        user_id=user.id, kind="daily_digest").one()
    assert "MEDU9573834" in notif.body
    # dedup: drugi przebieg tego samego dnia nic nie wysyła
    assert n.check_daily_digest_alerts(db_session, now=at7) == 0
    # poza oknem godzinowym: nic
    assert n.check_daily_digest_alerts(
        db_session, now=at7 + datetime.timedelta(hours=3)) == 0


def test_daily_digest_disabled_by_matrix(client, db_session):
    from app import notifications as n
    headers = login(client)
    cid = _company_id(client, headers)
    _mk_user(client, headers, "logdig2", company_id=cid)
    container_id = _mk_container(client, headers, "CSNU0110266", cid)["id"]
    db_session.execute(
        __import__("sqlalchemy").text("UPDATE containers SET notify_date=:d WHERE id=:i"),
        {"d": today_pl().isoformat(), "i": container_id})
    for ch in ("bell", "email"):
        db_session.add(NotificationRule(kind="daily_digest", role="logistics",
                                        channel=ch, enabled=False))
    db_session.commit()
    at7 = datetime.datetime.combine(today_pl(), datetime.time(5, 0))
    assert n.check_daily_digest_alerts(db_session, now=at7) == 0


# --- @wzmianki ---

def test_mention_notifies_only_users_with_access(client, db_session):
    headers = login(client)
    acme = _company_id(client, headers)
    other = _company_id(client, headers, "DOMILING") if any(
        c["code"] == "DOMILING" for c in
        client.get("/api/companies", headers=headers).json()) else None
    if other is None:
        other = client.post("/api/companies", headers=headers,
                            json={"name": "Inna Sp.", "code": "INNA"}).json()["id"]
    _mk_user(client, headers, "kasia", company_id=acme)
    _mk_user(client, headers, "obcy.user", company_id=other)
    container = _mk_container(client, headers, "CAIU7654324", acme)
    resp = client.post(f"/api/containers/{container['id']}/messages", headers=headers,
                       json={"body": "Hej @kasia i @obcy.user, sprawdźcie @nieistnieje"})
    assert resp.status_code == 201, resp.text
    kasia = db_session.query(User).filter_by(login="kasia").one()
    obcy = db_session.query(User).filter_by(login="obcy.user").one()
    assert db_session.query(Notification).filter_by(
        user_id=kasia.id, kind="mention").count() == 1
    assert db_session.query(Notification).filter_by(
        user_id=obcy.id, kind="mention").count() == 0


# --- dziennik zmian dnia ---

def test_changes_feed_filters_and_pagination(client):
    headers = login(client)
    cid = _company_id(client, headers)
    created = _mk_container(client, headers, "GESU1234564", cid)
    client.post(f"/api/containers/{created['id']}/status", headers=headers,
                json={"status": "W_TRANSPORCIE"})
    resp = client.get("/api/changes/feed", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 2
    nos = {e["container_no"] for e in data["entries"]}
    assert "GESU1234564" in nos
    assert "containers" in data["entity_types"]
    # filtr po spółce + paginacja per_page=1
    resp = client.get(f"/api/changes/feed?company_id={cid}&per_page=1", headers=headers)
    data = resp.json()
    assert len(data["entries"]) == 1 and data["total"] >= 2
    # obca spółka = pusto
    empty = client.get("/api/changes/feed?company_id=999999", headers=headers).json()
    assert empty["total"] == 0


def test_changes_feed_forbidden_for_warehouse(client, db_session):
    headers = login(client)
    cid = _company_id(client, headers)
    wh = client.post("/api/warehouses", headers=headers,
                     json={"name": "Mag W4", "company_id": cid}).json()
    _mk_user(client, headers, "magazynier1", role="warehouse", company_id=cid,
             warehouse_id=wh["id"])
    wh_headers = login(client, "magazynier1", "haslo1234")
    assert client.get("/api/changes/feed", headers=wh_headers).status_code == 403
