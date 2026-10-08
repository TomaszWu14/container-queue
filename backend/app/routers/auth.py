import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import record
from ..automation_policy import is_service_login
from ..config import settings
from ..database import get_db
import json

import jwt as _jwt
from sqlalchemy import update

from ..models import RefreshToken, Role, User, utcnow
from ..notifications import notify, send_password_reset
from ..schemas import (
    ChangePasswordIn,
    ForgotPasswordIn,
    MeSettingsIn,
    RefreshIn,
    ResetPasswordIn,
    SessionOut,
    Token,
    TwoFAEnableIn,
    TwoFAVerifyIn,
    UserOut,
)
from ..security import (
    ACCESS_COOKIE,
    ALGORITHM,
    REFRESH_COOKIE,
    consume_password_reset_token,
    consume_refresh_token,
    create_access_token,
    create_password_reset_token,
    create_pending_2fa_token,
    dummy_verify,
    ensure_ip_not_blocked,
    generate_backup_codes,
    generate_totp_secret,
    get_current_user,
    hash_backup_code,
    hash_password,
    issue_refresh_token,
    login_limiter,
    revoke_user_refresh_tokens,
    user_id_from_token_lenient,
    validate_password_policy,
    verify_password,
    totp_matched_step,
    verify_totp,
)
from ..security import (
    client_ip as _client_ip,
)
from ..serializers import serialize_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_access_cookie(response: Response, access: str) -> None:
    response.set_cookie(ACCESS_COOKIE, access, max_age=settings.access_token_minutes * 60,
                        httponly=True, samesite="lax", secure=settings.secure_cookies)


def _set_auth_cookies(response: Response, access: str, refresh: str) -> None:
    common = {"httponly": True, "samesite": "lax", "secure": settings.secure_cookies}
    _set_access_cookie(response, access)
    response.set_cookie(REFRESH_COOKIE, refresh, path="/api/auth",
                        max_age=settings.refresh_token_days * 86400, **common)


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE)
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")


def _alert_account_lock(db: Session, user: User, ip: str) -> None:
    """SEC-012: konto weszło w progresywną przerwę (porażki z wielu IP) — ślad w audycie
    i dzwonek/e-mail/Teams dla adminów (kind „system”, wyłączalny w matrycy reguł)."""
    logger.warning("Konto %s: %d nieudanych logowań w %d min — przerwa progresywna",
                   user.login, settings.login_account_lock_after, settings.login_window_minutes)
    record(db, entity_type="auth", entity_id=user.id, field="account_locked", old_value=None,
           new_value=user.login, user=None, note=f"przerwa po porażkach logowania, ostatnia z {ip}")
    admins = db.scalars(select(User).where(User.role == Role.admin, User.is_active)).all()
    notify(db, list(admins), kind="system", title=f"Podejrzane logowania na konto {user.login}",
           body=f"{settings.login_account_lock_after} nieudanych prób w "
                f"{settings.login_window_minutes} min z różnych adresów (ostatnia z {ip}). "
                "Konto dostaje rosnące przerwy między próbami.")


@router.post("/login", response_model=None)
def login(request: Request, response: Response,
          form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    ip = _client_ip(request)
    ensure_ip_not_blocked(db, ip)  # W14 #90: 403 przed rate-limitem
    # Dwa liczniki (audyt SEC-001): para IP+login (limit login_max_attempts) i samo IP (wyższy
    # limit, nigdy nie zerowany sukcesem). Sam login bez IP pozwoliłby zablokować cudze konto
    # z dowolnego miejsca; samo IP zerowane sukcesem pozwalało atakującemu kasować licznik
    # logowaniem na własne konto między próbami na cudze.
    ip_key = f"ip:{ip}"
    pair_key = f"ip:{ip}|login:{form.username.strip().lower()}"
    # SEC-012: trzeci licznik — konto ze wszystkich IP (rozproszony brute force), z
    # progresywną przerwą; liczony też dla nieistniejących loginów (bez wyroczni istnienia)
    acct_key = f"acct:{form.username.strip().lower()}"
    login_limiter.check(ip_key, limit=settings.login_max_attempts_per_ip)
    login_limiter.check(pair_key)
    login_limiter.check_account(acct_key)
    user = db.scalar(select(User).where(User.login == form.username))
    password_ok = verify_password(form.password, user.hashed_password) if user else (
        dummy_verify())  # stały narzut czasu, gdy login nie istnieje
    # ACL-005: konto serwisowe n8n chodzi tylko tokenem — hasłem się nie zaloguje
    if user and is_service_login(user.login):
        password_ok = False
    if not user or not user.is_active or not password_ok:
        login_limiter.register_failure(ip_key, pair_key, acct_key)
        record(db, entity_type="auth", entity_id=user.id if user else 0, field="login_failed",
               old_value=None, user=user, note=f"nieudane logowanie z {ip}",
               # GDPR-004: nieistniejący login bywa pomyłkowo wpisanym hasłem — tylko skrót
               new_value=form.username if user
               else f"{form.username[:2]}… ({len(form.username)} zn.)")
        if user and login_limiter.failures(acct_key) == settings.login_account_lock_after:
            _alert_account_lock(db, user, ip)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Błędny login lub hasło.")
    # tylko to konto z tego IP + licznik konta; licznik IP wygasa oknem
    login_limiter.reset(pair_key, acct_key)
    if user.totp_secret:
        # W14 #49: drugi krok — hasło poprawne, ale tokeny dopiero po kodzie TOTP
        return {"totp_required": True, "pending_token": create_pending_2fa_token(user)}
    record(db, entity_type="auth", entity_id=user.id, field="login",
           old_value=None, new_value=user.login, user=user, note=f"logowanie z {ip}")
    db.commit()
    access = create_access_token(user)
    refresh = issue_refresh_token(db, user.id)
    _set_auth_cookies(response, access, refresh)
    return Token(access_token=access, refresh_token=refresh)


def _consume_backup_code(user: User, code: str) -> bool:
    """Kod zapasowy 2FA: dopasowany hash jest usuwany z listy (jednorazowy)."""
    try:
        hashes = json.loads(user.totp_backup_codes or "[]")
    except ValueError:
        return False
    hashed = hash_backup_code(code)
    if hashed not in hashes:
        return False
    hashes.remove(hashed)
    user.totp_backup_codes = json.dumps(hashes)
    return True


@router.post("/2fa/verify", response_model=Token)
def verify_2fa(request: Request, response: Response, body: TwoFAVerifyIn,
               db: Session = Depends(get_db)):
    """Drugi krok logowania: kod TOTP lub kod zapasowy po poprawnym haśle."""
    ip = _client_ip(request)
    ensure_ip_not_blocked(db, ip)
    key = f"2fa:ip:{ip}"
    login_limiter.check(key)
    try:
        payload = _jwt.decode(body.pending_token, settings.secret_key, algorithms=[ALGORITHM])
    except _jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesja logowania wygasła.") from None
    if payload.get("type") != "totp_pending":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nieprawidłowy typ tokenu.")
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active or not user.totp_secret:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Konto nieaktywne lub nie istnieje.")
    # limit per konto obok per IP: rotacja IP nie daje nieograniczonych prób na 10^6 kodów
    user_key = f"2fa:user:{user.id}"
    login_limiter.check(user_key)
    step = totp_matched_step(user.totp_secret, body.code)
    # anty-replay: kod z już zaakceptowanego (lub starszego) kroku czasowego odrzucamy
    if step is not None and (user.totp_last_step is None or step > user.totp_last_step):
        user.totp_last_step = step
        ok = True
    else:
        ok = _consume_backup_code(user, body.code)
    if not ok:
        login_limiter.register_failure(key, user_key)
        record(db, entity_type="auth", entity_id=user.id, field="login_failed",
               old_value=None, new_value=user.login, user=user,
               note=f"błędny kod 2FA z {ip}")
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nieprawidłowy kod 2FA.")
    login_limiter.reset(key, user_key)
    record(db, entity_type="auth", entity_id=user.id, field="login",
           old_value=None, new_value=user.login, user=user, note=f"logowanie (2FA) z {ip}")
    db.commit()
    access = create_access_token(user)
    refresh = issue_refresh_token(db, user.id)
    _set_auth_cookies(response, access, refresh)
    return Token(access_token=access, refresh_token=refresh)


@router.post("/2fa/setup")
def setup_2fa(user: User = Depends(get_current_user)):
    """W14 #49: wygenerowanie sekretu TOTP (aktywacja w /2fa/enable). Każda rola (SEC-006);
    dla admina obowiązkowe przy REQUIRE_2FA_ADMIN (twofa_policy.py)."""
    if user.totp_secret:
        raise HTTPException(status.HTTP_409_CONFLICT, "2FA jest już włączone.")
    secret = generate_totp_secret()
    uri = (f"otpauth://totp/TIMPORYE:{user.login}?secret={secret}"
           "&issuer=TIMPORYE&algorithm=SHA1&digits=6&period=30")
    return {"secret": secret, "otpauth_url": uri}


@router.post("/2fa/enable")
def enable_2fa(body: TwoFAEnableIn, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    """Aktywacja 2FA: kod z aplikacji potwierdza, że sekret został zeskanowany.
    Zwraca 10 kodów zapasowych (jednorazowo; w bazie tylko hashe)."""
    if user.totp_secret:
        raise HTTPException(status.HTTP_409_CONFLICT, "2FA jest już włączone.")
    if not body.secret or not verify_totp(body.secret, body.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Nieprawidłowy kod — zeskanuj QR i spróbuj ponownie.")
    codes = generate_backup_codes()
    user.totp_secret = body.secret
    user.totp_backup_codes = json.dumps([hash_backup_code(c) for c in codes])
    record(db, entity_type="auth", entity_id=user.id, field="2fa_enabled",
           old_value=None, new_value=user.login, user=user, note="włączenie 2FA")
    db.commit()
    return {"backup_codes": codes}


# --- W14 #88: sesje aktywne (refresh tokeny) ---

def _current_jti(request: Request) -> str | None:
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        return None
    try:
        return _jwt.decode(raw, settings.secret_key, algorithms=[ALGORITHM],
                           options={"verify_exp": False}).get("jti")
    except _jwt.PyJWTError:
        return None


def list_user_sessions(db: Session, user_id: int, current_jti: str | None) -> list[SessionOut]:
    rows = db.scalars(select(RefreshToken).where(
        RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False),
        RefreshToken.expires_at > utcnow()).order_by(RefreshToken.created_at.desc())).all()
    return [SessionOut(id=r.id, created_at=r.created_at, expires_at=r.expires_at,
                       current=(r.jti == current_jti)) for r in rows]


@router.get("/sessions", response_model=list[SessionOut])
def my_sessions(request: Request, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    return list_user_sessions(db, user.id, _current_jti(request))


@router.delete("/sessions/{session_id}", status_code=204)
def revoke_my_session(session_id: int, request: Request,
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(RefreshToken, session_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono sesji.")
    # revoked_at zostaje NULL — odwołanie sesji nie otwiera okna łaski rotacji
    row.revoked = True
    record(db, entity_type="auth", entity_id=user.id, field="session_revoked",
           old_value=None, new_value=str(session_id), user=user,
           note=f"wylogowanie sesji z {_client_ip(request)}")
    db.commit()


@router.post("/sessions/revoke-others", status_code=204)
def revoke_other_sessions(request: Request, user: User = Depends(get_current_user),
                          db: Session = Depends(get_db)):
    """Wyloguj wszystkie inne sesje (bieżący refresh token zostaje)."""
    current = _current_jti(request)
    stmt = update(RefreshToken).where(
        RefreshToken.user_id == user.id, RefreshToken.revoked.is_(False))
    if current:
        stmt = stmt.where(RefreshToken.jti != current)
    db.execute(stmt.values(revoked=True))
    record(db, entity_type="auth", entity_id=user.id, field="sessions_revoked_others",
           old_value=None, new_value=user.login, user=user,
           note=f"wylogowanie pozostałych sesji z {_client_ip(request)}")
    db.commit()


@router.post("/refresh", response_model=Token)
def refresh(request: Request, response: Response,
            body: RefreshIn | None = None, db: Session = Depends(get_db)):
    raw = (body.refresh_token if body and body.refresh_token else None) \
        or request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Brak refresh tokenu.")
    user_id, rotated = consume_refresh_token(db, raw)
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Konto nieaktywne lub nie istnieje.")
    access = create_access_token(user)
    if not rotated:
        # okno łaski (wyścig kart, SEC-010): sam access; cookie refresh zostaje z rotacji
        # drugiej karty — zużyty token nie wydaje nowego refresh tokenu
        _set_access_cookie(response, access)
        return Token(access_token=access, refresh_token=None)
    new_refresh = issue_refresh_token(db, user.id)
    _set_auth_cookies(response, access, new_refresh)
    return Token(access_token=access, refresh_token=new_refresh)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    """Wylogowanie ze wszystkich urządzeń: podbija wersję sesji (unieważnia access
    tokeny), odwołuje refresh tokeny i czyści cookies. Działa też, gdy access token
    już wygasł — użytkownik ustalany best-effort z cookie refresh lub access."""
    raw = request.cookies.get(REFRESH_COOKIE) or request.cookies.get(ACCESS_COOKIE)
    user_id = user_id_from_token_lenient(raw) if raw else None
    user = db.get(User, user_id) if user_id is not None else None
    if user is not None:
        user.session_version += 1
        revoke_user_refresh_tokens(db, user.id)
        record(db, entity_type="auth", entity_id=user.id, field="logout",
               old_value=None, new_value=user.login, user=user,
               note=f"wylogowanie z {_client_ip(request)}")
        db.commit()
    clear_auth_cookies(response)


@router.post("/forgot-password", status_code=202)
def forgot_password(request: Request, body: ForgotPasswordIn, db: Session = Depends(get_db)):
    """Wysyła link resetu na e-mail konta. Zawsze zwraca 202 (bez zdradzania,
    czy konto istnieje — ochrona przed enumeracją). Rate-limit per IP."""
    ip = _client_ip(request)
    key = f"forgot:ip:{ip}"
    login_limiter.check(key)
    login_limiter.register_failure(key)  # każde żądanie liczy się do limitu
    email = body.email.strip().lower()
    user = db.scalar(select(User).where(func.lower(User.email) == email, User.is_active))
    if user and user.email:
        raw = create_password_reset_token(db, user.id)
        base = settings.public_base_url.rstrip("/") or str(request.base_url).rstrip("/")
        link = f"{base}/reset-password?token={raw}"
        record(db, entity_type="auth", entity_id=user.id, field="password_reset_requested",
               old_value=None, new_value=user.login, user=user, note=f"reset hasła z {ip}")
        db.commit()
        try:
            send_password_reset(user.email, user.full_name, link,
                                settings.password_reset_minutes)
        except Exception as exc:  # noqa: BLE001 — best-effort, nie ujawniamy stanu konta
            logger.warning("Nie udało się wysłać e-maila resetu: %s", exc)
    return {"detail": "Jeśli konto o tym adresie istnieje, wysłaliśmy link do resetu hasła."}


@router.post("/reset-password", status_code=200)
def reset_password(request: Request, body: ResetPasswordIn, db: Session = Depends(get_db)):
    """Ustawia nowe hasło na podstawie jednorazowego tokenu; unieważnia wszystkie sesje."""
    ip = _client_ip(request)
    reset_key = f"reset:ip:{ip}"
    login_limiter.check(reset_key)
    validate_password_policy(body.password)  # W14 #89
    user = consume_password_reset_token(db, body.token)
    if user is None:
        login_limiter.register_failure(reset_key)  # throttling prób zgadywania tokenu
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Link wygasł lub jest nieprawidłowy. Poproś o nowy.")
    user.hashed_password = hash_password(body.password)
    user.session_version += 1              # unieważnia access tokeny
    revoke_user_refresh_tokens(db, user.id)  # i refresh tokeny (wylogowanie wszędzie)
    record(db, entity_type="auth", entity_id=user.id, field="password_reset",
           old_value=None, new_value=user.login, user=user,
           note=f"reset hasła z {_client_ip(request)}")
    db.commit()
    return {"detail": "Hasło zostało zmienione. Zaloguj się nowym hasłem."}


@router.post("/change-password", status_code=200)
def change_password(request: Request, body: ChangePasswordIn,
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Zmiana własnego hasła przez zalogowanego użytkownika. Używane m.in. przy
    pierwszym logowaniu konta z zaproszenia (czyści must_change_password)."""
    # Zmiana dobrowolna (konto bez wymuszenia) wymaga potwierdzenia obecnego hasła —
    # blokuje ciche przejęcie konta skradzionym tokenem/otwartą sesją. Pierwsza zmiana
    # z zaproszenia (must_change_password) jest pominięta: user właśnie zalogował się hasłem tymczasowym.
    if not user.must_change_password:
        if not body.current_password or not verify_password(
                body.current_password, user.hashed_password):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Nieprawidłowe obecne hasło.")
    validate_password_policy(body.new_password)  # W14 #89
    user.hashed_password = hash_password(body.new_password)
    user.must_change_password = False
    user.session_version += 1                 # unieważnia access tokeny innych sesji
    revoke_user_refresh_tokens(db, user.id)   # + refresh tokeny — stare sesje giną
    record(db, entity_type="auth", entity_id=user.id, field="password_changed",
           old_value=None, new_value=user.login, user=user,
           note=f"zmiana hasła z {_client_ip(request)}")
    db.commit()
    return {"detail": "Hasło zostało zmienione."}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return serialize_user(db, user)


_UI_PREFS_MAX = 64_000  # ~64 KB — profil widoku to małe JSON-y, twardy limit na wypadek pętli


@router.get("/me/prefs")
def my_prefs(user: User = Depends(get_current_user)):
    """Profil widoku UI (kolumny/gęstość/zapisane widoki) — podąża za kontem."""
    import json
    try:
        data = json.loads(user.ui_prefs or "{}")
    except ValueError:
        data = {}
    return data if isinstance(data, dict) else {}


@router.put("/me/prefs")
def save_my_prefs(body: dict, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    import json
    raw = json.dumps(body, ensure_ascii=False)
    if len(raw) > _UI_PREFS_MAX:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            "Profil widoku jest zbyt duży.")
    user.ui_prefs = raw
    db.commit()
    return {"detail": "ok"}


@router.patch("/me/settings", response_model=UserOut)
def update_my_settings(body: MeSettingsIn, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    """Wąski self-update: dziś tylko przełącznik „powiadomienia tylko o obserwowanych"."""
    user.watch_only_notifications = body.watch_only_notifications
    db.commit()
    return serialize_user(db, user)
