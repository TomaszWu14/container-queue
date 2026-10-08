"""XML SADUE (eksport WinSAD — ten sam format, który agencja odsyła z draftem, `sad_xml`) z
zatwierdzonych faktur paczki: agencja importuje pozycje zamiast przepisywać je z Excela.

Wypełniamy część towarową: nadawca (dostawca), odbiorca (spółka), waluta (profil dostawcy),
warunki dostawy, kontener, faktury [N935 / proforma N325] i pozycje SAD. Identyfikatory WinSAD,
dane agencji, opłaty i korekty uzupełnia agencja. Pozycje = grupy CN (8) + TARIC + kraj
pochodzenia (indeks dostawcy EINA, inaczej kraj dostawcy) — tak łączy je agencja; źródła pozycji
jak Excel i mail (`sad_ours.confirmed_jobs`, bez pominiętych).

Blokady (`SadExportError`): brak zatwierdzonych faktur, profil dostawcy bez waluty, pozycja bez
dopasowanego REF albo bez 8-cyfrowego CN — XML bez CN agencja i tak musiałaby poprawiać ręcznie."""
import datetime
import xml.etree.ElementTree as ET  # nosec B405 — tylko budujemy XML, nic nie parsujemy
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import InvoiceBatch, InvoiceDocKind, Material, SupplierMaterial
from .matching import effective, get_material
from .sad_ours import _num, _text, confirmed_jobs
from .symbols import cn_codes


class SadExportError(ValueError):
    """Z tej paczki nie da się zbudować XML — komunikat mówi, co poprawić."""


def _origins(db: Session, supplier_id: int | None) -> dict[int, str]:
    """Kraj pochodzenia materiału u dostawcy (SAP EINA)."""
    if supplier_id is None:
        return {}
    return dict(db.execute(select(SupplierMaterial.material_id, SupplierMaterial.origin_country)
                           .where(SupplierMaterial.supplier_id == supplier_id,
                                  SupplierMaterial.origin_country != "")).all())


def _groups(db: Session, batch: InvoiceBatch, jobs, country: str) -> dict[tuple, dict]:
    company_id = batch.container.company_id
    origins = _origins(db, batch.supplier_id or batch.container.supplier_id)
    materials: dict[str, Material | None] = {}
    groups: dict[tuple, dict] = {}
    blocked: list[str] = []
    for job in jobs:
        for item in job.items:
            if item.skipped:
                continue
            ref = item.master_ref or item.raw_ref or item.descr[:30]
            if item.master_ref not in materials:
                materials[item.master_ref] = get_material(db, item.master_ref)
            material = materials[item.master_ref]
            if material is None:
                blocked.append(f"{ref} (bez dopasowania REF)")
                continue
            view = effective(material, company_id)
            cn, taric = cn_codes(view["tariff_cn"], view["customs_code"])
            if len(cn) != 8:
                blocked.append(f"{ref} (brak 8-cyfrowego CN)")
                continue
            origin = (origins.get(material.id) or country).upper()
            group = groups.setdefault((cn, taric, origin), {
                "value": Decimal(0), "net": Decimal(0), "gross": Decimal(0), "cartons": Decimal(0),
                "names": {}})
            group["value"] += _num(item.amount) or Decimal(0)
            group["net"] += _num(item.weight_net, weight=True) or Decimal(0)
            group["gross"] += _num(item.weight_gross, weight=True) or Decimal(0)
            group["cartons"] += _num(item.cartons) or Decimal(0)
            group["names"][view["name_pl"] or item.name_pl or item.descr] = None
    if blocked:
        raise SadExportError(f"{len(blocked)} pozycji nie trafi do XML — popraw w weryfikacji faktury: "
                             + ", ".join(dict.fromkeys(blocked)))
    return groups


def _terms(raw: str) -> dict[str, str]:
    """„FOB WUHAN” → Kod FOB, Miejsce WUHAN (incoterm = pierwsze 3 litery)."""
    code, _, place = (raw or "").strip().upper().partition(" ")
    return {"Kod": code, "Miejsce": place.strip()} if len(code) == 3 and code.isalpha() else {}


def build(db: Session, batch: InvoiceBatch,
          now: datetime.datetime | None = None) -> tuple[bytes, list[str]]:
    """(XML SADUE, ostrzeżenia). SadExportError — XML nie powstanie."""
    container = batch.container
    supplier = batch.supplier or container.supplier
    profile = supplier.doc_profile if supplier else None
    currency = (profile.currency or "").upper() if profile else ""
    country = (supplier.country or "").upper() if supplier else ""
    jobs = confirmed_jobs(batch)
    if not jobs:
        raise SadExportError("Brak zatwierdzonych faktur w paczce — zatwierdź faktury w weryfikacji.")
    if not currency:
        raise SadExportError("Profil dokumentów dostawcy nie ma waluty — uzupełnij ją w profilu dostawcy.")
    groups = _groups(db, batch, jobs, country)

    stamp = (now or datetime.datetime.now()).replace(microsecond=0).isoformat()
    root = ET.Element("SADUE", {"P15aKodKrajuWys": country, "P17aKodKrajuPrzeznacz": "PL",
                                "P19Kontenery": "1", "P22WalutaSADu": currency,
                                "DataUtworzeniaSADu": stamp})
    if supplier:
        ET.SubElement(ET.SubElement(root, "P2Nadawca"), "Firmy", {
            "Nazwa": supplier.name, "UlicaDom": supplier.street or supplier.address or "",
            "Miasto": supplier.city or "", "Kod": supplier.zip or "", "Kraj": country})
    if container.company:
        ET.SubElement(ET.SubElement(root, "P8Odbiorca"), "Firmy", {"Nazwa": container.company.name, "Kraj": "PL"})
    terms = _terms(next((j.delivery_terms for j in jobs if j.delivery_terms), ""))
    if terms:
        ET.SubElement(root, "P20WarDostawy", terms)

    total = sum((g["value"] for g in groups.values()), Decimal(0))
    gross = sum((g["gross"] for g in groups.values()), Decimal(0))
    cartons = sum((g["cartons"] for g in groups.values()), Decimal(0))
    ET.SubElement(root, "ZestawySADu", {"P6LiczbaOpakowan": _text(cartons), "P22WartoscZestawu": _text(total),
                                        "P35BruttoZestawu": _text(gross)})
    docs = list(dict.fromkeys((("N325" if j.doc_kind == InvoiceDocKind.proforma else "N935"), j.invoice_number)
                              for j in jobs if j.invoice_number))
    warnings = []
    for (cn, taric, origin), g in sorted(groups.items()):
        poz = ET.SubElement(root, "PozycjeSADu", {
            "P34KrajPochodz": origin, "P35MasaBrutto": _text(g["gross"]), "P38MasaNetto": _text(g["net"]),
            "P42WartoscPozycji": _text(g["value"])})
        marks = ET.SubElement(poz, "P31ZnakiINumery", {"OpisTowaru": "; ".join(n for n in g["names"] if n)})
        ET.SubElement(marks, "Opakowania", {"RodzOpak": "CT", "LiczbaOpak": _text(g["cartons"])})
        ET.SubElement(marks, "Kontenery", {"Numer": container.container_no or "", "Wszedzie": "true"})
        ET.SubElement(poz, "P33KodTowaru", {"KodCN": cn, "KodTaric": taric})
        for code, number in docs:
            ET.SubElement(poz, "DokumWymag", {"KodDokum": code, "NrDokum": number, "Wszedzie": "true"})
        missing = [label for key, label in (("net", "masy netto"), ("gross", "masy brutto"),
                                            ("cartons", "liczby kartonów")) if not g[key]]
        if missing:
            warnings.append(f"XML: CN {cn} ({origin}) bez {', '.join(missing)} — agencja uzupełni ręcznie.")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), warnings
