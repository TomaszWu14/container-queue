"""Wzory plików dla agencji celnej (2026-10-06): jaki układ kolumn i skąd dane — widoczne
i edytowalne w Master data, żeby zmiana wzoru u agencji nie wymagała zmiany kodu.

Wzór = JSON w AppSetting (`agency_template:<klucz>`); plik-próbka od agencji w uploads.
Pierwszy: „Symbole” WinSAD (kartoteka towarowa: jeden wiersz na materiał z faktur paczki).
Plik generuje invoices/symbols.py (szkic maila do agencji) — WEDŁUG tego wzoru."""
import json

from sqlalchemy.orm import Session

from .app_settings import get_setting, set_setting

# źródło danych kolumny → opis dla użytkownika (kolejność = kolejność w liście wyboru)
SOURCES = {
    "ref": "REF materiału (symbol)",
    "cn8": "Kod CN — 8 cyfr",
    "taric2": "TARIC — cyfry 9–10 kodu (domyślnie 00)",
    "name_pl": "Nazwa PL (master data)",
    "descr": "Opis z faktury dostawcy",
    "unit_weight": "Waga netto na sztukę (kg)",
    "supplier_country": "Kraj dostawcy (kartoteka dostawcy)",
    "base_uom": "Jednostka podstawowa (master data)",
    "suppl_unit": "Jednostka uzupełniająca (master data)",
    "suppl_factor": "Przelicznik do jedn. uzupełniającej (master data)",
    "agency_set_id": "IDZestawu z ustawień agencji (domyślnie 106)",
    "user_login": "Login osoby generującej",
    "today": "Data wygenerowania",
    "const": "Stała wartość",
    "empty": "Puste",
}


def _col(name, source="empty", value="", required=False, note="", example=""):
    return {"name": name, "source": source, "value": value, "required": required,
            "note": note, "example": example}


# wzór z pliku SymboleAcme_EXCEL.xlsx od agencji (44 kolumny, ta kolejność); przykłady
# z pierwszego wiersza próbki — bez danych osobowych (OstatniModyfikujacy)
WINSAD_SYMBOLE = {
    "name": "Symbole WinSAD (kartoteka towarowa)",
    "description": "Excel .xlsx, arkusz „Arkusz1”: wiersz 1 = nagłówki, dalej jeden wiersz na "
                   "materiał z zatwierdzonych faktur paczki. Agencja importuje go do WinSAD, "
                   "żeby zgłoszenie podpowiadało opisy i kody. Aplikacja dołącza go jako "
                   "„kartoteka_symboli_<kontener>.xlsx” do „Przygotuj maila do agencji” — "
                   "według układu z tej tabeli.",
    "sheet": "Arkusz1",
    "columns": [
        _col("Symbol", "ref", required=True, note="numer materiału ACME", example="145851"),
        _col("KodPCN", "cn8", required=True, example="48237090"),
        _col("KodTaric", "taric2", required=True, example="00"),
        *(_col(n) for n in ("KodUE1", "KodUE2", "KodUE3", "KodPL1", "KodPL2", "KodPL3",
                            "KodPL4", "KodCUS")),
        _col("NazwaPolska", "name_pl", required=True,
             example="kaczka tradycyjna j.u. jednorazowy pojemnik medyczny z papieru"),
        _col("NazwaObca", "descr", required=True, example="BULBOUS URINAL - PHURI046"),
        _col("DodOpisTowaru"), _col("NazwaJednMiar", "base_uom"),
        _col("KodKrajuPoch", "supplier_country", required=True,
             note="kraj pochodzenia — dziś = kraj dostawcy", example="GB"),
        _col("KodKrajuPrefPoch", "supplier_country", note="zwykle jak KodKrajuPoch", example="GB"),
        _col("Cena"),
        _col("Waga", "unit_weight", example="0"),
        *(_col(n) for n in ("Kwiu", "KodPaskowy", "TypKoduPaskowego", "Uwagi")),
        _col("Niepochodzacy", "const", "N", example="N"),
        _col("Militarny", "const", "N", example="N"),
        _col("PokazUwagi", "const", "N", example="N"),
        _col("IDZestawu", "agency_set_id", note="identyfikator zestawu ACME u agencji", example="106"),
        _col("OstatniModyfikujacy", "user_login"),
        _col("DataOstModyfikacji", "today"),
        _col("SaDokumentyPowiazane"), _col("NazwaJednMiarUzup", "suppl_unit"),
        _col("PrzelicznikDoUzupJM", "suppl_factor"),
        *(_col(n) for n in ("RodzajOpakowania", "LiczbaJednostekNaOpak", "MasaMaterialuWybuchowego",
                            "KlasaADR", "KodTowaruNiebezpiecznego", "Objetosc", "ZweryfikowanoCN",
                            "ZweryfikowanoWaga", "Komentarz1", "Komentarz2",
                            "SaWazneDeklDlugoterm", "SaWazneInfWIT")),
    ],
}
DEFAULTS = {"winsad_symbole": WINSAD_SYMBOLE}


def setting_key(key: str) -> str:
    return f"agency_template:{key}"


def sample_name(key: str) -> str:
    return f"agency_template_{key}.xlsx"


def load(db: Session, key: str) -> dict:
    """Zapisany wzór albo domyślny z kodu (nigdy nie zapisany = domyślny)."""
    raw = get_setting(db, setting_key(key))
    return json.loads(raw) if raw else json.loads(json.dumps(DEFAULTS[key]))


def validate_columns(columns: list[dict]) -> list[str]:
    """Błędy kontraktu (pusta / powtórzona nazwa, nieznane źródło, stała bez wartości)."""
    errors, seen = [], set()
    for i, col in enumerate(columns, start=1):
        name = (col.get("name") or "").strip()
        if not name:
            errors.append(f"Kolumna {i}: brak nazwy.")
        elif name.lower() in seen:
            errors.append(f"Kolumna {i}: nazwa „{name}” się powtarza.")
        seen.add(name.lower())
        if col.get("source") not in SOURCES:
            errors.append(f"Kolumna {i} „{name}”: nieznane źródło danych.")
        elif col["source"] == "const" and not str(col.get("value") or "").strip():
            errors.append(f"Kolumna {i} „{name}”: stała wartość jest pusta.")
    return errors


def save(db: Session, key: str, template: dict) -> None:
    set_setting(db, setting_key(key), json.dumps(template, ensure_ascii=False))


def merge_sample(template: dict, headers: list[str], example: list) -> dict:
    """Nowa próbka od agencji: układ kolumn z jej nagłówków; mapowanie (źródło, stała,
    wymagana, uwagi) zostaje dla kolumn o tej samej nazwie, nowe kolumny = puste."""
    old = {c["name"].lower(): c for c in template["columns"]}
    columns = []
    for i, name in enumerate(headers):
        value = example[i] if i < len(example) else None
        prev = old.get(name.lower(), _col(name))
        columns.append({**prev, "name": name, "example": "" if value is None else str(value)})
    return {**template, "columns": columns}
