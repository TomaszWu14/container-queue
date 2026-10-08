"""Kto jest teraz w aplikacji — awatary w górnym pasku (jak w plikach SharePoint).

Karta przeglądarki co ~30 s wysyła sygnał (ekran + czy użytkownik coś robił od poprzedniego).
Stan w PAMIĘCI procesu, nie w bazie: to ulotna informacja, a aplikacja chodzi w jednym procesie
(docs/JEDNA-INSTANCJA.md) — restart = pasek zapełnia się od nowa w ciągu pół minuty.
- widoczny (online): ruch w ostatnich ONLINE_S sekundach; sama otwarta karta bez ruchu — nie,
- czasu bezczynności NIE wysyłamy nikomu (decyzja 2026-10-01: pasek pokazuje tylko online),
- wpis znika z pamięci: brak sygnału przez GONE_S (zamknięta karta, uśpiony komputer) albo wylogowanie.
Widoczność: tylko role wewnętrzne widzą i są widoczne. Konta zewnętrzne (spedytor, agencja celna)
i konta magazynu (m.in. zewnętrzny DLT — w modelu nie da się odróżnić magazynu własnego) — nie.
Między spółkami jak obserwujący (shares_company_scope): swoja spółka + konta grupowe (view_all)."""
import threading
import time
from types import SimpleNamespace
from typing import cast

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .deps import require_roles
from .models import Role, User
from .security import shares_company_scope

ONLINE_S = 5 * 60
GONE_S = 15 * 60
PRESENCE_ROLES = (Role.admin, Role.logistics, Role.purchasing, Role.sales)

_lock = threading.Lock()
_seen: dict[int, dict] = {}    # user_id → {name, role, path, active_at, seen_at, has_avatar}


class Ping(BaseModel):
    path: str = Field(default="/", max_length=120)
    active: bool = True


def _snapshot(now: float, viewer: User) -> list[dict]:
    with _lock:
        for uid in [u for u, e in _seen.items() if now - e["seen_at"] > GONE_S]:
            del _seen[uid]
        rows = [{"user_id": uid, "name": e["name"], "role": e["role"], "path": e["path"],
                 "has_avatar": e["has_avatar"]}
                for uid, e in _seen.items()
                if now - e["active_at"] <= ONLINE_S
                and shares_company_scope(viewer, cast(User, e["who"]))]
    return sorted(rows, key=lambda r: r["name"])


def record(user: User, ping: Ping, now: float | None = None) -> list[dict]:
    now = time.time() if now is None else now
    path = ping.path if ping.path.startswith("/") else "/"
    with _lock:
        entry = _seen.get(user.id)
        active_at = now if ping.active or entry is None else entry["active_at"]
        _seen[user.id] = {"name": user.full_name or user.login, "role": user.role.value,
                          "path": path.split("?")[0], "has_avatar": bool(user.avatar),
                          "active_at": active_at, "seen_at": now,
                          # pola reguły widoczności (nie obiekt ORM — sesja żądania się zamknie)
                          "who": SimpleNamespace(id=user.id, role=user.role,
                                                 company_id=user.company_id,
                                                 view_all_companies=user.view_all_companies)}
    return _snapshot(now, user)


def forget(user_id: int) -> None:
    with _lock:
        _seen.pop(user_id, None)


router = APIRouter(prefix="/api/presence", tags=["obecność"])
_viewers = Depends(require_roles(*PRESENCE_ROLES))


@router.post("")
def ping(body: Ping, user: User = _viewers) -> list[dict]:
    """Sygnał karty (co ~30 s i przy zmianie ekranu) → lista obecnych (z Tobą)."""
    return record(user, body)


@router.post("/leave", status_code=204)
def leave(user: User = _viewers) -> None:
    """Wylogowanie / zamknięcie karty — znikasz od razu, nie po 15 min."""
    forget(user.id)
