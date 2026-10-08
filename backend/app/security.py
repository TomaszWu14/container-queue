import datetime
import hashlib
import secrets
import time

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jwt import PyJWTError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from . import automation_policy
from .config import settings
from .database import get_db
from .models import PasswordResetToken, RefreshToken, Role, User, utcnow
from .twofa_policy import enforce_admin_2fa

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

ALGORITHM = "HS256"
ACCESS_COOKIE = "timporye_access"
REFRESH_COOKIE = "timporye_refresh"
# nagłówek tokenu serwisowego automatyzacji (n8n) — patrz docs/N8N.md
AUTOMATION_HEADER = "X-Automation-Token"


def _bcrypt_bytes(password: str) -> bytes:
    # bcrypt bierze pod uwagę tylko pierwsze 72 bajty; przycinamy jawnie, żeby
    # bcrypt 5.x nie rzucał ValueError (passlib robił to po cichu — dlatego stare
    # hashe pozostają zgodne). Format $2b$ jest ten sam co z passlib → weryfikacja
    # istniejących haseł działa bez migracji danych.
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_bcrypt_bytes(password),
                         bcrypt.gensalt(rounds=settings.bcrypt_rounds)).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_bcrypt_bytes(plain), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


def validate_password_policy(password: str) -> None:
    """W14 #89: polityka haseł — min. długość z env + litera i cyfra. 422 przy naruszeniu."""
    n = settings.password_min_length
    if len(password) < n:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Hasło musi mieć min. {n} znaków.")
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Hasło musi zawierać literę i cyfrę.")


# --- 2FA TOTP (RFC 6238) czystym stdlib — bez zależności pyotp ---

import base64  # noqa: E402
import hmac as _hmac  # noqa: E402
import struct  # noqa: E402


def generate_totp_secret() -> str:
    """Losowy sekret base32 (20 bajtów, jak Google Authenticator)."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii")


def hotp(secret_b32: str, counter: int, digits: int = 6, algo: str = "sha1") -> str:
    key = base64.b32decode(secret_b32.upper() + "=" * (-len(secret_b32) % 8))
    digest = _hmac.new(key, struct.pack(">Q", counter), algo).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def totp(secret_b32: str, at: float | None = None, step: int = 30,
         digits: int = 6, algo: str = "sha1") -> str:
    return hotp(secret_b32, int((time.time() if at is None else at) // step), digits, algo)


def totp_matched_step(secret_b32: str, code: str, at: float | None = None,
                      window: int = 1) -> int | None:
    """Krok czasowy (licznik HOTP), któremu odpowiada kod, albo None. Porównanie w stałym
    czasie, z tolerancją ±window kroków (dryf zegara) — sprawdzamy wszystkie kroki."""
    now = time.time() if at is None else at
    code = code.strip().replace(" ", "")
    matched = None
    for offset in range(-window, window + 1):
        counter = int((now + offset * 30) // 30)
        try:
            expected = hotp(secret_b32, counter)
        except ValueError:  # binascii.Error: sekret spoza base32 → brak dopasowania, nie 500
            return None
        if _hmac.compare_digest(expected, code):
            matched = counter
    return matched


def verify_totp(secret_b32: str, code: str, at: float | None = None,
                window: int = 1) -> bool:
    return totp_matched_step(secret_b32, code, at, window) is not None


def hash_backup_code(raw: str) -> str:
    return hashlib.sha256(raw.strip().replace("-", "").lower().encode("utf-8")).hexdigest()


def generate_backup_codes(n: int = 10) -> list[str]:
    """10 kodów zapasowych (pokazywane raz; w bazie tylko hashe SHA-256)."""
    return [secrets.token_hex(5) for _ in range(n)]


def ensure_ip_not_blocked(db: Session, ip: str) -> None:
    """W14 #90: adres z listy BlockedIP dostaje 403 zanim zadziała rate-limit."""
    from .models import BlockedIP
    if db.scalar(select(BlockedIP.id).where(BlockedIP.ip == ip)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Adres IP jest zablokowany.")


# stały hash „na pusto" — porównujemy z nim, gdy login nie istnieje, aby czas
# odpowiedzi nie zdradzał istnienia konta (ochrona przed enumeracją użytkowników)
_DUMMY_HASH = hash_password("timporye-dummy-password")


def dummy_verify() -> bool:
    """Zawsze False — istnieje tylko po to, by zużyć czas porównania bcrypt."""
    verify_password("x", _DUMMY_HASH)
    return False


def _create_token(user_id: int, token_type: str, expires_delta: datetime.timedelta,
                  jti: str | None = None) -> str:
    now = datetime.datetime.now(datetime.UTC)
    payload = {"sub": str(user_id), "type": token_type, "iat": now, "exp": now + expires_delta}
    if jti:
        payload["jti"] = jti
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def _create_access(user_id: int, session_version: int, expires_delta: datetime.timedelta) -> str:
    now = datetime.datetime.now(datetime.UTC)
    payload = {"sub": str(user_id), "type": "access", "sv": session_version,
               "iat": now, "exp": now + expires_delta}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_access_token(user: "User") -> str:
    # osadzamy wersję sesji — wylogowanie podbija ją i unieważnia stare tokeny
    return _create_access(user.id, user.session_version,
                          datetime.timedelta(minutes=settings.access_token_minutes))


def create_pending_2fa_token(user: "User") -> str:
    """Krótki token „po haśle, przed kodem TOTP" — drugi krok logowania (5 min)."""
    return _create_token(user.id, "totp_pending", datetime.timedelta(minutes=5))


def create_impersonation_token(admin: "User", ctx: dict) -> str:
    """W14 #87: token podglądu „jako rola" — sub to ADMIN (audyt), imp_ctx niesie
    tymczasową rolę/przypisania. Tylko GET; ważny 60 min."""
    now = datetime.datetime.now(datetime.UTC)
    payload = {"sub": str(admin.id), "type": "access", "sv": admin.session_version,
               "imp": True, "imp_ctx": ctx,
               "iat": now, "exp": now + datetime.timedelta(minutes=60)}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def _impersonated_user(real: "User", ctx: dict) -> "User":
    """Ulotny (niedodany do sesji) User z rolą/przypisaniami podglądu."""
    shadow = User(
        id=real.id, login=real.login, email=real.email,
        full_name=f"{real.full_name} (podgląd)", hashed_password="",  # nosec B106
        role=Role(ctx.get("role", "logistics")),
        company_id=ctx.get("company_id"), forwarder_id=ctx.get("forwarder_id"),
        customs_agency_id=ctx.get("customs_agency_id"),
        warehouse_id=ctx.get("warehouse_id"),
        view_all_companies=bool(ctx.get("view_all", False)),
        is_active=True, session_version=real.session_version,
        must_change_password=False, watch_only_notifications=False, ui_prefs="",
        totp_secret=None, totp_backup_codes="", allowed_warehouse_ids=None,
        last_seen=real.last_seen,
    )
    shadow.impersonated = True  # znacznik dla /me → baner w panelu
    return shadow


def issue_refresh_token(db: Session, user_id: int) -> str:
    """Wystawia refresh token i zapisuje jego JTI, aby można było go odwołać."""
    jti = secrets.token_hex(32)
    delta = datetime.timedelta(days=settings.refresh_token_days)
    db.add(RefreshToken(user_id=user_id, jti=jti, expires_at=utcnow() + delta))
    db.commit()
    return _create_token(user_id, "refresh", delta, jti=jti)


def consume_refresh_token(db: Session, token: str) -> tuple[int, bool]:
    """Waliduje refresh token, odwołuje go (rotacja) i zwraca (id użytkownika, rotated).
    rotated=False: ponowne użycie w oknie łaski — wolno wydać tylko access token, bez
    nowego refresh (SEC-010: zużyty token nie może przedłużyć sesji)."""
    payload = _decode(token)
    if payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nieprawidłowy typ tokenu.")
    jti = payload.get("jti")
    # atomowe odwołanie: przy równoległych/powtórzonych żądaniach tylko jedno
    # trafia w niewykorzystany token (rowcount==1); reszta dostaje 401
    result = db.execute(
        update(RefreshToken)
        .where(RefreshToken.jti == jti,
               RefreshToken.revoked.is_(False),
               RefreshToken.expires_at > utcnow())
        .values(revoked=True, revoked_at=utcnow())) if jti else None
    if result is None or result.rowcount != 1:
        # ponowne użycie już odwołanego tokenu = możliwa kradzież → unieważnij rodzinę.
        # WYJĄTEK (okno łaski): dwie karty przeglądarki dzielą cookie i odświeżają
        # równolegle — druga trafia w token zrotowany ułamek sekundy wcześniej.
        # To nie atak: w oknie łaski wydajemy sam access token (refresh z rotacji ma już
        # pierwsza karta we wspólnym cookie) zamiast ubijać wszystkie sesje.
        if jti:
            stolen = db.scalar(select(RefreshToken).where(RefreshToken.jti == jti))
            if stolen and stolen.revoked:
                grace = datetime.timedelta(seconds=settings.refresh_reuse_grace_seconds)
                if stolen.revoked_at is not None and utcnow() - stolen.revoked_at <= grace:
                    db.commit()
                    return int(payload["sub"]), False
                revoke_user_refresh_tokens(db, stolen.user_id)
                # podbij wersję sesji, by natychmiast unieważnić też wydane access tokeny
                victim = db.get(User, stolen.user_id)
                if victim:
                    victim.session_version += 1
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nieprawidłowy lub wygasły token.")
    db.commit()
    return int(payload["sub"]), True


def _hash_reset_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_password_reset_token(db: Session, user_id: int) -> str:
    """Tworzy jednorazowy token resetu; zwraca surową wartość do linku (hash idzie do bazy)."""
    raw = secrets.token_urlsafe(32)
    delta = datetime.timedelta(minutes=settings.password_reset_minutes)
    db.add(PasswordResetToken(user_id=user_id, token_hash=_hash_reset_token(raw),
                              expires_at=utcnow() + delta))
    db.commit()
    return raw


def consume_password_reset_token(db: Session, raw: str) -> User | None:
    """Waliduje token (istnieje, nieużyty, nieprzeterminowany), zużywa go i unieważnia
    pozostałe tokeny użytkownika. Zwraca aktywnego użytkownika lub None."""
    row = db.scalar(select(PasswordResetToken).where(
        PasswordResetToken.token_hash == _hash_reset_token(raw),
        PasswordResetToken.used_at.is_(None),
        PasswordResetToken.expires_at > utcnow()))
    if row is None:
        return None
    now = utcnow()
    db.execute(update(PasswordResetToken)
               .where(PasswordResetToken.user_id == row.user_id,
                      PasswordResetToken.used_at.is_(None))
               .values(used_at=now))
    user = db.get(User, row.user_id)
    db.commit()
    return user if user and user.is_active else None


def revoke_user_refresh_tokens(db: Session, user_id: int) -> None:
    """Wylogowanie ze wszystkich urządzeń — unieważnia wszystkie refresh tokeny."""
    db.execute(update(RefreshToken)
               .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
               # revoked_at celowo NULL: znaczy „zrotowany" (okno łaski); odwołanie
               # rodziny (wylogowanie/kradzież) nie może otwierać okna łaski
               .values(revoked=True))
    db.commit()


def _decode(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nieprawidłowy lub wygasły token.") from None


def user_id_from_token_lenient(token: str) -> int | None:
    """Zwraca sub z tokenu, ignorując wygaśnięcie — do best-effort wylogowania."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM],
                             options={"verify_exp": False})
        return int(payload["sub"])
    except (PyJWTError, KeyError, ValueError, TypeError):
        return None


def decode_token(token: str, expected_type: str) -> int:
    payload = _decode(token)
    if payload.get("type") != expected_type:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nieprawidłowy typ tokenu.")
    return int(payload["sub"])


def automation_user(request: Request, db: Session) -> User | None:
    """Konto serwisowe automatyzacji (n8n): stały token w nagłówku zamiast JWT.

    Zwraca None, gdy integracja jest wyłączona (pusty AUTOMATION_API_TOKEN) lub gdy
    żądanie nie nosi nagłówka — wtedy dalej obowiązuje zwykłe uwierzytelnianie.
    Token jest sekretem długoterminowym, więc porównujemy go w stałym czasie, a
    uprawnienia bierzemy z ROLI konta serwisowego: n8n przechodzi przez te same
    kontrole ról i izolacji per zasób co człowiek (deps.py), bez własnej ścieżki.
    """
    provided = request.headers.get(AUTOMATION_HEADER)
    configured = settings.automation_api_token
    if not configured or not provided:
        return None
    # porównanie na bajtach: compare_digest na str rzuca TypeError przy znakach
    # non-ASCII (nagłówki Starlette dekoduje latin-1), a nagłówek jest z zewnątrz.
    # ACL-005: także poprzedni token (rotacja), termin ważności, sieci, zakaz roli admin
    if not automation_policy.token_matches(provided):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nieprawidłowy token automatyzacji.")
    automation_policy.check_token_use(request)
    login = settings.automation_actor_login
    user = db.scalar(select(User).where(User.login == login))
    if not user or not user.is_active:
        # token poprawny, ale konto nie istnieje/jest wyłączone — świadomy 403, żeby
        # wyłączenie konta serwisowego w panelu natychmiast odcinało automatyzacje
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            f"Konto serwisowe automatyzacji „{login}” nie istnieje "
                            "lub jest nieaktywne.")
    automation_policy.check_service_account(user)
    return user


def get_current_user(request: Request, token: str | None = Depends(oauth2_scheme),
                     db: Session = Depends(get_db)) -> User:
    service = automation_user(request, db)
    if service is not None:
        request.state.user_id = service.id
        return service
    # nagłówek Authorization (API, testy) lub cookie HttpOnly (panel webowy)
    raw = token or request.cookies.get(ACCESS_COOKIE)
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Brak uwierzytelnienia.",
                            headers={"WWW-Authenticate": "Bearer"})
    payload = _decode(raw)
    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nieprawidłowy typ tokenu.")
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Konto nieaktywne lub nie istnieje.")
    # token wystawiony przed wylogowaniem („ze wszystkich urządzeń") jest nieważny
    if payload.get("sv", 0) != user.session_version:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesja wygasła. Zaloguj się ponownie.")
    _enforce_password_change(request, user)
    if payload.get("imp"):
        # W14 #87: podgląd „jako rola" — WSZYSTKIE mutacje 403, każdy GET z audytem
        # przypisanym do prawdziwego admina (sub tokenu).
        # podgląd to uprawnienie admina — po degradacji właściciela token przestaje działać
        if user.role != Role.admin:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                                "Podgląd wygasł. Zaloguj się ponownie.")
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                "Tryb podglądu — zmiany są zablokowane.")
        ctx = payload.get("imp_ctx") or {}
        from .audit import record
        record(db, entity_type="impersonation", entity_id=user.id, field="get",
               old_value=None, new_value=request.url.path, user=user,
               note=f"podgląd jako {ctx.get('role', '?')}")
        db.commit()
        shadow = _impersonated_user(user, ctx)
        request.state.user_id = shadow.id
        return shadow
    # znacznik aktywności („online") — zapis z throttlingiem (max raz na 60 s), by nie
    # obciążać bazy przy każdym żądaniu
    now = utcnow()
    if user.last_seen is None or (now - user.last_seen).total_seconds() > 60:
        db.execute(update(User).where(User.id == user.id).values(last_seen=now))
        db.commit()
        user.last_seen = now
    _enforce_demo_readonly(request, user)
    enforce_admin_2fa(request, user)   # SEC-006: admin bez 2FA — tylko odczyt
    request.state.user_id = user.id
    return user


# hasło tymczasowe (zaproszenie / reset przez admina): do ustawienia własnego hasła konto
# może tylko odczytać siebie, zmienić hasło i się wylogować (SEC-007 — blokada w API,
# nie tylko ekranem panelu; hasło z maila nie daje dostępu do danych)
_MUST_CHANGE_ALLOWED = {("GET", "/api/auth/me"), ("GET", "/api/auth/me/prefs"),
                        ("POST", "/api/auth/change-password"), ("POST", "/api/auth/logout")}


def _enforce_password_change(request: Request, user: User) -> None:
    if user.must_change_password and \
            (request.method, request.url.path) not in _MUST_CHANGE_ALLOWED:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Najpierw ustaw własne hasło (konto z hasłem tymczasowym).")


# konto demo może się tylko wylogować / odświeżyć sesję — reszta zapisów zablokowana
_DEMO_ALLOWED_WRITES = {"/api/auth/logout", "/api/auth/refresh"}


def _enforce_demo_readonly(request: Request, user: User) -> None:
    """Instancja portfolio: konta z DEMO_READONLY_LOGINS tylko czytają (egzekwowane w API,
    nie ukryciem przycisków)."""
    demo = {x.strip().lower() for x in settings.demo_readonly_logins.split(",") if x.strip()}
    if (demo and user.login.lower() in demo and request.method not in ("GET", "HEAD", "OPTIONS")
            and request.url.path not in _DEMO_ALLOWED_WRITES):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Konto demo — tylko podgląd, zmiany są wyłączone.")


def require_roles(*roles: Role):
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Brak uprawnień do tej operacji.")
        return user
    return checker


# partnerzy zewnętrzni: zakres wg forwarder_id / customs_agency_id, NIGDY wg spółki —
# company_id / view_all_companies na takim koncie są ignorowane (deps.own_company_id)
PARTNER_ROLES = (Role.forwarder, Role.customs)


def can_view_all(user: User) -> bool:
    # Konto magazynu jest zawsze zawężone do swojego magazynu, a partner zewnętrzny do
    # swoich kontenerów; view_all_companies na tych rolach to błąd konfiguracji i nie
    # może otwierać dostępu do innych spółek.
    if user.role == Role.warehouse or user.role in PARTNER_ROLES:
        return False
    return user.role == Role.admin or user.view_all_companies


def shares_company_scope(viewer: User, target: User) -> bool:
    """Czy wewnętrzny viewer widzi osobę target (obserwujący, awatar, pasek obecności): swoja
    spółka, a konta grupowe (view_all) widzą wszystkich i są widoczne dla wszystkich."""
    return (target.id == viewer.id or can_view_all(viewer) or can_view_all(target)
            or (viewer.company_id is not None and target.company_id == viewer.company_id))


# limitery i IP klienta — w osobnym module (limit 500 linii); re-eksport dla importów
from .rate_limit import (  # noqa: E402,F401
    ApiRateLimiter,
    LoginRateLimiter,
    _is_trusted_proxy,
    api_limiter,
    client_ip,
    login_limiter,
)
