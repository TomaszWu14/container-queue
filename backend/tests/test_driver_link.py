"""SMS do kierowcy (bez linku — decyzja 2026-10-07: nic bez logowania), spóźnienie wpisane
w aplikacji, auto-wysyłka dzień przed dostawą."""
import datetime

from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models import AuditLog, Notification, today_pl
from app.routers.driver import send_tomorrow_sms
from app.sms import mock_outbox

VALID_NO = "MSDU0806613"


def _setup(client, admin_headers, notify_days=1):
    settings.sms_provider = "mock"
    mock_outbox.clear()
    companies = client.get("/api/companies", headers=admin_headers).json()
    borealis = next(c["id"] for c in companies if c["code"] == "BOREALIS")
    wh = client.post("/api/warehouses", headers=admin_headers, json={
        "name": "MAG-SMS", "company_id": borealis, "address": "Hutnicza 1, Radom",
        "contact_phone": "500600700", "entry_instructions": "Brama B, zgłoś się na portierni",
    }).json()
    day = (today_pl() + datetime.timedelta(days=notify_days)).isoformat()
    container = client.post("/api/containers", headers=admin_headers, json={
        "container_no": VALID_NO, "company_id": borealis, "warehouse_id": wh["id"],
        "notify_date": day}).json()
    # dane kierowcy przez dedykowany endpoint (ContainerIn ich nie przyjmuje)
    client.patch(f"/api/containers/{container['id']}/driver", headers=admin_headers,
                 json={"driver_name": "Jan", "driver_id_no": "", "truck_no": "",
                       "trailer_no": "", "driver_phone": "600100200"})
    return container


def test_driver_sms_without_link(client, admin_headers):
    container = _setup(client, admin_headers)
    cid = container["id"]

    # provider off → 409 z komunikatem konfiguracyjnym
    settings.sms_provider = "off"
    assert client.post(f"/api/containers/{cid}/driver-sms",
                       headers=admin_headers).status_code == 409
    settings.sms_provider = "mock"

    sent = client.post(f"/api/containers/{cid}/driver-sms", headers=admin_headers)
    assert sent.status_code == 200 and sent.json()["status"] == "sent", sent.text
    body = mock_outbox[0]["body"]
    assert VALID_NO in body and "Hutnicza 1, Radom" in body and "500600700" in body
    assert "http" not in body and "/dostawa/" not in body          # żadnego linku publicznego

    # historia wysyłek widoczna w panelu
    history = client.get(f"/api/containers/{cid}/driver-sms", headers=admin_headers).json()
    assert history["configured"] is True and len(history["messages"]) == 1
    # stara strona kierowcy nie istnieje
    assert client.get("/api/driver/deadbeef").status_code == 404


def test_auto_sms_day_before(client, admin_headers):
    container = _setup(client, admin_headers, notify_days=1)
    after_15 = datetime.datetime.combine(today_pl(), datetime.time(14, 0))

    # przed bramką godzinową nic nie leci
    assert send_tomorrow_sms(SessionLocal(),
                             now=after_15.replace(hour=8)) == 0
    # po 13:00 UTC — jedna wysyłka, dedup przy kolejnym przebiegu
    assert send_tomorrow_sms(SessionLocal(), now=after_15) == 1
    assert send_tomorrow_sms(SessionLocal(), now=after_15) == 0
    assert any(container["container_no"] in m["body"] for m in mock_outbox)


def _delay_titles(cid):
    with SessionLocal() as db:
        return [n.title for n in db.scalars(select(Notification).where(
            Notification.kind == "driver", Notification.container_id == cid))
            if "spóźni" in n.title]


def test_driver_delay_dedup_same_value(client, admin_headers):
    """Powtórzone spóźnienie z tą samą godziną (retry) nie spamuje obserwatorów;
    inna godzina w oknie 30 min = 429 bez powiadomień, po oknie — powiadamiamy."""
    import pytest
    from fastapi import HTTPException

    from app.models import Container
    from app.routers.driver import report_delay
    cid = _setup(client, admin_headers)["id"]

    def delay(eta):
        with SessionLocal() as db:
            report_delay(db, db.get(Container, cid), eta, None, "test")

    for _ in range(3):
        delay("14:30")
    first = _delay_titles(cid)
    assert len(first) >= 1
    with pytest.raises(HTTPException) as spam:
        delay("15:00")
    assert spam.value.status_code == 429 and "już" in spam.value.detail
    assert len(_delay_titles(cid)) == len(first)
    with SessionLocal() as db:   # po oknie 30 min nowa godzina znów powiadamia
        for a in db.scalars(select(AuditLog).where(AuditLog.field == "driver-delayed")):
            a.created_at -= datetime.timedelta(minutes=31)
        db.commit()
    delay("15:00")
    assert len(_delay_titles(cid)) == 2 * len(first)


def _container_no(prefix: str) -> str:
    from app.iso6346 import check_digit
    return prefix + str(check_digit(prefix))


def test_auto_sms_commits_each_send_and_survives_error(client, admin_headers, monkeypatch):
    """Wyjątek (nie-SmsError) przy 2. kontenerze: SMS 1. zostaje w bazie (SmsMessage),
    pętla idzie dalej do 3. kontenera."""
    from app.models import SmsMessage
    from app.routers import driver as driver_mod
    first = _setup(client, admin_headers)
    borealis, wh, day = first["company_id"], first["warehouse_id"], first["notify_date"]
    others = []
    for prefix in ("MSDU808831", "MSDU808832"):
        c = client.post("/api/containers", headers=admin_headers, json={
            "container_no": _container_no(prefix), "company_id": borealis,
            "warehouse_id": wh, "notify_date": day}).json()
        client.patch(f"/api/containers/{c['id']}/driver", headers=admin_headers,
                     json={"driver_name": "Jan", "driver_id_no": "", "truck_no": "",
                           "trailer_no": "", "driver_phone": "600100201"})
        others.append(c["id"])
    calls = []
    real = driver_mod.send_sms

    def flaky(phone, body):
        calls.append(body)
        if len(calls) == 2:
            raise RuntimeError("redeploy w połowie pętli")
        real(phone, body)

    monkeypatch.setattr(driver_mod, "send_sms", flaky)
    now = datetime.datetime.combine(today_pl(), datetime.time(14, 0))
    with SessionLocal() as db:   # with: wyjątek nie zostawia blokady SQLite
        assert send_tomorrow_sms(db, now=now) == 2
    assert len(calls) == 3
    with SessionLocal() as db:
        ids = [first["id"], *others]
        with_sms = set(db.scalars(select(SmsMessage.container_id).where(
            SmsMessage.container_id.in_(ids), SmsMessage.status == "sent")))
    assert len(with_sms) == 2


def test_smsapi_non_json_response_is_sms_error(monkeypatch):
    import httpx
    import pytest

    from app.sms import SmsError, send_sms
    monkeypatch.setattr(settings, "sms_provider", "smsapi")
    monkeypatch.setattr(settings, "smsapi_token", "tok")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(
        200, text="<html>proxy</html>", request=httpx.Request("POST", "http://x")))
    with pytest.raises(SmsError):
        send_sms("600100200", "x")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(
        200, json=["?"], request=httpx.Request("POST", "http://x")))
    with pytest.raises(SmsError):
        send_sms("600100200", "x")
