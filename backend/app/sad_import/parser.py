"""Odczyt PDF „Podgląd danych zgłoszenia celnego importowego” z WinSAD (Huzar Software,
wydruk z pliku ZC415) — pełne dane: nagłówek, wszystkie pozycje, opłaty, podsumowanie.

Pułapki układu (sprawdzone na drafach Delta Brokers, testy: tests/fixtures/sad):
- dwie kolumny — lewa (opis, CN, dokumenty, opłaty) od x≈27, prawa (wartości, masy, kraje)
  od x≈441; tniemy na `COLUMN_X` i czytamy kolumny osobno (`extract_text` całej strony skleja
  je w jedną linię);
- górny blok strony 1 (nadawca, stan AIS, daty, LRN) jest jednokolumnowy — z pełnego tekstu
  strony, regexami liniowymi;
- pozycje przechodzą przez strony: region pozycji = od słowa „Pozycja” (bywa sklejone:
  „Pozycja 1Towar:”) do następnej pozycji albo „Podsumowanie”, także przez granicę strony;
- etykiety łamią się między liniami („[14⏎08]”) — wzorce po spłaszczeniu białych znaków;
- tabela opłat [14 03] zawija się nieregularnie — blok kodu parsowany niezależnie od kolejności.

Kwoty wyłącznie jako Decimal. Dane osobowe (osoba kontaktowa, telefon, e-mail) nie są
odczytywane ani przechowywane — żaden wzorzec ich nie obejmuje."""
import datetime
import io
import pathlib
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

COLUMN_X = 435.0
_NUM = r"(-?\d+(?:[.,]\d+)?)"


class SadFormatError(ValueError):
    """Plik nie jest podglądem zgłoszenia z WinSAD (albo nie da się go otworzyć)."""


@dataclass
class Oplata:
    kod: str                               # A00 cło, B00 VAT, …
    podstawa: Decimal | None = None        # PLN
    stawka: Decimal | None = None          # w procentach: 12 = 12 %
    kwota_wyliczona: Decimal | None = None
    kwota_nalezna: Decimal | None = None   # pełne PLN
    metoda: str | None = None              # R / G; brak przy 0 PLN


@dataclass
class Dokument:
    kod: str                               # N935 faktura, N325 proforma, 1DK7, …
    numer: str


@dataclass
class Pozycja:
    nr: int
    opis: str = ""
    cn: str = ""
    taric: str = ""
    kody_dodatkowe: list[str] = field(default_factory=list)
    dokument_poprzedni: str = ""
    dokumenty: list[Dokument] = field(default_factory=list)
    wartosc_fakturowa: Decimal | None = None
    metoda_wyceny: str = ""
    preferencje: str = ""
    procedura: str = ""
    kraj_pochodzenia: str = ""
    masa_netto: Decimal | None = None
    ilosc_uzup: Decimal | None = None
    wartosc_stat: Decimal | None = None
    doliczenia_ak: list[Decimal] = field(default_factory=list)
    doliczenia_ca: list[Decimal] = field(default_factory=list)
    opakowania_liczba: int | None = None
    opakowania_rodzaj: str = ""
    oplaty: list[Oplata] = field(default_factory=list)
    kwota_ogolem: Decimal | None = None
    vat_fr7: str = ""
    grn: str = ""

    @property
    def faktury(self) -> list[str]:
        return [d.numer for d in self.dokumenty if d.kod == "N935"]

    @property
    def proformy(self) -> list[str]:
        return [d.numer for d in self.dokumenty if d.kod == "N325"]

    @property
    def suma_ak(self) -> Decimal:
        return sum(self.doliczenia_ak, Decimal(0))

    @property
    def suma_ca(self) -> Decimal:
        return sum(self.doliczenia_ca, Decimal(0))

    def oplata(self, kod: str) -> Oplata | None:
        return next((o for o in self.oplaty if o.kod == kod), None)


@dataclass
class Zgloszenie:
    numer: str = ""
    stan_ais: str = ""
    data_zgloszenia: datetime.date | None = None
    data_wydruku: datetime.datetime | None = None
    nr_referencyjny: str = ""
    lrn: str = ""
    nadawca: str = ""
    odbiorca: str = ""
    zglaszajacy: str = ""
    importer_nip: str = ""
    importer_eori: str = ""
    zglaszajacy_nip: str = ""
    typ_zgloszenia: str = ""
    uc_zgloszenia: str = ""
    liczba_pozycji: int | None = None
    liczba_opakowan: int | None = None
    kurs: Decimal | None = None
    eksporter: str = ""
    kontenery: list[str] = field(default_factory=list)
    masa_brutto: Decimal | None = None
    wartosc_faktur: Decimal | None = None
    waluta: str = ""
    kraj_przeznaczenia: str = ""
    kraj_wysylki: str = ""
    rodzaj_transakcji: str = ""
    incoterm: str = ""
    miejsce_dostawy: str = ""
    lokalizacja_pozwolenie: str = ""
    vat_fr7: str = ""
    grn: str = ""
    pozycje: list[Pozycja] = field(default_factory=list)
    podsumowanie: dict[str, tuple[Decimal, str | None]] = field(default_factory=dict)
    plik: str = ""

    def suma_naleznych(self, kod: str) -> Decimal:
        return sum(((o.kwota_nalezna or Decimal(0)) for p in self.pozycje for o in p.oplaty
                    if o.kod == kod), Decimal(0))


# --- drobne narzędzia --------------------------------------------------------------------

def _dec(raw: str | None) -> Decimal | None:
    if not raw:
        return None
    try:
        return Decimal(raw.replace(" ", "").replace(",", "."))   # kurs ma przecinek, reszta kropkę
    except InvalidOperation:
        return None


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _de(group: str, element: str) -> str:
    """„[14 08]:” — etykieta bywa złamana („[14⏎08]”); po spłaszczeniu to jedna spacja."""
    return r"\[\s*" + group + r"\s*" + element + r"\s*\]\s*:?\s*"


def _find(pattern: str, text: str, group: int = 1, flags: int = 0) -> str:
    match = re.search(pattern, text, flags)
    return match.group(group).strip() if match else ""


def _find_dec(pattern: str, text: str) -> Decimal | None:
    return _dec(_find(pattern, text))


def _find_int(pattern: str, text: str) -> int | None:
    value = _find(pattern, text)
    return int(value) if value.isdigit() else None


# --- regiony strony ----------------------------------------------------------------------

@dataclass
class _Mark:
    page: int
    top: float
    kind: str                  # "item" / "summary"
    nr: int | None = None


def _marks(pdf) -> list[_Mark]:
    """Początki pozycji i podsumowania opłat (słowo „Pozycja” jest wyśrodkowane, x≈274)."""
    marks = []
    for index, page in enumerate(pdf.pages):
        words = page.extract_words()
        for pos, word in enumerate(words):
            if word["x0"] >= COLUMN_X:
                continue
            match = re.match(r"Pozycja(\d*)", word["text"])
            if match:
                digits = match.group(1)
                if not digits and pos + 1 < len(words) and abs(words[pos + 1]["top"] - word["top"]) < 2:
                    digits = _find(r"^(\d+)", words[pos + 1]["text"])   # „Pozycja 1Towar:”
                if digits:
                    marks.append(_Mark(index, word["top"], "item", int(digits)))
            elif word["text"].startswith("Podsumowanie"):
                marks.append(_Mark(index, word["top"], "summary"))
    return sorted(marks, key=lambda m: (m.page, m.top))


def _region(pdf, start: tuple[int, float], end: tuple[int, float]) -> tuple[str, str]:
    """Tekst lewej i prawej kolumny od `start` do `end` (strona, y), także przez strony."""
    lefts, rights = [], []
    for index in range(start[0], end[0] + 1):
        page = pdf.pages[index]
        top = max(0.0, start[1] - 1) if index == start[0] else 0.0
        bottom = min(float(page.height), end[1] - 1) if index == end[0] else float(page.height)
        if bottom - top < 1:
            continue
        lefts.append(page.crop((0, top, COLUMN_X, bottom)).extract_text() or "")
        rights.append(page.crop((COLUMN_X, top, page.width, bottom)).extract_text() or "")
    return "\n".join(lefts), "\n".join(rights)


# --- nagłówek ----------------------------------------------------------------------------

def _header(z: Zgloszenie, top_text: str, left: str, right: str) -> None:
    z.numer = _find(r"zgłoszenia celnego importowego nr\s*(\d+)", top_text)
    z.stan_ais = _find(r"Stan AIS:\s*(.+?)\s*$", top_text, flags=re.M)
    raw_date = _find(r"Deklarowana data zgłoszenia:\s*(\d{4}-\d{2}-\d{2})", top_text)
    z.data_zgloszenia = datetime.date.fromisoformat(raw_date) if raw_date else None
    raw_print = _find(r"Data wygenerowania wydruku:\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})", top_text)
    z.data_wydruku = datetime.datetime.strptime(raw_print, "%Y-%m-%d %H:%M") if raw_print else None
    z.nr_referencyjny = _find(r"Numer referencyjny\s+(\S+)", top_text)
    z.lrn = _find(r"Numer LRN\s*" + _de("12", "09") + r"(\S+)", top_text)
    z.nadawca = _find(r"^Nadawca:\s*(.+?)\s*$", top_text, flags=re.M)
    z.odbiorca = _find(r"^Odbiorca:\s*(.+?)\s*$", top_text, flags=re.M)
    z.zglaszajacy = _find(r"^Zgłaszający:\s*(.+?)\s*$", top_text, flags=re.M)

    lf, rf = _flat(left), _flat(right)
    both = lf + " " + rf
    z.importer_nip = _find(r"Importer\s*" + _de("13", "04") + r".*?NIP:\s*(\d{10})", lf)
    z.importer_eori = _find(r"Importer\s*" + _de("13", "04") + r".*?identyfikacyjny:\s*([A-Z]{2}\w+)", lf)
    z.zglaszajacy_nip = _find(r"Zgłaszający\s*" + _de("13", "05") + r".*?NIP:\s*(\d{10})", lf)
    z.typ_zgloszenia = _find(r"Typ zgł\.\s*\[11 01/02\]:\s*([A-Z]{2}(?:\s*,\s*[A-Z])?)", both)
    z.uc_zgloszenia = _find(r"UC zgłoszenia:\s*([A-Z]{2}\d+)", both)
    z.liczba_pozycji = _find_int(r"Liczba pozycji:\s*(\d+)", both)
    z.liczba_opakowan = _find_int(r"Liczba opakowań:\s*(\d+)", both)
    z.kurs = _find_dec(r"Kurs waluty\s*" + _de("14", "09") + _NUM, both)
    z.eksporter = _find(r"Eksporter\s*" + _de("13", "01") + r"(.*?)\s*Adres:", lf).rstrip(".")
    z.kontenery = re.findall(r"Nr kontenera:\s*([A-Z]{4}\d{7})", lf)
    z.masa_brutto = _find_dec(r"Masa brutto\s*" + _de("18", "04") + _NUM, rf)
    total = re.search(r"Wartość faktur\s*" + _de("14", "06") + _NUM + r"\s*([A-Z]{3})", rf)
    if total:
        z.wartosc_faktur, z.waluta = _dec(total.group(1)), total.group(2)
    z.kraj_przeznaczenia = _find(r"Kraj przeznaczenia\s*" + _de("16", "03") + r"([A-Z]{2})\b", rf)
    z.kraj_wysylki = _find(r"Kraj wysyłki\s*" + _de("16", "06") + r"([A-Z]{2})\b", rf)
    z.rodzaj_transakcji = _find(r"Rodzaj transakcji\s*" + _de("99", "05") + r"(\d+)", rf)
    terms = re.search(r"Warunki dostawy\s*" + _de("14", "01") + r"([A-Z]{3})\s*,\s*([^,]+,\s*[A-Z]{2})\b", rf)
    if terms:
        z.incoterm, z.miejsce_dostawy = terms.group(1), terms.group(2).strip()
    z.lokalizacja_pozwolenie = _find(r"Lokalizacja towarów\s*" + _de("16", "15")
                                     + r".*?nr pozwolenia:\s*([A-Z0-9]+)", lf)


# --- pozycja -----------------------------------------------------------------------------

def _documents(left: str) -> list[Dokument]:
    """[12 03]: „KOD-NUMER poz. 0; …” — numer bywa złamany na końcu linii po „-”."""
    match = re.search(r"Dokumenty załączone\s*\[12 03\]:\s*(.*?)(?=\n(?:Dodatkowe|Zabezpieczenia|"
                      r"Opakowania|Cła|Pozycja)|\Z)", left, re.S)
    if not match:
        return []
    joined = ""
    for line in match.group(1).splitlines():
        line = line.strip()
        joined += line if joined.endswith("-") or not joined else " " + line
    out = []
    for part in joined.split(";"):
        part = re.sub(r"\s*poz\.\s*\d+\s*$", "", part.strip())
        if "-" in part:
            code, number = part.split("-", 1)
            out.append(Dokument(code.strip(), number.strip()))
    return out


def _fee(block: str) -> Oplata:
    """Blok „A00 Kwota: 107055 PLN, stawka opł.: 12846 PLN R 12%, kwota opł.: 12846.6 PLN”
    w dowolnym zawinięciu: podstawa, stawka %, kwota wyliczona; reszta = należna + metoda."""
    text = _flat(block)
    fee = Oplata(kod=text[:3])
    patterns = {"podstawa": r"Kwota:\s*" + _NUM + r"\s*PLN",
                "stawka": r"(\d+(?:\.\d+)?)\s*%",
                "kwota_wyliczona": r"kwota opł\.:\s*" + _NUM + r"\s*PLN"}
    for name, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            setattr(fee, name, _dec(match.group(1)))
            text = text[:match.start()] + " " + text[match.end():]
    due = re.search(_NUM + r"\s*PLN(?:\s+([A-Z])\b)?", text[3:])
    if due:
        fee.kwota_nalezna, fee.metoda = _dec(due.group(1)), due.group(2)
    return fee


def _fees(left: str) -> list[Oplata]:
    section = _find(r"Cła i podatki\s*\[14 03\]:(.*?)(?:Kwota opłat i podatków ogółem|\Z)", left,
                    flags=re.S)
    blocks = re.split(r"(?m)^(?=[A-Z]\d{2} Kwota:)", section)
    return [_fee(b) for b in blocks if re.match(r"[A-Z]\d{2} Kwota:", b)]


def _item(nr: int, left: str, right: str) -> Pozycja:
    lf, rf = _flat(left), _flat(right)
    item = Pozycja(nr=nr)
    item.opis = _find(r"Opis\s*" + _de("18", "05") + r"(.*?),\s*kod CN", lf)
    codes = re.search(r"kod CN\s*" + _de("18", "09") + r"(\d{8})\s*,\s*kod TARIC:\s*(\d{2})", lf)
    if codes:
        item.cn, item.taric = codes.group(1), codes.group(2)
    extra = _find(r"kody\s+dod\.\s*" + _de("18", "07") + r"([A-Z0-9]{4}(?:\s*,\s*[A-Z0-9]{4})*)", lf)
    item.kody_dodatkowe = [c.strip() for c in extra.split(",") if c.strip()]
    item.dokument_poprzedni = _find(r"Dokumenty poprzednie\s*" + _de("12", "01")
                                    + r"(.*?)\s*(?=Dokumenty załączone|$)", lf)
    item.dokumenty = _documents(left)
    packages = re.search(r"Opakowania\s*" + _de("18", "06") + r".*?:\s*(\d+)/([A-Z0-9]+)", lf)
    if packages:
        item.opakowania_liczba, item.opakowania_rodzaj = int(packages.group(1)), packages.group(2)
    item.oplaty = _fees(left)
    item.kwota_ogolem = _find_dec(r"Kwota opłat i podatków ogółem\s*" + _de("14", "16") + _NUM, lf)
    item.vat_fr7 = _find(r"Rola:\s*FR7\s*,\s*nr VAT:\s*([A-Z]{2}\w+)", lf)
    item.grn = _find(r"GRN:\s*([A-Z0-9]+)", lf)

    item.wartosc_fakturowa = _find_dec(r"Wartość fakturowa poz\.\s*" + _de("14", "08") + _NUM, rf)
    item.metoda_wyceny = _find(r"Metoda wyceny\s*" + _de("14", "10") + r"(\w+)", rf)
    item.preferencje = _find(r"Preferencje\s*" + _de("14", "11") + r"(\w+)", rf)
    item.procedura = _find(r"Procedura\s*" + _de("11", "09") + r"(\w+)", rf)
    item.kraj_pochodzenia = _find(r"Kraj pochodzenia\s*" + _de("16", "08") + r"([A-Z]{2})\b", rf)
    item.masa_netto = _find_dec(r"Masa netto\s*" + _de("18", "01") + _NUM, rf)
    item.ilosc_uzup = _find_dec(r"Ilość w jedn\. uzup\.\s*" + _de("18", "02") + _NUM, rf)
    item.wartosc_stat = _find_dec(r"Wartość stat\.\s*" + _de("99", "06") + _NUM, rf)
    additions = _find(r"Doliczenia i odliczenia\s*" + _de("14", "04") + r"(.*)", rf)
    for kind, amount in re.findall(r"\b(AK|CA):\s*" + _NUM + r"\s*PLN", additions):
        (item.doliczenia_ak if kind == "AK" else item.doliczenia_ca).append(_dec(amount) or Decimal(0))
    return item


def _summary(left: str) -> dict[str, tuple[Decimal, str | None]]:
    out = {}
    for code, amount, method in re.findall(r"(?m)^([A-Z]\d{2})\s+" + _NUM + r"\s*PLN(?:\s+([A-Z]))?\s*$",
                                            left):
        out[code] = (_dec(amount) or Decimal(0), method or None)
    return out


# --- wejście ------------------------------------------------------------------------------

def parse_sad(file: str | pathlib.Path | io.BytesIO | io.BufferedReader) -> Zgloszenie:
    """Ścieżka albo strumień binarny (np. BytesIO z uploadu). Nie-WinSAD → SadFormatError."""
    import pdfplumber
    try:
        pdf = pdfplumber.open(file)
    except Exception as exc:  # noqa: BLE001 — każdy błąd biblioteki PDF = „nie da się otworzyć”
        raise SadFormatError("Nie da się otworzyć pliku jako PDF.") from exc
    with pdf:
        if not pdf.pages:
            raise SadFormatError("PDF nie ma stron.")
        top_text = pdf.pages[0].extract_text() or ""
        if "zgłoszenia celnego" not in top_text or "WinSAD" not in top_text:
            raise SadFormatError("To nie jest podgląd zgłoszenia celnego z programu WinSAD.")
        marks = _marks(pdf)
        last_page = len(pdf.pages) - 1
        end_of_doc = (last_page, float(pdf.pages[last_page].height))
        z = Zgloszenie()
        first = (marks[0].page, marks[0].top) if marks else end_of_doc
        _header(z, top_text, *_region(pdf, (0, 0.0), first))
        for index, mark in enumerate(marks):
            nxt = marks[index + 1] if index + 1 < len(marks) else None
            end = (nxt.page, nxt.top) if nxt else end_of_doc
            left, right = _region(pdf, (mark.page, mark.top), end)
            if mark.kind == "item" and mark.nr is not None:
                z.pozycje.append(_item(mark.nr, left, right))
            else:
                z.podsumowanie = _summary(left)
    z.vat_fr7 = next((p.vat_fr7 for p in z.pozycje if p.vat_fr7), "")
    z.grn = next((p.grn for p in z.pozycje if p.grn), "")
    return z
