"""Obowiązkowe 2FA dla administratorów (audyt SEC-006, REQUIRE_2FA_ADMIN — domyślnie wyłączone).

Admin bez włączonego 2FA dalej czyta dane, ale każda zmiana poza własnym kontem
(`/api/auth/*`: włączenie 2FA, zmiana hasła, sesje, ustawienia, wylogowanie) kończy się 403,
dopóki nie włączy 2FA. Panel po zalogowaniu pokazuje wtedy ekran włączania 2FA
(`UserOut.must_enroll_2fa`). Pozostałe role mogą włączyć 2FA dobrowolnie (Profil).
Zgubiony telefon: 2FA wyłącza INNY administrator (`POST /api/users/{id}/2fa/disable`, audyt)."""
from fastapi import HTTPException, Request, status

from .config import settings
from .models import Role, User

_READ_METHODS = ("GET", "HEAD", "OPTIONS")


def must_enroll_2fa(user: User) -> bool:
    if not settings.require_2fa_admin or user.role != Role.admin or user.totp_secret:
        return False
    if getattr(user, "impersonated", False):
        return False            # podgląd „jako rola” — tylko odczyt, nie konto admina
    # konto demo (DEMO_READONLY_LOGINS) i tak niczego nie zmieni — bez ekranu 2FA
    demo = {x.strip().lower() for x in settings.demo_readonly_logins.split(",") if x.strip()}
    return user.login.lower() not in demo


def enforce_admin_2fa(request: Request, user: User) -> None:
    if (request.method not in _READ_METHODS
            and not request.url.path.startswith("/api/auth/") and must_enroll_2fa(user)):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Włącz uwierzytelnianie dwuskładnikowe (2FA) w profilu — "
                            "jest wymagane dla administratorów.")
