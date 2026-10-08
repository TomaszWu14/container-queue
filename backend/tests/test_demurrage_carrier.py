"""Dni wolne od demurrage: ręcznie przy kontenerze → armator (słownik) → domyślna (decyzja 2026-09-28)."""
import datetime

from sqlalchemy import select

from app.config import settings
from app.models import Carrier, Company, Container
from app.notification_alerts import demurrage_deadlines

ETA = datetime.date(2030, 3, 1)


def test_free_days_priority(db_session):
    co = db_session.scalars(select(Company)).first()
    msc = Carrier(name="MSC-T", demurrage_free_days=21)
    db_session.add(msc)
    db_session.flush()
    by_carrier = Container(company_id=co.id, container_no="MSKU1111110", eta=ETA, carrier_id=msc.id)
    manual = Container(company_id=co.id, container_no="MSKU2222220", eta=ETA, carrier_id=msc.id,
                       demurrage_free_days=5)
    default = Container(company_id=co.id, container_no="MSKU3333330", eta=ETA)
    db_session.add_all([by_carrier, manual, default])
    db_session.commit()
    d = demurrage_deadlines(db_session, [by_carrier, manual, default])
    assert d[by_carrier.id] == ETA + datetime.timedelta(days=21)
    assert d[manual.id] == ETA + datetime.timedelta(days=5)
    assert d[default.id] == ETA + datetime.timedelta(days=settings.demurrage_default_free_days)


def test_carrier_free_days_via_api(client, admin_headers):
    r = client.post("/api/carriers", headers=admin_headers, json={"name": "CMA-T", "demurrage_free_days": 14})
    assert r.status_code == 201 and r.json()["demurrage_free_days"] == 14
    cleared = client.patch(f"/api/carriers/{r.json()['id']}", headers=admin_headers,
                           json={"name": "CMA-T", "demurrage_free_days": ""})
    assert cleared.status_code == 200 and cleared.json()["demurrage_free_days"] is None
