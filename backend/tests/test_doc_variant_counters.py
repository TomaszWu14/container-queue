"""DATA-006: `supplier_doc_variants.docs_count/ok_count` nikt nie zapisywał ani nie czytał —
zawsze 0, rozjazd z liczbą próbek. Model ich nie wystawia (liczbę próbek liczy się zapytaniem
po `supplier_doc_samples.variant_id`); kolumny zdejmuje migracja dropcnt001."""
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.models import SupplierDocVariant
from tests.test_kartoteka_migration import PRE_001, _apply, _engine, _load


def test_model_has_no_dead_counters():
    cols = set(SupplierDocVariant.__table__.columns.keys())
    assert not {"docs_count", "ok_count"} & cols


def test_orm_insert_works_on_migrated_schema(tmp_path, monkeypatch):
    # baza w kształcie z migracji (z kolumnami liczników NOT NULL) — ORM bez nich musi działać
    mig = _load("kartoteka001_kartoteka_dostawcow.py")
    eng = _engine(tmp_path, PRE_001)
    _apply(eng, mig, mig.upgrade, monkeypatch)
    with Session(eng) as s:
        s.add(SupplierDocVariant(profile_id=1, doc_type="ci"))
        s.commit()
    with eng.connect() as conn:
        assert conn.exec_driver_sql(
            "SELECT docs_count, ok_count FROM supplier_doc_variants").one() == (0, 0)


def test_dropcnt001_drops_and_restores_counters(tmp_path, monkeypatch):
    kart = _load("kartoteka001_kartoteka_dostawcow.py")
    mig = _load("dropcnt001_usun_liczniki_wariantow.py")
    assert mig.down_revision == "trgm002"
    eng = _engine(tmp_path, PRE_001)
    _apply(eng, kart, kart.upgrade, monkeypatch)
    with eng.begin() as conn:
        conn.exec_driver_sql("INSERT INTO supplier_doc_variants (profile_id, doc_type, fingerprint, column_map) VALUES (1, 'ci', '{}', '{}')")

    def cols():
        return {c["name"] for c in inspect(eng).get_columns("supplier_doc_variants")}

    _apply(eng, mig, mig.upgrade, monkeypatch)
    assert not {"docs_count", "ok_count"} & cols()
    _apply(eng, mig, mig.downgrade, monkeypatch)
    assert {"docs_count", "ok_count"} <= cols()
    with eng.connect() as conn:
        assert conn.exec_driver_sql(
            "SELECT docs_count, ok_count FROM supplier_doc_variants").one() == (0, 0)
