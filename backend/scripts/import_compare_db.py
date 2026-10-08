"""Migracja danych z bazy aplikacji Compare (DocCompare) do TIMPORYE.

Przenosi to, co pipeline Faktury → Excel potrzebuje od pierwszego dnia:
  * `material_master`  → `materials` (REF, nazwy, EAN, CN, SENT, jm, poziomy opakowań),
  * `uom_conversion`   → `uom_conversions` (przeliczniki per REF i globalne '*'),
  * `suppliers` (mapa kolumn PI/CI) → `Supplier.column_map` w KAŻDEJ spółce, w której
    istnieje dostawca o tej samej nazwie (dostawcy w TIMPORYE są per spółka).
Historii paczek faktur nie przenosimy — Excele zostały pobrane, a stan „u operatora”
nie ma już źródła.

Idempotentny (upsert po ref_code / (ref_norm, unit_from, unit_to) / nazwie dostawcy).
Domyślnie podgląd; zapis dopiero z --commit. Baza Compare: SQLite albo PostgreSQL:
  python -m scripts.import_compare_db --db sqlite:////data/doccompare.db
  python -m scripts.import_compare_db --db postgresql://user:pass@host/compare --commit
PRZED --commit na produkcji zrób backup: sh scripts/backup.sh
"""
import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, inspect, select, text  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.invoices import uom  # noqa: E402
from app.invoices.extractor import COLUMN_ROLES, ROLE_ALIASES  # noqa: E402
from app.invoices.master_import import clean_ean, import_records, norm_vat  # noqa: E402
from app.invoices.uom import normalize_ref  # noqa: E402
from app.models import Supplier, UomConversion  # noqa: E402

# Compare trzyma mapę kolumn raz jako {rola: nagłówek}, raz jako {nagłówek: rola}
# (dwa moduły, dwie konwencje) — rozpoznajemy po tym, czy klucz jest znaną rolą.
# role kolumn = ekstraktor TIMPORYE + nazwy compare (ROLE_ALIASES) + „skip” z kreatora
ROLES = (*COLUMN_ROLES, *ROLE_ALIASES, "skip")
ROLE_ALIAS = ROLE_ALIASES


def _rows(conn, table: str) -> list[dict]:
    if table not in inspect(conn).get_table_names():
        print(f"  (brak tabeli {table} w bazie Compare — pomijam)")
        return []
    result = conn.execute(text(f"SELECT * FROM {table}"))
    return [dict(row._mapping) for row in result]


def _truthy(value) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "t", "tak", "x", "yes")


def material_records(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        ref = str(row.get("ref_code") or "").strip()
        if not ref or not _truthy(row.get("active", 1)):
            continue
        try:
            levels = json.loads(row.get("levels_json") or "{}")
        except (TypeError, ValueError):
            levels = {}
        out.append({
            "ref_code": ref[:100],
            "ref_norm": normalize_ref(ref),
            "name_pl": str(row.get("opis_pl") or row.get("txt_short_pl") or "")[:500],
            "name_en": str(row.get("opis_en") or "")[:500],
            "ean": clean_ean(row.get("ean")),
            "family": str(row.get("rodzina") or "")[:160],
            "base_uom": str(row.get("base_uom") or "")[:20],
            "producer_code": str(row.get("producer_code") or "")[:60],
            "tariff_cn": str(row.get("tariff_cn") or "")[:30],
            "customs_code": str(row.get("customs_code") or "")[:30],
            "vat_rate": norm_vat(row.get("vat_rate")),
            "sent": (_truthy(row["sent"]) if row.get("sent") not in (None, "") else None),
            "supplier_codes": str(row.get("supplier_codes") or "")[:500],
            "levels": levels if isinstance(levels, dict) else {},
            # z bazy Compare przychodzi komplet pól — nadpisujemy wszystkie (import_records
            # bez tej listy zostawiłby istniejące materiały nietknięte)
            "present": {"name_pl", "name_en", "ean", "family", "base_uom", "producer_code",
                        "tariff_cn", "customs_code", "supplier_codes"},
            "levels_present": True,
        })
    return out


def column_map_text(row: dict) -> str:
    """pi_column_mapping_json (fallback column_mapping_json['PI']) → "ref=…; qty=…"."""
    mapping = {}
    for key in ("pi_column_mapping_json", "ci_column_mapping_json"):
        raw = row.get(key)
        try:
            mapping = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except ValueError:
            mapping = {}
        if mapping:
            break
    if not mapping:
        try:
            general = json.loads(row.get("column_mapping_json") or "{}")
        except (TypeError, ValueError):
            general = {}
        mapping = general.get("PI") or general.get("pi") or {}
    if not isinstance(mapping, dict):
        return ""
    # konwencję rozpoznajemy dla całej mapy: same role w kluczach = {rola: nagłówek},
    # inaczej {nagłówek: rola} (nagłówek „Qty” wygląda jak rola, ale „Item No.” już nie)
    keys_are_roles = all(str(k).strip().lower() in ROLES for k in mapping)
    pairs = []
    for key, value in mapping.items():
        key_s, value_s = str(key).strip(), str(value).strip()
        if keys_are_roles:
            role, header = key_s.lower(), value_s
        else:
            role, header = value_s.lower(), key_s
        role = ROLE_ALIAS.get(role, role)
        if role == "skip" or role not in ROLES or not header:
            continue
        pairs.append(f"{role}={header}")
    return "; ".join(pairs)[:2000]


def _norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", required=True, help="URL bazy Compare (sqlite:///… albo postgresql://…)")
    parser.add_argument("--commit", action="store_true", help="zapisz (domyślnie tylko podgląd)")
    args = parser.parse_args()
    if args.db.startswith("postgres://"):
        args.db = "postgresql://" + args.db[len("postgres://"):]

    source = create_engine(args.db)
    with source.connect() as conn:
        materials = _rows(conn, "material_master")
        conversions = _rows(conn, "uom_conversion")
        suppliers = _rows(conn, "suppliers")

    records = material_records(materials)
    db = SessionLocal()
    try:
        counts = import_records(db, records, dry_run=not args.commit)
        db.flush()   # reguły z poziomów opakowań muszą być widoczne dla upsertu niżej
        print(f"Materiały: {counts['total']} (nowe {counts['new']}, aktualizowane {counts['updated']}, "
              f"przeliczniki z poziomów {counts['conversions']})")

        existing = {(r.ref_norm, r.unit_from, r.unit_to): r for r in db.scalars(select(UomConversion))}
        conv_new = conv_upd = 0
        for row in conversions:
            unit_from, unit_to = uom.canonical_unit(row.get("unit_from")), uom.canonical_unit(row.get("unit_to"))
            try:
                factor = float(row.get("factor"))
            except (TypeError, ValueError):
                continue
            if not unit_from or not unit_to or factor <= 0 or unit_from == unit_to:
                continue
            key = (str(row.get("ref_norm") or "*"), unit_from, unit_to)
            rule = existing.get(key)
            if rule is None:
                conv_new += 1
                if args.commit:
                    rule = UomConversion(ref_norm=key[0], unit_from=unit_from, unit_to=unit_to, factor=factor)
                    db.add(rule)
                    existing[key] = rule
            else:
                conv_upd += 1
                if args.commit:
                    rule.factor = factor
        print(f"Przeliczniki (uom_conversion): nowe {conv_new}, aktualizowane {conv_upd}")

        by_name: dict[str, list[Supplier]] = {}
        for supplier in db.scalars(select(Supplier)):
            by_name.setdefault(_norm_name(supplier.name), []).append(supplier)
        mapped = missing = 0
        for row in suppliers:
            cmap = column_map_text(row)
            if not cmap:
                continue
            targets = by_name.get(_norm_name(row.get("name"))) or []
            if not targets:
                missing += 1
                print(f"  brak dostawcy „{row.get('name')}” w TIMPORYE — mapa kolumn pominięta: {cmap}")
                continue
            for supplier in targets:
                mapped += 1
                if args.commit:
                    supplier.column_map = cmap
        print(f"Mapy kolumn dostawców: przypisane {mapped}, bez odpowiednika {missing}")

        if args.commit:
            db.commit()
            print("Zapisano.")
        else:
            db.rollback()
            print("Podgląd — nic nie zapisano (dodaj --commit).")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
