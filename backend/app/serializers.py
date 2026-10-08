"""Wspólna serializacja modeli ORM do schematów wyjściowych z dopełnianiem pól."""
from sqlalchemy.orm import Session

from .models import Company, CustomsAgency, User
from .schemas import UserOut
from .twofa_policy import must_enroll_2fa


def serialize_user(db: Session, user: User) -> UserOut:
    """UserOut z dopełnionym `company_code` (kod spółki potrzebny UI do modułów)."""
    out = UserOut.model_validate(user)
    out.totp_enabled = bool(user.totp_secret)
    out.impersonated = bool(getattr(user, "impersonated", False))
    out.must_enroll_2fa = must_enroll_2fa(user)
    if user.company_id:
        company = db.get(Company, user.company_id)
        out.company_code = company.code if company else None
    if user.customs_agency_id:
        agency = db.get(CustomsAgency, user.customs_agency_id)
        out.customs_agency_name = agency.name if agency else None
    return out


# --- objętość pozycji zamówień z MARM (przeliczniki jednostek) ---

# jednostka objętości SAP (VOLEH) -> mnożnik do m³; nieznana jednostka = brak wyniku
VOLEH_TO_M3 = {"M3": 1.0, "MTQ": 1.0, "CDM": 0.001, "DM3": 0.001,
               "L": 0.001, "LTR": 0.001, "CCM": 0.000001, "CM3": 0.000001}


def _volume_m3(row) -> float | None:
    """Objętość JEDNEJ jednostki z wiersza MARM przeliczona do m³ (None gdy brak/nieznana)."""
    if row.volume is None:
        return None
    factor = VOLEH_TO_M3.get((row.volume_unit or "").upper())
    return float(row.volume) * factor if factor is not None else None


def marm_volume_m3(quantity: float, unit: str, material_rows: list) -> float | None:
    """Objętość pozycji w m³: ilość × objętość jednostki z MARM.

    Jednostka pozycji z objętością wprost -> mnożenie. Bez objętości -> przeliczenie
    przez jednostkę bazową (UMREZ/UMREN) do pierwszej jednostki materiału z objętością.
    """
    unit = (unit or "").upper()
    direct = next((r for r in material_rows if r.unit == unit), None)
    if direct is not None:
        vol = _volume_m3(direct)
        if vol is not None:
            return quantity * vol
    # ilość w jednostkach bazowych (1 alt = UMREZ/UMREN bazowych); brak wiersza = baza
    base_qty = quantity * (direct.numerator / direct.denominator) if direct else quantity
    for row in sorted(material_rows, key=lambda r: r.unit):
        vol = _volume_m3(row)
        if vol is None or not row.numerator:
            continue
        return base_qty * (row.denominator / row.numerator) * vol
    return None


def attach_marm_volumes(db: Session, items: list) -> dict[int, float | None]:
    """Mapa OrderItem.id -> objętość m³ wyliczona z MARM (jedno zapytanie na listę)."""
    from sqlalchemy import select

    from .models import MaterialUnit, quantity_value

    materials = {i.material for i in items if i.material}
    if not materials:
        return {i.id: None for i in items}
    by_material: dict[str, list] = {}
    for row in db.scalars(select(MaterialUnit)
                          .where(MaterialUnit.material_no.in_(materials))):
        by_material.setdefault(row.material_no, []).append(row)
    out: dict[int, float | None] = {}
    for item in items:
        # DB-008: typowana ilość; dawniej float(replace) gubił „1.234,000” (ValueError → None)
        qty = quantity_value(getattr(item, "quantity_num", None), item.quantity)
        rows = by_material.get(item.material)
        out[item.id] = marm_volume_m3(qty, item.unit, rows) \
            if qty is not None and rows else None
    return out
