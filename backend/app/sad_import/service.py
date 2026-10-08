"""Import podglądów SAD (WinSAD) z uploadu: odczyt w pamięci, walidacja, zakres spółek i ślad
audytu na kontenerach. Router: app/routers/sad_import.py (HTTP — tu tylko domena).

Zakres: SAD widzi konto grupowe (`can_view_all`) albo konto, któremu choć jeden kontener
z SAD [19 07] w TIMPORYE przechodzi `deps.check_container_access` — reguła izolacji
zostaje w deps.py, tu jej nie powielamy. Brak dostępu = błąd pliku BEZ odczytanych danych.
Pliki nie trafiają na dysk ani do logów (także nazwy i treść); parser nie czyta danych osobowych."""
import datetime
import io
import logging
from dataclasses import dataclass, field
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..deps import check_container_access
from ..models import Container, User
from ..security import can_view_all
from .parser import Oplata, Pozycja, SadFormatError, Zgloszenie, parse_sad
from .validator import Wynik, najgorszy, validate

logger = logging.getLogger(__name__)

BRAK_DOSTEPU = ("Brak dostępu: kontener z SAD nie należy do Twoich spółek albo nie ma go "
                "w TIMPORYE.")
NIE_PDF = "To nie jest plik PDF."
NIECZYTELNY = "Nie udało się odczytać pliku jako podglądu SAD."


@dataclass
class FileResult:
    plik: str
    zgloszenie: Zgloszenie | None = None
    wyniki: list[Wynik] = field(default_factory=list)
    blad: str = ""

    @property
    def ok(self) -> bool:
        return self.zgloszenie is not None and not self.blad

    @property
    def status(self) -> str:
        return najgorszy(self.wyniki)


def _parse(name: str, content: bytes) -> Zgloszenie | str:
    """Zgłoszenie albo komunikat błędu pliku (jeden zły plik nie przerywa reszty)."""
    if not name.lower().endswith(".pdf") or not content.startswith(b"%PDF-"):
        return NIE_PDF
    try:
        return parse_sad(io.BytesIO(content))
    except SadFormatError as exc:
        return str(exc)
    except Exception as exc:  # noqa: BLE001 — uszkodzony PDF = błąd pliku; bez treści w logu
        logger.warning("Import SAD: nieczytelny PDF (%s)", type(exc).__name__)
        return NIECZYTELNY


def _accessible(db: Session, user: User, numbers: list[str]) -> list[Container]:
    """Kontenery z SAD, które użytkownik widzi (ten sam numer bywa w kilku spółkach)."""
    if not numbers:
        return []
    found = db.scalars(select(Container).where(Container.container_no.in_(numbers))
                       .order_by(Container.id)).all()
    out = []
    for container in found:
        try:
            check_container_access(user, container)
        except HTTPException:
            continue
        out.append(container)
    return out


def _record(db: Session, user: User, containers: list[Container], z: Zgloszenie, status: str,
            note: str) -> None:
    for container in containers:
        audit.record(db, entity_type="containers", entity_id=container.id, field="sad_import",
                     old_value=None, new_value=f"SAD {z.numer}: {status}", user=user, note=note)


def check_files(db: Session, user: User, uploads: list[tuple[str, bytes]],
                dzis: datetime.date | None = None,
                note: str = "Import SAD: sprawdzenie") -> list[FileResult]:
    """(nazwa, treść) → wynik per plik w kolejności uploadu; ślad audytu na widocznych
    kontenerach z SAD i jeden commit na całe żądanie."""
    results, audited = [], False
    for name, content in uploads:
        parsed = _parse(name, content)
        if isinstance(parsed, str):
            results.append(FileResult(name, blad=parsed))
            continue
        containers = _accessible(db, user, parsed.kontenery)
        if not containers and not can_view_all(user):
            results.append(FileResult(name, blad=BRAK_DOSTEPU))
            continue
        parsed.plik = name
        result = FileResult(name, parsed, validate(parsed, dzis))
        _record(db, user, containers, parsed, result.status, note)
        audited = audited or bool(containers)
        results.append(result)
    if audited:
        db.commit()
    return results


# --- JSON dla frontu ---------------------------------------------------------------------

def _d(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _fee(fee: Oplata | None) -> dict | None:
    if fee is None:
        return None
    return {"podstawa": _d(fee.podstawa), "stawka": _d(fee.stawka),
            "kwota_nalezna": _d(fee.kwota_nalezna), "metoda": fee.metoda}


def _item(p: Pozycja) -> dict:
    return {"nr": p.nr, "opis": p.opis, "cn": p.cn, "taric": p.taric,
            "wartosc_fakturowa": _d(p.wartosc_fakturowa), "masa_netto": _d(p.masa_netto),
            "ilosc_uzup": _d(p.ilosc_uzup), "faktury": p.faktury, "proformy": p.proformy,
            "a00": _fee(p.oplata("A00")), "b00": _fee(p.oplata("B00")),
            "kwota_ogolem": _d(p.kwota_ogolem)}


def _header(z: Zgloszenie, status: str) -> dict:
    return {"numer": z.numer, "stan_ais": z.stan_ais,
            "data_zgloszenia": z.data_zgloszenia.isoformat() if z.data_zgloszenia else None,
            "data_wydruku": z.data_wydruku.isoformat() if z.data_wydruku else None,
            "lrn": z.lrn, "nadawca": z.nadawca, "odbiorca": z.odbiorca,
            "kontenery": list(z.kontenery), "wartosc_faktur": _d(z.wartosc_faktur),
            "waluta": z.waluta, "kurs": _d(z.kurs), "liczba_pozycji": z.liczba_pozycji,
            "liczba_opakowan": z.liczba_opakowan, "masa_brutto": _d(z.masa_brutto),
            "suma_cla": _d(z.suma_naleznych("A00")), "suma_vat": _d(z.suma_naleznych("B00")),
            "status": status}


def to_json(result: FileResult) -> dict:
    z = result.zgloszenie if result.ok else None
    return {
        "plik": result.plik, "ok": z is not None, "blad": result.blad or None,
        "zgloszenie": _header(z, result.status) if z else None,
        "pozycje": [_item(p) for p in z.pozycje] if z else [],
        "wyniki": [{"poziom": w.poziom, "pozycja": w.pozycja, "regula": w.regula,
                    "oczekiwane": w.oczekiwane, "odczytane": w.odczytane, "status": w.status}
                   for w in result.wyniki] if z else [],
    }
