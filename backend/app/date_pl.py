"""Data dla człowieka w tekstach generowanych przez serwer (maile, SMS, eksporty, PDF, .eml).

Konwencja suity: dd.mm.rrrr (25.09.2026); ISO rrrr-mm-dd zostaje w bazie i w API/JSON.
Odpowiednik frontowego `formatDate()` z `frontend/src/dates.ts`; w szablonach Jinja
dostępny jako filtr `|date_pl`.
"""
import datetime


def date_pl(value, time: bool = False) -> str:
    """date / datetime / napis ISO → „25.09.2026" (`time=True` → „25.09.2026 14:05");
    None/pusty → "". Nierozpoznany napis wraca bez zmian (nie gubimy danych)."""
    if not value:
        return ""
    if isinstance(value, str):
        try:
            s = value.strip()
            value = (datetime.date if len(s) == 10 else datetime.datetime).fromisoformat(s)
        except ValueError:
            return value
    text = value.strftime("%d.%m.%Y")
    if time and isinstance(value, datetime.datetime):
        text += value.strftime(" %H:%M")
    return text
