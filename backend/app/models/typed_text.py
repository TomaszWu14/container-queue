"""DB-008: typowane kopie kolumn tekstowych — ilości SAP (Numeric) i daty PO (Date).

Tekst zostaje „surowy” (to, co przyszło z pliku), a obok liczba/data do obliczeń, sortowania
i filtrów. `mirror()` podpina nasłuch ORM „set”: każdy zapis tekstu (import, API, record_changes)
od razu aktualizuje kopię. Wstawienia rdzeniowe (`insert(...)` bez ORM) nasłuchu nie widzą —
w aplikacji ich dla tych tabel nie ma; istniejące wiersze wypełnia migracja typed001.
"""
import datetime
from decimal import Decimal

from sqlalchemy import event

from ..invoices.numbers import normalize_number

__all__ = ["mirror", "parse_quantity", "parse_text_date", "quantity_value"]

_QTY_MAX = Decimal("99999999999.999")   # Numeric(14, 3)
_DATE_FORMATS = ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y",
                 "%Y.%m.%d", "%Y/%m/%d")


def parse_quantity(raw) -> Decimal | None:
    """Ilość z tekstu („1.234,000”, „1 200,5”, „1,234.50”, „12,5”) → Decimal z 3 miejscami
    albo None. Pojedynczy przecinek = separator dziesiętny (format PL eksportu SAP) — tak
    samo jak tabular.to_float, którym dotąd liczyły packer i status przyjęć."""
    if raw is None or raw == "":
        return None
    number = normalize_number(raw, prefer_decimal=True)
    if number is None or not number.is_finite() or abs(number) > _QTY_MAX:
        return None
    return number.quantize(Decimal("0.001"))


def parse_text_date(raw) -> datetime.date | None:
    """Data z tekstu arkusza („15.10.2026”, „15.10.26”, „2026-10-15 00:00:00”) albo None dla
    wpisów typu „Confirmed”/„TBC” i dat spoza 2000–2100 (literówki roku)."""
    s = (raw or "").strip().split(" ")[0].split("T")[0]
    for fmt in _DATE_FORMATS:
        try:
            day = datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
        if 2000 <= day.year <= 2100:
            return day
    return None


def quantity_value(number, raw) -> float | None:
    """Liczba do obliczeń: typowana kolumna, a gdy pusta (tekst nieparsowalny albo wiersz
    sprzed migracji) — parsowanie tekstu jak dotąd."""
    if number is not None:
        return float(number)
    parsed = parse_quantity(raw)
    return None if parsed is None else float(parsed)


def mirror(text_attr, typed_name: str, parse) -> None:
    """Zapis `text_attr` (atrybut modelu) ustawia też `typed_name` = parse(tekst)."""
    @event.listens_for(text_attr, "set", retval=False)
    def _mirror(target, value, _old, _initiator):
        setattr(target, typed_name, parse(value))
