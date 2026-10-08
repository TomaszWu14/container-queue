"""List przewozowy CMR (#19): drukowalny HTML wypełniony danymi kontenera."""
from sqlalchemy import select

from app.models import Company, Container

from .conftest import login


def test_cmr_renders_html_with_container_no(client, db_session):
    co = db_session.scalars(select(Company)).first()
    c = Container(company_id=co.id, container_no="CMAU7654321")
    db_session.add(c)
    db_session.commit()
    r = client.get(f"/api/containers/{c.id}/cmr", headers=login(client))
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "CMR" in r.text and "CMAU7654321" in r.text
