"""Administracja: spółki i użytkownicy (tylko admin)."""
import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..audit import record, record_changes, record_created
from ..database import get_db
from ..deps import AdminOnly as admin_only
from ..deps import Editors as editors
from ..deps import scope_company
from ..models import (
    Company,
    CustomsAgency,
    Notification,
    PasswordResetToken,
    RefreshToken,
    Role,
    User,
)
from ..schemas import (
    CompanyIn,
    CompanyOut,
    CustomsAgencyIn,
    CustomsAgencyOut,
    UserIn,
    UserOut,
    UserUpdate,
)
from ..security import PARTNER_ROLES, hash_password, revoke_user_refresh_tokens, validate_password_policy
from ..serializers import serialize_user

logger = logging.getLogger(__name__)


def _generate_temp_password() -> str:
    """Losowe hasło tymczasowe zaproszenia — per użytkownik, jednorazowo zwracane w
    odpowiedzi (admin wkleja je do maila). Zastępuje wspólne, statyczne hasło z
    konfiguracji, które znał każdy wcześniej zaproszony."""
    return secrets.token_urlsafe(9)

router = APIRouter(prefix="/api", tags=["admin"])


def _validate_role_bindings(role: Role, company_id: int | None, forwarder_id: int | None,
                            view_all: bool, warehouse_id: int | None = None,
                            customs_agency_id: int | None = None) -> None:
    """Blokuje kombinacje roli i przypisań, które zablokowałyby konto przy każdym żądaniu."""
    if role == Role.forwarder:
        # spedytor jest zawężany po forwarder_id, nie po spółce
        if forwarder_id is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Rola spedytor wymaga przypisania spedytora.")
        return
    if role == Role.customs:
        # agencja celna jest zawężana po customs_agency_id, nie po spółce
        if customs_agency_id is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Rola agencja celna wymaga przypisania agencji.")
        return
    if role == Role.warehouse and warehouse_id is None:
        # konto magazynu (np. zewnętrzny DLT) musi mieć magazyn — inaczej fail-closed = brak dostępu
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Rola magazyn wymaga przypisania magazynu.")
    if role != Role.admin and not view_all and company_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Konto wymaga przypisania spółki lub dostępu do wszystkich spółek.")


def _partner_scope_reset(role: Role) -> dict:
    """Partner zewnętrzny (spedytor, agencja celna) nie należy do spółki: przy zapisie konta
    czyścimy company_id i view_all_companies zamiast odrzucać formularz (stare UI wysyłało
    je dla każdej roli). Odczyt i tak je ignoruje (deps.own_company_id, can_view_all)."""
    return {"company_id": None, "view_all_companies": False} if role in PARTNER_ROLES else {}


@router.get("/companies", response_model=list[CompanyOut])
def list_companies(db: Session = Depends(get_db), user: User = editors):
    # odczyt także dla logistyki (przeglądarka master data); zapis zostaje admin-only.
    # Logistyk bez view_all widzi tylko swoją spółkę — spójnie z separacją danych.
    q = select(Company).order_by(Company.name)
    q = scope_company(q, Company.id, user)
    return db.scalars(q).all()


@router.post("/companies", response_model=CompanyOut, status_code=201)
def create_company(body: CompanyIn, db: Session = Depends(get_db), user: User = admin_only):
    if db.scalar(select(Company).where((Company.name == body.name) | (Company.code == body.code))):
        raise HTTPException(status.HTTP_409_CONFLICT, "Spółka o tej nazwie lub kodzie już istnieje.")
    company = Company(**body.model_dump())
    db.add(company)
    record_created(db, company, user)
    db.commit()
    return company


@router.patch("/companies/{company_id}", response_model=CompanyOut)
def update_company(company_id: int, body: CompanyIn,
                   db: Session = Depends(get_db), user: User = admin_only):
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono spółki.")
    clash = db.scalar(select(Company).where(
        Company.id != company_id,
        (Company.name == body.name) | (Company.code == body.code)))
    if clash:
        raise HTTPException(status.HTTP_409_CONFLICT, "Spółka o tej nazwie lub kodzie już istnieje.")
    record_changes(db, company, body.model_dump(exclude_unset=True), user)
    db.commit()
    return company


# --- agencje celne (rejestr) ---

@router.get("/customs-agencies", response_model=list[CustomsAgencyOut])
def admin_list_customs_agencies(db: Session = Depends(get_db), user: User = admin_only):
    return db.scalars(select(CustomsAgency).order_by(CustomsAgency.name)).all()


@router.post("/customs-agencies", response_model=CustomsAgencyOut, status_code=201)
def create_customs_agency(body: CustomsAgencyIn, db: Session = Depends(get_db),
                          user: User = admin_only):
    if db.scalar(select(CustomsAgency).where(CustomsAgency.name == body.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Taka agencja celna już istnieje.")
    agency = CustomsAgency(name=body.name, email=body.email, is_active=body.is_active,
                           contact_person=body.contact_person, contact_phone=body.contact_phone,
                           address=body.address, note=body.note,
                           export_format=body.export_format, export_params=body.export_params)
    db.add(agency)
    record_created(db, agency, user)
    db.commit()
    return agency


@router.patch("/customs-agencies/{agency_id}", response_model=CustomsAgencyOut)
def update_customs_agency(agency_id: int, body: CustomsAgencyIn,
                          db: Session = Depends(get_db), user: User = admin_only):
    agency = db.get(CustomsAgency, agency_id)
    if not agency:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono agencji celnej.")
    clash = db.scalar(select(CustomsAgency).where(
        CustomsAgency.id != agency_id, CustomsAgency.name == body.name))
    if clash:
        raise HTTPException(status.HTTP_409_CONFLICT, "Taka agencja celna już istnieje.")
    record_changes(db, agency, body.model_dump(exclude_unset=True), user)
    db.commit()
    return agency


@router.delete("/customs-agencies/{agency_id}", status_code=204)
def delete_customs_agency(agency_id: int, db: Session = Depends(get_db),
                          user: User = admin_only):
    from .dictionaries import guarded_delete
    guarded_delete(db, CustomsAgency, agency_id, user, "agencja celna")


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), user: User = admin_only):
    return [serialize_user(db, u) for u in db.scalars(select(User).order_by(User.login))]


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserIn, db: Session = Depends(get_db), user: User = admin_only):
    if db.scalar(select(User).where(User.login == body.login)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Login jest już zajęty.")
    _validate_role_bindings(body.role, body.company_id, body.forwarder_id,
                            body.view_all_companies, body.warehouse_id,
                            body.customs_agency_id)
    data = body.model_dump()
    data.update(_partner_scope_reset(body.role))
    send_invite = data.pop("send_invite", False)
    raw_password = data.pop("password", "")
    if send_invite:
        if not body.email:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Zaproszenie wymaga adresu e-mail.")
        raw_password = _generate_temp_password()
        data["must_change_password"] = True
    else:
        validate_password_policy(raw_password)  # W14 #89
    data["hashed_password"] = hash_password(raw_password)
    new_user = User(**data)
    db.add(new_user)
    db.flush()  # nadaje id do audytu — wciąż w jednej transakcji z rekordami audytu
    # audyt utworzenia konta: dotąd logowaliśmy tylko edycje (record_changes), samo
    # tworzenie nie — konto z bypassem separacji (view_all_companies) mogło powstać bez
    # śladu. Per-pole, żeby AuditLog dało się odpytać po field='view_all_companies' także
    # dla nadań przy tworzeniu, spójnie z edycjami. Null-e (nieużyte przypisania) pomijamy.
    for field in ("login", "role", "company_id", "forwarder_id", "customs_agency_id",
                  "warehouse_id", "view_all_companies", "is_active"):
        val = getattr(new_user, field)
        if val is None:
            continue
        record(db, entity_type=User.__tablename__, entity_id=new_user.id, field=field,
               old_value=None, new_value=getattr(val, "value", val), user=user,
               note="utworzenie konta")
    db.commit()
    # Konto z zaproszeniem powstaje z hasłem tymczasowym i wymuszeniem zmiany hasła.
    # Samą wiadomość zaproszenia admin wysyła ręcznie z Outlooka (mailto po stronie
    # panelu) — bez serwerowego SMTP, żeby nie angażować IT.
    out = serialize_user(db, new_user)
    if send_invite:
        # jednorazowo: hasło tymczasowe wraca tylko w tej odpowiedzi (do treści maila)
        out.temp_password = raw_password
    return out


@router.post("/users/{user_id}/reset-invite", response_model=UserOut)
def reset_invite(user_id: int, db: Session = Depends(get_db), user: User = admin_only):
    """Ponowne zaproszenie: nowe losowe hasło tymczasowe + wymuszenie zmiany przy
    logowaniu. Zwraca hasło jednorazowo (admin wysyła je mailem z Outlooka)."""
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono użytkownika.")
    if not target.email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Zaproszenie wymaga adresu e-mail.")
    raw_password = _generate_temp_password()
    target.hashed_password = hash_password(raw_password)
    target.must_change_password = True
    target.session_version += 1  # reset = konto mogło być przejęte → stare sesje giną
    record(db, entity_type=User.__tablename__, entity_id=target.id,
           field="must_change_password", old_value=None, new_value=True, user=user,
           note="ponowne zaproszenie (reset hasła tymczasowego)")
    db.commit()
    revoke_user_refresh_tokens(db, target.id)
    out = serialize_user(db, target)
    out.temp_password = raw_password
    return out


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate,
                db: Session = Depends(get_db), user: User = admin_only):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono użytkownika.")
    changes = body.model_dump(exclude_unset=True)
    # wartości efektywne po zmianach — do walidacji spójności roli i ochrony admina
    eff_role = changes.get("role", target.role)
    eff_company = changes.get("company_id", target.company_id)
    eff_forwarder = changes.get("forwarder_id", target.forwarder_id)
    eff_view_all = changes.get("view_all_companies", target.view_all_companies)
    eff_warehouse = changes.get("warehouse_id", target.warehouse_id)
    eff_customs = changes.get("customs_agency_id", target.customs_agency_id)
    _validate_role_bindings(eff_role, eff_company, eff_forwarder, eff_view_all,
                            eff_warehouse, eff_customs)
    changes.update(_partner_scope_reset(eff_role))
    # ochrona przed zablokowaniem systemu: ostatni aktywny admin nie może stracić roli/aktywności
    losing_admin = target.role == Role.admin and (
        eff_role != Role.admin or changes.get("is_active") is False)
    if losing_admin:
        others = db.scalar(select(func.count()).select_from(User).where(
            User.role == Role.admin, User.is_active.is_(True), User.id != target.id))
        if not others:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Nie można zdegradować ani deaktywować ostatniego administratora.")
    password = changes.pop("password", None)
    if password:
        validate_password_policy(password)  # W14 #89
        target.hashed_password = hash_password(password)
        # reset hasła przez admina = hasło zna osoba trzecia → wymuś zmianę przy logowaniu
        target.must_change_password = True
        target.session_version += 1  # unieważnia access tokeny (jak change_password)
        record(db, entity_type=User.__tablename__, entity_id=target.id,
               field="password_reset", old_value=None, new_value=target.login, user=user,
               note="reset hasła przez administratora")
    record_changes(db, target, changes, user)
    db.commit()
    if password:
        revoke_user_refresh_tokens(db, target.id)  # + refresh tokeny — po commicie zmian
    return serialize_user(db, target)


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, db: Session = Depends(get_db), user: User = admin_only):
    """Usunięcie konta = dezaktywacja + anonimizacja danych osobowych (OBS-002).
    Wiersz konta zostaje, więc historia audytu i „kto utworzył" w rekordach biznesowych
    nie giną; stary login zostaje tylko we wpisie audytu `__deleted__`. Zabezpieczenia:
    nie można usunąć samego siebie ani ostatniego aktywnego admina."""
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono użytkownika.")
    if target.id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nie można usunąć własnego konta.")
    if target.role == Role.admin:
        others = db.scalar(select(func.count()).select_from(User).where(
            User.role == Role.admin, User.is_active.is_(True), User.id != target.id))
        if not others:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Nie można usunąć ostatniego administratora.")
    uid, old_login, avatar = target.id, target.login, target.avatar
    logger.warning("Usunięcie (anonimizacja) konta id=%s przez %s", uid, user.login)
    record(db, entity_type=User.__tablename__, entity_id=uid, field="__deleted__",
           old_value=old_login, new_value=None, user=user,
           note="usunięcie konta: dezaktywacja + anonimizacja")
    # dane własne i tokeny kasujemy; wiadomości i audyt zostają (rozliczalność)
    for model in (Notification, RefreshToken, PasswordResetToken):
        db.execute(delete(model).where(model.user_id == uid))
    target.login = f"usuniety-{uid}"
    target.email = ""
    target.full_name = ""
    target.hashed_password = hash_password(secrets.token_urlsafe(32))
    target.is_active = False
    target.session_version += 1  # unieważnia wydane access tokeny
    target.totp_secret = None
    target.totp_backup_codes = ""
    target.ui_prefs = ""
    target.avatar = ""
    db.commit()
    if avatar:
        from .avatars import avatars_dir
        (avatars_dir() / avatar).unlink(missing_ok=True)
