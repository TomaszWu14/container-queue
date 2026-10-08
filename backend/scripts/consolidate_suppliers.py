"""Scalanie dubli dostawców po przejściu na globalną kartotekę (spec 2026-09-25, PR1).

Uruchomienie (z katalogu backend/, na prod: docker exec w kontenerze backendu):
  python -m scripts.consolidate_suppliers                  → podgląd, NIC nie zapisuje
  python -m scripts.consolidate_suppliers --apply           → scala grupy tego samego kodu SAP
  python -m scripts.consolidate_suppliers --delete-orphans  → podgląd kopii bez powiązań
  python -m scripts.consolidate_suppliers --delete-orphans --apply → kasuje kopie bez powiązań

Dostawców bez kodu SAP rozstrzyga admin: Master data → Dostawcy → „Do rozstrzygnięcia".
PRZED --apply na produkcji zrób kopię bazy (sh scripts/backup.sh).
"""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.database import SessionLocal  # noqa: E402
from app.supplier_consolidation import (  # noqa: E402
    apply_groups,
    delete_orphans,
    orphans_preview,
    proposal,
)


def _run_merge(apply: bool) -> dict:
    with SessionLocal() as db:
        plan = proposal(db)
        for group in plan["merge_groups"]:
            # ASCII w wydruku: konsola Windows (cp1250) nie zakoduje strzałki unicode
            sources = ", ".join(f"{s['name']!r} (id={s['id']}, uzyc: {s['usage']})"
                                for s in group["sources"])
            print(f"SAP {group['sap_code']}: {sources} -> {group['target']['name']!r} "
                  f"(id={group['target']['id']})"
                  + (" [2 profile - scal recznie, pomijane]" if group["profile_conflict"] else ""))
        print(f"Grup do scalenia: {len(plan['merge_groups'])}; "
              f"do rozstrzygniecia (bez kodu SAP): {len(plan['unresolved'])}")
        if not apply:
            print("Podglad - nic nie zapisano. Dodaj --apply, zeby scalic.")
            return {"groups": len(plan["merge_groups"]), "merged": 0}
        result = apply_groups(db, None)
        db.commit()
        print(f"Scalono: {result['merged']}")
        return result


def _run_orphans(apply: bool) -> dict:
    with SessionLocal() as db:
        preview = orphans_preview(db)
        print(f"Kopii bez powiazan: {preview['count']}; per spolka: {preview['by_company']}")
        if not apply:
            print("Podglad - nic nie zapisano. Dodaj --apply, zeby usunac.")
            return {"count": preview["count"], "deleted": 0}
        deleted = delete_orphans(db, None)
        db.commit()
        print(f"Usunieto: {deleted}")
        return {"count": preview["count"], "deleted": deleted}


def run(apply: bool, delete_orphans_flag: bool = False) -> dict:
    if delete_orphans_flag:
        return _run_orphans(apply)
    return _run_merge(apply)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true",
                        help="scal grupy / usun kopie (bez tego tylko podglad)")
    parser.add_argument("--delete-orphans", action="store_true", dest="delete_orphans_flag",
                        help="tryb: kopie bez powiazan zamiast scalania kodow SAP")
    args = parser.parse_args()
    run(args.apply, args.delete_orphans_flag)
