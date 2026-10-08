"""Cykl planowania dostawy: PROPOZYCJA -> WYSLANE -> POTWIERDZONE."""
import datetime

from app.models import Container, PlanningStatus, Port, PortTransitTime
from app.planning import (
    PLAN_LEAD_DAYS,
    estimated_eta,
    eta_shift_days,
    proposed_date,
    transit_days_for,
)
from tests.conftest import login


def _create(client, headers, container_no, **extra):
    companies = client.get("/api/companies", headers=headers).json()
    company_id = next(c["id"] for c in companies if c["code"] == "BOREALIS")
    payload = {"container_no": container_no, "company_id": company_id,
               "status": "ZAPOWIEDZIANY", **extra}
    response = client.post("/api/containers", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_new_container_starts_as_proposal(client):
    headers = login(client)
    created = _create(client, headers, "MSDU0806613")
    assert created["planning_status"] == "PROPOZYCJA"
    assert created["notify_date_manual"] is False


def test_proposed_date_is_eta_plus_lead():
    assert proposed_date(datetime.date(2026, 9, 1)) == datetime.date(2026, 9, 1 + PLAN_LEAD_DAYS)


def test_transit_days_for_uses_month_of_the_date():
    """Wyliczenia oparte o transit time biorą miesiąc właściwej daty (tu: ETD)."""
    port = Port(name="Shanghai", transit_time_days=32)
    port.transit_rows = [PortTransitTime(month=9, days=65)]
    etd = datetime.date(2026, 9, 20)
    assert transit_days_for(port, etd.month) == 65
    assert etd + datetime.timedelta(days=transit_days_for(port, etd.month)) \
        == datetime.date(2026, 11, 24)


def test_estimated_eta_only_as_fallback_without_tracking_eta():
    """D12: ETD + transit sezonowy tylko gdy brak ETA; ETA z trackingu zawsze wygrywa."""
    port = Port(name="Ningbo", transit_time_days=32)
    port.transit_rows = [PortTransitTime(month=9, days=65)]
    container = Container(port=port, etd=datetime.date(2026, 9, 20))
    assert estimated_eta(container) == datetime.date(2026, 11, 24)
    container.eta = datetime.date(2026, 11, 1)
    assert estimated_eta(container) is None, "jest ETA z trackingu — bez szacunku"
    assert estimated_eta(Container(port=port)) is None, "bez ETD nie ma z czego liczyć"
    assert estimated_eta(Container(etd=datetime.date(2026, 9, 20))) is None, "bez portu"


def test_eta_shift_is_none_without_snapshot():
    container = Container(eta=datetime.date(2026, 9, 10), planning_eta_at_send=None)
    assert eta_shift_days(container) is None


def test_eta_shift_counts_days_from_snapshot():
    container = Container(eta=datetime.date(2026, 9, 12),
                          planning_eta_at_send=datetime.date(2026, 9, 10))
    assert eta_shift_days(container) == 2


def test_creating_container_with_eta_sets_proposal_date(client):
    headers = login(client)
    created = _create(client, headers, "PLAN0000005", eta="2026-10-01")
    assert created["notify_date"] == "2026-10-05", "eta + 4 dni"
    assert created["planning_status"] == "PROPOZYCJA"


def test_manual_notify_date_marks_container_as_manual(client):
    headers = login(client)
    created = _create(client, headers, "PLAN0000010", eta="2026-10-01")
    response = client.patch(f"/api/containers/{created['id']}",
                            json={"notify_date": "2026-10-09"}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["notify_date_manual"] is True


def test_proposal_does_not_count_towards_daily_limit(client):
    headers = login(client)
    _create(client, headers, "PLAN0000108", notify_date="2026-11-02")
    days = client.get("/api/queue?date_from=2026-11-02&date_to=2026-11-02",
                      headers=headers).json()
    assert days[0]["used"] == 0, "propozycja jest widoczna, ale nie zajmuje slotu"
    assert len(days[0]["containers"]) == 1


def test_confirmed_container_counts_towards_daily_limit(client, db_session):
    headers = login(client)
    created = _create(client, headers, "PLAN0000113", notify_date="2026-11-03")
    container = db_session.get(Container, created["id"])
    container.planning_status = PlanningStatus.POTWIERDZONE
    db_session.commit()
    days = client.get("/api/queue?date_from=2026-11-03&date_to=2026-11-03",
                      headers=headers).json()
    assert days[0]["used"] == 1


def test_queue_filters_by_planning_status(client, db_session):
    headers = login(client)
    created = _create(client, headers, "PLAN0000129", notify_date="2026-11-04")
    _create(client, headers, "PLAN0000134", notify_date="2026-11-04")
    container = db_session.get(Container, created["id"])
    container.planning_status = PlanningStatus.POTWIERDZONE
    db_session.commit()
    days = client.get("/api/queue?date_from=2026-11-04&date_to=2026-11-04"
                      "&planning=POTWIERDZONE", headers=headers).json()
    assert [c["container_no"] for c in days[0]["containers"]] == ["PLAN0000129"]
