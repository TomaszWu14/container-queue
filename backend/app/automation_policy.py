"""Zasady konta serwisowego automatyzacji n8n (audyt ACL-005) — mniejsze skutki wycieku tokenu.

Token `X-Automation-Token` jest sekretem długoterminowym, a jego zakres = rola konta serwisowego:
- konto serwisowe nie może mieć roli admin (403) — admin przez token = zarządzanie kontami;
  `view_all_companies` zostaje dozwolone (importy SAP całej grupy, #21);
- logowanie HASŁEM na konto serwisowe jest zablokowane, gdy integracja jest włączona;
- AUTOMATION_ALLOWED_CIDRS (opcjonalnie): token działa tylko z tych sieci (np. sieć Dockera n8n);
- rotacja bez przestoju: AUTOMATION_API_TOKEN_PREVIOUS akceptowany obok nowego do czasu
  przełączenia credentiala w n8n (procedura: docs/N8N.md);
- AUTOMATION_TOKEN_EXPIRES (opcjonalnie, RRRR-MM-DD): po tej dacie token nie działa.
"""
import datetime
import ipaddress
import logging
import secrets

from fastapi import HTTPException, Request, status

from .config import settings
from .models import Role, User, today_pl
from .rate_limit import client_ip

logger = logging.getLogger(__name__)


def token_matches(provided: str) -> bool:
    raw = provided.encode("utf-8")
    ok = False
    for token in (settings.automation_api_token, settings.automation_api_token_previous):
        if token:   # bez skrótu: czas porównania nie zdradza, który token pasuje
            ok |= secrets.compare_digest(raw, token.encode("utf-8"))
    return ok


def _expired() -> bool:
    raw = settings.automation_token_expires.strip()
    if not raw:
        return False
    try:
        return today_pl() > datetime.date.fromisoformat(raw)
    except ValueError:
        logger.error("AUTOMATION_TOKEN_EXPIRES=%r — oczekiwano RRRR-MM-DD; token odrzucony", raw)
        return True   # literówka w dacie nie może otworzyć tokenu bez terminu


def _ip_allowed(ip: str, cidrs: list[str]) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for cidr in cidrs:
        try:
            if addr in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            logger.warning("AUTOMATION_ALLOWED_CIDRS: pomijam niepoprawny wpis %r", cidr)
    return False


def check_token_use(request: Request) -> None:
    """Po poprawnym tokenie: termin ważności i sieć źródłowa."""
    if _expired():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Token automatyzacji wygasł (AUTOMATION_TOKEN_EXPIRES) — "
                            "wygeneruj nowy, patrz docs/N8N.md.")
    cidrs = [c.strip() for c in settings.automation_allowed_cidrs.split(",") if c.strip()]
    if cidrs and not _ip_allowed(client_ip(request), cidrs):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Token automatyzacji użyty spoza dozwolonych sieci "
                            "(AUTOMATION_ALLOWED_CIDRS).")


def check_service_account(user: User) -> None:
    if user.role == Role.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            f"Konto serwisowe automatyzacji „{user.login}” nie może mieć roli "
                            "admin — ustaw np. logistics (docs/N8N.md).")


def is_service_login(login: str) -> bool:
    """Logowanie hasłem na konto serwisowe — zablokowane, gdy integracja jest włączona."""
    return bool(settings.automation_api_token) and login == settings.automation_actor_login
