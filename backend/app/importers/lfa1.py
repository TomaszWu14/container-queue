"""Import kartoteki dostawców z eksportu SAP LFA1 (SE16N) z podglądem — spec 2026-09-25 §3.

`parse_lfa1` → wiersze + błędy wierszy; `build_plan` (bez zmian w bazie) dzieli je na Nowi ·
Zmienieni (pole po polu stara→nowa) · Zniknęli z SAP · Błędy; `apply_plan` zapisuje w jednej
transakcji (commit u wołającego): audyt każdej zmiany pola („import SAP <plik>”) i wpis w
`sap_imports`. Zniknięci → `sap_status = inactive_in_sap` TYLKO przy pełnym eksporcie (decyzja
usera 2026-09-26 — plik częściowy nie może zdezaktywować kartoteki); nigdy nie kasujemy.
Klucz: kod SAP; rekord kartoteki bez kodu dopasowany po nazwie dostaje kod. Nadawców
spółek-klientów (client_company_id) nie dotyka. Puste wartości z SAP nie kasują danych.
"""
from dataclasses import dataclass, field

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record
from ..models import SapImport, Supplier, User
from .excel import _cap, _cell_getter, _map_headers, _open_first_sheet, _text

LFA1_HEADERS = [
    ("DOSTAWCA", "sap_code"),
    ("KRAJ", "country"),
    ("NAZWA 1", "name1"),
    ("NAZWA 2", "name2"),
    ("NAZWA 3", "name3"),
    ("NAZWA 4", "name4"),
    ("MIASTO", "city"),
    ("KOD POCZT", "zip"),
    ("ULICA", "street"),
    ("VAT", "vat"),
    # ponytail: nagłówki blokad zgadnięte z opisów pól SE16N (SPERR/SPERM/LOEVM) — sprawdzić na
    # prawdziwym pliku; brak tych kolumn = status z SAP nieznany (poza powrotem „zniknięty” → active)
    ("BLOKADA KSIĘG", "block_post"),
    ("BLOKADA ZAKUP", "block_purch"),
    ("ZNACZNIK USUNI", "deleted"),
]
_STATUS_KEYS = ("block_post", "block_purch", "deleted")
# pola kartoteki, których właścicielem jest SAP (spec §2) — tylko te import zmienia
SAP_FIELDS = ("name", "country", "street", "city", "zip", "vat", "address", "sap_status")
INACTIVE = "inactive_in_sap"
PREVIEW_CAP = 200   # ponytail: listy w odpowiedzi ucięte; liczniki pełne, błędy w całości w xlsx


def _error(line: int, code: str, name: str, reason: str) -> dict:
    return {"row": line, "sap_code": code, "name": name, "reason": reason}


def parse_lfa1(content: bytes) -> tuple[list[dict], list[dict]]:
    """Arkusz LFA1 → (wiersze, błędy). Nazwa sklejana z 4 kolumn; pusty wiersz/stopka pomijane;
    wiersz z kodem bez nazwy (albo odwrotnie) = błąd; powtórzony kod — błąd w `build_plan`."""
    sheet = _open_first_sheet(content)
    columns: dict[str, int] = {}
    rows: list[dict] = []
    errors: list[dict] = []
    for line, row in enumerate(sheet.iter_rows(values_only=True), start=1):
        if not columns:
            columns = _map_headers(row, LFA1_HEADERS)
            if not ("sap_code" in columns and "name1" in columns):
                columns = {}
            continue
        get = _cell_getter(row, columns)
        name = " ".join(p for p in (_text(get(f"name{i}")) for i in (1, 2, 3, 4)) if p)
        code = _text(get("sap_code"))
        if not code and not name:
            continue
        if not code or not name:
            errors.append(_error(line, code, name, "brak kodu SAP" if not code else "brak nazwy"))
            continue
        street, zip_code, city = _text(get("street")), _text(get("zip")), _text(get("city"))
        country = _text(get("country"))
        town = " ".join(p for p in (zip_code, city) if p)
        has_status = any(k in columns for k in _STATUS_KEYS)
        blocked = any(_text(get(k)).upper() == "X" for k in _STATUS_KEYS)
        rows.append({
            "line": line,
            "sap_code": _cap(code, 20),
            "name": _cap(name, 160),
            "country": _cap(country, 2),
            "street": _cap(street, 160),
            "city": _cap(city, 80),
            "zip": _cap(zip_code, 20),
            "vat": _cap(_text(get("vat")), 30),
            "address": _cap(", ".join(p for p in (street, town, country) if p), 300),
            "sap_status": ("blocked" if blocked else "active") if has_status else None,
        })
    if not columns:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Nie znaleziono nagłówków eksportu LFA1 (Dostawca / Nazwa 1).")
    return rows, errors


@dataclass
class Plan:
    total: int
    new: list[dict] = field(default_factory=list)
    changed: list[tuple[Supplier, dict]] = field(default_factory=list)
    disappeared: list[Supplier] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)


def build_plan(db: Session, rows: list[dict], errors: list[dict]) -> Plan:
    """Porównanie pliku z kartoteką — bez żadnych zmian w bazie."""
    catalog = db.scalars(select(Supplier).where(Supplier.client_company_id.is_(None))
                         .order_by(Supplier.id)).all()
    by_code: dict[str, Supplier] = {}
    for supplier in catalog:
        if supplier.sap_code:
            by_code.setdefault(supplier.sap_code, supplier)
    by_name = {s.name.strip().upper(): s for s in catalog if not s.sap_code}
    plan = Plan(total=len(rows) + len(errors), errors=list(errors))
    seen: dict[str, int] = {}
    for row in rows:
        code = row["sap_code"]
        if code in seen:
            plan.errors.append(_error(row["line"], code, row["name"],
                                      f"kod SAP powtórzony w pliku (pierwszy w wierszu {seen[code]})"))
            continue
        seen[code] = row["line"]
        supplier = by_code.get(code) or by_name.pop(row["name"].strip().upper(), None)
        if supplier is None:
            plan.new.append(row)
            continue
        changes = {f: row[f] for f in SAP_FIELDS
                   if row[f] and getattr(supplier, f) != row[f]}
        if row["sap_status"] is None and supplier.sap_status == INACTIVE:
            changes["sap_status"] = "active"    # wrócił do SAP, a plik nie ma kolumn blokad
        if not supplier.sap_code:
            changes["sap_code"] = code
        if changes:
            plan.changed.append((supplier, changes))
    plan.disappeared = [s for s in catalog if s.sap_code and s.sap_code not in seen
                        and s.sap_status != INACTIVE]
    plan.errors.sort(key=lambda e: e["row"])
    return plan


def _brief(supplier: Supplier) -> dict:
    return {"id": supplier.id, "sap_code": supplier.sap_code, "name": supplier.name}


def preview(plan: Plan) -> dict:
    """Podgląd dla UI: pełne liczniki, listy ucięte do PREVIEW_CAP."""
    cap = PREVIEW_CAP
    return {
        "counts": {"total": plan.total, "new": len(plan.new), "changed": len(plan.changed),
                   "disappeared": len(plan.disappeared), "errors": len(plan.errors)},
        "new": [{"sap_code": r["sap_code"], "name": r["name"], "country": r["country"]}
                for r in plan.new[:cap]],
        "changed": [{**_brief(s), "changes": [
            {"field": f, "old": getattr(s, f), "new": v} for f, v in changes.items()]}
            for s, changes in plan.changed[:cap]],
        "disappeared": [_brief(s) for s in plan.disappeared[:cap]],
        "errors": plan.errors[:cap],
    }


def apply_plan(db: Session, plan: Plan, *, full_export: bool, user: User | None,
               filename: str) -> SapImport:
    """Zapis planu + audyt + wpis w sap_imports. Bez commit — transakcję domyka wołający."""
    note = f"import SAP {filename}"
    created = [Supplier(**{k: v for k, v in row.items() if k != "line" and v is not None})
               for row in plan.new]
    db.add_all(created)
    db.flush()
    for supplier in created:
        record(db, entity_type="suppliers", entity_id=supplier.id, field="__created__",
               old_value=None, new_value=supplier.sap_code, user=user, note=note)
    for supplier, changes in plan.changed:
        for name, value in changes.items():
            record(db, entity_type="suppliers", entity_id=supplier.id, field=name,
                   old_value=getattr(supplier, name), new_value=value, user=user, note=note)
            setattr(supplier, name, value)
    deactivated = plan.disappeared if full_export else []
    for supplier in deactivated:
        record(db, entity_type="suppliers", entity_id=supplier.id, field="sap_status",
               old_value=supplier.sap_status, new_value=INACTIVE, user=user, note=note)
        supplier.sap_status = INACTIVE
    counts = {**preview(plan)["counts"], "deactivated": len(deactivated), "full_export": full_export}
    log = SapImport(kind="lfa1", filename=filename[:255], user_id=user.id if user else None,
                    counts=counts, errors=plan.errors)
    db.add(log)
    db.flush()
    return log
