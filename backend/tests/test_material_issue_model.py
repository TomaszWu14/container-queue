import datetime

from app.database import Base, SessionLocal, engine
from app.models import MaterialIssue


def test_material_issue_persists_and_dedups():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        db.query(MaterialIssue).delete()
        db.add(MaterialIssue(produkt="A", date=datetime.date(2026, 1, 2), qty=10,
                             firma="BOREALIS", magazyn="MAG1", kontrahent="", source_file="f1.csv"))
        db.commit()
        row = db.query(MaterialIssue).one()
        assert row.produkt == "A" and float(row.qty) == 10.0
