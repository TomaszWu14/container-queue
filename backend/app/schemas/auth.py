"""Schematy uwierzytelniania, sesji, firm i użytkowników."""
import datetime

from pydantic import BaseModel, Field, field_validator

from ..models import Role
from .base import ORMModel, _validate_email

# --- auth / users ---

class Token(BaseModel):
    access_token: str
    # None: odświeżenie w oknie łaski (SEC-010) — bez nowego refresh, obecny zostaje
    refresh_token: str | None = None
    token_type: str = "bearer"


class RefreshIn(BaseModel):
    # opcjonalny — panel webowy przekazuje refresh token w cookie HttpOnly
    refresh_token: str | None = None


class ForgotPasswordIn(BaseModel):
    email: str = Field(min_length=3, max_length=160)


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    password: str = Field(min_length=8, max_length=200)


class ChangePasswordIn(BaseModel):
    """Zmiana własnego hasła przez zalogowanego użytkownika (np. po zaproszeniu).
    current_password wymagane tylko przy zmianie dobrowolnej (konto bez wymuszenia);
    przy pierwszym logowaniu z zaproszenia (must_change_password) jest pomijane."""
    new_password: str = Field(min_length=8, max_length=200)
    current_password: str | None = None


class TwoFAVerifyIn(BaseModel):
    """Drugi krok logowania: token oczekujący + kod TOTP lub kod zapasowy."""
    pending_token: str = Field(min_length=10, max_length=1000)
    code: str = Field(min_length=4, max_length=20)


class TwoFAEnableIn(BaseModel):
    secret: str = Field(min_length=16, max_length=64)
    code: str = Field(min_length=4, max_length=20)


class ImpersonateIn(BaseModel):
    """W14 #87: podgląd „jako rola" (read-only)."""
    role: Role
    company_id: int | None = None
    forwarder_id: int | None = None
    customs_agency_id: int | None = None
    warehouse_id: int | None = None


class BlockedIPIn(BaseModel):
    ip: str = Field(min_length=3, max_length=64)
    note: str = Field(default="", max_length=300)


class BlockedIPOut(ORMModel):
    id: int
    ip: str
    note: str
    created_at: datetime.datetime


class ClientErrorIn(BaseModel):
    """Beacon błędu JS z panelu — twarde limity rozmiaru (bez auth)."""
    name: str = Field(default="", max_length=200)
    message: str = Field(default="", max_length=2000)
    stack: str = Field(default="", max_length=8000)
    url: str = Field(default="", max_length=500)


class SessionOut(ORMModel):
    id: int
    created_at: datetime.datetime
    expires_at: datetime.datetime
    current: bool = False


class MeSettingsIn(BaseModel):
    """Wąski self-update własnych ustawień (poza profilem/hasłem)."""
    watch_only_notifications: bool


class CompanyOut(ORMModel):
    id: int
    name: str
    code: str
    is_active: bool
    avizo_cc: str = ""


class CompanyIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    code: str = Field(min_length=2, max_length=20)
    is_active: bool = True
    avizo_cc: str = Field(default="", max_length=500)   # CC maili awizacji (CSV)


class UserOut(ORMModel):
    id: int
    login: str
    email: str
    full_name: str
    role: Role
    company_id: int | None
    forwarder_id: int | None
    customs_agency_id: int | None = None
    customs_agency_name: str | None = None
    warehouse_id: int | None
    view_all_companies: bool
    is_active: bool
    must_change_password: bool = False
    watch_only_notifications: bool = False
    last_seen: datetime.datetime | None = None  # ostatnia aktywność (status „online")
    company_code: str | None = None  # kod spółki (np. ACME) — dostęp do modułów
    totp_enabled: bool = False       # 2FA aktywne (sekret ustawiony)
    must_enroll_2fa: bool = False    # SEC-006: admin musi włączyć 2FA (do tego tylko odczyt)
    impersonated: bool = False       # W14 #87: sesja podglądu „jako rola"
    allowed_warehouse_ids: list[int] | None = None  # W14 #91 (tylko logistyka)
    has_avatar: bool = False
    # tylko w odpowiedzi na utworzenie z zaproszeniem / reset-invite (jednorazowo)
    temp_password: str | None = None


class UserIn(BaseModel):
    login: str = Field(min_length=3, max_length=80)
    email: str = ""
    full_name: str = ""
    # puste, gdy send_invite=True (hasło tymczasowe ustawia serwer); inaczej wymagane min. 8
    password: str = Field(default="", max_length=200)
    # wyślij zaproszenie e-mail z loginem + hasłem tymczasowym; wymusza zmianę hasła
    send_invite: bool = False

    _check_email = field_validator("email")(_validate_email)
    role: Role = Role.logistics
    company_id: int | None = None
    forwarder_id: int | None = None
    customs_agency_id: int | None = None
    warehouse_id: int | None = None
    view_all_companies: bool = False
    is_active: bool = True


class UserUpdate(BaseModel):
    email: str | None = None
    full_name: str | None = None
    password: str | None = Field(default=None, min_length=8)
    role: Role | None = None
    company_id: int | None = None
    forwarder_id: int | None = None
    customs_agency_id: int | None = None
    warehouse_id: int | None = None
    view_all_companies: bool | None = None
    is_active: bool | None = None
    allowed_warehouse_ids: list[int] | None = None  # W14 #91

    # ten sam format co przy tworzeniu; None (pole pominięte) przechodzi bez zmian
    _check_email = field_validator("email")(_validate_email)
