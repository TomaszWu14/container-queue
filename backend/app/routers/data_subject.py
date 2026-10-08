"""GDPR-005: panel admina — dane osoby (eksport, art. 15) i anonimizacja kierowcy (art. 17).

Logika w app/data_subject.py; tu walidacja kryteriów i ślad w audycie: kto i po jakich
kryteriach (bez ich wartości — audyt nie może stać się kolejną kopią danych osobowych).
Konto użytkownika anonimizuje DELETE /api/users/{id} (audyt zostaje z pseudonimem).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import data_subject as ds
from ..audit import record
from ..database import get_db
from ..deps import AdminOnly as admin_only
from ..models import User, utcnow

router = APIRouter(prefix="/api/admin/data-subject", tags=["administracja"])


def _criteria(email: str = "", phone: str = "", name: str = "") -> list[str]:
    email, phone, name = email.strip(), phone.strip(), name.strip()
    if email and "@" not in email:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Nieprawidłowy adres e-mail.")
    if phone and len(ds.phone_digits(phone)) < 6:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Numer telefonu: co najmniej 6 cyfr.")
    if name and len(name) < 3:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Imię i nazwisko: co najmniej 3 znaki.")
    used = [key for key, value in (("email", email), ("phone", phone), ("name", name)) if value]
    if not used:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Podaj e-mail, telefon albo imię i nazwisko osoby.")
    return used


@router.get("")
def export_subject(email: str = "", phone: str = "", name: str = "",
                   db: Session = Depends(get_db), user: User = admin_only):
    """Wszystkie miejsca z danymi osoby (JSON do przekazania osobie). E-mail / imię i nazwisko
    szuka kont (dokładne dopasowanie, bez wielkości liter); telefon / imię i nazwisko — kierowcy."""
    used = _criteria(email, phone, name)
    result = {"generated_at": utcnow().isoformat(), "criteria": used,
              "users": [ds.user_export(db, u) for u in ds.find_users(db, email, name)],
              "driver": ds.driver_export(db, phone, name) if phone.strip() or name.strip()
              else None}
    record(db, entity_type="data_subject", entity_id=0, field="export", old_value=None,
           new_value=",".join(used), user=user, note="RODO art. 15 — eksport danych osoby")
    db.commit()
    return result


class DriverAnonymizeIn(BaseModel):
    phone: str = ""
    name: str = ""


@router.post("/anonymize-driver")
def anonymize_driver(body: DriverAnonymizeIn, db: Session = Depends(get_db),
                     user: User = admin_only):
    """Usunięcie danych kierowcy na żądanie: kontenery (wpis w audycie z adminem jako autorem),
    powiadomienia „driver” i historia SMS. Nieodwracalne."""
    used = _criteria(phone=body.phone, name=body.name)
    stats = ds.anonymize_driver(db, user, body.phone, body.name)
    record(db, entity_type="data_subject", entity_id=0, field="anonymize_driver",
           old_value=None, new_value=f"kontenery: {stats['containers']}, SMS: {stats['sms']}",
           user=user, note="RODO art. 17 — kryteria: " + ",".join(used))
    db.commit()
    return stats
