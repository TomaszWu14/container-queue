"""Draft SAD jako XML z WinSAD (eksport `SADUE`, Delta Brokers) — te same pola co odczyt PDF
(`sad_winsad.parse`), ale z nazwanych atrybutów zamiast układu wydruku. Agencja przysyła XML
zawsze, ale po PDF: dołącza do istniejącej wersji draftu i zastępuje odczyt z PDF.

To wewnętrzny format WinSAD, nie komunikat ZC415 z PUESC — inna agencja/wersja programu może go
zmienić; wtedy `parse` zwraca None („to nie ten XML”), a draft zostaje przy odczycie z PDF."""
import xml.etree.ElementTree as ET  # nosec B405 — DTD/encje odrzucamy przed parsowaniem (_has_dtd)
from decimal import Decimal, InvalidOperation
from xml.parsers import expat  # nosec B407 — tylko wykrycie DTD, bez budowania drzewa
INVOICE_DOCS = ("N935", "N325")           # faktura, faktura proforma [12 03]


def _has_dtd(content: bytes) -> bool:
    """XXE / „billion laughs” wymagają DTD — eksport go nie ma. Sprawdza expat (sam rozpoznaje
    kodowanie: UTF-16/BOM/deklaracja), nie szukanie bajtów: `<!DOCTYPE` w UTF-16 to inne bajty.
    Handler rzuca już na początku DOCTYPE — encje nie zdążą się rozwinąć."""
    def _reject(*_args):
        raise ValueError("DTD")
    parser = expat.ParserCreate()
    parser.StartDoctypeDeclHandler = _reject
    parser.EntityDeclHandler = _reject
    try:
        parser.Parse(content, True)
    except ValueError:
        return True
    except expat.ExpatError:
        return False   # niepoprawny XML — fromstring niżej i tak zwróci None
    return False


def _num(raw: str | None) -> str | None:
    """Liczba z kropką dziesiętną jak w eksporcie → tekst bez zbędnych zer (jak sad_parse._text)."""
    try:
        return format(Decimal(raw).normalize(), "f") if raw else None
    except InvalidOperation:
        return None


def _item(no: int, poz: ET.Element) -> dict:
    code = poz.find("P33KodTowaru")
    cn = (code.get("KodCN") or "") if code is not None else ""
    # ponytail: nazwa atrybutu j. uzupełniających [18 02] niepotwierdzona na próbce (CN bez j. uzup.);
    # bierzemy pierwszy atrybut P41*, gdy pierwszy XML z j. uzup. pokaże nazwę — przypnij ją tu
    suppl = next((v for k, v in poz.attrib.items() if k.startswith("P41")), None)
    return {"no": no, "cn": cn[:8], "value": _num(poz.get("P42WartoscPozycji")),
            "net_mass": _num(poz.get("P38MasaNetto")), "suppl_qty": _num(suppl),
            "origin": poz.get("P34KrajPochodz")}


def parse(content: bytes) -> tuple[dict, str] | None:
    """Pola jak `sad_winsad.parse` (+ `sad_no`) i tekst z numerami dokumentów [12 03] (szukanie
    faktur w porównaniu) albo None — to nie XML draftu z WinSAD."""
    if _has_dtd(content):
        return None
    try:
        root = ET.fromstring(content)  # nosec B314 — bez DTD (_has_dtd wyżej), encje zewnętrzne nieobsługiwane
    except ET.ParseError:
        return None
    if root.tag != "SADUE":
        return None
    items = [_item(no, poz) for no, poz in enumerate(root.iter("PozycjeSADu"), start=1)]
    totals = [_num(z.get("P22WartoscZestawu")) for z in root.iter("ZestawySADu")]
    total = format(sum(Decimal(t) for t in totals if t is not None), "f") \
        if totals and None not in totals else None
    container = next((k.get("Numer") for k in root.iter("Kontenery") if k.get("Numer")), None)
    context = root.find("P1Kontekst")
    docs = [d.get("NrDokum") or "" for d in root.iter("DokumWymag")
            if d.get("KodDokum") in INVOICE_DOCS]
    fields = {"currency": root.get("P22WalutaSADu"), "total": total,
              "country_dispatch": root.get("P15aKodKrajuWys"),
              "container": container.replace(" ", "") if container else None, "items": items,
              "sad_no": context.get("IDSADu") if context is not None else None}
    return fields, "\n".join(dict.fromkeys(docs))
