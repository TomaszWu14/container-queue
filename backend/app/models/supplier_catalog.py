"""Kartoteka dostawców (spec 2026-09-25-kartoteka-dostawcy): indeksy dostawcy z SAP (EINA),
warianty układu dokumentów, dziennik importów z SAP. PR1 = schemat; wypełnia je import SAP
(PR2) i masowe dokumenty (PR5)."""
import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .enums import utcnow

__all__ = ["SapImport", "SupplierDocVariant", "SupplierMaterial"]


class SupplierMaterial(Base):
    """Indeks dostawcy: dostawca + nasz materiał + kod artykułu u dostawcy (SAP EINA).
    `unconfirmed` = przeniesione z ręcznego SupplierMaterialMap, czeka na potwierdzenie
    importem EINA. `lead_days` — jedyne pole prowadzone w aplikacji."""
    __tablename__ = "supplier_materials"
    __table_args__ = (
        UniqueConstraint("supplier_id", "material_id",
                         name="uq_supplier_materials_supplier_material"),
        Index("ix_supplier_materials_supplier_code", "supplier_id", "supplier_code"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), index=True)
    supplier_code: Mapped[str] = mapped_column(String(120), default="", server_default=text("''"))
    sap_status: Mapped[str] = mapped_column(String(20), default="", server_default=text("''"))
    origin_country: Mapped[str] = mapped_column(String(2), default="", server_default=text("''"))
    tariff_cn: Mapped[str] = mapped_column(String(30), default="", server_default=text("''"))
    lead_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unconfirmed: Mapped[bool] = mapped_column(Boolean, default=False,
                                              server_default=text("false"))
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow)


class SupplierDocVariant(Base):
    """Wariant układu dokumentu (CI/PL) w profilu dostawcy: odcisk nagłówków + mapa kolumn."""
    __tablename__ = "supplier_doc_variants"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("supplier_doc_profiles.id", ondelete="CASCADE"), index=True)
    doc_type: Mapped[str] = mapped_column(String(4))                     # ci | pl
    fingerprint: Mapped[dict] = mapped_column(JSON, default=dict)
    column_map: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(10), default="proposed",
                                        server_default=text("'proposed'"))  # proposed|approved|rejected
    # DATA-006: docs_count/ok_count celowo poza modelem — nikt ich nie aktualizował (zawsze 0).
    # Liczbę próbek licz zapytaniem po supplier_doc_samples.variant_id. Kolumny w bazie
    # (kartoteka001, server_default 0) do usunięcia osobną migracją.
    ref_hit_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=utcnow)


class SapImport(Base):
    """Dziennik importów z SAP (lfa1 | eina | materials): kto, kiedy, plik, liczniki, błędy."""
    __tablename__ = "sap_imports"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    filename: Mapped[str] = mapped_column(String(255), default="", server_default=text("''"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=utcnow)
    counts: Mapped[dict] = mapped_column(JSON, default=dict)
    errors: Mapped[list] = mapped_column(JSON, default=list)
