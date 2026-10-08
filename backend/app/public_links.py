"""Twardy termin ważności publicznych linków (audyt SEC-014, PUBLIC_LINK_MAX_DAYS).

Niezależnie od własnych reguł linku (expires_at, wygasanie po realizacji kontenera) żaden
publiczny link — udostępnienie kontenera, portal klienta, DLT, strona kierowcy — nie działa
dłużej niż PUBLIC_LINK_MAX_DAYS od wystawienia. Liczone od created_at, więc obejmuje też
stare linki bez expires_at (działają do created_at + limit). Nowy link = nowy termin.
"""
import datetime

from .config import settings
from .models import utcnow


def hard_deadline(created_at: datetime.datetime) -> datetime.datetime:
    return created_at + datetime.timedelta(days=settings.public_link_max_days)


def capped(created_at: datetime.datetime,
           expires_at: datetime.datetime | None) -> datetime.datetime:
    """expires_at nowego linku przycięte do twardego limitu (None = sam limit)."""
    deadline = hard_deadline(created_at)
    return min(expires_at, deadline) if expires_at else deadline


def past_hard_limit(created_at: datetime.datetime | None) -> bool:
    return created_at is not None and hard_deadline(created_at) < utcnow()
