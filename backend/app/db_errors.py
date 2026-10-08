"""DB-007: naruszenie biznesowego klucza unikalnego (indeksy ux_*) → 409 z komunikatem.

Klucze pilnuje baza (migracja chk001), więc każda ścieżka zapisu (API, PATCH, zmiana statusu,
import) kończy się tym samym IntegrityError — jeden handler zamiast sprawdzeń w routerach.
Inne naruszenia (CHECK, FK) zostają błędem 500: znaczą błąd w kodzie, nie w danych
użytkownika. Postgres podaje nazwę indeksu, SQLite (testy) — listę kolumn.
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

UNIQUE_MESSAGES = {
    ("ux_containers_active_no", "containers.company_id, containers.container_no"):
        "Kontener o tym numerze jest już w kolejce tej spółki (niezrealizowany). "
        "Otwórz istniejący rekord albo najpierw zakończ poprzednią dostawę.",
}


def conflict_message(exc: IntegrityError) -> str | None:
    text = str(exc.orig)
    for keys, message in UNIQUE_MESSAGES.items():
        if any(k in text for k in keys):
            return message
    return None


async def integrity_error_handler(_request: Request, exc: IntegrityError):
    message = conflict_message(exc)
    if message is None:
        raise exc   # nieznane naruszenie — jak dotąd 500 (ServerErrorMiddleware)
    return JSONResponse(status_code=409, content={"detail": message})
