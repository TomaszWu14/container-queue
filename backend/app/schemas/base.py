"""Wspólna baza schematów (ORMModel), walidacja e-maila i zakresu dat operacyjnych."""
import datetime
import re

from pydantic import BaseModel, ConfigDict

# lekka walidacja e-maila bez zależności email-validator; pusty = brak adresu
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_email(value: str) -> str:
    if value and not _EMAIL_RE.match(value):
        raise ValueError("Nieprawidłowy adres e-mail.")
    return value


# daty operacyjne (ETA, awizacja, odprawa…) — rok spoza 2000–2099 to literówka albo niedopisany
# rok z pola daty w przeglądarce (np. „2” → 0002); 400/422 zamiast zapisu bzdury
OP_YEAR_MIN, OP_YEAR_MAX = 2000, 2099


def _validate_op_date(value: datetime.date | None) -> datetime.date | None:
    if value is not None and not OP_YEAR_MIN <= value.year <= OP_YEAR_MAX:
        raise ValueError(f"Rok daty musi być w zakresie {OP_YEAR_MIN}–{OP_YEAR_MAX}.")
    return value


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
