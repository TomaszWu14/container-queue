"""„Kartoteka symboli” dla agencji celnej (wzór Delta Brokers `SymboleAcme_EXCEL.xlsx`, 44 kolumny):
jeden wiersz na nasz REF z zatwierdzonych pozycji faktur — co to za towar (CN, nazwy, kraj),
bez ilości i kwot (te idą w Excelu pozycji). Układ kolumn i źródła danych = wzór z Master data
(agency_templates, „Wzory plików dla agencji”); COLUMNS = układ domyślny wzoru."""
import datetime
import re
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import agency_templates
from ..exports import append_row
from ..models import InvoiceJob, Material
from .matching import effective
from .numbers import normalize_number

COLUMNS = [
    "Symbol", "KodPCN", "KodTaric", "KodUE1", "KodUE2", "KodUE3", "KodPL1", "KodPL2", "KodPL3",
    "KodPL4", "KodCUS", "NazwaPolska", "NazwaObca", "DodOpisTowaru", "NazwaJednMiar",
    "KodKrajuPoch", "KodKrajuPrefPoch", "Cena", "Waga", "Kwiu", "KodPaskowy", "TypKoduPaskowego",
    "Uwagi", "Niepochodzacy", "Militarny", "PokazUwagi", "IDZestawu", "OstatniModyfikujacy",
    "DataOstModyfikacji", "SaDokumentyPowiazane", "NazwaJednMiarUzup", "PrzelicznikDoUzupJM",
    "RodzajOpakowania", "LiczbaJednostekNaOpak", "MasaMaterialuWybuchowego", "KlasaADR",
    "KodTowaruNiebezpiecznego", "Objetosc", "ZweryfikowanoCN", "ZweryfikowanoWaga", "Komentarz1",
    "Komentarz2", "SaWazneDeklDlugoterm", "SaWazneInfWIT",
]
DEFAULT_ID_ZESTAWU = 106


def cn_codes(tariff_cn: str, customs_code: str) -> tuple[str, str]:
    """(KodPCN = 8 cyfr CN, KodTaric = cyfry 9–10 kodu celnego albo „00”)."""
    full = re.sub(r"\D", "", customs_code or "") or re.sub(r"\D", "", tariff_cn or "")
    cn = re.sub(r"\D", "", tariff_cn or "")[:8] or full[:8]
    return cn, (full[8:10] if len(full) >= 10 else "00")


def _weight_per_unit(items) -> float:
    """Waga netto na jednostkę: suma wag / suma ilości pozycji danego REF; brak danych = 0 (jak wzór)."""
    # ponytail: ilość z faktury traktowana jak jednostka podstawowa (dostawcy bez kolumny jm);
    # przy fakturach w kartonach przeliczyć przez uom_factor
    weight = sum((normalize_number(i.weight_net, prefer_decimal=True) or Decimal(0) for i in items), Decimal(0))
    qty = sum((normalize_number(i.qty) or Decimal(0) for i in items), Decimal(0))
    return round(float(weight / qty), 6) if weight and qty else 0


def _const(value: str):
    """Stała ze wzoru: same cyfry → liczba (jak IDZestawu 106 we wzorze agencji), reszta tekst."""
    text = (value or "").strip()
    return int(text) if text.isdigit() else text


def build_workbook(db: Session, jobs: list[InvoiceJob], company_id: int | None, country: str,
                   id_zestawu, login: str, now: datetime.datetime | None = None,
                   template: dict | None = None):
    import openpyxl
    from openpyxl.styles import Font
    by_ref: dict[str, list] = {}
    for job in jobs:
        for item in job.items:
            if not item.skipped and item.master_ref:   # bez dopasowania do master = nie nasz symbol
                by_ref.setdefault(item.master_ref, []).append(item)
    materials = {m.ref_code: m for m in db.scalars(
        select(Material).where(Material.ref_code.in_(by_ref)))} if by_ref else {}
    wb = openpyxl.Workbook()
    ws = wb.active
    template = template or agency_templates.DEFAULTS["winsad_symbole"]
    columns = template["columns"]
    ws.title = template.get("sheet") or "Arkusz1"
    append_row(ws, [c["name"] for c in columns])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    stamp = (now or datetime.datetime.now()).replace(microsecond=0)
    for ref, items in by_ref.items():
        material = materials.get(ref)
        view = effective(material, company_id) if material else {}
        cn, taric = cn_codes(view.get("tariff_cn", "") or items[0].tariff_cn, view.get("customs_code", ""))
        foreign = next((i.descr for i in items if i.descr), "") or (material.name_en if material else "")
        # wartość każdego źródła danych wzoru (agency_templates.SOURCES) dla tego REF
        source = {
            "ref": ref, "cn8": cn, "taric2": taric,
            "name_pl": view.get("name_pl") or items[0].name_pl, "descr": foreign,
            "unit_weight": _weight_per_unit(items), "supplier_country": country or None,
            "user_login": login, "today": stamp, "base_uom": view.get("base_uom") or None,
            "suppl_unit": (material.suppl_unit if material else "") or None,
            "suppl_factor": material.suppl_factor if material else None,
            "agency_set_id": id_zestawu, "empty": None,
        }
        append_row(ws, [_const(c.get("value", "")) if c["source"] == "const" else source.get(c["source"])
                        for c in columns])
    return wb
