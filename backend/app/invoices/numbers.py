"""Normalizacja liczb z dokumentów: '13,500.00' / '13.500,00' / '13 500,00' → Decimal."""
import re
from decimal import Decimal, InvalidOperation

_DASHES = str.maketrans({"−": "-", "–": "-", "—": "-", "‒": "-", "―": "-"})
_SCI = re.compile(r"^[-+]?\d+\.?\d*[eE][-+]?\d+$")
_RANGE = re.compile(r"\d[,.]\d[\d.,]*-\d")
# prefiks kraju przy dolarze („US$7,416.90”, „HK$ 12.00”)
_DOLLAR_PREFIX = re.compile(r"\b[A-Z]{1,3}\$", re.IGNORECASE)
# kody walut / jednostki doklejone do liczby w komórce („250.00 USD”, „1,000 PCS”, „12,5 kg”)
_TOKENS = re.compile(r"\b(USD|EUR|PLN|GBP|CHF|CNY|RMB|JPY|PCS|PC|SZT|KG|KGS|CTN|CTNS|SET|SETS|"
                     r"EA|PAIRS?|PRS|M|CM|MM|L|ML|G)\b\.?", re.IGNORECASE)


def normalize_number(raw, prefer_decimal: bool = False) -> Decimal | None:
    """None, gdy tekst nie jest liczbą (zakres cen, tokeny walut, śmieci OCR).

    `prefer_decimal`: kolumny wag/cen — „12,500” to 12.5 kg, nie 12 500; dla ilości i kwot
    (domyślnie) przecinek z dokładnie 3 cyframi to angielski separator tysięcy („1,000 pcs”)."""
    if raw is None:
        return None
    s = str(raw).strip().translate(_DASHES)
    if not s or len(s) > 50:
        return None
    if _SCI.match(s):
        try:
            return Decimal(s)
        except InvalidOperation:
            return None
    if _RANGE.search(s):
        return None
    s = _DOLLAR_PREFIX.sub("", s)
    s = _TOKENS.sub("", s)
    s = re.sub(r"[€$£¥\s\u00a0]", "", s)
    if not s or s in ("-", "n/a", "N/A"):
        return None
    dots, commas = s.count("."), s.count(",")
    if dots > 3 or commas > 3:
        return None
    try:
        if dots == 0 and commas == 0:
            return Decimal(s)
        if dots == 1 and commas == 0:
            # Kropka z dokładnie 3 cyframi („12.500”) jest dwuznaczna: europejskie tysiące
            # albo waga/cena z 3 miejscami. Wybieramy DZIESIĘTNĄ interpretację — europejski
            # separator tysięcy w dokumentach handlowych występuje praktycznie zawsze z częścią
            # dziesiętną („12.500,00”), a wagi z packing list mają 3 miejsca standardowo;
            # pomyłka w drugą stronę (×1000 w Excelu celnym) jest znacznie groźniejsza.
            return Decimal(s)
        if dots == 0 and commas == 1:
            # Przecinek z dokładnie 3 cyframi: angielskie tysiące („1,000 pcs”, „2,500 USD”)
            # — chyba że kolumna to waga/cena (prefer_decimal), gdzie „12,500” to 12.5
            int_p, frac_p = s.split(",", 1)
            digits = int_p.lstrip("-")
            if (not prefer_decimal and digits.isdigit() and digits != "0"
                    and len(frac_p) == 3 and frac_p.isdigit()):
                return Decimal(s.replace(",", ""))
            return Decimal(s.replace(",", "."))
        if dots > 1 and commas == 0:
            return Decimal(s.replace(".", ""))
        if dots == 0 and commas > 1:
            return Decimal(s.replace(",", ""))
        if s.rindex(".") > s.rindex(","):
            return Decimal(s.replace(",", ""))          # 1,234.56
        return Decimal(s.replace(".", "").replace(",", "."))  # 1.234,56
    except InvalidOperation:
        return None


def number_text(raw, prefer_decimal: bool = False) -> str:
    """Liczba jako tekst do Excela ('' gdy nie liczba). Zachowuje wartość, nie format."""
    value = normalize_number(raw, prefer_decimal=prefer_decimal)
    if value is None:
        return ""
    text = format(value.normalize(), "f")
    return text if text != "-0" else "0"
