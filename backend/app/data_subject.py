"""GDPR-005: prawa osoby — dostęp/eksport (art. 15) i usunięcie (art. 17).

Wyszukuje dane osoby we wszystkich miejscach: konto użytkownika (profil, wiadomości,
powiadomienia, jego wpisy w audycie, obserwowane kontenery) albo kierowca (dane kierowcy
w kontenerach, historia SMS, powiadomienia „driver”).

Usunięcie konta = anonimizacja (DELETE /api/users/{id}): login → usuniety-{id}, dane osobowe
puste, audyt i wiadomości zostają z pseudonimem jako autorem (rozliczalność, art. 5 ust. 2).
Kierowca nie ma konta — `anonymize_driver` czyści jego dane w kontenerach i kopiach
(ta sama ścieżka co retencja awizacji, avizo_workflow._purge_driver_data).
"""
import re

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .avizo_workflow import _purge_driver_data
from .models import (AuditLog, Container, Message, Notification, SmsMessage, User,
                     WatchedContainer)

EXPORT_LIMIT = 1000        # wierszy na sekcję; więcej → "truncated": true
PHONE_MATCH_DIGITS = 9     # numer PL bez prefiksu kraju; formatowanie (+48, spacje) pomijamy


def phone_digits(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")[-PHONE_MATCH_DIGITS:]


def _iso(value):
    return value.isoformat() if value else None


def _section(db: Session, stmt, row) -> dict:
    rows = db.scalars(stmt.limit(EXPORT_LIMIT + 1)).all()
    return {"items": [row(r) for r in rows[:EXPORT_LIMIT]], "truncated": len(rows) > EXPORT_LIMIT}


def find_users(db: Session, email: str = "", name: str = "") -> list[User]:
    conds = []
    if email:
        conds.append(func.lower(User.email) == email.strip().lower())
    if name:
        conds.append(func.lower(User.full_name) == name.strip().lower())
    return list(db.scalars(select(User).where(or_(*conds)).order_by(User.id))) if conds else []


def user_export(db: Session, user: User) -> dict:
    return {
        "account": {"id": user.id, "login": user.login, "email": user.email,
                    "full_name": user.full_name, "role": user.role.value,
                    "company_id": user.company_id, "is_active": user.is_active,
                    "last_seen": _iso(user.last_seen)},
        "messages": _section(db, select(Message).where(Message.user_id == user.id)
                             .order_by(Message.id), lambda m: {
            "container_id": m.container_id, "created_at": _iso(m.created_at), "body": m.body}),
        "notifications": _section(db, select(Notification).where(Notification.user_id == user.id)
                                  .order_by(Notification.id), lambda n: {
            "kind": n.kind, "title": n.title, "body": n.body, "is_read": n.is_read,
            "container_id": n.container_id, "created_at": _iso(n.created_at)}),
        "audit_entries": _section(db, select(AuditLog).where(AuditLog.user_id == user.id)
                                  .order_by(AuditLog.id), lambda a: {
            "entity_type": a.entity_type, "entity_id": a.entity_id, "field": a.field,
            "old_value": a.old_value, "new_value": a.new_value, "note": a.note,
            "created_at": _iso(a.created_at)}),
        "watched_container_ids": list(db.scalars(select(WatchedContainer.container_id).where(
            WatchedContainer.user_id == user.id))),
    }


def _phone_rows(db: Session, model, column, digits: str) -> list:
    """Wiersze z numerem pasującym po ostatnich cyfrach; LIKE zawęża, Python dopasowuje."""
    if not digits:
        return []
    rows = db.scalars(select(model).where(column.contains(digits[-3:]))).all()
    return [r for r in rows if phone_digits(getattr(r, column.key)) == digits]


def driver_containers(db: Session, phone: str = "", name: str = "") -> list[Container]:
    found = {c.id: c for c in _phone_rows(db, Container, Container.driver_phone,
                                            phone_digits(phone))}
    if name:
        for c in db.scalars(select(Container).where(
                func.lower(Container.driver_name) == name.strip().lower())):
            found[c.id] = c
    return sorted(found.values(), key=lambda c: c.id)


def driver_export(db: Session, phone: str = "", name: str = "") -> dict:
    containers = driver_containers(db, phone, name)
    sms = _phone_rows(db, SmsMessage, SmsMessage.phone, phone_digits(phone))
    return {
        "containers": [{"id": c.id, "container_no": c.container_no,
                        "driver_name": c.driver_name, "driver_phone": c.driver_phone,
                        "driver_id_no": c.driver_id_no, "truck_no": c.truck_no,
                        "trailer_no": c.trailer_no} for c in containers[:EXPORT_LIMIT]],
        "sms": [{"container_id": s.container_id, "phone": s.phone, "status": s.status,
                 "body": s.body, "created_at": _iso(s.created_at)} for s in sms[:EXPORT_LIMIT]],
        "truncated": len(containers) > EXPORT_LIMIT or len(sms) > EXPORT_LIMIT,
    }


def anonymize_driver(db: Session, actor: User, phone: str = "", name: str = "") -> dict:
    """Czyści dane kierowcy w kontenerach (z wpisem w audycie, autor = admin) oraz kopie:
    powiadomienia „driver” tych kontenerów i historię SMS (także na inne kontenery z tym
    numerem). Commit u wołającego."""
    note = "żądanie osoby (RODO art. 17) — anonimizacja danych kierowcy"
    sms = _phone_rows(db, SmsMessage, SmsMessage.phone, phone_digits(phone))
    containers = driver_containers(db, phone, name)
    cleared = sum(_purge_driver_data(db, c, note, user=actor) for c in containers)
    for row in sms:   # SMS na ten numer także przy kontenerach z innym kierowcą dziś
        row.phone, row.body = "", ""
    return {"containers": cleared, "sms": len(sms)}
