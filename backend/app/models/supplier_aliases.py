"""Alias nazwy dostawcy z pliku kolejki → dostawca ze słownika. Import kolejki nie tworzy
dostawców: nazwę z pliku trzyma Container.supplier_raw, a supplier_id rozwiązuje
dokładna nazwa słownikowa albo alias (po znormalizowanej nazwie, per spółka)."""
import datetime
import re

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .enums import utcnow

__all__ = ["SupplierAlias", "normalize_alias"]

_PUNCT = re.compile(r"[.,;\"']")


def normalize_alias(name: str) -> str:
    """„ACME  Ltd." / "acme ltd" → "acme ltd": casefold, bez . , ; " ', zwinięte spacje."""
    return " ".join(_PUNCT.sub("", name or "").casefold().split())


class SupplierAlias(Base):
    __tablename__ = "supplier_aliases"
    __table_args__ = (UniqueConstraint("company_id", "alias_norm"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    alias_norm: Mapped[str] = mapped_column(String(160))
    alias: Mapped[str] = mapped_column(String(160))
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
