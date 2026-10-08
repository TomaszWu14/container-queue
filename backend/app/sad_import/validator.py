"""Walidacja zgłoszenia z podglądu WinSAD: spójność rachunkowa (wartość celna, cło, VAT,
podsumowanie opłat) i formalna (ISO 6346, NIP, stan AIS, daty). Wzory sprawdzone na
drafach Delta Brokers (tests/fixtures/sad), zgodność do 1 PLN.

Wartość celna (A00) = wartość fakturowa poz. × kurs + Σ doliczeń AK; CA (transport od
granicy UE do miejsca przeznaczenia) nie wchodzi do wartości celnej, tylko do podstawy VAT
(art. 30b ustawy o VAT): B00 = A00 + cło + Σ CA."""
import datetime
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from ..iso6346 import validate as iso6346_validate
from .parser import Pozycja, Zgloszenie

OK, WARN, ERROR = "OK", "WARN", "ERROR"
_RANK = {OK: 0, WARN: 1, ERROR: 2}
TOL_PLN = Decimal("1")
TOL_GROSZ = Decimal("0.01")
DATA_WSTECZ_MAX_DNI = 14         # podgląd starszy niż 2 tygodnie od deklarowanej daty = podejrzany
_NIP_WAGI = (6, 5, 7, 2, 3, 4, 5, 6, 7)
_STAN_POTWIERDZONY = ("zwolnion", "przyjęt")


@dataclass
class Wynik:
    poziom: str                 # "zgłoszenie" / "pozycja"
    pozycja: int | None
    regula: str
    oczekiwane: str
    odczytane: str
    status: str                 # OK / WARN / ERROR


def round_half_up(value: Decimal) -> Decimal:
    """Zaokrąglenie do pełnych PLN jak w zgłoszeniu (0,5 w górę — nie bankierskie)."""
    return value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def najgorszy(wyniki: list[Wynik]) -> str:
    return max((w.status for w in wyniki), key=_RANK.__getitem__, default=OK)


def _s(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    return str(value)


def nip_poprawny(nip: str) -> bool:
    if not re.fullmatch(r"\d{10}", nip or ""):
        return False
    suma = sum(int(c) * w for c, w in zip(nip, _NIP_WAGI, strict=False)) % 11
    return suma != 10 and suma == int(nip[9])


class _Zbior:
    def __init__(self) -> None:
        self.wyniki: list[Wynik] = []

    def dodaj(self, regula: str, oczekiwane, odczytane, ok: bool, pozycja: int | None = None,
              blad: str = ERROR) -> None:
        self.wyniki.append(Wynik("pozycja" if pozycja is not None else "zgłoszenie", pozycja,
                                 regula, _s(oczekiwane), _s(odczytane), OK if ok else blad))

    def porownaj(self, regula: str, oczekiwane: Decimal | None, odczytane: Decimal | None,
                 tolerancja: Decimal, pozycja: int | None = None) -> None:
        ok = (oczekiwane is not None and odczytane is not None
              and abs(oczekiwane - odczytane) <= tolerancja)
        self.dodaj(regula, oczekiwane, odczytane, ok, pozycja)


def _oplaty(out: _Zbior, p: Pozycja) -> None:
    for o in p.oplaty:
        wyliczona = (o.podstawa * o.stawka / 100
                     if o.podstawa is not None and o.stawka is not None else None)
        out.porownaj(f"{o.kod}: kwota wyliczona = podstawa × stawka", wyliczona,
                     o.kwota_wyliczona, TOL_GROSZ, p.nr)
        out.porownaj(f"{o.kod}: należna = zaokrąglenie kwoty wyliczonej",
                     round_half_up(o.kwota_wyliczona) if o.kwota_wyliczona is not None else None,
                     o.kwota_nalezna, Decimal(0), p.nr)


def _pozycja(out: _Zbior, z: Zgloszenie, p: Pozycja) -> None:
    a00, b00 = p.oplata("A00"), p.oplata("B00")
    celna = (round_half_up(p.wartosc_fakturowa * z.kurs + p.suma_ak)
             if p.wartosc_fakturowa is not None and z.kurs is not None else None)
    out.porownaj("wartość celna (A00) = wart. fakt. × kurs + ΣAK", celna,
                 a00.podstawa if a00 else None, TOL_PLN, p.nr)
    out.porownaj("wartość celna (A00) = wartość stat. [99 06]", p.wartosc_stat,
                 a00.podstawa if a00 else None, Decimal(0), p.nr)
    _oplaty(out, p)
    vat = (round_half_up(a00.podstawa + (a00.kwota_nalezna or Decimal(0)) + p.suma_ca)
           if a00 and a00.podstawa is not None else None)
    out.porownaj("podstawa VAT (B00) = A00 + cło + ΣCA", vat, b00.podstawa if b00 else None,
                 TOL_PLN, p.nr)
    out.porownaj("Σ należnych = kwota ogółem [14 16]",
                 sum(((o.kwota_nalezna or Decimal(0)) for o in p.oplaty), Decimal(0)),
                 p.kwota_ogolem, Decimal(0), p.nr)
    out.dodaj("masa netto > 0", "> 0", p.masa_netto,
              p.masa_netto is not None and p.masa_netto > 0, p.nr)
    out.dodaj("kraj pochodzenia podany", "kod kraju", p.kraj_pochodzenia or None,
              bool(p.kraj_pochodzenia), p.nr)
    out.dodaj("kod CN: 8 cyfr", "8 cyfr", p.cn or None, bool(re.fullmatch(r"\d{8}", p.cn)), p.nr)
    sztuki = re.search(r"(\d+)\s*SZT", p.opis)
    if sztuki and p.ilosc_uzup is not None:
        out.dodaj("ilość z opisu (SZT) = ilość w jedn. uzup. [18 02]", sztuki.group(1),
                  p.ilosc_uzup, Decimal(sztuki.group(1)) == p.ilosc_uzup, p.nr, blad=WARN)
    out.dodaj("faktura (N935) w dokumentach [12 03]", "N935",
              ", ".join(p.faktury) or None, bool(p.faktury), p.nr, blad=WARN)


def _sumy(out: _Zbior, z: Zgloszenie) -> None:
    out.dodaj("liczba pozycji z nagłówka = odczytane pozycje", z.liczba_pozycji, len(z.pozycje),
              z.liczba_pozycji == len(z.pozycje))
    wartosci = [p.wartosc_fakturowa for p in z.pozycje if p.wartosc_fakturowa is not None]
    out.porownaj("Σ wartości fakturowych pozycji = wartość faktur [14 06]", z.wartosc_faktur,
                 sum(wartosci, Decimal(0)) if len(wartosci) == len(z.pozycje) else None,
                 TOL_GROSZ)
    opakowania = sum(p.opakowania_liczba or 0 for p in z.pozycje)
    out.dodaj("Σ opakowań pozycji = liczba opakowań", z.liczba_opakowan, opakowania,
              z.liczba_opakowan == opakowania)
    masy = [p.masa_netto for p in z.pozycje if p.masa_netto is not None]
    netto = sum(masy, Decimal(0)) if len(masy) == len(z.pozycje) else None
    out.dodaj("Σ mas netto ≤ masa brutto [18 04]", f"≤ {_s(z.masa_brutto)}", netto,
              netto is not None and z.masa_brutto is not None and netto <= z.masa_brutto)
    for kod in sorted({o.kod for p in z.pozycje for o in p.oplaty} | set(z.podsumowanie)):
        suma = z.suma_naleznych(kod)
        podsumowanie = z.podsumowanie.get(kod, (None, None))[0]
        out.porownaj(f"Σ należnych {kod} = podsumowanie opłat", suma, podsumowanie, Decimal(0))


def _formalne(out: _Zbior, z: Zgloszenie, dzis: datetime.date) -> None:
    if not z.kontenery:
        out.dodaj("numer kontenera [19 07]", "numer kontenera", None, False, blad=WARN)
    for kontener in z.kontenery:
        poprawny, _komunikat = iso6346_validate(kontener)
        out.dodaj("kontener: cyfra kontrolna ISO 6346", "poprawna", kontener, poprawny)
    out.dodaj("NIP importera: cyfra kontrolna", "poprawna", z.importer_nip or None,
              nip_poprawny(z.importer_nip))
    out.dodaj("nr VAT FR7 [13 16] = PL + NIP importera", f"PL{z.importer_nip}", z.vat_fr7 or None,
              bool(z.importer_nip) and z.vat_fr7 == f"PL{z.importer_nip}")
    potwierdzony = any(s in z.stan_ais.lower() for s in _STAN_POTWIERDZONY)
    out.dodaj("stan AIS: zgłoszenie przyjęte / zwolnione", "przyjęte / zwolnione",
              z.stan_ais or None, potwierdzony, blad=WARN)
    if z.data_zgloszenia is None:
        out.dodaj("deklarowana data zgłoszenia", "data", None, False, blad=WARN)
        return
    wydruk = z.data_wydruku.date() if z.data_wydruku else None
    stary = wydruk is not None and (wydruk - z.data_zgloszenia).days > DATA_WSTECZ_MAX_DNI
    out.dodaj(f"data zgłoszenia nie starsza niż {DATA_WSTECZ_MAX_DNI} dni od wydruku",
              f"≥ {_s(wydruk)} − {DATA_WSTECZ_MAX_DNI} dni", z.data_zgloszenia, not stary, blad=WARN)
    out.dodaj("data zgłoszenia nie w przyszłości", f"≤ {dzis}", z.data_zgloszenia,
              z.data_zgloszenia <= dzis, blad=WARN)


def validate(z: Zgloszenie, dzis: datetime.date | None = None) -> list[Wynik]:
    """Wszystkie reguły z wynikiem (także OK — arkusz walidacji pokazuje pełny ślad)."""
    out = _Zbior()
    for p in z.pozycje:
        _pozycja(out, z, p)
    _sumy(out, z)
    _formalne(out, z, dzis or datetime.date.today())
    return out.wyniki
