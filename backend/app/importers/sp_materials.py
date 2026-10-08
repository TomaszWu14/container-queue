"""Import pliku „SAP_Dane_materiałowe.xlsm” (SharePoint): każda zakładka z danymi → surowa
tabela; z „Hierarchii produktów” krótka nazwa PL, nazwa EN i kod CN trafiają do `Material`
(decyzja 2026-09-29: agencja dostaje KRÓTKĄ nazwę PL)."""
import datetime

from fastapi import HTTPException, status
from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from ..invoices.uom import normalize_ref
from ..models import Material, SpMaterialRow, SpMaterialSheet, utcnow
from ..tabular import load_workbook_or_422

MATERIALS_SHEET = "Hierarchia produktów"
_BATCH = 2000


def _cell(value):
    if value is None:
        return ""
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value if isinstance(value, (int, float)) else str(value).strip()


def parse(content: bytes) -> list[dict]:
    """[{name, headers, rows}] — zakładki z nagłówkiem w 1. wierszu (≥2 niepuste komórki);
    techniczne (Admin, Params, Dictionary, ukryty arkusz SAP BI) odpadają same."""
    wb = load_workbook_or_422(content)   # SEC-009: limit po rozpakowaniu (zip-bomba) + 422
    sheets = []
    for ws in wb.worksheets:
        if ws.sheet_state != "visible":
            continue
        rows = ws.iter_rows(values_only=True)
        header = next(rows, None) or ()
        # kolumny do ostatniego niepustego nagłówka (arkusze mają puste „ogony” kolumn)
        last = max((i for i, h in enumerate(header) if h not in (None, "")), default=-1)
        if sum(1 for h in header if h not in (None, "")) < 2:
            continue
        headers = [str(h or "").strip() for h in header[:last + 1]]
        data = []
        for row in rows:
            cells = [_cell(v) for v in row[:last + 1]]
            if any(c != "" for c in cells):
                data.append(cells + [""] * (len(headers) - len(cells)))
        sheets.append({"name": ws.title[:80], "headers": headers, "rows": data})
    wb.close()
    if not sheets:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Plik nie ma zakładek z danymi.")
    return sheets


def store(db: Session, sheets: list[dict], filename: str, user_id: int | None) -> None:
    """Snapshot: arkusz z pliku zastępuje poprzednią wersję; arkusze spoza pliku zostają."""
    for position, sheet in enumerate(sheets):
        meta = db.scalar(select(SpMaterialSheet).where(SpMaterialSheet.name == sheet["name"]))
        if meta is None:
            meta = SpMaterialSheet(name=sheet["name"])
            db.add(meta)
            db.flush()
        else:
            db.execute(delete(SpMaterialRow).where(SpMaterialRow.sheet_id == meta.id))
        meta.position, meta.headers, meta.row_count = position, sheet["headers"], len(sheet["rows"])
        meta.filename, meta.imported_at, meta.imported_by_id = filename[:255], utcnow(), user_id
        values = [{"sheet_id": meta.id, "row_no": i, "cells": cells,
                   "search": " ".join(str(c) for c in cells if c != "").lower()[:2000]}
                  for i, cells in enumerate(sheet["rows"], start=1)]
        for start in range(0, len(values), _BATCH):
            db.execute(insert(SpMaterialRow), values[start:start + _BATCH])


def apply_materials(db: Session, sheets: list[dict], dry_run: bool) -> dict:
    """„Hierarchia produktów” → Material: nazwa PL (krótka), nazwa EN, CN. Plik jest źródłem
    prawdy — niepusta wartość nadpisuje; pusta nie czyści. Brakujący REF = nowy materiał."""
    sheet = next((s for s in sheets if s["name"] == MATERIALS_SHEET), None)
    if sheet is None:
        return {"materials_sheet": False}
    col = {h: i for i, h in enumerate(sheet["headers"])}
    if "REF" not in col:
        return {"materials_sheet": False}
    fields = {"name_pl": "TXT_SHORT_PL", "name_en": "TXT_SHORT_EN", "tariff_cn": "KOD_CN"}
    limits = {"name_pl": 500, "name_en": 500, "tariff_cn": 30}
    existing = {m.ref_code: m for m in db.scalars(select(Material))}
    new = updated = 0
    for row in sheet["rows"]:
        ref = str(row[col["REF"]] or "").strip()
        if not ref:
            continue
        values = {f: str(row[col[h]]).strip()[:limits[f]] for f, h in fields.items()
                  if h in col and str(row[col[h]]).strip()}
        material = existing.get(ref)
        if material is None:
            new += 1
            if dry_run:
                continue
            material = Material(ref_code=ref[:100], ref_norm=normalize_ref(ref))
            db.add(material)
            existing[ref] = material
        elif any(getattr(material, f) != v for f, v in values.items()):
            updated += 1
        if not dry_run:
            for f, v in values.items():
                setattr(material, f, v)
            material.updated_at = utcnow()
    return {"materials_sheet": True, "materials_new": new, "materials_updated": updated}
