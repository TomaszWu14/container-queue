"""Potwierdzenia DLT: tokenowy link z maila wywołania palet.

Flow:
  1. Wysyłka wywołania (pallets.send) generuje świeży token (stare wygaszane)
     i dokleja link /dlt/{token} do maila do DLT.
  2. DLT otwiera stronę: wywołanie tylko-do-odczytu (auta → pozycje → HU/ilości)
     + przyciski „Przygotowane" i „Wysłane" (sekwencyjnie).
  3. Przejścia statusu: sent/confirmed → przygotowane → wyslane_z_dlt; każde
     zapisuje audyt + dzwonek (notify) dla logistyki spółki i autora wywołania.
     „Wysłane" dezaktywuje token. Bez logowania; token = SHA-256 w bazie
     (wzorzec driver_links), jednolite 404 bez rozróżniania przyczyny.
"""
import datetime
import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record
from ..database import get_db
from ..models import PalletCall, PalletCallLink, PalletCallStatus, User, utcnow
from ..notifications import company_watchers, notify
from ..public_links import capped, past_hard_limit

router = APIRouter(prefix="/api/dlt", tags=["dlt"])


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def create_dlt_link(db: Session, call: PalletCall) -> str:
    """Świeży token dla wywołania; stare linki wygaszane. Commit u wołającego."""
    raw = secrets.token_hex(24)
    for old in db.scalars(select(PalletCallLink).where(
            PalletCallLink.pallet_call_id == call.id,
            PalletCallLink.deactivated_at.is_(None))):
        old.deactivated_at = utcnow()
    expires = None
    if call.needed_by:
        # link żyje do tygodnia po terminie — potem jednolite 404
        expires = datetime.datetime.combine(
            call.needed_by + datetime.timedelta(days=7), datetime.time.max)
    now = utcnow()   # bez needed_by — twardy limit PUBLIC_LINK_MAX_DAYS (SEC-014)
    db.add(PalletCallLink(token=_hash_token(raw), pallet_call_id=call.id,
                          created_at=now, expires_at=capped(now, expires)))
    return raw


def _get_link(db: Session, token: str) -> PalletCallLink:
    link = db.scalar(select(PalletCallLink).where(
        PalletCallLink.token == _hash_token(token)))
    # 404 dla nieistniejącego, wygasłego i wygaszonego — bez rozróżniania (enumeracja)
    if (not link or link.deactivated_at
            or (link.expires_at and link.expires_at < utcnow())
            or past_hard_limit(link.created_at)):      # SEC-014: także stare linki bez terminu
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link nie istnieje lub wygasł.")
    return link


def _line_out(ln) -> dict:
    return {"produkt": ln.produkt, "krotki_opis": ln.krotki_opis,
            "ilosc_pal": float(ln.ilosc_pal or 0),
            "pallets": float(ln.pallets) if ln.pallets is not None else None,
            "hu_numbers": ln.hu_numbers,
            "data_dostawy": ln.data_dostawy.isoformat() if ln.data_dostawy else None}


@router.get("/{token}")
def dlt_info(token: str, db: Session = Depends(get_db)):
    link = _get_link(db, token)
    call = link.call
    return {
        "number": call.number,
        "status": call.status.value,
        "needed_by": call.needed_by.isoformat() if call.needed_by else None,
        "notes": call.notes,
        "trucks": [{"ordinal": t.ordinal, "capacity": t.capacity,
                    "lines": [_line_out(ln) for ln in t.lines]}
                   for t in call.trucks],
        "unassigned_lines": [_line_out(ln) for ln in call.lines
                             if ln.truck_id is None],
    }


def _transition(db: Session, call: PalletCall, target: PalletCallStatus,
                allowed_from: tuple[PalletCallStatus, ...], title: str,
                user: User | None, note: str) -> None:
    if call.status == target:
        return  # idempotentnie: ponowne tapnięcie (flaky sieć) nie dubluje niczego
    if call.status not in allowed_from:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Nieprawidłowa kolejność potwierdzeń.")
    old = call.status.value
    call.status = target
    record(db, entity_type="pallet_call", entity_id=call.id, field="status",
           old_value=old, new_value=target.value, user=user, note=note)
    recipients = company_watchers(db, call.company_id)
    if call.created_by:
        author = db.get(User, call.created_by)
        if author:
            recipients = recipients + [author]
    notify(db, recipients, kind="dlt", title=f"{title}: {call.number}",
           exclude_user_id=user.id if user else None)
    if target == PalletCallStatus.wyslane_z_dlt:
        # wywołanie zrealizowane — dezaktywuj wszystkie aktywne linki
        for lnk in db.scalars(select(PalletCallLink).where(
                PalletCallLink.pallet_call_id == call.id,
                PalletCallLink.deactivated_at.is_(None))):
            lnk.deactivated_at = utcnow()
    db.commit()


def mark_prepared(db: Session, call: PalletCall, user: User | None, note: str) -> None:
    _transition(db, call, PalletCallStatus.przygotowane,
                (PalletCallStatus.sent, PalletCallStatus.confirmed),
                "DLT: wywołanie przygotowane", user, note)


def mark_shipped(db: Session, call: PalletCall, user: User | None, note: str) -> None:
    _transition(db, call, PalletCallStatus.wyslane_z_dlt, (PalletCallStatus.przygotowane,),
                "DLT: wywołanie wysłane", user, note)


@router.post("/{token}/prepared")
def dlt_prepared(token: str, db: Session = Depends(get_db)):
    mark_prepared(db, _get_link(db, token).call, None, "strona DLT")
    return {"status": "ok"}


@router.post("/{token}/shipped")
def dlt_shipped(token: str, db: Session = Depends(get_db)):
    mark_shipped(db, _get_link(db, token).call, None, "strona DLT")
    return {"status": "ok"}
