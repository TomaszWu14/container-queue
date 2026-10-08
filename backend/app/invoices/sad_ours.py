"""Nasza strona porównania z draftem SAD (spec 2026-09-29-agencja-draft-sad §2, PR 2): paczka
faktur zsumowana w grupy CN — agencja łączy pozycje po kodzie towaru.

Źródła jak Excel i mail do agencji: pozycje zatwierdzonych faktur/proform bez pominiętych.
CN świeżo z kartoteki (`effective` + `cn_codes`); `InvoiceItem.tariff_cn` to migawka z chwili
dopasowania — tylko gdy materiału brak. Masa netto = suma wag pozycji (PL wpisuje wagę REF na
jego pierwszą linię); REF bez żadnej wagi = masa grupy nieznana. J. uzupełniające = ilość
w j. podstawowej × `Material.suppl_factor`, gdy materiał ma `suppl_unit`; pozycja bez ilości
albo bez przelicznika jednostki = ilość grupy nieznana (sprawdź ręcznie, nie zaniżamy)."""
import re
from decimal import Decimal

from sqlalchemy.orm import Session

from ..models import (INVOICE_LIKE_KINDS, InvoiceBatch, InvoiceItem, InvoiceJob,
                      InvoiceJobStatus, Material)
from .checks import DEFAULT_TOL_AMOUNT, DEFAULT_TOL_QTY, _to_base
from .matching import effective, get_material, load_conversions
from .numbers import normalize_number
from .symbols import cn_codes


def _num(raw: str | None, weight: bool = False) -> Decimal | None:
    return normalize_number(raw, prefer_decimal=weight) if raw not in (None, "") else None


def _text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def confirmed_jobs(batch: InvoiceBatch) -> list[InvoiceJob]:
    """Dokumenty wysłane agencji — ten sam wybór co Excel i szkic maila."""
    return [j for j in batch.jobs
            if j.doc_kind in INVOICE_LIKE_KINDS and j.status == InvoiceJobStatus.confirmed]


class _Groups:
    """Akumulator grup CN: reguły jednej pozycji w `add`, podsumowanie w `result`."""

    def __init__(self, db: Session, company_id: int | None) -> None:
        self.db, self.company_id = db, company_id
        self.conversions = load_conversions(db)
        self.materials: dict[str, Material | None] = {}
        self.groups: dict[str, dict] = {}
        self.weighed: dict[str, bool] = {}
        self.no_cn: set[str] = set()

    def _material(self, ref: str) -> Material | None:
        if ref not in self.materials:
            self.materials[ref] = get_material(self.db, ref)
        return self.materials[ref]

    def add(self, item: InvoiceItem, amount: Decimal) -> None:
        ref = item.master_ref or item.raw_ref
        material = self._material(item.master_ref)
        view = effective(material, self.company_id) if material else None
        cn = (cn_codes(view["tariff_cn"], view["customs_code"])[0] if view
              else re.sub(r"\D", "", item.tariff_cn or "")[:8])
        if len(cn) != 8:
            self.no_cn.add(ref)
            return
        group = self.groups.setdefault(cn, {"value": Decimal(0), "net_mass": Decimal(0),
                                            "suppl_qty": Decimal(0), "suppl_unit": "",
                                            "suppl_missing": False, "refs": set()})
        group["value"] += amount
        group["refs"].add(ref)
        weight = _num(item.weight_net, weight=True)
        group["net_mass"] += weight or Decimal(0)
        self.weighed[ref] = self.weighed.get(ref, False) or weight is not None
        self._suppl(group, item, material, view, ref)

    def _suppl(self, group: dict, item: InvoiceItem, material: Material | None,
               view: dict | None, ref: str) -> None:
        if material is None or view is None or not material.suppl_unit or not material.suppl_factor:
            group["suppl_missing"] = True     # w grupie z j. uzupełniającą ten REF jej nie ma
            return
        group["suppl_unit"] = material.suppl_unit
        qty = _num(item.qty)
        base = None if qty is None else _to_base(qty, item.uom_src, view["base_uom"], ref,
                                                 self.conversions)
        if base is None:
            group["suppl_missing"] = True
        else:
            group["suppl_qty"] += base * Decimal(str(material.suppl_factor))

    def result(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for cn, group in sorted(self.groups.items()):
            unit = group["suppl_unit"]
            weighed = all(self.weighed[ref] for ref in group["refs"])
            out[cn] = {"cn": cn, "value": _text(group["value"]),
                       "net_mass": _text(group["net_mass"]) if weighed else None,
                       "suppl_qty": _text(group["suppl_qty"])
                       if unit and not group["suppl_missing"] else None,
                       "suppl_unit": unit, "refs": sorted(group["refs"])}
        return out


def batch_side(db: Session, batch: InvoiceBatch) -> dict:
    """Paczka faktur jako nagłówek + grupy CN (liczone z bieżących pozycji przy każdym porównaniu)."""
    container = batch.container
    supplier = batch.supplier or (container.supplier if container else None)
    profile = supplier.doc_profile if supplier else None
    jobs = confirmed_jobs(batch)
    acc = _Groups(db, container.company_id if container else None)
    total = charges = Decimal(0)
    for job in jobs:
        for charge in (job.check_data or {}).get("charges") or []:
            charges += _num(charge.get("amount")) or Decimal(0)
        for item in job.items:
            if item.skipped:
                continue
            amount = _num(item.amount) or Decimal(0)
            total += amount
            acc.add(item, amount)
    return {"invoices": sorted({j.invoice_number for j in jobs if j.invoice_number}),
            "container": container.container_no if container else "",
            "currency": (profile.currency or "").upper() if profile else "",
            "total": _text(total + charges), "charges": _text(charges),
            "country": (supplier.country or "").upper() if supplier else "",
            "groups": acc.result(), "no_cn": sorted(acc.no_cn),
            "tol_amount_pct": profile.tol_amount_pct if profile else DEFAULT_TOL_AMOUNT,
            "tol_qty_pct": profile.tol_qty_pct if profile else DEFAULT_TOL_QTY}
