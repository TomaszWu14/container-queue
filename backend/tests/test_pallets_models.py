from sqlalchemy.orm import Session

from app import models
from app.database import Base, engine


def test_pallet_call_roundtrip():
    Base.metadata.create_all(bind=engine)
    with Session(bind=engine) as db:
        company = models.Company(name="ACME test", code="ACMET")
        db.add(company)
        db.flush()
        call = models.PalletCall(
            company_id=company.id, number="PC-2026-0001",
            status=models.PalletCallStatus.draft, created_by=None,
        )
        call.lines.append(models.PalletCallLine(
            produkt="DEMO-SKU-020", ilosc_pal=3, data_dostawy=None))
        db.add(call)
        db.commit()
        db.refresh(call)
        assert call.id and call.lines[0].produkt == "DEMO-SKU-020"
        assert call.status == models.PalletCallStatus.draft
        db.delete(company)
        db.query(models.PalletCall).filter_by(id=call.id).delete()
        db.commit()


def test_product_paz_unique():
    Base.metadata.create_all(bind=engine)
    with Session(bind=engine) as db:
        db.query(models.ProductPaz).delete()
        db.add(models.ProductPaz(produkt="X-1", sztuk_na_palete=100))
        db.commit()
        assert db.query(models.ProductPaz).filter_by(produkt="X-1").one().sztuk_na_palete == 100
