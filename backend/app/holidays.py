"""Święta państwowe PL i PT (stałe + ruchome liczone od Wielkanocy)."""
import datetime
from functools import lru_cache


def _easter(year: int) -> datetime.date:
    """Niedziela wielkanocna (algorytm Meeusa/Jonesa/Butchera)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    weekday_off = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * weekday_off) // 451
    month, day = divmod(h + weekday_off - 7 * m + 114, 31)
    return datetime.date(year, month, day + 1)


@lru_cache(maxsize=64)
def holidays(year: int, country: str) -> frozenset[datetime.date]:
    e = _easter(year)
    d = datetime.date
    common = {d(year, 1, 1), d(year, 5, 1), d(year, 8, 15), d(year, 11, 1), d(year, 12, 25)}
    if country == "PT":
        days = common | {
            e - datetime.timedelta(days=2),          # Sexta-feira Santa
            e,                                        # Páscoa
            e + datetime.timedelta(days=60),          # Corpo de Deus
            d(year, 4, 25), d(year, 6, 10), d(year, 10, 5),
            d(year, 12, 1), d(year, 12, 8),
        }
    else:  # PL
        days = common | {
            e, e + datetime.timedelta(days=1),        # Wielkanoc, Poniedziałek Wielkanocny
            e + datetime.timedelta(days=49),          # Zesłanie Ducha Świętego (Zielone Świątki)
            e + datetime.timedelta(days=60),          # Boże Ciało
            d(year, 1, 6), d(year, 5, 3), d(year, 8, 15),
            d(year, 11, 11), d(year, 12, 24), d(year, 12, 26),
        }
    return frozenset(days)


def is_free_day(day: datetime.date, country: str = "PL") -> bool:
    return day.weekday() >= 5 or day in holidays(day.year, country)
