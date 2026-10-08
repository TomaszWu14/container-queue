"""Klocki firmowych maili (HTML) i escapowanie dla pozostałych, krótkich fragmentów.

Nowe maile i pisma: szablony Jinja2 z autoescape (html_templates.render, ARCH-008)."""
import html

from .date_pl import date_pl
from .html_templates import env, render


def esc(value, empty: str = "") -> str:
    """Escapuje wartość do bezpiecznego wstawienia w HTML (chroni przed wstrzyknięciem).
    Pusta wartość (None/"") → `empty` (np. "—" w pismach i drukach)."""
    return html.escape(str(value or "")) or empty


# --- klocki firmowych maili z tabelą kontenerów (awizacja, kolejka dnia, reklamacja) ---

# jedyne źródło: makra w templates/mail/_parts.html (szablony wołają je same, bez Markup)
_PARTS = env.get_template("mail/_parts.html").module
TABLE_OPEN = str(_PARTS.table_open())
HEAD_ROW = str(_PARTS.head_row())
SIGNATURE = str(_PARTS.signature())
RED = "color:#c00000;font-weight:bold"


# klucz → (nagłówek, surowa wartość — escapuje szablon, domyślny styl komórki, wielowierszowe)
_COLUMNS = {
    "unload": ("DATA ROZŁADUNKU", lambda c: date_pl(c.notify_date), "", False),
    "eta": ("ETA", lambda c: date_pl(c.eta), "", False),
    "container": ("NR KONTENERA", lambda c: c.container_no, RED, False),
    "supplier": ("DOSTAWCA", lambda c: c.supplier.name if c.supplier else "", "", False),
    "vessel": ("STATEK", lambda c: c.vessel, "", False),
    "transport": ("TRANSPORT", lambda c: c.transport_type.value if c.transport_type else "",
                  "background:#bdd7ee", False),
    "orders": ("NR ZAMÓWIENIA",
               lambda c: c.order_numbers or (c.order.number if c.order else ""), "", True),
    "warehouse": ("MAGAZYN", lambda c: c.warehouse.name if c.warehouse else "", "", False),
    "delivery": ("NR DOSTAWY", lambda c: c.incoming_delivery_no, "", True),
    "rf": ("NR RF", lambda c: c.rf_number, "", False),
}


def table_context(containers, columns) -> dict:
    """Kontekst szablonu mail/container_table.html (także przez {% include %} w mailach):
    nagłówki i wiersze (wartość surowa, styl, wielowierszowe). `columns` to klucze z _COLUMNS
    albo krotki (klucz, styl) nadpisujące domyślny styl komórki."""
    cols = []
    for col in columns:
        key, style = col if isinstance(col, tuple) else (col, None)
        header, value, default, lines = _COLUMNS[key]
        cols.append((header, value, default if style is None else style, lines))
    return {"headers": [header for header, _, _, _ in cols],
            "rows": [[(str(value(c) or ""), style, lines) for _, value, style, lines in cols]
                     for c in containers]}


def container_table(containers, columns) -> str:
    """Tabela kontenerów w stylu firmowego maila (zielone wiersze) jako gotowy HTML."""
    return render("mail/container_table.html", **table_context(containers, columns)).rstrip("\n")

