"""Tranzyt (numer zamówienia od "47") -> auto-flaga is_transit + auto-SZKIC wyceny.

Strażnik jednej reguły: kontener z numerem zamówienia zaczynającym się od "47"
dostaje is_transit=True i dokładnie jedno zlecenie wyceny TransportJob w SZKIC,
utworzone raz (idempotentnie) niezależnie ile razy kontener jest zapisywany.
"""
TRANSIT_NO = "MEDU1234562"
NORMAL_NO = "CAIU7654324"


def _company_id(client, headers):
    companies = client.get("/api/companies", headers=headers).json()
    return next(c["id"] for c in companies if c["code"] == "BOREALIS")


def _create(client, headers, container_no, **extra):
    body = {"container_no": container_no, "company_id": _company_id(client, headers),
            "status": "ZAPOWIEDZIANY", **extra}
    response = client.post("/api/containers", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _jobs_for_container(client, headers, container_id):
    jobs = client.get("/api/transport-jobs", headers=headers).json()
    out = []
    for job in jobs:
        for container in job.get("containers", []):
            if container.get("container_id") == container_id:
                out.append(job)
                break
    return out


def test_transit_number_creates_szkic_and_flags(client, admin_headers):
    created = _create(client, admin_headers, TRANSIT_NO, order_numbers="47123, 88001")
    assert created["is_transit"] is True

    fetched = client.get(f"/api/containers/{created['id']}", headers=admin_headers).json()
    assert fetched["is_transit"] is True

    jobs = _jobs_for_container(client, admin_headers, created["id"])
    assert len(jobs) == 1
    assert jobs[0]["status"] == "SZKIC"


def test_non_transit_number_does_nothing(client, admin_headers):
    created = _create(client, admin_headers, NORMAL_NO, order_numbers="88001")
    assert created["is_transit"] is False
    assert _jobs_for_container(client, admin_headers, created["id"]) == []


def test_idempotent_no_duplicate_job(client, admin_headers):
    created = _create(client, admin_headers, TRANSIT_NO, order_numbers="47123")
    assert len(_jobs_for_container(client, admin_headers, created["id"])) == 1

    r = client.patch(f"/api/containers/{created['id']}", headers=admin_headers,
                     json={"vessel": "MV TEST"})
    assert r.status_code == 200

    jobs = _jobs_for_container(client, admin_headers, created["id"])
    assert len(jobs) == 1


def test_cancelled_auto_job_not_recreated(client, admin_headers, db_session):
    """Anulowanie auto-SZKICU to decyzja logistyki (np. obsłużone poza systemem) —
    kolejny zapis kontenera nie może tworzyć nowego SZKICU (audyt 2026-09-23).
    Wraca się przez „Wznów” na anulowanym zleceniu."""
    from sqlalchemy import func, select

    from app.models import TransportJobContainer
    created = _create(client, admin_headers, TRANSIT_NO, order_numbers="4712345")
    job = _jobs_for_container(client, admin_headers, created["id"])[0]
    r = client.post(f"/api/transport-jobs/{job['id']}/cancel", headers=admin_headers,
                    json={"reason": "obsłużone poza systemem"})
    assert r.status_code == 200, r.text
    r = client.patch(f"/api/containers/{created['id']}", headers=admin_headers,
                     json={"notes": "zmiana"})
    assert r.status_code == 200
    n = db_session.scalar(select(func.count(TransportJobContainer.id)).where(
        TransportJobContainer.container_id == created["id"]))
    assert n == 1
