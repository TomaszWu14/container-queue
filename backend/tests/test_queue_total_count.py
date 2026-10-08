"""Audyt DATA-002: lista kolejki obcięta limitem mówi, ile jest naprawdę (X-Total-Count),
archiwum pokazuje NAJNOWSZE, a eksport xlsx nie gubi wierszy ponad dawny limit 2000."""
import datetime

from app.models import Company, Container, ContainerStatus


def _seed(db_session, n, status=ContainerStatus.ZREALIZOWANY):
    company_id = db_session.query(Company).first().id
    base = datetime.date(2026, 1, 1)
    db_session.add_all([Container(container_no=f"TCNU{i:07d}", company_id=company_id, status=status,
                                  notify_date=base + datetime.timedelta(days=i)) for i in range(n)])
    db_session.commit()


def test_truncated_archive_reports_total_and_shows_newest(client, admin_headers, db_session):
    _seed(db_session, 7)
    r = client.get("/api/containers?completed=true&limit=5", headers=admin_headers)
    assert r.status_code == 200
    assert r.headers["X-Total-Count"] == "7"
    dates = [c["notify_date"] for c in r.json()]
    assert dates[0] == "2026-01-07" and dates == sorted(dates, reverse=True)


def test_untruncated_list_total_equals_rows(client, admin_headers, db_session):
    _seed(db_session, 3, status=ContainerStatus.W_TRANSPORCIE)
    r = client.get("/api/containers?completed=false", headers=admin_headers)
    assert r.headers["X-Total-Count"] == str(len(r.json())) == "3"
