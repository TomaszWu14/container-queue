"""Dane materiałowe z SharePoint (plik `SAP_Dane_materiałowe.xlsm`, 2026-09-29): każda zakładka
z danymi = osobna tabela w UI. Trzymamy surowe wiersze arkusza (kolumny zmieniają się
w pliku bez uprzedzenia), a pola potrzebne aplikacji (nazwa PL, CN) import przepisuje do
`Material`. Każdy import podmienia arkusz w całości (snapshot)."""
import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .enums import utcnow

__all__ = ["SpMaterialRow", "SpMaterialSheet"]


class SpMaterialSheet(Base):
    __tablename__ = "sp_material_sheets"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    position: Mapped[int] = mapped_column(Integer, default=0)       # kolejność zakładek w pliku
    headers: Mapped[list] = mapped_column(JSON, default=list)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    filename: Mapped[str] = mapped_column(String(255), default="")
    imported_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    imported_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class SpMaterialRow(Base):
    __tablename__ = "sp_material_rows"
    id: Mapped[int] = mapped_column(primary_key=True)
    sheet_id: Mapped[int] = mapped_column(ForeignKey("sp_material_sheets.id", ondelete="CASCADE"),
                                          index=True)
    row_no: Mapped[int] = mapped_column(Integer, default=0)
    cells: Mapped[list] = mapped_column(JSON, default=list)
    # tekst całego wiersza (małe litery) — wyszukiwarka tabeli bez zależności od typu JSON bazy
    search: Mapped[str] = mapped_column(String(2000), default="")
