"""Słowniki: historia zmian wpisów master data (AuditLog per encja).

Router bez prefiksu — prefiks /api i tag nadaje dictionaries.router, który go dołącza.
"""
import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..deps import (
    Editors as editors,
)
from ..deps import (
    can_view_all,
    check_company_access,
    check_supplier_access,
    company_column,
    company_filter_ids,
    scope_suppliers,
)
from ..models import (
    AuditLog,
    Carrier,
    Company,
    ContainerPort,
    ContainerType,
    CustomsAgency,
    CustomsCaseStatus,
    DocumentType,
    Forwarder,
    MaterialUnit,
    Port,
    PurchaseOrder,
    Role,
    Supplier,
    User,
    Warehouse,
    pl_midnight_utc,
)
from ..schemas import AuditOut

router = APIRouter()


# --- historia wiersza master data (⟲ w przeglądarce Dane podstawowe) ---
#
# Wspólny odczyt AuditLog per encja, zamiast osobnego endpointu w każdym routerze.
# Klucz mapy = entity_type z audytu (tablename). Guard: Editors — te same osoby,
# które pracują z master data; izolacja spółek jak w reszcie deps.py.

_AUDITABLE = {
    m.__tablename__: m for m in (
        Supplier, Port, Warehouse, Company, CustomsAgency, DocumentType,
        CustomsCaseStatus, MaterialUnit, ContainerPort, PurchaseOrder,
        Carrier, Forwarder, ContainerType,
    )
}


@router.get("/audit/{entity_type}", response_model=list[AuditOut])
def entity_type_history(entity_type: str, limit: int = Query(default=50, ge=1, le=500),
                        offset: int = Query(default=0, ge=0),
                        field: str | None = None, user_id: int | None = None,
                        date_from: datetime.date | None = None,
                        date_to: datetime.date | None = None,
                        db: Session = Depends(get_db), user: User = editors):
    """Historia zmian CAŁEGO słownika (#19) — paginowana, filtr po polu/użytkowniku.

    Izolacja jak w widoku per-id: dla encji per spółka konto ograniczone widzi tylko
    wpisy rekordów swojej spółki (wpisy rekordów skasowanych odpadają — fail-closed,
    spójnie z komentarzem w entity_history)."""
    model = _AUDITABLE.get(entity_type)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nieznany typ encji.")
    q = select(AuditLog).options(selectinload(AuditLog.user)) \
        .where(AuditLog.entity_type == entity_type)
    if model is Supplier:
        # kartoteka globalna (client_company_id nullable) — izolacja przez scope_suppliers
        # (deps.py), nie company_column (Supplier nie ma już company_id).
        q = q.where(AuditLog.entity_id.in_(scope_suppliers(select(Supplier.id), user)))
    else:
        col = company_column(model)
        if col is not None:
            ids = company_filter_ids(user)
            if ids is not None:
                q = q.where(AuditLog.entity_id.in_(
                    select(model.id).where(col.in_(ids))))
    if field:
        q = q.where(AuditLog.field == field)
    if user_id is not None:
        q = q.where(AuditLog.user_id == user_id)
    if date_from:
        q = q.where(AuditLog.created_at >= pl_midnight_utc(date_from))
    if date_to:
        q = q.where(AuditLog.created_at < pl_midnight_utc(date_to + datetime.timedelta(days=1)))
    entries = db.scalars(
        q.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset(max(offset, 0)).limit(min(max(limit, 1), 200))).all()
    result = []
    for entry in entries:
        out = AuditOut.model_validate(entry)
        out.user_login = entry.user.login if entry.user else None
        result.append(out)
    return result


@router.get("/audit/{entity_type}/{entity_id}", response_model=list[AuditOut])
def entity_history(entity_type: str, entity_id: int,
                   limit: int = Query(default=50, ge=1, le=500),
                   db: Session = Depends(get_db), user: User = editors):
    model = _AUDITABLE.get(entity_type)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nieznany typ encji.")
    row = db.get(model, entity_id)
    if model is Supplier:
        if row is not None:
            check_supplier_access(user, row)
        elif not can_view_all(user):
            # fail-closed: dostawca skasowany, nie da się sprawdzić kartoteka/nadawca —
            # historia tylko dla kont widzących wszystkie spółki (jak przy company_column).
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono.")
    else:
        col = company_column(model)
        if row is not None and col is not None:
            check_company_access(user, getattr(row, col.key))
        elif row is None and col is not None \
                and user.role != Role.admin and company_filter_ids(user) is not None:
            # fail-closed: rekord skasowany, nie da się sprawdzić spółki — historia
            # encji per spółka tylko dla kont widzących wszystkie spółki.
            # 404 jak w check_company_access — nie zdradzamy istnienia cudzych danych.
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono.")
    entries = db.scalars(
        select(AuditLog).options(selectinload(AuditLog.user))
        .where(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(min(max(limit, 1), 200))).all()
    result = []
    for entry in entries:
        out = AuditOut.model_validate(entry)
        out.user_login = entry.user.login if entry.user else None
        result.append(out)
    return result
