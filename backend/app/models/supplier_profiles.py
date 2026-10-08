"""Profil dokumentów dostawcy (CI + packing list) i próbki do testu — spec
2026-09-24-profil-dostawcy-ci-pl-agencja. Mapy kolumn: rola (COLUMN_ROLES ekstraktora)
→ lista aliasów nagłówka. `ref_kind`: kolumna `ref` to nasz REF (`ours`) albo kod
dostawcy (`supplier`, tłumaczony przez SupplierMaterialMap)."""
import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .enums import utcnow

__all__ = ["SupplierDocProfile", "SupplierDocSample"]


class SupplierDocProfile(Base):
    __tablename__ = "supplier_doc_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String(10), default="draft")        # draft | active
    currency: Mapped[str] = mapped_column(String(3), default="")
    doc_language: Mapped[str] = mapped_column(String(10), default="")
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    ci_map: Mapped[dict] = mapped_column(JSON, default=dict)
    pl_map: Mapped[dict] = mapped_column(JSON, default=dict)
    ref_kind: Mapped[str] = mapped_column(String(10), default="ours")      # ours | supplier
    split_marker: Mapped[str] = mapped_column(String(60), default="")      # np. „PACKING LIST"
    tol_amount_pct: Mapped[float] = mapped_column(Float, default=0.5)
    tol_qty_pct: Mapped[float] = mapped_column(Float, default=0.0)
    # kody kafelków wymaganych u tego dostawcy (spec 2026-10-06 decyzja 16); None = domyślny zestaw
    required_docs: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    supplier: Mapped["Supplier"] = relationship(back_populates="doc_profile")  # noqa: F821
    samples: Mapped[list["SupplierDocSample"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", lazy="selectin")


class SupplierDocSample(Base):
    __tablename__ = "supplier_doc_samples"
    # ten sam plik (sha256) raz na dostawcę — profil jest 1:1 z dostawcą
    __table_args__ = (UniqueConstraint("profile_id", "sha256",
                                       name="uq_supplier_doc_samples_profile_sha"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("supplier_doc_profiles.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    last_test: Mapped[dict] = mapped_column(JSON, default=dict)
    last_test_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    # masowe wgrywanie (PR5): deduplikacja, typ dokumentu, wariant układu, wynik, status
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    doc_type: Mapped[str] = mapped_column(String(4), default="", server_default="")   # ci | pl
    variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("supplier_doc_variants.id", ondelete="SET NULL"), nullable=True)
    pages: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # queued | ok | review | rejected | duplicate (dotychczasowe próbki kreatora = ok)
    status: Mapped[str] = mapped_column(String(12), default="ok", server_default="ok")
    reason: Mapped[str] = mapped_column(String(300), default="", server_default="")
    profile: Mapped[SupplierDocProfile] = relationship(back_populates="samples")
